#!/usr/bin/env python3
"""Compare option-14 contexts using the real launcher and isolated scratch caches.

Run from the checkout with its .venv Python. Defaults to an ABC-CBA order;
reports survive, scratch caches are removed after their server has stopped.
"""

import argparse
import contextlib
import json
import math
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from . import abba
else:
    import abba


ROOT = Path(__file__).resolve().parents[2]


def fetch(url):
    with urllib.request.urlopen(url + "/status", timeout=5) as response:
        return json.load(response)


def swap():
    return subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


@contextlib.contextmanager
def server(args, row, cache, config, suffix=""):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SPLASH_BONSAI_")
    }
    env.update(
        LLAMA_HOST="127.0.0.1",
        LLAMA_PORT=str(args.port),
        LLAMA_LOG_DIR=str(args.results / "logs"),
        OPENCODE_CONFIG_PATH=str(config),
        SPLASH_BIN=str(ROOT / "splash"),
        SPLASH_BONSAI_MAX_CONTEXT=row["context"],
        SPLASH_BONSAI_CACHE_DIR=str(cache),
        SPLASH_BONSAI_STATE_FORMAT="bf16",
        SPLASH_BONSAI_PREFILL_CHUNK_TOKENS="512",
    )
    name = row["name"] + suffix
    started = time.monotonic()
    with (args.results / (name + "-launcher.log")).open("w") as log:
        process = subprocess.Popen(
            ["bash", str(args.launcher), "--direct", "14"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"{name}: launcher exited; inspect its log")
                try:
                    ready = fetch(args.url)
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() - started > 300:
                        raise RuntimeError(f"{name}: readiness timed out")
                    time.sleep(1)
            assert ready["maximum_context_tokens"] == int(row["context"][:-1]) * 1024
            assert ready["prefill_chunk_tokens"] == 512
            assert ready["memory_plan"]["model"]["state_format"] == "bf16"
            startup = time.monotonic() - started
            cooling = time.monotonic()
            while (
                ready["thermal_state"] != "nominal"
                and time.monotonic() - cooling < args.cooldown
            ):
                time.sleep(5)
                ready = fetch(args.url)
            row["restart" if suffix else "start"] = {
                "startup_seconds": startup,
                "cooldown_seconds": time.monotonic() - cooling,
                "status": ready,
                "swap": swap(),
                "disk_available_bytes": os.statvfs(args.results).f_bavail
                * os.statvfs(args.results).f_frsize,
            }
            print(
                name,
                "ready",
                round(startup, 2),
                "thermal",
                ready["thermal_state"],
                flush=True,
            )
            yield
        finally:
            stop(process)
            # The launcher's EXIT trap must finish before the scratch cache goes.
            if process.returncode not in (0, 143, -signal.SIGTERM):
                print(name, "launcher stop status", process.returncode, flush=True)


def workload(args, row, kind, records=220, suffix=""):
    name = row["name"] + suffix + "-" + kind
    script = "bonsai_coding.py" if kind == "coding" else "bonsai_context.py"
    extra = ["--order", "0"] if kind == "coding" else ["--records", str(records)]
    output = args.results / (name + ".json")
    with (args.results / (name + ".log")).open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "dev/benchmarks" / script),
                "--url",
                args.url,
                *extra,
                "--results",
                str(output),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=900,
        )
    value = json.loads(output.read_text())
    if kind == "coding":
        assert len(value["runs"]) == 3
        assert all(run["correct"] and run["isolated"] for run in value["runs"])
    else:
        assert value["cached"]["response"]["timings"]["cache_n"] > 0
        assert (
            value["cold"]["response"]["choices"][0]["message"]["content"]
            == value["cached"]["response"]["choices"][0]["message"]["content"]
        )
    after = fetch(args.url)
    assert after["metal"]["healthy"] and after["requests"]["failed"] == 0
    print(name, "passed", flush=True)
    return value


def compare(rounds):
    groups = {}
    for row in rounds:
        coding = row["coding"]["runs"]
        cycle_ms = [
            run["metrics_delta"]["decode_cycle_ms"]
            / run["metrics_delta"]["decode_output_tokens"]
            for run in coding
        ]
        item = {
            "coding_ms_per_token": math.exp(
                sum(math.log(ms) for ms in cycle_ms) / len(cycle_ms)
            ),
            "cold_seconds": row["context_workload"]["cold"]["seconds"],
            "cached_seconds": row["context_workload"]["cached"]["seconds"],
            "thermal": [
                row["start"]["status"]["thermal_state"],
                row["after"]["thermal_state"],
            ],
            "outputs": [
                run["response"]["choices"][0]["message"]["content"] for run in coding
            ],
            "acceptance": [run["draft_acceptance"] for run in coding],
        }
        groups.setdefault(row["context"], []).append(item)
    summary = {}
    baseline_context = "24K" if "24K" in groups else next(iter(groups))
    baseline = groups[baseline_context]
    for context, items in groups.items():
        values = [item["coding_ms_per_token"] for item in items]
        noise = (max(values) - min(values)) / (sum(values) / len(values)) * 100
        summary[context] = {
            "samples": len(items),
            "coding_tok_per_second": 1000 / (sum(values) / len(values)),
            "coding_spread_percent": noise,
            "cold_seconds": sum(item["cold_seconds"] for item in items) / len(items),
            "cached_seconds": sum(item["cached_seconds"] for item in items)
            / len(items),
            "outputs_identical": all(
                item["outputs"] == items[0]["outputs"] for item in items
            ),
            "acceptance": [item["acceptance"] for item in items],
            "speed_verdict_eligible": len(items) >= 2
            and noise <= 5
            and all(item["outputs"] == baseline[0]["outputs"] for item in items)
            and all(item["acceptance"] == baseline[0]["acceptance"] for item in items)
            and all(state == "nominal" for item in items for state in item["thermal"]),
        }
    for context, items in groups.items():
        row = summary[context]
        row["speedup_supported"] = False
        if context != baseline_context and len(items) == len(baseline) == 2:
            result = abba.compare(
                baseline[0]["coding_ms_per_token"],
                items[0]["coding_ms_per_token"],
                items[1]["coding_ms_per_token"],
                baseline[1]["coding_ms_per_token"],
            )
            row["comparison_to_baseline"] = result
            row["speedup_supported"] = (
                row["speed_verdict_eligible"]
                and summary[baseline_context]["speed_verdict_eligible"]
                and result["noise"] <= abba.NOISE_LIMIT
                and result["regression"] < -result["bound"]
            )
    return summary


