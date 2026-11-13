#!/usr/bin/env python3
"""Run paired A/B arms of option 21 on one machine and compare them.

An arm is the launcher plus the flags that differ from the stock option-21
profile. Rounds run ABBA: baseline, candidate, candidate, baseline. The
machine's own drift then shows up as the run's noise instead of as an arm's
effect, and abba.py decides the verdict - a candidate wins only if it beats
the baseline by more than the spread the run measures in itself.

Each round launches the real launcher, waits for Ready, warms the engine with
one short request, then probes it with the same fixed requests. Throughput comes
from the timings each response carries, so a request that waited behind another
client's request still reports the work the engine actually did. Expert staging
work, residency and draft acceptance come from the engine's counters, which are
cumulative, so they are read over the whole round rather than one request.

Run from the checkout with its .venv Python:

  .venv/bin/python dev/benchmarks/option21_arms.py --arms chunk1024,context64k
  .venv/bin/python dev/benchmarks/option21_arms.py --attach http://127.0.0.1:1235

A round launches its own engine, so a live option-21 server has to be stopped
first: two of them do not fit in one machine's memory. Any other client that
hits the server during a round shows up in `foreign_requests`.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from . import abba
else:
    import abba

ROOT = Path(__file__).resolve().parents[2]

# Every arm is the stock profile plus the flags it changes. Both candidates buy
# expert residency from somewhere else: a 1,024-token prefill chunk halves the
# shared prefill scratch, and a 65,536-token context drops the spill floor that
# a 131,072-token context has to reserve.
ARMS = {
    "baseline": {},
    "chunk1024": {"SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS": "1024"},
    "context64k": {"SPLASH_FLASH_NEXT_MAX_CONTEXT": "65536"},
}

# A short warm-up, then one cold prefill, one decode-heavy turn, and the same
# prefill again to see how much of a warm prefix the engine reuses. Output
# length is fixed so decode work is comparable across arms.
#
# Thinking is off by default. It is the biggest single determinant of decode
# speed here: with reasoning tokens the draft accepts about 3 rows per cycle,
# with them off about 7, so a thinking-on probe decodes at roughly half the rate
# of a thinking-off one. The option-21 context runs in
# qwen38-option21-performance-20261112.md used thinking off, temperature 1.0 and
# top_p 0.95, so the probes use the same settings to be comparable.
WARMUP = ("warmup", "records", 40, 32)
PROBES = (
    ("cold_8k", "records", 500, 96),
    ("decode_512", "task", 0, 512),
    ("cached_8k", "records", 500, 96),
)

TASK = (
    "Review this merge_intervals implementation. Explain the correctness bugs, "
    "their triggers, and the fixes, then provide corrected Python code. Discuss "
    "input mutation, nested intervals, and intervals that touch at an endpoint.\n"
    "\ndef merge_intervals(intervals):\n"
    "    intervals.sort()\n"
    "    merged = []\n"
    "    for start, end in intervals:\n"
    "        if merged and start < merged[-1][1]:\n"
    "            merged[-1][1] = end\n"
    "        else:\n"
    "            merged.append([start, end])\n"
    "    return merged\n"
)

# Lower is better, so each of these feeds abba directly.
LOWER_IS_BETTER = (
    "decode_ms_per_token",
    "cold_prefill_seconds",
    "cached_prefill_seconds",
    "expert_work_ms_per_output_token",
    "expert_reads_per_output_token",
    "total_seconds",
)


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url + "/status", timeout=10) as response:
        return json.load(response)


def wait_idle(url: str, limit: int = 300) -> None:
    """The engine runs one request at a time, so a probe that queues behind
    another client's request measures queue time, not the engine. Refuse to
    measure while the server is busy."""
    started = time.monotonic()
    while True:
        snapshot = fetch(url)
        if not snapshot.get("active_requests"):
            return
        if time.monotonic() - started > limit:
            raise RuntimeError(
                f"server is still serving {snapshot['active_requests']} request(s) "
                f"after {limit} s"
            )
        time.sleep(3)


def chat(url: str, model: str | None, prompt: str, max_tokens: int, thinking: bool = False) -> dict:
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
        "stream": False,
    }
    if not thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if model:
        body["model"] = model
    request = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as response:
        payload = json.load(response)
    return {"seconds": time.monotonic() - started, "payload": payload}


def prompt_for(kind: str, records: int) -> str:
    if kind == "task":
        return TASK
    return (
        "Read the records and remember the final code.\n"
        + "\n".join(
            f"Record {i}: the stored code is AMBER and the sequence number is {i}."
            for i in range(records)
        )
        + "\nFinal record: the stored code is ORCHID. State the final code, "
        "then list the numbers from 1 to 100 separated by commas."
    )


def counters(snapshot: dict) -> dict:
    """The cumulative counters a round needs, flattened for differencing."""
    metrics = snapshot["metrics"]
    experts = snapshot["streamed_experts"]
    decode = experts["decode"]
    budget = snapshot["memory_plan"]["budget"]
    return {
        "requests_completed": snapshot["requests"]["completed"],
        "prefill_tokens": metrics["prefill_input_tokens"],
        "prefill_ms": metrics["prefill_wall_ms"],
        "decode_tokens": metrics["decode_output_tokens"],
        "decode_ms": metrics["decode_wall_ms"],
        "drafted": metrics["drafted_tokens"],
        "accepted": metrics["accepted_draft_tokens"],
        "expert_reads": decode["read"],
        "expert_routed": decode["routed"],
        "expert_read_bytes": decode["read_bytes"],
        "expert_work_ms": decode["host_steps"]["work_ms"]["total"],
        "expert_loads": decode["loads"],
        "resident_experts": experts["resident"],
        "expert_slots": experts["slots"],
        "expert_chunks": experts["chunks"],
        "expert_cap_bytes": experts["cap_bytes"],
        "shared_prefill_bytes": budget["shared_prefill_bytes"],
        "hot_floor_bytes": budget["kv_spill"]["hot_floor_bytes"],
        "host_available_bytes": snapshot["memory_governor"]["host_available_bytes"],
        "growth_allowed": snapshot["memory_governor"]["growth_allowed"],
    }


def difference(before: dict, after: dict) -> dict:
    delta = {}
    for key, value in after.items():
        previous = before[key]
        if isinstance(value, bool) or not isinstance(value, int):
            delta[key] = value
        else:
            delta[key] = value - previous
    return delta


def probe(
    url: str, model: str | None, name: str, kind: str, records: int, max_tokens: int, thinking: bool = False
) -> dict:
    """One probe. The response carries its own timings, which count engine work
    only, so a probe queued behind another client's request is not miscounted."""
    result = chat(url, model, prompt_for(kind, records), max_tokens, thinking)
    payload = result["payload"]
    timings = payload.get("timings", {})
    speculation = payload.get("metrics", {}).get("speculation", {})
    cache = payload.get("metrics", {}).get("cache", {})
    choice = payload.get("choices", [{}])[0]
    return {
        "probe": name,
        "seconds": result["seconds"],
        "input_tokens": payload.get("usage", {}).get("prompt_tokens"),
        "cached_tokens": cache.get("matched_tokens", timings.get("cache_n")),
        "prefill_ms": timings.get("prompt_ms"),
        "output_tokens": timings.get("predicted_n"),
        "decode_ms": timings.get("predicted_ms"),
        "cycles": speculation.get("cycles"),
        "drafted": speculation.get("drafted_tokens"),
        "accepted": speculation.get("accepted_draft_tokens"),
        "finish": choice.get("finish_reason"),
        "content": choice.get("message", {}).get("content", ""),
    }


