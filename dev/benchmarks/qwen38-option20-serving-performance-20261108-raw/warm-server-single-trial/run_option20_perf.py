#!/usr/bin/env python3
"""Live serving-path performance probe for startllamacpp.sh option 20.

Option 20 profile: ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS served by
Splash (131,072 context, 2,048 prefill chunks, INT8 KV, BF16 state, DFlash2).

Mirrors the established harness methodology:
  * smoke gate  : 351-token cold prompt + exact reuse (correctness + cache gate)
  * matrix      : 4,019-token cold/reuse pair (prefill tok/s, TTFT) plus three
                  128-token-capped coding probes (decode tok/s)
Every probe waits for the server to be idle first, samples /status while the
request runs, and writes a per-probe JSON record plus an aggregated summary.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:1235"
MODEL = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS"
OUT_DIR = Path("/private/tmp/option20-perf-20261108")

SLEEP_WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu "
)


def http_json(method: str, path: str, payload=None, timeout: float = 10.0):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def tokenize(text: str) -> int:
    return len(http_json("POST", "/tokenize", {"content": text})["tokens"])


def status_snapshot() -> dict:
    status = http_json("GET", "/status", timeout=5)
    metrics = status.get("metrics", {})
    governor = status.get("memory_governor", {})
    actual = status.get("memory_actual", {})
    requests = status.get("requests", {})
    return {
        "ready": status.get("ready"),
        "memory_pressure": status.get("memory_pressure"),
        "thermal_state": status.get("thermal_state"),
        "active_requests": len(status.get("active_requests") or []),
        "waiting": status.get("admission", {}).get("waiting"),
        "waiting_memory": status.get("admission", {}).get("waiting_memory"),
        "suspended": status.get("admission", {}).get("suspended"),
        "requests_completed": requests.get("completed"),
        "prefill_input_tokens": metrics.get("prefill_input_tokens"),
        "prefill_tokens_per_second": metrics.get("prefill_tokens_per_second"),
        "decode_output_tokens": metrics.get("decode_output_tokens"),
        "decode_tokens_per_second": metrics.get("decode_tokens_per_second"),
        "drafted_tokens": metrics.get("drafted_tokens"),
        "accepted_draft_tokens": metrics.get("accepted_draft_tokens"),
        "draft_acceptance_rate": metrics.get("draft_acceptance_rate"),
        "capacity_failures": metrics.get("capacity_failures"),
        "metal_failures": metrics.get("metal_failures"),
        "metal_allocated_gib": round(actual.get("allocated_bytes", 0) / 2**30, 3),
        "metal_peak_gib": round(actual.get("peak_bytes", 0) / 2**30, 3),
        "host_available_bytes": governor.get("host_available_bytes"),
        "host_spare_bytes": governor.get("host_spare_bytes"),
        "host_headroom_bytes": governor.get("host_headroom_bytes"),
        "growth_allowed": governor.get("growth_allowed"),
    }


def wait_idle(out, limit: float = 300.0) -> tuple[float, bool, int]:
    """Return (idle_wait_seconds, started_blocked, foreign_active_samples)."""
    started = time.monotonic()
    started_blocked = False
    foreign_samples = 0
    quiet = 0
    while time.monotonic() - started < limit:
        before = status_snapshot()
        if before["active_requests"] or before["waiting"] or before["suspended"]:
            started_blocked = True
            foreign_samples += 1
            quiet = 0
        else:
            quiet += 1
            if quiet >= 3:
                return round(time.monotonic() - started, 3), started_blocked, foreign_samples
        time.sleep(0.5)
    raise RuntimeError("server did not become idle")


def build_prompt(salt: str, filler_tokens: int) -> str:
    head = (
        "You are a deterministic benchmark probe. Do not explain.\n"
        f"Benchmark salt: {salt}\n"
        "First line: the single uppercase word ORCHID.\n"
        "Second line: the integers 1 through 40 separated by comma and space.\n"
    )
    filler = ""
    for repeat in range(1, 400):
        candidate = head + (SLEEP_WORDS * repeat)
        if tokenize(candidate) >= filler_tokens:
            filler = SLEEP_WORDS * repeat
            break
    return head + filler


def run_probe(out: Path, name: str, prompt: str, max_tokens: int, phase: str) -> dict:
    idle_wait, blocked, foreign = wait_idle(out)
    before = status_snapshot()
    time.sleep(2.0)  # fixed cooldown so probes do not overlap the previous cache write

    body = {
        "model": MODEL,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )

    text_parts: list[str] = []
    timings = None
    usage = None
    finish_reason = None
    complete = False
    started = time.monotonic()
    ttft_client = None
    samples: list[dict] = []
    next_sample = 0.0

    with urllib.request.urlopen(request, timeout=1800) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                complete = True
                break
            chunk = json.loads(payload)
            if ttft_client is None and chunk.get("choices"):
                delta = chunk["choices"][0].get("delta") or {}
                if delta.get("content"):
                    ttft_client = time.monotonic() - started
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text_parts.append(delta["content"])
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
            if chunk.get("timings"):
                timings = chunk["timings"]
            if chunk.get("usage"):
                usage = chunk["usage"]
            now = time.monotonic()
            if now >= next_sample:
                samples.append(status_snapshot())
                next_sample = now + 0.5

    wall = time.monotonic() - started
    after = status_snapshot()
    time.sleep(5.0)  # cooldown between probes

    text = "".join(text_parts)
    decode_tokens = (timings or {}).get("predicted_n") or usage.get("completion_tokens", 0)
    record = {
        "name": name,
        "phase": phase,
        "wall_seconds": round(wall, 3),
        "sse_ttft_seconds": round(ttft_client, 3) if ttft_client is not None else None,
        "prompt_tokens": (timings or {}).get("prompt_n"),
        "completion_tokens": usage.get("completion_tokens") if usage else decode_tokens,
        "cached_tokens": (timings or {}).get("cache_n"),
        "prefill_tokens": (timings or {}).get("prompt_n"),
        "prefill_ms": (timings or {}).get("prompt_ms"),
        "prefill_tok_s": round((timings or {}).get("prompt_per_second", 0), 2),
        "decode_tokens": decode_tokens,
        "decode_ms": (timings or {}).get("predicted_ms"),
        "decode_tok_s": round((timings or {}).get("predicted_per_second", 0), 2),
        "draft_n": (timings or {}).get("draft_n"),
        "draft_n_accepted": (timings or {}).get("draft_n_accepted"),
        "finish_reason": finish_reason,
        "complete_sse": complete,
        "idle_wait_seconds": idle_wait,
        "started_blocked": blocked,
        "foreign_active_samples": foreign,
        "status_samples": len(samples),
        "memory_pressure_before": before["memory_pressure"],
        "memory_pressure_after": after["memory_pressure"],
        "thermal_state_before": before["thermal_state"],
        "thermal_state_after": after["thermal_state"],
        "metal_peak_gib_before": before["metal_peak_gib"],
        "metal_peak_gib_after": after["metal_peak_gib"],
        "host_available_bytes_before": before["host_available_bytes"],
        "host_headroom_bytes_before": before["host_headroom_bytes"],
        "growth_allowed_before": before["growth_allowed"],
        "text": text[:220],
        "usage": usage,
        "timings": timings,
        "status_before": before,
        "status_after": after,
    }
    (out / f"{name}.json").write_text(json.dumps(record, indent=2))
    print(
        f"[{name}] prompt={record['prompt_tokens']} cached={record['cached_tokens']} "
        f"prefill={record['prefill_tok_s']} tok/s ttft={record['sse_ttft_seconds']}s "
        f"decode={record['decode_tokens']} tok/s pressure={before['memory_pressure']}->{after['memory_pressure']}"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    preflight = status_snapshot()
    instance = http_json("GET", "/status")["instance"]
    preflight_path = out / "preflight.json"
    preflight_path.write_text(json.dumps({"instance": instance, "status": preflight}, indent=2))
    print(
        f"server pid={instance['pid']} model={instance['model']} "
        f"pressure={preflight['memory_pressure']} thermal={preflight['thermal_state']} "
        f"metal_peak={preflight['metal_peak_gib']} GiB host_available={preflight['host_available_bytes']}"
    )

    rows: list[dict] = []

    salt_smoke = uuid.uuid4().hex[:8]
    smoke_prompt = build_prompt(salt_smoke, 351)
    print(f"smoke prompt tokens={tokenize(smoke_prompt)}")
    smoke_cold = run_probe(out, "smoke-cold", smoke_prompt, 96, "gate")
    smoke_reuse = run_probe(out, "smoke-reuse", smoke_prompt, 96, "gate")

    def gate_ok(row: dict) -> bool:
        text = row["text"]
        return text.startswith("ORCHID") and "1, 2, 3, 4, 5, 6, 7, 8, 9, 10" in text

    smoke_cold["correct"] = gate_ok(smoke_cold)
    smoke_reuse["correct"] = gate_ok(smoke_reuse)
    if not smoke_cold["correct"] or not smoke_reuse["correct"]:
        raise SystemExit("smoke correctness gate failed")
    if (smoke_reuse["cached_tokens"] or 0) < 320:
        raise SystemExit(f"smoke reuse gate failed: cached={smoke_reuse['cached_tokens']}")
    rows.extend([smoke_cold, smoke_reuse])

    salt_4k = uuid.uuid4().hex[:8]
    prompt_4k = build_prompt(salt_4k, 4019)
    tokens_4k = tokenize(prompt_4k)
    print(f"4k prompt tokens={tokens_4k}")
    cold = run_probe(out, "4k-cold", prompt_4k, 96, "matrix")
    reuse = run_probe(out, "4k-reuse", prompt_4k, 96, "matrix")
    cold["correct"] = gate_ok(cold)
    reuse["correct"] = gate_ok(reuse)
    rows.extend([cold, reuse])

    code_prompts = [
        "Write a Python function `merge_sorted_lists(list1, list2)` that merges two sorted "
        "lists into one sorted list without calling sort. Include a docstring and type hints.",
        "Write a Python function `first_duplicate(values)` returning the first value that "
        "appears twice, or None. Include a docstring and type hints.",
        "Write a Python function `roman_to_int(s: str) -> int` for standard Roman numerals. "
        "Include a docstring.",
    ]
    for index, prompt in enumerate(code_prompts, start=1):
        rows.append(run_probe(out, f"code-{index}", prompt, 128, "matrix"))

    summary = {
        "complete": True,
        "phase": "option20-live-performance",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "server": instance,
        "preflight": preflight,
        "rows": rows,
    }
    (out / "matrix-results.json").write_text(json.dumps(summary, indent=2))

    def mean(name: str, key: str):
        values = [r[key] for r in rows if r["name"].startswith(name) and r.get(key)]
        return statistics.mean(values) if values else None

    lines = [
        "| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cached tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['prompt_tokens']} | {row['prefill_tok_s']} | "
            f"{row['sse_ttft_seconds']} | {row['decode_tok_s']} | {row['cached_tokens']} |"
        )
    code_rows = [r for r in rows if r["name"].startswith("code-")]
    lines.append("")
    lines.append(
        f"coding decode mean: {statistics.mean([r['decode_tok_s'] for r in code_rows]):.2f} tok/s "
        f"(range {min(r['decode_tok_s'] for r in code_rows):.2f}-"
        f"{max(r['decode_tok_s'] for r in code_rows):.2f})"
    )
    draft_accepted = sum(r["draft_n_accepted"] or 0 for r in rows)
    drafted = sum(r["draft_n"] or 0 for r in rows)
    lines.append(
        f"draft acceptance over all probes: {draft_accepted}/{drafted} "
        f"({(draft_accepted / drafted if drafted else 0) * 100:.1f}%)"
    )
    (out / "matrix.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
