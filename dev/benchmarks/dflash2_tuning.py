#!/usr/bin/env python3
"""ABBA comparison of two DFlash2 checkpoints through actual launcher option 14.

Uses isolated OpenCode configuration and persistent caches. Refuses to load a
second model while port 1235 is serving. Each phase records cold/cached coding
at approximately 4K, 12K and 20K filled context, plus a forced tool call.
"""

import argparse
import contextlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from . import abba, bonsai_coding
else:
    import abba
    import bonsai_coding

ROOT = Path(__file__).resolve().parents[2]
METRICS = (
    "prefill_input_tokens",
    "prefill_wall_ms",
    "decode_output_tokens",
    "decode_wall_ms",
    "decode_cycle_ms",
    "drafted_tokens",
    "accepted_draft_tokens",
)


def request(url, path="/status", body=None):
    data = None if body is None else json.dumps(body).encode()
    with urllib.request.urlopen(
        urllib.request.Request(url + path, data, {"Content-Type": "application/json"}),
        timeout=600 if body is not None else 5,
    ) as response:
        return json.load(response)


def swap():
    return subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def released_primary():
    """The normal server may stay online only after releasing its model."""
    try:
        status = request("http://127.0.0.1:1235")
    except (OSError, urllib.error.URLError):
        return None
    if not status["weights"]["released"] or status["active_requests"]:
        raise RuntimeError("normal option-14 server needs the GPU")
    if status["transport"]["pending"] or status["transport"]["frontend_waiting"]:
        raise RuntimeError("normal option-14 server has pending requests")
    return status["requests"]["submitted"]


@contextlib.contextmanager
def guard_primary(process, allowed):
    baseline = released_primary() if allowed else None
    done = threading.Event()
    errors = []

    def watch():
        while not done.wait(0.5):
            try:
                if released_primary() != baseline:
                    raise RuntimeError("normal option-14 server received a request")
            except Exception as error:
                errors.append(str(error))
                if process.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                return

    watcher = threading.Thread(target=watch, daemon=True) if allowed else None
    if watcher is not None:
        watcher.start()
    try:
        yield
    finally:
        done.set()
        if watcher is not None:
            watcher.join(timeout=10)
        if errors:
            raise RuntimeError(
                "benchmark stopped to spare the normal server: " + errors[0]
            )