def round_metrics(probes: list[dict], round_delta: dict) -> dict:
    """Per-request timings give throughput; the counters give the work behind it.
    Expert rates use the whole round because they are cumulative, so they are a
    rate over everything the engine ran, including another client's requests."""
    decode_ms = sum(p["decode_ms"] for p in probes)
    decode_tokens = sum(p["output_tokens"] for p in probes)
    cycles = sum(p["cycles"] for p in probes)
    drafted = sum(p["drafted"] for p in probes)
    accepted = sum(p["accepted"] for p in probes)
    cold = next(p for p in probes if p["probe"] == "cold_8k")
    cached = next(p for p in probes if p["probe"] == "cached_8k")
    expert_tokens = round_delta["decode_tokens"] or decode_tokens
    return {
        "decode_ms_per_token": decode_ms / decode_tokens,
        "decode_tokens_per_second": decode_tokens * 1000.0 / decode_ms,
        "tokens_per_cycle": decode_tokens / cycles if cycles else None,
        "cold_prefill_seconds": cold["prefill_ms"] / 1000.0,
        "cold_prefill_tokens": cold["input_tokens"],
        "cached_prefill_tokens": cached["cached_tokens"],
        "cached_prefill_seconds": cached["prefill_ms"] / 1000.0,
        "expert_work_ms_per_output_token": round_delta["expert_work_ms"] / expert_tokens,
        "expert_reads_per_output_token": round_delta["expert_reads"] / expert_tokens,
        "expert_hit_rate": (
            (round_delta["expert_routed"] - round_delta["expert_reads"])
            / round_delta["expert_routed"]
            if round_delta["expert_routed"]
            else None
        ),
        "draft_acceptance_rate": accepted / drafted if drafted else None,
        "total_seconds": sum(p["seconds"] for p in probes),
    }