def interrupted(_signal, _frame):
    raise KeyboardInterrupt("benchmark interrupted; stopping its launcher")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--launcher", type=Path, default=Path.home() / "startllamacpp.sh"
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--order", default="24K,16K,8K,8K,16K,24K")
    parser.add_argument("--port", type=int, default=1236)
    parser.add_argument("--cooldown", type=int, default=60)
    parser.add_argument(
        "--filled-check",
        action="store_true",
        help="also test ~7K/15K/23K filled prompts",
    )
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    order = args.order.split(",")
    if not order or any(context not in {"8K", "16K", "24K"} for context in order):
        parser.error("order must contain 8K,16K,24K profiles")
    if not 1 <= args.port <= 65535 or args.cooldown < 0:
        parser.error("invalid port or cooldown")
    args.url = f"http://127.0.0.1:{args.port}"
    # Check the socket itself: an unrelated server may not have a /status route.
    try:
        with socket.create_connection(("127.0.0.1", args.port), timeout=1):
            parser.error("benchmark port is occupied")
    except ConnectionRefusedError:
        pass
    args.results = args.results.resolve()
    if args.results.exists() and any(args.results.iterdir()):
        parser.error("results directory must be empty; preserve earlier measurements")
    args.results.mkdir(parents=True, exist_ok=True)
    report = {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "order": order,
        "kv": "int8",
        "state": "bf16",
        "chunk_tokens": 512,
        "rounds": [],
        "filled_checks": [],
        "scratch_caches_removed": False,
    }

    def save():
        (args.results / "run.json").write_text(json.dumps(report, indent=2) + "\n")

    try:
        for index, context in enumerate(order, 1):
            row = {"name": f"round-{index}-{context}", "context": context}
            report["rounds"].append(row)
            with tempfile.TemporaryDirectory(
                prefix="scratch-", dir=args.results
            ) as temporary:
                scratch = Path(temporary)
                config = scratch / "opencode.json"
                config.write_text(
                    json.dumps(
                        {
                            "provider": {"local-llama": {"options": {}, "models": {}}},
                            "agent": {"general": {"model": "local-llama/old"}},
                        }
                    )
                )
                cache = scratch / "cache"
                with server(args, row, cache, config):
                    row["coding"] = workload(args, row, "coding")
                    row["context_workload"] = workload(args, row, "context")
                    assert (
                        row["context_workload"]["cold"]["response"]["timings"][
                            "cache_n"
                        ]
                        == 0
                    )
                    row["after"] = fetch(args.url)
                    row["swap_after"] = swap()
                save()
                # Reuse the same scratch cache after a clean launcher stop.
                with server(args, row, cache, config, "-restart"):
                    row["restarted_workload"] = workload(
                        args, row, "context", suffix="-restart"
                    )
                    restarted = row["restarted_workload"]["cold"]["response"]
                    original = row["context_workload"]["cold"]["response"]
                    assert restarted["timings"]["cache_n"] > 0
                    assert restarted["choices"] == original["choices"]
                save()
            print(row["name"], "scratch cache removed", flush=True)
        report["comparison"] = compare(report["rounds"])
        # Keep long-fill checks out of the matched short-workload phases.
        if args.filled_check:
            for context, records in (("8K", 320), ("16K", 680), ("24K", 1000)):
                row = {"name": "filled-" + context, "context": context}
                report["filled_checks"].append(row)
                with tempfile.TemporaryDirectory(
                    prefix="scratch-", dir=args.results
                ) as temporary:
                    scratch = Path(temporary)
                    config = scratch / "opencode.json"
                    config.write_text("{}")
                    with server(args, row, scratch / "cache", config):
                        row["workload"] = workload(
                            args, row, "context", records=records
                        )
                        assert (
                            row["workload"]["cold"]["response"]["timings"]["cache_n"]
                            == 0
                        )
                save()
        report["scratch_caches_removed"] = True
    except BaseException as error:
        report["error"] = repr(error)
        raise
    finally:
        save()
    print(json.dumps(report["comparison"], indent=2), flush=True)


if __name__ == "__main__":
    main()