@contextlib.contextmanager
def server(args, phase):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SPLASH_BONSAI_") and key != "SPLASH_DRAFT_MODEL"
    }
    env.update(
        LLAMA_HOST="127.0.0.1",
        LLAMA_PORT=str(args.port),
        LLAMA_LOG_DIR=str(args.results / "logs"),
        OPENCODE_CONFIG_PATH=str(args.results / "opencode.json"),
        SPLASH_BIN=str(ROOT / "splash"),
        SPLASH_BONSAI_MAX_CONTEXT="24K",
        SPLASH_BONSAI_STATE_FORMAT="bf16",
        SPLASH_BONSAI_PREFILL_CHUNK_TOKENS="512",
        SPLASH_BONSAI_CACHE_DIR=str(args.results / (phase["name"] + "-cache")),
        SPLASH_DRAFT_MODEL=phase["draft"],
    )
    with (args.results / (phase["name"] + "-launcher.log")).open("w") as log:
        started = time.monotonic()
        process = subprocess.Popen(
            ["bash", str(args.launcher), "--direct", "14"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        primary_guard = None
        try:
            if args.allow_released_primary:
                primary_guard = guard_primary(process, True)
                primary_guard.__enter__()
            while True:
                if process.poll() is not None:
                    raise RuntimeError("launcher exited; inspect " + phase["name"])
                try:
                    status = request(args.url)
                    if status["ready"]:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() - started > 600:
                    raise RuntimeError("launcher readiness timed out")
                time.sleep(1)
            assert status["maximum_context_tokens"] == 24576
            assert status["prefill_chunk_tokens"] == 512
            assert status["memory_plan"]["model"]["state_format"] == "bf16"
            assert status["identity"]["kv"]["format"] == "int8"
            phase["startup_seconds"] = time.monotonic() - started
            cooling = time.monotonic()
            while (
                status["thermal_state"] != "nominal"
                and time.monotonic() - cooling < args.cooldown
            ):
                time.sleep(5)
                status = request(args.url)
            phase["cooldown_seconds"] = time.monotonic() - cooling
            phase["before"] = status
            selection = subprocess.check_output(
                [
                    sys.executable,
                    str(ROOT / "install/models.py"),
                    "--model",
                    "prism-ml/Ternary-Bonsai-2-27B-gguf:PTQ1_0",
                    "--language-only",
                    "--draft-model",
                    phase["draft"],
                    "link",
                ],
                cwd=ROOT,
                text=True,
            ).strip()
            assembly = json.loads((Path(selection) / "model.json").read_text())
            phase["target_artifact_digest"] = assembly["files"][
                "target/Ternary-Bonsai-2-27B-PTQ1_0.gguf"
            ]["digest"]
            phase["swap_before"] = swap()
            print(
                phase["name"], "ready", round(phase["startup_seconds"], 2), flush=True
            )
            yield
        finally:
            stop(process)
            if primary_guard is not None:
                primary_guard.__exit__(None, None, None)


def context_text(url, depth):
    line = "Repository note: pure Python utilities preserve caller data and stable ordering.\n"
    low, high = 1, depth
    target = depth - 160
    while low < high:
        middle = (low + high + 1) // 2
        tokens = request(url, "/tokenize", {"content": line * middle})["tokens"]
        if len(tokens) <= target:
            low = middle
        else:
            high = middle - 1
    return line * low


def measure(args, phase, key, body, task=None):
    before = request(args.url)
    assert (
        not before["active_requests"] and before["transport"]["frontend_waiting"] == 0
    )
    started = time.monotonic()
    reply = request(args.url, "/v1/chat/completions", body)
    elapsed = time.monotonic() - started
    after = request(args.url)
    delta = {key: after["metrics"][key] - before["metrics"][key] for key in METRICS}
    assert after["requests"]["submitted"] - before["requests"]["submitted"] == 1
    assert after["requests"]["completed"] - before["requests"]["completed"] == 1
    assert after["metal"]["healthy"] and after["requests"]["failed"] == 0
    correct, error = True, ""
    if task is not None:
        check = subprocess.run(
            [
                sys.executable,
                str(ROOT / "dev/benchmarks/bonsai_coding.py"),
                "--check",
                task,
            ],
            input=reply["choices"][0]["message"]["content"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        correct, error = check.returncode == 0, check.stderr[-1200:]
        if correct and task == "review_intervals":
            check = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "dev/benchmarks/bonsai_coding.py"),
                    "--check",
                    "merge_intervals",
                ],
                input=reply["choices"][0]["message"]["content"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            correct, error = check.returncode == 0, check.stderr[-1200:]
    row = {
        "key": key,
        "temperature": body.get("temperature", 0),
        "seconds": elapsed,
        "response": reply,
        "metrics_delta": delta,
        "correct": correct,
        "error": error,
        "thermal": [before["thermal_state"], after["thermal_state"]],
        "memory_pressure": [before["memory_pressure"], after["memory_pressure"]],
        "cycle_ms_per_token": delta["decode_cycle_ms"]
        / max(1, delta["decode_output_tokens"]),
        "draft_acceptance": delta["accepted_draft_tokens"]
        / max(1, delta["drafted_tokens"]),
        "state_disk_reads": after["disk"]["read_bytes"] - before["disk"]["read_bytes"],
    }
    phase["runs"].append(row)
    save(args.results / "run.json", args.record)
    print(
        phase["name"],
        key,
        "PASS" if correct else "FAIL",
        round(elapsed, 2),
        "seconds",
        "acceptance",
        round(row["draft_acceptance"], 3),
        flush=True,
    )
    if not correct:
        raise RuntimeError("coding correctness failed: " + key)
    return row


def workload(args, phase):
    for depth in args.depths:
        context = context_text(args.url, depth)
        for index, task in enumerate(args.tasks):
            instruction = bonsai_coding.TASKS[task][0]
            if task == "review_intervals":
                instruction = (
                    "Review the implementation below. In at most three short bullets describe input mutation, "
                    "nested intervals, and touching endpoints. Then provide a corrected merge_intervals "
                    "function in one Python code block. Use no imports.\n\n"
                    + instruction.split("\n\n", 1)[1]
                )
            else:
                instruction = (
                    "Return only the requested function's code, without commentary. "
                    + instruction
                )
            body = {
                "model": "bonsai-27b-splash",
                "temperature": args.temperature,
                "top_p": 0.8,
                "top_k": 20,
                "seed": 42,
                "reasoning_effort": "none",
                "max_tokens": 768 if task == "review_intervals" else 384,
                "cache_salt": "dflash2-depth-" + str(depth),
                "messages": [
                    {
                        "role": "system",
                        "content": "You implement and review correct Python utilities. "
                        "Follow the user's requested format and use no imports.",
                    },
                    {
                        "role": "user",
                        "content": context + "\nTask: " + instruction,
                    },
                ],
            }
            key = str(depth) + "-" + task
            first = measure(args, phase, key, body, task)
            prompt = first["response"]["usage"]["prompt_tokens"]
            assert depth - 256 <= prompt <= depth + 256, prompt
            if index == 0:
                assert first["response"]["timings"]["cache_n"] == 0
                cached = measure(args, phase, key + "-cached", body, task)
                assert cached["response"]["timings"]["cache_n"] > 0
                if args.temperature == 0:
                    assert cached["response"]["choices"] == first["response"]["choices"]
    body = {
        "model": "bonsai-27b-splash",
        "temperature": 0,
        "reasoning_effort": "none",
        "max_tokens": 128,
        "messages": [{"role": "user", "content": "Use add to calculate 17 plus 25."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two integers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "integer"},
                            "b": {"type": "integer"},
                        },
                        "required": ["a", "b"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "add"}},
    }
    row = measure(args, phase, "tool-call", body)
    calls = row["response"]["choices"][0]["message"]["tool_calls"]
    assert len(calls) == 1 and calls[0]["function"]["name"] == "add"
    assert json.loads(calls[0]["function"]["arguments"]) == {"a": 17, "b": 25}
    body["messages"].extend(
        [
            {"role": "assistant", "content": None, "tool_calls": calls},
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": "42"},
        ]
    )
    body["tool_choice"] = "none"
    result = measure(args, phase, "tool-result", body)
    assert re.search(r"\b42\b", result["response"]["choices"][0]["message"]["content"])


def compare(phases):
    if len(phases) != 4:
        return {"eligible": False, "reason": "four completed ABBA phases required"}
    by_key = [{row["key"]: row for row in phase["runs"]} for phase in phases]
    comparisons = {}
    for key in by_key[0]:
        if key.startswith("tool-"):
            continue
        rows = [values[key] for values in by_key]
        outputs = [row["response"]["choices"] for row in rows]
        metric = abba.compare(*(row["cycle_ms_per_token"] for row in rows))
        metric["outputs_identical"] = all(output == outputs[0] for output in outputs)
        metric["output_check_passed"] = all(row["correct"] for row in rows) and (
            all(row.get("temperature", 0) > 0 for row in rows)
            or metric["outputs_identical"]
        )
        metric["request_latency"] = abba.compare(*(row["seconds"] for row in rows))
        metric["thermal_states"] = [row["thermal"] for row in rows]
        metric["draft_acceptance"] = [row["draft_acceptance"] for row in rows]
        metric["thermal_matched"] = all(
            row["thermal"] == rows[0]["thermal"] for row in rows
        )
        comparisons[key] = metric
    phase_rates = [
        math.exp(
            sum(
                math.log(row["cycle_ms_per_token"])
                for row in phase["runs"]
                if not row["key"].startswith("tool-")
            )
            / sum(not row["key"].startswith("tool-") for row in phase["runs"])
        )
        for phase in phases
    ]
    overall = abba.compare(*phase_rates)
    overall["outputs_identical"] = all(
        row["outputs_identical"] for row in comparisons.values()
    )
    overall["per_workload"] = comparisons
    overall["build_matched"] = (
        len({phase["before"]["identity"]["cache"]["build_id"] for phase in phases}) == 1
    )
    overall["target_matched"] = (
        len({phase["target_artifact_digest"] for phase in phases}) == 1
    )
    overall["eligible"] = (
        overall["noise"] <= 0.05
        and overall["build_matched"]
        and overall["target_matched"]
        and all(row["output_check_passed"] for row in comparisons.values())
        and all(
            row["thermal_matched"]
            and row["noise"] <= 0.05
            and row["regression"] <= row["bound"]
            and row["request_latency"]["noise"] <= 0.05
            and row["request_latency"]["regression"] <= row["request_latency"]["bound"]
            for row in comparisons.values()
        )
    )
    overall["candidate_wins"] = overall["eligible"] and overall["regression"] < -max(
        0.02, 2 * overall["noise"]
    )
    return overall


def profile(args, root):
    for depth in args.depths:
        if args.allow_released_primary:
            released_primary()
        path = args.results / ("profile-" + str(depth) + ".log")
        with path.open("w") as output:
            process = subprocess.Popen(
                [
                    str(ROOT / "build/engine-tests/decode-profile"),
                    str(ROOT / "build/splash.metallib"),
                    str(root),
                    "--prompt-tokens",
                    str(depth),
                    "--cycles",
                    "5",
                    "--max-lanes",
                    "1",
                    "--kv-format",
                    "int8",
                    "--state-format",
                    "bf16",
                    "--prefill-chunk-tokens",
                    "512",
                ],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                with guard_primary(process, args.allow_released_primary):
                    process.wait(timeout=1200)
                    if process.returncode:
                        raise RuntimeError(
                            "decode profiling failed; inspect " + str(path)
                        )
            finally:
                stop(process)
        print("profile", depth, "complete", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", default="incoai/Qwen3.8-27B-DFlash2")
    parser.add_argument(
        "--launcher", type=Path, default=Path("/Users/mymac/startllamacpp.sh")
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--port", type=int, default=1236)
    parser.add_argument("--cooldown", type=int, default=120)
    parser.add_argument(
        "--temperature",
        type=float,
        default=0,
        help="coding sampling temperature; sampled runs check behavior, not identical text",
    )
    parser.add_argument(
        "--profile-root",
        type=Path,
        help="profile the installed baseline before running ABBA",
    )
    parser.add_argument(
        "--allow-released-primary",
        action="store_true",
        help="keep an idle, weight-released primary online; abort if it resumes",
    )
    parser.add_argument(
        "--depths",
        type=lambda value: [int(n) for n in value.split(",")],
        default=[4096, 12288, 20480],
    )
    parser.add_argument(
        "--tasks",
        type=lambda value: value.split(","),
        default=["chunked", "merge_intervals", "stable_unique"],
    )
    args = parser.parse_args()
    if not args.candidate.is_dir():
        parser.error("candidate must be a local checkpoint directory")
    if (
        not args.depths
        or len(set(args.depths)) != len(args.depths)
        or any(not 4096 <= depth <= 22528 for depth in args.depths)
    ):
        parser.error("depths must be distinct token counts in [4096, 22528]")
    if not 1 <= args.port <= 65535 or args.port == 1235:
        parser.error("port must be valid and separate from the normal option-14 port")
    if args.cooldown < 0:
        parser.error("cooldown must be nonnegative")
    if not math.isfinite(args.temperature) or not 0 <= args.temperature <= 2:
        parser.error("temperature must be finite and in [0, 2]")
    if not args.tasks or any(task not in bonsai_coding.TASKS for task in args.tasks):
        parser.error("tasks must name the supported coding workloads")
    args.results = args.results.resolve()
    args.candidate = args.candidate.resolve()
    args.url = "http://127.0.0.1:" + str(args.port)
    for url in ("http://127.0.0.1:1235", args.url):
        if url.endswith(":1235") and args.allow_released_primary:
            released_primary()
            continue
        try:
            request(url)
        except (OSError, urllib.error.URLError):
            pass
        else:
            raise RuntimeError(
                "exclusive GPU access required; server still running at " + url
            )
    args.results.mkdir(parents=True, exist_ok=False)
    save(
        args.results / "opencode.json",
        {
            "provider": {"local-llama": {"options": {}, "models": {}}},
            "agent": {"general": {"model": "local-llama/old"}},
        },
    )
    args.record = {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "candidate": str(args.candidate),
        "baseline": args.baseline,
        "temperature": args.temperature,
        "depths": args.depths,
        "tasks": args.tasks,
        "allow_released_primary": args.allow_released_primary,
        "phases": [],
    }
    try:
        if args.profile_root is not None:
            profile(args, args.profile_root.resolve())
        for number, draft in enumerate(
            (args.baseline, str(args.candidate), str(args.candidate), args.baseline), 1
        ):
            phase = {"name": "phase-" + str(number), "draft": draft, "runs": []}
            args.record["phases"].append(phase)
            with server(args, phase):
                workload(args, phase)
                phase["after"] = request(args.url)
                phase["swap_after"] = swap()
            phase["stopped"] = True
            save(args.results / "run.json", args.record)
        args.record["comparison"] = compare(args.record["phases"])
        print(json.dumps(args.record["comparison"], indent=2), flush=True)
    except BaseException as error:
        args.record["error"] = repr(error)
        raise
    finally:
        save(args.results / "run.json", args.record)


if __name__ == "__main__":
    main()