def plan(row: dict) -> dict:
    status = row["status"]
    return {
        "prefill_chunk_tokens": row["prefill_chunk_tokens"],
        "maximum_context_tokens": row["maximum_context_tokens"],
        "shared_prefill_bytes": status["shared_prefill_bytes"],
        "hot_floor_bytes": status["hot_floor_bytes"],
        "expert_cap_bytes": status["expert_cap_bytes"],
        "expert_slots": status["expert_slots"],
        "resident_experts": status["resident_experts"],
        "expert_chunks": status["expert_chunks"],
        "host_available_bytes": status["host_available_bytes"],
    }


def answer_checks(probes: list[dict]) -> dict:
    """Cheap correctness guard: the probes have answers a run can be checked
    against, so an arm that trades speed for correctness is caught."""
    texts = {p["probe"]: p["content"] for p in probes}
    return {
        "cold_final_code": "ORCHID" in texts.get("cold_8k", ""),
        "cached_final_code": "ORCHID" in texts.get("cached_8k", ""),
        "decode_returns_code": "merge_intervals" in texts.get("decode_512", ""),
    }


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def engine_processes(ps_output: str | None = None) -> list[int]:
    """PIDs of the launcher and engine that hold the machine right now."""
    if ps_output is None:
        ps_output = subprocess.check_output(["ps", "-ax", "-o", "pid,command"], text=True)
    pids = []
    for line in ps_output.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid, command = parts
        if "serve-native" in command or "startllamacpp.sh" in command:
            pids.append(int(pid))
    return pids


def free_port(port: int) -> None:
    """One option-21 engine fits a 16 GiB Mac, so a round takes the port from
    whatever is on it, including a launcher whose retry loop would relaunch it."""
    for _ in range(30):
        pids = engine_processes()
        if not pids:
            return
        for pid in pids:
            with contextlib.suppress(Exception):
                os.kill(pid, signal.SIGTERM)
        time.sleep(2)
    raise RuntimeError(f"port {port} still held by an engine after 60 s")


