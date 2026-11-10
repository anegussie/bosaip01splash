#!/usr/bin/env python3
"""Option 20 live serving-path performance test, two trials, Nov-6 harness parity.

Option 20 profile: ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS served by
Splash on 127.0.0.1:1235 (131,072 context, 2,048 prefill chunks, INT8 KV, BF16
state, DFlash2, 10.8 GiB Metal cap).

Methodology mirrors dev/benchmarks/qwen38-option20-telemetry-performance-20261106:
  * per trial: smoke cold/reuse correctness + cache gate, 4K cold/reuse pair,
    three 128-token-capped coding probes
  * trial 1 natural order, trial 2 reversed group order
  * fresh prompt salt per trial so every "cold" probe is genuinely cold
  * every probe waits for an idle server, samples /status during the request,
    and records the per-request metrics block (cycles, cache status, latency)
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
OUT_DIR = Path("/private/tmp/option20-perf2-20261108")

SLEEP_WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu "
)

CODE_PROMPTS = [
    "Write a Python function `merge_sorted_lists(list1, list2)` that merges two sorted "
    "lists into one sorted list without calling sort. Include a docstring and type hints.",
    "Write a Python function `first_duplicate(values)` returning the first value that "
    "appears twice, or None. Include a docstring and type hints.",
    "Write a Python function `roman_to_int(s: str) -> int` for standard Roman numerals. "
    "Include a docstring.",
]


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
    kv = status.get("kv", {})
    disk = status.get("disk", {})
    cache = status.get("cache", {})
    table = status.get("streamed_table", {})
    return {
        "ready": status.get("ready"),
        "active_requests": len(status.get("active_requests") or []),
        "waiting": status.get("admission", {}).get("waiting"),
        "waiting_memory": status.get("admission", {}).get("waiting_memory"),
        "suspended": status.get("admission", {}).get("suspended"),
        "memory_pressure": status.get("memory_pressure"),
        "thermal_state": status.get("thermal_state"),
        "requests_completed": status.get("requests", {}).get("completed"),
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
        "kv_pages_allocated": kv.get("pages_allocated"),
        "kv_pages_active": kv.get("pages_active"),
        "kv_pages_cache": kv.get("pages_cache"),
        "kv_pages_free": kv.get("pages_free"),
        "disk_used_bytes": disk.get("used_bytes"),
        "disk_kv_blocks": disk.get("kv_blocks"),
        "disk_read_bytes": disk.get("read_bytes"),
        "disk_written_bytes": disk.get("written_bytes"),
        "disk_kv_demotions": disk.get("kv_demotions"),
        "cache_hits": cache.get("hits"),
        "cache_reused_tokens": cache.get("reused_tokens"),
        "cache_kv_disk_hit_tokens": cache.get("kv_disk_hit_tokens"),
        "streamed_prefill_hit_rate": table.get("prefill", {}).get("hit_rate"),
        "streamed_decode_hit_rate": table.get("decode", {}).get("hit_rate"),
    }


def wait_idle(limit: float = 900.0) -> tuple[float, bool, int]:
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


def build_prompt(salt: str, target_tokens: int) -> str:
    head = (
        "You are a deterministic benchmark probe. Do not explain.\n"
        f"Benchmark salt: {salt}\n"
        "First line: the single uppercase word ORCHID.\n"
        "Second line: the integers 1 through 40 separated by comma and space.\n"
    )
    filler = ""
    for repeat in range(1, 400):
        candidate = head + (SLEEP_WORDS * repeat)
        if tokenize(candidate) >= target_tokens:
            filler = SLEEP_WORDS * repeat
            break
    return head + filler


def run_probe(out: Path, name: str, prompt: str, max_tokens: int, phase: str) -> dict:
    idle_wait, blocked, foreign = wait_idle()
    before = status_snapshot()
    time.sleep(2.0)  # fixed cooldown so a probe never overlaps the previous cache write

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
    metrics = None
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
            if chunk.get("metrics"):
                metrics = chunk["metrics"]
            now = time.monotonic()
            if now >= next_sample:
                samples.append(status_snapshot())
                next_sample = now + 0.5

    wall = time.monotonic() - started
    after = status_snapshot()
    time.sleep(5.0)  # cooldown between probes

    text = "".join(text_parts)
    contended_samples = sum(1 for s in samples if s["active_requests"] > 1 or s["waiting"] or s["suspended"])
    completed_delta = (after["requests_completed"] or 0) - (before["requests_completed"] or 0)
    speculation = (metrics or {}).get("speculation", {})
    latency = (metrics or {}).get("request_latency", {})
    cache_metrics = (metrics or {}).get("cache", {})
    decode_tokens = (timings or {}).get("predicted_n") or (usage or {}).get("completion_tokens", 0)
    cycles = speculation.get("cycles")
    record = {
        "name": name,
        "phase": phase,
        "clean": foreign == 0 and not blocked and contended_samples == 0 and completed_delta == 1,
        "foreign_active_samples": foreign,
        "contended_samples": contended_samples,
        "requests_completed_delta": completed_delta,
        "status_samples": len(samples),
        "started_blocked": blocked,
        "idle_wait_seconds": idle_wait,
        "wall_seconds": round(wall, 3),
        "sse_ttft_seconds": round(ttft_client, 3) if ttft_client is not None else None,
        "prompt_tokens": (timings or {}).get("prompt_n"),
        "completion_tokens": (usage or {}).get("completion_tokens", decode_tokens),
        "cached_tokens": (timings or {}).get("cache_n"),
        "prefill_tokens": (metrics or {}).get("prefill", {}).get("tokens", (timings or {}).get("prompt_n")),
        "prefill_ms": (timings or {}).get("prompt_ms"),
        "prefill_tok_s": round((timings or {}).get("prompt_per_second", 0), 2),
        "ttft_ms": latency.get("ttft_ms"),
        "queue_to_start_ms": latency.get("queue_to_start_ms"),
        "decode_tokens": (metrics or {}).get("decode", {}).get("tokens", decode_tokens),
        "decode_ms": (timings or {}).get("predicted_ms"),
        "decode_tok_s": round((timings or {}).get("predicted_per_second", 0), 2),
        "draft_n": (timings or {}).get("draft_n"),
        "draft_n_accepted": (timings or {}).get("draft_n_accepted"),
        "cycles": cycles,
        "acceptance_rate": (
            speculation["accepted_draft_tokens"] / speculation["drafted_tokens"]
            if speculation.get("drafted_tokens")
            else None
        ),
        "tokens_per_cycle": (
            decode_tokens / cycles if cycles else None
        ),
        "cache_status": cache_metrics.get("status"),
        "matched_tokens": cache_metrics.get("matched_tokens"),
        "finish_reason": finish_reason,
        "complete_sse": complete,
        "memory_pressure_before": before["memory_pressure"],
        "memory_pressure_after": after["memory_pressure"],
        "thermal_state_before": before["thermal_state"],
        "thermal_states_during": sorted({s["thermal_state"] for s in samples}),
        "thermal_state_after": after["thermal_state"],
        "metal_peak_gib_before": before["metal_peak_gib"],
        "metal_peak_gib_after": after["metal_peak_gib"],
        "metal_peak_gib_during": max((s["metal_peak_gib"] for s in samples), default=0),
        "host_available_bytes_before": before["host_available_bytes"],
        "host_headroom_bytes_before": before["host_headroom_bytes"],
        "growth_allowed_before": before["growth_allowed"],
        "kv_pages_free_before": before["kv_pages_free"],
        "kv_pages_cache_before": before["kv_pages_cache"],
        "disk_used_bytes_before": before["disk_used_bytes"],
        "text": text[:220],
        "usage": usage,
        "timings": timings,
        "metrics": metrics,
        "status_before": before,
        "status_after": after,
    }
    (out / f"{name}.json").write_text(json.dumps(record, indent=2))
    print(
        f"[{name}] prompt={record['prompt_tokens']} cached={record['cached_tokens']} "
        f"prefill={record['prefill_tok_s']} tok/s ttft={record['sse_ttft_seconds']}s "
        f"decode={record['decode_tok_s']} tok/s cycles={cycles} "
        f"thermal={before['thermal_state']}->{after['thermal_state']} "
        f"foreign={foreign}"
    )
    return record


def gate_ok(row: dict) -> bool:
    text = row["text"]
    return text.startswith("ORCHID") and "1, 2, 3, 4, 5, 6, 7, 8, 9, 10" in text


def run_trial(out: Path, trial: int, reversed_order: bool) -> list[dict]:
    tag = f"trial{trial}"
    trial_dir = out / tag
    trial_dir.mkdir(parents=True, exist_ok=True)

    def probe(name: str, prompt: str, max_tokens: int) -> dict:
        record = run_probe(trial_dir, name, prompt, max_tokens, tag)
        (trial_dir / f"{name}.json").write_text(json.dumps(record, indent=2))
        return record

    rows: list[dict] = []

    smoke_prompt = build_prompt(uuid.uuid4().hex[:8], 351)
    print(f"trial {trial}: smoke prompt tokens={tokenize(smoke_prompt)}")
    smoke_cold = probe("smoke-cold", smoke_prompt, 96)
    smoke_reuse = probe("smoke-reuse", smoke_prompt, 96)
    smoke_cold["correct"] = gate_ok(smoke_cold)
    smoke_reuse["correct"] = gate_ok(smoke_reuse)
    if not smoke_cold["correct"] or not smoke_reuse["correct"]:
        raise SystemExit(f"trial {trial}: smoke correctness gate failed")
    if (smoke_reuse["cached_tokens"] or 0) < 320:
        raise SystemExit(f"trial {trial}: smoke reuse gate failed cached={smoke_reuse['cached_tokens']}")

    prompt_4k = build_prompt(uuid.uuid4().hex[:8], 4019)
    print(f"trial {trial}: 4k prompt tokens={tokenize(prompt_4k)}")
    cold = probe("4k-cold", prompt_4k, 96)
    reuse = probe("4k-reuse", prompt_4k, 96)
    cold["correct"] = gate_ok(cold)
    reuse["correct"] = gate_ok(reuse)
    if (reuse["cached_tokens"] or 0) < 3900:
        print(f"trial {trial}: WARNING 4k reuse cached={reuse['cached_tokens']}")

    code_rows = []
    order = [3, 2, 1] if reversed_order else [1, 2, 3]
    for index in order:
        code_rows.append(probe(f"code-{index}", CODE_PROMPTS[index - 1], 128))

    rows = [smoke_cold, smoke_reuse, cold, reuse] + code_rows
    (trial_dir / "matrix-results.json").write_text(json.dumps({"rows": rows}, indent=2))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--trials", type=int, default=2)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    instance = http_json("GET", "/status")["instance"]
    preflight = status_snapshot()
    (out / "preflight.json").write_text(json.dumps({"instance": instance, "status": preflight}, indent=2))
    print(
        f"server pid={instance['pid']} model={instance['model']} build={instance.get('build_id')} "
        f"pressure={preflight['memory_pressure']} thermal={preflight['thermal_state']} "
        f"metal={preflight['metal_allocated_gib']}/{preflight['metal_peak_gib']} GiB "
        f"host_available={preflight['host_available_bytes']} kv_free={preflight['kv_pages_free']} "
        f"disk_used={preflight['disk_used_bytes']}"
    )

    all_rows: list[dict] = []
    per_trial: dict[str, list[dict]] = {}
    for trial in range(1, args.trials + 1):
        rows = run_trial(out, trial, reversed_order=(trial % 2 == 0))
        per_trial[f"trial{trial}"] = rows
        for row in rows:
            labelled = dict(row)
            labelled["trial"] = trial
            labelled["name"] = row["name"]
            all_rows.append(labelled)

    summary = {
        "complete": True,
        "phase": "option20-live-performance-two-trial",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "server": instance,
        "preflight": preflight,
        "trials": args.trials,
        "rows": all_rows,
    }
    (out / "matrix-results.json").write_text(json.dumps(summary, indent=2))

    def fmt(rows: list[dict]) -> list[str]:
        lines = [
            "| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in rows:
            acc = row["acceptance_rate"]
            lines.append(
                f"| {row['name']} | {row['prompt_tokens']} | {row['prefill_tok_s']} | "
                f"{row['sse_ttft_seconds']} | {row['decode_tok_s']} | {row['cycles']} | "
                f"{round(row['tokens_per_cycle'], 3) if row['tokens_per_cycle'] else ''} | "
                f"{row['cached_tokens']} | "
                f"{row['draft_n_accepted']}/{row['draft_n']}"
                f"{f' ({acc * 100:.1f}%)' if acc is not None else ''} |"
            )
        code_rows = [r for r in rows if r["name"].startswith("code-")]
        if code_rows:
            values = [r["decode_tok_s"] for r in code_rows]
            lines.append("")
            lines.append(
                f"coding decode mean {statistics.mean(values):.2f} tok/s "
                f"(range {min(values):.2f}-{max(values):.2f})"
            )
            prefill_values = [r["prefill_tok_s"] for r in rows if r["name"].startswith("4k-cold")]
            if prefill_values:
                lines.append(f"4k cold prefill mean {statistics.mean(prefill_values):.2f} tok/s")
        drafted = sum(r["draft_n"] or 0 for r in rows)
        accepted = sum(r["draft_n_accepted"] or 0 for r in rows)
        if drafted:
            lines.append(f"draft acceptance {accepted}/{drafted} ({accepted / drafted * 100:.1f}%)")
        foreign = sum(r["foreign_active_samples"] for r in rows)
        lines.append(f"foreign active samples during probes: {foreign}")
        thermals = sorted({r["thermal_state_after"] for r in rows})
        lines.append(f"thermal states after probes: {', '.join(thermals)}")
        return lines

    lines = []
    for label, rows in per_trial.items():
        lines.append(f"## {label}")
        lines.extend(fmt(rows))
        lines.append("")
    lines.append("## pooled")
    lines.extend(fmt(all_rows))
    (out / "matrix.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