@contextlib.contextmanager
def launched_server(arm: str, env: dict, url: str, log: Path, cooldown: int, port: int):
    free_port(port)
    with log.open("w") as handle:
        process = subprocess.Popen(
            ["bash", str(ROOT / "startllamacpp.sh"), "--direct", "21"],
            cwd=str(ROOT),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started = time.monotonic()
        try:
            ready = None
            while ready is None:
                if process.poll() is not None:
                    raise RuntimeError(f"{arm}: launcher exited; read {log}")
                try:
                    candidate = fetch(url)
                    if candidate.get("ready"):
                        ready = candidate
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() - started > 420:
                    raise RuntimeError(f"{arm}: readiness timed out; read {log}")
                time.sleep(2)
            while (
                ready["thermal_state"] != "nominal"
                and time.monotonic() - started < cooldown
            ):
                time.sleep(5)
                ready = fetch(url)
            yield ready
        finally:
            stop(process)


def build_env(arm: str, port: int, cache: Path, log_dir: Path) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SPLASH_") and not key.startswith("LLAMA_")
    }
    env.update(
        LLAMA_HOST="127.0.0.1",
        LLAMA_PORT=str(port),
        LLAMA_LOG_DIR=str(log_dir),
        SPLASH_BIN=str(ROOT / "splash"),
        SPLASH_FLASH_NEXT_CACHE_DIR=str(cache),
    )
    env.update(ARMS[arm])
    return env


def run_round(arm: str, args, number: int) -> dict:
    """Run a round, and run it again if another client shared the machine while
    it was running or a probe could not complete. A round measured against
    foreign load, or cut short, is not comparable to the others."""
    for attempt in range(1, args.attempts + 1):
        try:
            row = single_round(arm, args, number)
        except (OSError, urllib.error.URLError, RuntimeError) as error:
            print(f"{arm} round {number}: attempt {attempt} failed: {error}", flush=True)
            continue
        if row["foreign_requests"] == 0 or attempt == args.attempts:
            return row
        print(
            f"{arm} round {number}: {row['foreign_requests']} requests from another "
            f"client during the round, rerunning",
            flush=True,
        )
    raise RuntimeError(f"{arm} round {number} did not complete in {args.attempts} attempts")


def single_round(arm: str, args, number: int) -> dict:
    url = args.url
    # The launcher names its cache from the directory around this path, so each
    # round gets its own cold cache instead of inheriting the last round's. An
    # attempt also starts clean, otherwise a rerun would reuse the prefix the
    # first attempt wrote and report a warm prefill as a cold one.
    round_dir = args.results / "rounds" / f"{arm}-{number}"
    shutil.rmtree(round_dir, ignore_errors=True)
    cache = round_dir / "scratch"
    log = args.results / f"{arm}-{number}-launcher.log"
    env = build_env(arm, args.port, cache, args.results)
    with launched_server(arm, env, url, log, args.cooldown, args.port) as ready:
        before = counters(ready)
        wait_idle(url)
        probes = [
            probe(url, args.model, name, kind, records, tokens, args.thinking)
            for name, kind, records, tokens in (WARMUP,) + PROBES
        ]
        measured = probes[1:]
        round_delta = difference(before, counters(fetch(url)))
        row = {
            "arm": arm,
            "round": number,
            "prefill_chunk_tokens": ready["prefill_chunk_tokens"],
            "maximum_context_tokens": ready["maximum_context_tokens"],
            "thermal": ready["thermal_state"],
            "memory_pressure": ready["memory_pressure"],
            "swap": subprocess.check_output(
                ["sysctl", "-n", "vm.swapusage"], text=True
            ).strip(),
            "status": counters(ready),
            "metrics": round_metrics(measured, round_delta),
            "foreign_requests": round_delta["requests_completed"] - len(measured) - 1,
            "warmup_seconds": probes[0]["seconds"],
            "answers": answer_checks(measured),
            "probe_details": [
                {
                    "probe": p["probe"],
                    "seconds": p["seconds"],
                    "input_tokens": p["input_tokens"],
                    "cached_tokens": p["cached_tokens"],
                    "prefill_seconds": p["prefill_ms"] / 1000.0,
                    "output_tokens": p["output_tokens"],
                    "decode_ms": p["decode_ms"],
                    "cycles": p["cycles"],
                    "finish": p["finish"],
                }
                for p in measured
            ],
        }
        print(
            f"{arm} round {number}: decode "
            f"{row['metrics']['decode_tokens_per_second']:.1f} tok/s, cold prefill "
            f"{row['metrics']['cold_prefill_seconds']:.1f} s, resident experts "
            f"{row['status']['resident_experts']}, expert work "
            f"{row['metrics']['expert_work_ms_per_output_token']:.0f} ms/token, "
            f"foreign requests {row['foreign_requests']}",
            flush=True,
        )
        return row


def verdict(rounds: list[dict], candidate: str) -> dict:
    baseline = [row for row in rounds if row["arm"] == "baseline"]
    arms = [row for row in rounds if row["arm"] == candidate]
    if len(baseline) != 2 or len(arms) != 2:
        return {}
    result = {}
    for metric in LOWER_IS_BETTER:
        samples = [[row["metrics"][metric]] for row in baseline[:1] + arms + baseline[1:]]
        result[metric] = abba.compare_samples(samples)
    result["answers"] = {
        arm: all(all(row["answers"].values()) for row in rows)
        for arm, rows in (("baseline", baseline), (candidate, arms))
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arms", default="chunk1024", help="comma separated candidate arms"
    )
    parser.add_argument("--port", type=int, default=1235)
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="let the model reason in the probes, which halves decode throughput",
    )
    parser.add_argument(
        "--model",
        default="",
        help="served model name; empty asks the server's own default",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
    )
    parser.add_argument("--cooldown", type=int, default=240)
    parser.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="rerun a round that shared the machine with another client",
    )
    parser.add_argument(
        "--attach",
        help="probe a server that is already running instead of launching rounds",
    )
    args = parser.parse_args()
    args.url = args.attach or f"http://127.0.0.1:{args.port}"
    args.results.mkdir(parents=True, exist_ok=True)

    candidates = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    for arm in candidates:
        if arm not in ARMS:
            parser.error(f"unknown arm {arm}; known: {', '.join(ARMS)}")

    if args.attach:
        before = counters(fetch(args.url))
        wait_idle(args.url)
        probes = [
            probe(args.url, args.model, name, kind, records, tokens, args.thinking)
            for name, kind, records, tokens in PROBES
        ]
        after = counters(fetch(args.url))
        print(json.dumps(round_metrics(probes, difference(before, after)), indent=2))
        return 0

    order = ["baseline"] + [arm for arm in candidates for _ in range(2)] + ["baseline"]
    rounds = []
    for number, arm in enumerate(order, 1):
        try:
            rounds.append(run_round(arm, args, number))
        finally:
            # A round's KV spill cache is gigabytes; only 16 GiB of the disk is free.
            shutil.rmtree(args.results / "rounds" / f"{arm}-{number}", ignore_errors=True)
    results = {
        "machine": subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip(),
        "order": order,
        "rounds": rounds,
        "verdicts": {arm: verdict(rounds, arm) for arm in candidates},
    }
    out = args.results / f"option21-arms-{time.strftime('%Y%m%d-%H%M')}.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out}")
    for arm, comparison in results["verdicts"].items():
        first = next(row for row in rounds if row["arm"] == arm)
        print(f"\n{arm}")
        print(f"  plan: {json.dumps(plan(first))}")
        for metric, sample in comparison.items():
            if isinstance(sample, dict) and "verdict" in sample:
                print(f"  {metric}: {abba.describe(sample)}")
        for arm, answers in comparison.get("answers", {}).items():
            if not answers:
                print(f"  {arm}: probe answers failed their correctness checks")
    return 0


def interrupted(_signal, _frame):
    raise KeyboardInterrupt("benchmark interrupted; stopping its launcher")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, interrupted)
    sys.exit(main())
