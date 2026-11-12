#!/usr/bin/env python3
"""Option 20 serving-path performance matrix against a live Splash server.

Profile under test: option 20 in startllamacpp.sh,
`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-XXS` served by Splash on 127.0.0.1:1235
(131,072 context, 2,048-token prefill chunks, INT8 KV, BF16 state, DFlash2
draft, 10.8 GiB Metal cap on a 16 GiB host).

Why this file exists: earlier option 20 runs used throwaway scripts under
/private/tmp, with prompt texts and token counts that drifted between runs
(351/4,019/33-32-36 tokens on 2026-11-06 versus 386/4,066/47-40-38 on
2026-11-08). Drift makes a regression indistinguishable from a probe change.
This harness pins prompt token counts, records `/status` counter deltas per
probe, declares the cache state of the server it measures, and keeps two
trials with reversed coding order.

Method (same shape as the 2026-11-06 telemetry runs):
  * per trial: smoke cold/reuse pair with a correctness gate and a cache-hit
    gate, 4K cold/reuse pair, three 128-token coding probes whose generated
    code is executed against asserts
  * trial 1 natural order, trial 2 reversed coding order
  * fresh prompt salt per trial so every "cold" probe is genuinely cold
  * every probe waits for an idle server, samples /status during the request,
    and stores before/after snapshots plus their deltas
  * probes are dropped as `clean: false` when another request overlaps them or
    when completion/capacity counters move unexpectedly

Usage:
  .venv/bin/python dev/benchmarks/option20_serving_matrix.py
  .venv/bin/python dev/benchmarks/option20_serving_matrix.py --group coding
  .venv/bin/python dev/benchmarks/option20_serving_matrix.py --thermal-gate nominal
  .venv/bin/python dev/benchmarks/option20_serving_matrix.py --out /private/tmp/run --trials 1
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

DEFAULT_BASE = "http://127.0.0.1:1235"
DEFAULT_MODEL = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS"

# Prompt text shapes copied from the 2026-11-06 runs so token counts match.
SMOKE_HEAD = "The secret code is ORCHID.\n"
SMOKE_TAIL = (
    "\nReturn the secret code, then list the integers from 1 through 30 in "
    "order. No explanation."
)
FILLER_LINE = "Background note: trees have leaves.\n"
# The filler line costs eight tokens per repeat, so exact parity sometimes needs
# a short word pad. Salt text tokenizes differently run to run.
PAD_WORDS = (
    "zero one two three four five six seven eight nine ten alpha bravo charlie "
    "delta echo foxtrot golf hotel india juliet".split()
)

# Pinned prompt token counts, measured with /tokenize on the served model.
# The smoke and 4K shapes are sized exactly with a word pad; the coding prompts
# are worded to land on these values, matching the counts recorded in the
# 2026-11-06 raw runs (351 / 4,019 / 33-32-36). build_prompt hard-fails if any
# prompt drifts beyond PROMPT_TOLERANCE, and each probe also records the
# server-side prompt_n so chat-template overhead stays visible.
PROMPT_TARGETS = {
    "smoke": 351,
    "4k": 4019,
    "code-1": 33,
    "code-2": 32,
    "code-3": 36,
}
PROMPT_TOLERANCE = 2

# The 2026-11-06 runs capped coding probes at 128 tokens, which truncates the
# generated function mid-body. 192 lets these three tasks finish naturally
# (measured 138-141 output tokens, finish_reason "stop") so the asserts below
# are a real correctness gate. Cycles therefore are compared only inside this
# harness; tokens_per_cycle is the cross-run metric.
CODE_MAX_TOKENS = 192
SMOKE_MAX_TOKENS = 96

# Prompt-processing groups. PREFILL_SIZES sweeps dense prefill and prefix reuse
# across prompt sizes; the turn ladder replays the shape a tool loop pays for.
PREFILL_SIZES = [1024, 2048, 4096, 8192, 16384]
PREFILL_MAX_TOKENS = 8
# A tool loop grows the prompt by roughly one tool block per turn, so eight
# turns at 400 tokens each lands near nine thousand prompt tokens.
LADDER_TURNS = 8
LADDER_STEP = 400
LADDER_MAX_TOKENS = 32
LADDER_SYSTEM = (
    "You are a coding agent working in a repository. Read the files you are "
    "given, change the smallest thing that fixes the failure, and report it."
)
LADDER_REPLY = "Applied the change and ran the focused test; it passes."


def ladder_turn_block(turn: int, step: int) -> str:
    """One agent turn: a diff-ish block of about `step * (turn + 1)` tokens."""
    lines = [f"Turn {turn + 1} tool output, cache tier trace segment {turn + 1}:"]
    for index in range(step // 8 + 1):
        lines.append(
            f"page {index:04d} lane {turn % 2} restore {index * 131 % 977} ms "
            f"state {index % 3} quota {index % 7}"
        )
    return "\n".join(lines)


def ladder_tool_block(turn: int, step: int) -> str:
    """The tool result the agent sees after its reply, growing the prefix further."""
    lines = [f"test run {turn + 1}:"]
    for index in range(step // 12 + 1):
        lines.append(
            f"test_cache_tier_{index:03d} ok in {index * 7 % 421} ms "
            f"restored {index % 9} pages"
        )
    return "\n".join(lines)

# Coding prompts copied from the 2026-11-06 harness: terse, no docstrings, so
# a 128-token cap still fits one complete function.
# Coding prompts ask for code only, with no docstrings or annotations, so the
# 128-token cap fits one complete function and the asserts below are a real
# correctness gate instead of tripping over a truncated docstring. Token counts
# match the 2026-11-06 raw runs (33 / 32 / 36) for the same three tasks.
CODE_TASKS = {
    "code-1": (
        "Write only Python code. Define merge_sorted_lists(list1, list2) that "
        "merges two sorted lists into a single sorted list without calling sort. "
        "No docstring.",
        "assert merge_sorted_lists([],[])==[]\n"
        "assert merge_sorted_lists([1,3,3],[2,3,8])==[1,2,3,3,3,8]\n"
        "assert merge_sorted_lists([],[-2,0])==[-2,0]\n"
        "assert merge_sorted_lists([1,2],[])==[1,2]",
    ),
    "code-2": (
        "Write only Python code, no docstrings or annotations. Define "
        "is_balanced(text) that returns whether parentheses, brackets, and braces "
        "in a string are balanced.",
        "assert is_balanced('')\nassert is_balanced('a{b[c(d)]}')\n"
        "assert not is_balanced('([)]')\nassert not is_balanced('(')\n"
        "assert not is_balanced(']')\nassert is_balanced('abc')",
    ),
    "code-3": (
        "Write only Python code, no docstrings or annotations. Define "
        "longest_common_prefix(strs) that returns the longest prefix shared by "
        "every string in the list, or an empty string.",
        "assert longest_common_prefix(['flower','flow','flight'])=='fl'\n"
        "assert longest_common_prefix(['dog','rat','cat'])==''\n"
        "assert longest_common_prefix([])==''\n"
        "assert longest_common_prefix(['a'])=='a'",
    ),
}

# Flat /status fields collected before, during, and after every probe. The
# per-probe record stores the raw snapshots plus the delta of every numeric
# field, which is what makes a run comparable across builds and cache states.
COUNTER_FIELDS = {
    "requests_completed": ("requests", "completed"),
    "requests_failed": ("requests", "failed"),
    "requests_cancelled": ("requests", "cancelled"),
    "prefill_input_tokens": ("metrics", "prefill_input_tokens"),
    "prefill_wall_ms": ("metrics", "prefill_wall_ms"),
    "decode_output_tokens": ("metrics", "decode_output_tokens"),
    "decode_wall_ms": ("metrics", "decode_wall_ms"),
    "decode_cycle_ms": ("metrics", "decode_cycle_ms"),
    "drafted_tokens": ("metrics", "drafted_tokens"),
    "accepted_draft_tokens": ("metrics", "accepted_draft_tokens"),
    "capacity_failures": ("metrics", "capacity_failures"),
    "metal_failures": ("metrics", "metal_failures"),
    "prefill_batches": ("scheduler", "prefill_batches"),
    "prefill_rows": ("scheduler", "prefill_rows"),
    "decode_batches": ("scheduler", "decode_batches"),
    "table_evictions": ("streamed_table", "evictions"),
    "table_prefill_requested": ("streamed_table", "prefill", "requested_rows"),
    "table_prefill_read": ("streamed_table", "prefill", "read_rows"),
    "table_prefill_stage_ms": ("streamed_table", "prefill", "stage_ms", "total"),
    "table_prefill_samples": ("streamed_table", "prefill", "samples"),
    "table_decode_requested": ("streamed_table", "decode", "requested_rows"),
    "table_decode_read": ("streamed_table", "decode", "read_rows"),
    "table_decode_stage_ms": ("streamed_table", "decode", "stage_ms", "total"),
    "table_decode_samples": ("streamed_table", "decode", "samples"),
    "experts_decode_loads": ("streamed_experts", "decode", "loads"),
    "experts_decode_routed": ("streamed_experts", "decode", "routed"),
    "experts_decode_read": ("streamed_experts", "decode", "read"),
    "experts_decode_read_bytes": ("streamed_experts", "decode", "read_bytes"),
    "experts_decode_ahead_read_bytes": (
        "streamed_experts", "decode", "ahead_read_bytes"),
    "experts_decode_ahead_used_bytes": (
        "streamed_experts", "decode", "ahead_used_bytes"),
    "experts_prefill_read_bytes": ("streamed_experts", "prefill", "read_bytes"),
    "experts_prefill_ahead_read_bytes": (
        "streamed_experts", "prefill", "ahead_read_bytes"),
    "experts_prefill_ahead_used_bytes": (
        "streamed_experts", "prefill", "ahead_used_bytes"),
    "kv_pages_allocated": ("kv", "pages_allocated"),
    "kv_pages_active": ("kv", "pages_active"),
    "kv_pages_cache": ("kv", "pages_cache"),
    "kv_pages_free": ("kv", "pages_free"),
    "kv_allocated_bytes": ("kv", "allocated_bytes"),
    "kv_extent_allocations": ("kv", "extent_allocations"),
    "kv_extent_releases": ("kv", "extent_releases"),
    "kv_extent_compactions": ("kv", "extent_compactions"),
    "kv_pages_moved": ("kv", "pages_moved"),
    "spill_whole_pages": ("kv_spill", "restores", "whole_pages"),
    "spill_partial_pages": ("kv_spill", "restores", "partial_pages"),
    "spill_restore_ms": ("kv_spill", "restores", "ms", "total"),
    "spill_requests": ("kv_spill", "requests", "spill"),
    "spill_pages": ("kv_spill", "pages", "spilled"),
    "spill_write_through_pages": ("kv_spill", "write_through", "pages"),
    "disk_used_bytes": ("disk", "used_bytes"),
    "disk_kv_blocks": ("disk", "kv_blocks"),
    "disk_kv_bytes": ("disk", "kv_bytes"),
    "disk_state_blocks": ("disk", "state_blocks"),
    "disk_state_bytes": ("disk", "state_bytes"),
    "disk_kv_demotions": ("disk", "kv_demotions"),
    "disk_kv_restores": ("disk", "kv_restores"),
    "disk_read_bytes": ("disk", "read_bytes"),
    "disk_written_bytes": ("disk", "written_bytes"),
    "disk_taken_back_states": ("disk", "taken_back", "states"),
    "disk_taken_back_kv_blocks": ("disk", "taken_back", "kv_blocks"),
    "disk_taken_back_bytes": ("disk", "taken_back", "bytes"),
    "disk_writes_deferred_ms": ("disk", "writes_deferred_ms"),
    "cache_hits": ("cache", "hits"),
    "cache_cold_misses": ("cache", "cold_misses"),
    "cache_kv_hit_tokens": ("cache", "kv_hit_tokens"),
    "cache_kv_disk_hit_tokens": ("cache", "kv_disk_hit_tokens"),
    "cache_reused_tokens": ("cache", "reused_tokens"),
    "cache_state_captures": ("cache", "state_captures"),
    "cache_disk_state_publications": ("cache", "disk_state_publications"),
    "cache_replay_state_publications": ("cache", "replay_state_publications"),
    "cache_checkpoint_publications": ("cache", "checkpoint_publications"),
    "cache_capture_cuts": ("cache", "capture_cuts"),
    "cache_lost_state_misses": ("cache", "lost_state_misses"),
    "cache_probe_hashed_blocks": ("cache", "probe_hashed_blocks"),
    "state_entries": ("state", "entries"),
    "state_evictions": ("state", "evictions"),
    "state_offloads": ("state", "offloads"),
    "state_disk_hits": ("state", "disk_hits"),
    "state_disk_promotions": ("state", "disk_promotions"),
    "governor_denied_reservations": ("memory_governor", "denied_reservations"),
    "metal_allocated_bytes": ("memory_actual", "allocated_bytes"),
    "metal_peak_bytes": ("memory_actual", "peak_bytes"),
}

# Non-counter fields that describe what the server is configured to do.
def profile_of_record(status: dict) -> dict:
    plan = status.get("memory_plan", {})
    model = plan.get("model", {})
    governor = status.get("memory_governor", {})
    disk = status.get("disk", {})
    table = status.get("streamed_table", {})
    experts = status.get("streamed_experts", {})
    identity = status.get("identity", {})
    return {
        "instance": status.get("instance"),
        "build_id": identity.get("cache", {}).get("build_id"),
        "loaded_model_layout_sha256": identity.get("cache", {}).get(
            "loaded_model_layout_sha256"),
        "target_model_sha256": identity.get("kv", {}).get("target_model_sha256"),
        "maximum_context_tokens": status.get("maximum_context_tokens"),
        "prefill_chunk_tokens": plan.get("prefill_chunk_tokens"),
        "verify_rows": status.get("verify_rows"),
        "model_bytes": model.get("model_bytes"),
        "kv_page_bytes": model.get("kv_page_bytes"),
        "kv_page_tokens": model.get("kv_page_tokens"),
        "kv_format": model.get("kv_format"),
        "kv_quantization": model.get("kv_quantization"),
        "state_format": model.get("state_format"),
        "model_state_bytes_per_token": model.get("model_state_bytes_per_token"),
        "governor_limit_bytes": governor.get("limit_bytes"),
        "governor_host_spare_reserve_bytes": governor.get("host_spare_reserve_bytes"),
        "disk_capacity_bytes": disk.get("capacity_bytes"),
        "disk_limit_bytes": disk.get("limit_bytes"),
        "disk_persistent": disk.get("persistent"),
        "table_cache_bytes": table.get("cache_bytes"),
        "table_cache_capacity_rows": table.get("cache_capacity_rows"),
        "expert_cap_bytes": experts.get("cap_bytes"),
        "expert_floor_bytes": experts.get("floor_bytes"),
        "expert_slot_count": experts.get("slot_count"),
        "expert_count": experts.get("expert_count"),
        "env": {k: v for k, v in sorted(__import__("os").environ.items())
                if k.startswith("SPLASH_")},
    }


def deep_get(status: dict, *keys):
    node = status
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def counters(status: dict) -> dict:
    out = {}
    for name, path in COUNTER_FIELDS.items():
        value = deep_get(status, *path)
        out[name] = value if isinstance(value, (int, float)) else 0
    out["decode_batches_by_width"] = deep_get(status, "scheduler", "decode_batches_by_width")
    return out


def scalar_state(status: dict) -> dict:
    return {
        "ready": status.get("ready"),
        "memory_pressure": status.get("memory_pressure"),
        "thermal_state": status.get("thermal_state"),
        "system_pressure": deep_get(status, "memory_governor", "system_pressure"),
        "active_requests": len(status.get("active_requests") or []),
        "waiting": deep_get(status, "admission", "waiting"),
        "waiting_memory": deep_get(status, "admission", "waiting_memory"),
        "suspended": deep_get(status, "admission", "suspended"),
        "kv_pages_free": deep_get(status, "kv", "pages_free"),
        "kv_pages_cache": deep_get(status, "kv", "pages_cache"),
        "disk_used_bytes": deep_get(status, "disk", "used_bytes"),
        "host_available_bytes": deep_get(status, "memory_governor", "host_available_bytes"),
        "host_headroom_bytes": deep_get(status, "memory_governor", "host_headroom_bytes"),
        "growth_allowed": deep_get(status, "memory_governor", "growth_allowed"),
        "metal_allocated_bytes": deep_get(status, "memory_actual", "allocated_bytes"),
        "metal_peak_bytes": deep_get(status, "memory_actual", "peak_bytes"),
    }


class Client:
    def __init__(self, base: str, model: str):
        self.base = base.rstrip("/")
        self.model = model

    def json(self, method: str, path: str, payload=None, timeout: float = 10.0):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())

    def status(self) -> dict:
        return self.json("GET", "/status", timeout=10)

    def tokenize(self, text: str) -> int:
        return len(self.json("POST", "/tokenize", {"content": text})["tokens"])


def build_prompt(client: Client, kind: str, salt: str) -> tuple[str, int]:
    """Build a probe prompt whose token count lands on the pinned target.

    Pinned kinds come from PROMPT_TARGETS. A kind of the form "pre-8192" pins the
    target to that token count instead, which is how the prefill scaling group
    measures 1K, 2K, 4K, 8K and 16K prompts on the same sizing rule.
    """
    target = PROMPT_TARGETS.get(kind)
    if target is None and kind.startswith("pre-"):
        target = int(kind[len("pre-"):])
    if target is None:
        raise SystemExit(f"unknown prompt kind {kind}")
    if kind in ("smoke", "4k") or kind.startswith("pre-"):
        head = SMOKE_HEAD + f"Benchmark salt: {salt}\n"

        def sized(pad_count: int, repeat: int) -> tuple[int, str]:
            pad = f"Pad: {' '.join(PAD_WORDS[:pad_count])}\n" if pad_count else ""
            candidate = head + FILLER_LINE * repeat + pad + SMOKE_TAIL
            return client.tokenize(candidate), candidate

        fixed = client.tokenize(head + SMOKE_TAIL)
        center = max(1, round((target - fixed) / 8))
        # One filler line is eight tokens and the first pad word costs four (the
        # "Pad:" label), then one each. So for any repeat within one line of the
        # estimate, the needed pad count is target - tokens - 3.
        exact = None
        for repeat in (center - 1, center, center + 1):
            if repeat < 1:
                continue
            base_tokens, base_prompt = sized(0, repeat)
            deficit = target - base_tokens
            for pad_count in {0, deficit - 3, deficit - 2, deficit - 4} & set(range(0, len(PAD_WORDS) + 1)):
                tokens, candidate = sized(pad_count, repeat)
                if tokens == target:
                    exact = (tokens, candidate)
                    break
            if exact:
                break
        if exact is None:
            raise SystemExit(
                f"{kind}: could not size a prompt to exactly {target} tokens; "
                f"nearest repeats around {center} do not close the gap"
            )
        actual, prompt = exact
    else:
        prompt = CODE_TASKS[kind][0]
        actual = client.tokenize(prompt)
    if abs(actual - target) > PROMPT_TOLERANCE:
        raise SystemExit(
            f"{kind}: prompt token count {actual} drifted more than "
            f"{PROMPT_TOLERANCE} from the pinned target {target}; adjust the "
            "prompt text rather than comparing across token counts"
        )
    return prompt, actual


def wait_quiet(client: Client, limit: float, thermal_gate: str | None) -> dict:
    """Wait until no other request is active and, when asked, the Mac is nominal."""
    started = time.monotonic()
    quiet_streak = 0
    thermal_streak = 0
    blocked_samples = 0
    thermals: list[str] = []
    while time.monotonic() - started < limit:
        status = client.status()
        state = scalar_state(status)
        thermals.append(state["thermal_state"])
        busy = state["active_requests"] or state["waiting"] or state["suspended"]
        if busy:
            quiet_streak = 0
            blocked_samples += 1
        else:
            quiet_streak += 1
        thermal_ok = thermal_gate is None or state["thermal_state"] == thermal_gate
        thermal_streak = thermal_streak + 1 if thermal_ok else 0
        if quiet_streak >= 3 and thermal_streak >= 3:
            return {
                "idle_wait_seconds": round(time.monotonic() - started, 3),
                "started_blocked": blocked_samples > 0,
                "foreign_active_samples": blocked_samples,
                "thermal_state_before": state["thermal_state"],
                "thermal_gate": thermal_gate,
            }
        time.sleep(0.5)
    raise SystemExit(
        f"server did not become quiet within {limit}s "
        f"(gate={thermal_gate}, last thermals={thermals[-5:]})"
    )


def run_code_check(name: str, prompt: str, text: str) -> dict:
    """Execute the generated function against asserts."""

    # A missing closing fence happens when the cap truncates the block.
    asserts = CODE_TASKS[name][1]
    blocks = re.findall(r"```(?:python)?[ \t]*\n(.*?)```", text, re.S)
    if blocks:
        code = blocks[0]
    elif "```" in text:
        tail = text.split("```", 1)[1]
        tail = re.sub(r"^python[ \t]*\n", "", tail)
        code = tail.split("```", 1)[0]
    else:
        code = text
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code + "\n" + asserts + "\n")
        path = handle.name
    try:
        run = subprocess.run(
            [sys.executable, "-I", path], capture_output=True, text=True, timeout=10)
        result = {
            "correct": run.returncode == 0,
            "returncode": run.returncode,
            "diagnostic": (run.stderr or run.stdout)[-400:],
        }
    except subprocess.TimeoutExpired:
        result = {"correct": False, "returncode": None, "diagnostic": "timeout"}
    finally:
        Path(path).unlink(missing_ok=True)
    return result


def smoke_gate_ok(text: str) -> bool:
    """Require the secret code first, then integers counting up from 1 with no skips.

    The 96-token cap can cut the list near 25 or 30, so the gate checks that the
    visible list is correct and reaches at least 20 rather than demanding 30.
    """
    if "ORCHID" not in text.split("\n", 1)[0]:
        return False
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    # The token cap can cut a number in half ("...24, 25, 2"), so score the
    # longest prefix that counts up from 1 instead of the whole token stream.
    counted = 0
    for expected, actual in enumerate(numbers, start=1):
        if actual != expected:
            break
        counted = expected
    return counted >= 20


def run_probe(client: Client, out: Path, name: str, prompt: str, max_tokens: int,
              phase: str, thermal_gate: str | None,
              messages: list[dict] | None = None) -> dict:
    gate = wait_quiet(client, 900.0, thermal_gate)
    before_status = client.status()
    before = counters(before_status)
    before_state = scalar_state(before_status)
    time.sleep(2.0)  # fixed cooldown so a probe never overlaps the previous cache write

    body = {
        "model": client.model,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": messages or [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        client.base + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )

    samples: list[dict] = []
    next_sample = time.monotonic()

    def sample():
        status = client.status()
        samples.append(scalar_state(status))

    with urllib.request.urlopen(request, timeout=1800) as response:
        parts: list[str] = []
        timings: dict = {}
        usage: dict = {}
        metrics: dict = {}
        finish_reason = None
        complete = False
        started = time.monotonic()
        first_token_at = None
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                complete = True
                break
            chunk = json.loads(payload)
            if first_token_at is None and chunk.get("choices"):
                delta = chunk["choices"][0].get("delta") or {}
                if delta.get("content"):
                    first_token_at = time.monotonic() - started
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    parts.append(delta["content"])
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
            timings.update(chunk.get("timings") or {})
            usage.update(chunk.get("usage") or {})
            metrics.update(chunk.get("metrics") or {})
            now = time.monotonic()
            if now >= next_sample:
                sample()
                next_sample = now + 0.5
        wall = time.monotonic() - started

    time.sleep(5.0)  # cooldown between probes so cache writes land before the next read
    after_status = client.status()
    after = counters(after_status)
    after_state = scalar_state(after_status)

    delta = {k: after[k] - before[k] for k in COUNTER_FIELDS}
    speculation = (metrics or {}).get("speculation", {})
    latency = (metrics or {}).get("request_latency", {})
    cache_metrics = (metrics or {}).get("cache", {})
    decode_tokens = (metrics or {}).get("decode", {}).get(
        "tokens", (timings or {}).get("predicted_n") or (usage or {}).get("completion_tokens", 0))
    prefill_tokens = (metrics or {}).get("prefill", {}).get(
        "tokens", (timings or {}).get("prompt_n"))
    cycles = speculation.get("cycles") or delta["decode_batches"]
    decode_wall_ms = delta["decode_wall_ms"]
    decode_tps = (
        delta["decode_output_tokens"] * 1000 / decode_wall_ms
        if decode_wall_ms > 0 else None
    )
    completion = (usage or {}).get("completion_tokens", decode_tokens)
    drafted = delta["drafted_tokens"]
    accepted = delta["accepted_draft_tokens"]

    contended = sum(1 for s in samples if s["active_requests"] > 1 or s["waiting"] or s["suspended"])
    record = {
        "name": name,
        "phase": phase,
        "prompt": prompt if len(prompt) < 2000 else prompt[:2000] + "...",
        "message_turns": len(messages) if messages else 1,
        "prompt_tokens": (timings or {}).get("prompt_n"),
        "content_tokens_pinned": client.tokenize(prompt),
        "completion_tokens": completion,
        "cached_tokens": (timings or {}).get("cache_n"),
        "max_tokens": max_tokens,
        "clean": (
            not gate["started_blocked"]
            and gate["foreign_active_samples"] == 0
            and contended == 0
            and delta["requests_completed"] == 1
            and delta["requests_failed"] == 0
            and delta["capacity_failures"] == 0
            and delta["metal_failures"] == 0
            and complete
        ),
        "finish_reason": finish_reason,
        "complete_sse": complete,
        "idle_wait_seconds": gate["idle_wait_seconds"],
        "started_blocked": gate["started_blocked"],
        "foreign_active_samples": gate["foreign_active_samples"],
        "contended_samples": contended,
        "status_samples": len(samples),
        "wall_seconds": round(wall, 3),
        "sse_ttft_seconds": round(first_token_at, 3) if first_token_at is not None else None,
        "ttft_ms": latency.get("ttft_ms"),
        "queue_to_start_ms": latency.get("queue_to_start_ms"),
        "prefill_ms": (timings or {}).get("prompt_ms"),
        "prefill_tokens": prefill_tokens,
        "prefill_tok_s": round((timings or {}).get("prompt_per_second") or 0, 2),
        "decode_tokens": decode_tokens,
        "decode_ms": (timings or {}).get("predicted_ms"),
        "decode_tok_s": round((timings or {}).get("predicted_per_second") or 0, 2),
        "decode_tok_s_from_counters": round(decode_tps, 2) if decode_tps else None,
        "cycles": cycles,
        "tokens_per_cycle": round(decode_tokens / cycles, 3) if cycles else None,
        "cycle_ms_from_counters": (
            round(delta["decode_cycle_ms"] / cycles, 2) if cycles else None),
        "draft_n": (timings or {}).get("draft_n"),
        "draft_n_accepted": (timings or {}).get("draft_n_accepted"),
        "drafted_delta": drafted,
        "accepted_delta": accepted,
        "acceptance_rate": round(accepted / drafted, 4) if drafted else None,
        "expert_read_bytes_per_output_token": (
            round(delta["experts_decode_read_bytes"] / decode_tokens, 1)
            if decode_tokens and delta["experts_decode_read_bytes"] else None),
        "expert_ahead_used_over_read_prefill": (
            round(delta["experts_prefill_ahead_used_bytes"]
                  / delta["experts_prefill_ahead_read_bytes"], 3)
            if delta["experts_prefill_ahead_read_bytes"] else None),
        "expert_ahead_used_over_read_decode": (
            round(delta["experts_decode_ahead_used_bytes"]
                  / delta["experts_decode_ahead_read_bytes"], 3)
            if delta["experts_decode_ahead_read_bytes"] else None),
        "table_prefill_stage_ms_mean": (
            round(delta["table_prefill_stage_ms"] / delta["table_prefill_samples"], 2)
            if delta["table_prefill_samples"] else None),
        "table_decode_stage_ms_mean": (
            round(delta["table_decode_stage_ms"] / delta["table_decode_samples"], 2)
            if decode_tokens and delta["table_decode_samples"] else None),
        "cache_status": cache_metrics.get("status"),
        "matched_tokens": cache_metrics.get("matched_tokens"),
        "spill_whole_pages_delta": delta["spill_whole_pages"],
        "spill_restore_ms_delta": delta["spill_restore_ms"],
        "disk_kv_demotions_delta": delta["disk_kv_demotions"],
        "disk_taken_back_kv_blocks_delta": delta["disk_taken_back_kv_blocks"],
        "cache_kv_disk_hit_tokens_delta": delta["cache_kv_disk_hit_tokens"],
        "kv_pages_free_before": before_state["kv_pages_free"],
        "kv_pages_cache_before": before_state["kv_pages_cache"],
        "disk_used_bytes_before": before_state["disk_used_bytes"],
        "host_available_bytes_before": before_state["host_available_bytes"],
        "host_headroom_bytes_before": before_state["host_headroom_bytes"],
        "growth_allowed_before": before_state["growth_allowed"],
        "metal_peak_bytes_before": before["metal_peak_bytes"],
        "metal_peak_bytes_after": after["metal_peak_bytes"],
        "metal_peak_bytes_during": max(
            (s["metal_peak_bytes"] or 0 for s in samples), default=0),
        "metal_allocated_bytes_during_max": max(
            (s["metal_allocated_bytes"] or 0 for s in samples), default=0),
        "memory_pressure_before": before_state["memory_pressure"],
        "memory_pressure_after": after_state["memory_pressure"],
        "thermal_state_before": gate["thermal_state_before"],
        "thermal_states_during": sorted({s["thermal_state"] for s in samples}),
        "thermal_state_after": after_state["thermal_state"],
        "text": "".join(parts)[:400],
        "usage": usage,
        "timings": timings,
        "metrics": metrics,
        "delta": delta,
        "status_before": before_status,
        "status_after": after_status,
    }
    if name in CODE_TASKS:
        record.update(run_code_check(name, prompt, "".join(parts)))
    elif name.startswith("pre-") or name.startswith("turn-"):
        # Prompt-processing probes generate eight or thirty-two tokens on purpose;
        # their gate is that the stream completed and produced tokens.
        record["correct"] = bool(complete) and completion > 0
    else:
        record["correct"] = smoke_gate_ok("".join(parts))
    (out / f"{name}.json").write_text(json.dumps(record, indent=2))
    print(
        f"[{phase}/{name}] prompt={record['prompt_tokens']} cached={record['cached_tokens']} "
        f"prefill={record['prefill_tok_s']} tok/s ttft={record['sse_ttft_seconds']}s "
        f"decode={record['decode_tok_s']} tok/s cycles={cycles} "
        f"tpc={record['tokens_per_cycle']} correct={record['correct']} "
        f"thermal={gate['thermal_state_before']}->{after_state['thermal_state']} "
        f"clean={record['clean']}"
    )
    return record


def run_trial(client: Client, out: Path, trial: int, groups: list[str],
              thermal_gate: str | None, prefill_sizes: list[int] | None = None,
              ladder_turns: int = 0, ladder_step: int = 1200) -> list[dict]:
    trial_dir = out / f"trial{trial}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    reversed_order = trial % 2 == 0

    if "smoke" in groups or "full" in groups:
        salt = uuid.uuid4().hex[:8]
        prompt, tokens = build_prompt(client, "smoke", salt)
        print(f"trial {trial}: smoke prompt tokens={tokens}")
        cold = run_probe(client, trial_dir, "smoke-cold", prompt, SMOKE_MAX_TOKENS, f"trial{trial}", thermal_gate)
        reuse = run_probe(client, trial_dir, "smoke-reuse", prompt, SMOKE_MAX_TOKENS, f"trial{trial}", thermal_gate)
        if not cold["correct"] or not reuse["correct"]:
            raise SystemExit(f"trial {trial}: smoke correctness gate failed")
        if (reuse["cached_tokens"] or 0) < tokens - 32:
            raise SystemExit(
                f"trial {trial}: smoke reuse gate failed cached={reuse['cached_tokens']} "
                f"of {tokens}")
        rows += [cold, reuse]

    if "4k" in groups or "full" in groups:
        salt = uuid.uuid4().hex[:8]
        prompt, tokens = build_prompt(client, "4k", salt)
        print(f"trial {trial}: 4k prompt tokens={tokens}")
        cold = run_probe(client, trial_dir, "4k-cold", prompt, SMOKE_MAX_TOKENS, f"trial{trial}", thermal_gate)
        reuse = run_probe(client, trial_dir, "4k-reuse", prompt, SMOKE_MAX_TOKENS, f"trial{trial}", thermal_gate)
        if (reuse["cached_tokens"] or 0) < tokens - 128:
            print(f"trial {trial}: WARNING 4k reuse cached={reuse['cached_tokens']} of {tokens}")
        rows += [cold, reuse]

    if "coding" in groups or "full" in groups:
        order = ["code-3", "code-2", "code-1"] if reversed_order else ["code-1", "code-2", "code-3"]
        for name in order:
            prompt, tokens = build_prompt(client, name, uuid.uuid4().hex[:8])
            row = run_probe(client, trial_dir, name, prompt, CODE_MAX_TOKENS, f"trial{trial}", thermal_gate)
            if not row["correct"]:
                raise SystemExit(
                    f"trial {trial}: {name} correctness failed: {row['diagnostic']}")
            rows.append(row)

    if "prefill" in groups:
        # Cold measures dense prefill; the identical prompt right after measures
        # what prefix reuse actually saves at the same size.
        for size in (prefill_sizes or PREFILL_SIZES):
            kind = f"pre-{size}"
            prompt, tokens = build_prompt(client, kind, uuid.uuid4().hex[:8])
            print(f"trial {trial}: prefill {size} prompt tokens={tokens}")
            cold = run_probe(client, trial_dir, f"pre-{size}-cold", prompt,
                             PREFILL_MAX_TOKENS, f"trial{trial}", thermal_gate)
            reuse = run_probe(client, trial_dir, f"pre-{size}-reuse", prompt,
                              PREFILL_MAX_TOKENS, f"trial{trial}", thermal_gate)
            rows += [cold, reuse]

    if "ladder" in groups:
        # An agent-shaped conversation: every turn appends a tool-output block of
        # ladder_step tokens, so turn n re-sends the whole prefix the way a tool
        # loop does. Replies are canned so the growth per turn is predictable.
        # A run-unique salt on the first turn, so turn 1 is genuinely cold and
        # turns 2..n are warm against it. Without a salt the ladder text is fixed
        # and a repeat run measures a prefix replayed from disk instead.
        salt = uuid.uuid4().hex[:8]
        conversation: list[dict] = [
            {"role": "system", "content": LADDER_SYSTEM},
            {"role": "user", "content": f"Fix the failing cache test in the repo. Benchmark salt: {salt}"},
        ]
        for turn in range(ladder_turns):
            block = ladder_turn_block(turn, ladder_step)
            conversation.append({"role": "user", "content": block})
            prompt = block
            row = run_probe(client, trial_dir, f"turn-{turn + 1}", prompt,
                            LADDER_MAX_TOKENS, f"trial{trial}", thermal_gate,
                            messages=list(conversation))
            row["ladder_turn"] = turn + 1
            row["ladder_step_tokens"] = ladder_step
            rows.append(row)
            conversation.append({"role": "assistant", "content": LADDER_REPLY})
            conversation.append({"role": "tool", "content": ladder_tool_block(turn, ladder_step)})

    (trial_dir / "matrix-results.json").write_text(json.dumps({"rows": rows}, indent=2))
    return rows


def summarize(rows: list[dict]) -> list[str]:
    lines = [
        "| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | "
        "Cached | Draft acc | Spill pages | Correct | Clean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        acc = row["acceptance_rate"]
        lines.append(
            f"| {row['name']} | {row['prompt_tokens']} | {row['prefill_tok_s']} | "
            f"{row['sse_ttft_seconds']} | {row['decode_tok_s']} | {row['cycles']} | "
            f"{row['tokens_per_cycle']} | {row['cached_tokens']} | "
            f"{row['draft_n_accepted']}/{row['draft_n']}"
            f"{f' ({acc * 100:.1f}%)' if acc is not None else ''} | "
            f"{row['spill_whole_pages_delta']} | {row['correct']} | {row['clean']} |"
        )
    codes = [r for r in rows if r["name"].startswith("code-")]
    if codes:
        values = [r["decode_tok_s"] for r in codes]
        tpc = [r["tokens_per_cycle"] for r in codes]
        lines.append("")
        lines.append(
            f"coding decode mean {statistics.mean(values):.2f} tok/s "
            f"(range {min(values):.2f}-{max(values):.2f}), "
            f"tokens/cycle mean {statistics.mean(tpc):.3f}")
    cold = [r["prefill_tok_s"] for r in rows if r["name"] == "4k-cold"]
    reuse = [r["sse_ttft_seconds"] for r in rows if r["name"] == "4k-reuse"]
    if cold:
        lines.append(f"4k cold prefill mean {statistics.mean(cold):.2f} tok/s")
    if reuse:
        lines.append(f"4k reuse TTFT mean {statistics.mean(reuse):.3f} s")
    prefill = [r for r in rows if r["name"].startswith("pre-")]
    if prefill:
        lines.append("")
        lines.append("Prompt processing by prompt size (cold = dense prefill, "
                     "reuse = same prompt right after):")
        sizes = sorted({int(r["name"].split("-")[1]) for r in prefill}, reverse=True)
        for size in sizes:
            cold = next((r for r in prefill if r["name"] == f"pre-{size}-cold"), None)
            reuse = next((r for r in prefill if r["name"] == f"pre-{size}-reuse"), None)
            if not cold or not reuse:
                continue
            speedup = (cold["sse_ttft_seconds"] or 0) / max(reuse["sse_ttft_seconds"] or 0, 0.001)
            lines.append(
                f"- {size}: cold prefill {cold['prefill_tok_s']} tok/s in "
                f"{cold['prefill_ms']} ms (TTFT {cold['sse_ttft_seconds']} s); reuse TTFT "
                f"{reuse['sse_ttft_seconds']} s = {speedup:.1f}x, cached "
                f"{reuse['cached_tokens']}, disk KV read-back "
                f"{reuse['cache_kv_disk_hit_tokens_delta']} tokens, spill pages "
                f"{reuse['spill_whole_pages_delta']}, kv pages free "
                f"{reuse['kv_pages_free_before']}")
    coded_ladder = [r for r in rows if r["name"].startswith("turn-")]
    if coded_ladder:
        lines.append("")
        lines.append("Turn ladder (each turn re-sends the whole conversation):")
        for row in coded_ladder:
            cached = row["cached_tokens"] or 0
            lines.append(
                f"- {row['name']}: {row['prompt_tokens']} prompt tokens, cached {cached} "
                f"({100.0 * cached / max(row['prompt_tokens'] or 1, 1):.0f}%), TTFT "
                f"{row['sse_ttft_seconds']} s, prefill {row['prefill_tok_s']} tok/s, "
                f"disk KV read-back {row['cache_kv_disk_hit_tokens_delta']} tokens, "
                f"spill pages {row['spill_whole_pages_delta']}")
    drafted = sum(r["drafted_delta"] for r in rows)
    accepted = sum(r["accepted_delta"] for r in rows)
    if drafted:
        lines.append(f"draft acceptance {accepted}/{drafted} ({accepted / drafted * 100:.1f}%)")
    lines.append(f"probes marked clean: {sum(1 for r in rows if r['clean'])}/{len(rows)}")
    lines.append(
        f"spill whole-page restores during probes: {sum(r['spill_whole_pages_delta'] for r in rows)}")
    lines.append(
        "disk KV read-back tokens during probes: "
        f"{sum(r['cache_kv_disk_hit_tokens_delta'] for r in rows)}")
    lines.append("thermal states: " + ", ".join(sorted({
        state for row in rows for state in row["thermal_states_during"]})))
    return lines


def mean(values: list) -> float:
    numbers = [float(value) for value in values if value is not None]
    return sum(numbers) / len(numbers) if numbers else 0.0


INDEX_COLUMNS = (
    "label",
    "started",
    "overrides",
    "cache_state",
    "build",
    "fourk_cold_prefill",
    "fourk_reuse_ttft",
    "coding_decode",
    "coding_tokens_per_cycle",
    "draft_accepted",
    "draft_proposed",
    "kv_disk_hit_tokens",
    "spill_pages",
    "clean_probes",
    "thermal",
    "notes",
)


def describe_extra_group(prefill_rows: list[dict], ladder_rows: list[dict]) -> str:
    """One-line description of a prompt-processing group run, for the index notes."""
    parts = []
    if prefill_rows:
        by_size: dict[int, dict[str, list[float]]] = {}
        for row in prefill_rows:
            size = int(row["name"].split("-")[1])
            bucket = by_size.setdefault(size, {"cold": [], "reuse": []})
            kind = "cold" if row["name"].endswith("-cold") else "reuse"
            bucket[kind].append(row["prefill_tok_s"] or 0.0)
        for size in sorted(by_size, reverse=True):
            cold = mean(by_size[size]["cold"])
            reuse = mean(by_size[size]["reuse"])
            parts.append(f"pre{size} {cold:.0f}/{reuse:.0f} tok/s")
    if ladder_rows:
        ttfts = [row["sse_ttft_seconds"] for row in ladder_rows if row["sse_ttft_seconds"]]
        cached = [
            100.0 * (row["cached_tokens"] or 0) / max(row["prompt_tokens"] or 1, 1)
            for row in ladder_rows
        ]
        parts.append(
            f"ladder ttft {mean(ttfts):.2f}s mean, cache {mean(cached):.0f}% mean")
    return "; ".join(parts)


def rows_of(run: Path) -> list[dict]:
    data = json.loads((run / "matrix-results.json").read_text())
    return data["rows"]


def run_summary(run: Path, label: str, overrides: str) -> dict[str, str]:
    data = json.loads((run / "matrix-results.json").read_text())
    rows = data["rows"]
    coding = [row for row in rows if row["name"].startswith("code-")]
    prefill_rows = [row for row in rows if row["name"].startswith("pre-")]
    ladder_rows = [row for row in rows if row["name"].startswith("turn-")]
    fourk_cold = [row for row in rows if row["name"] == "4k-cold"]
    fourk_reuse = [row for row in rows if row["name"] == "4k-reuse"]
    accepted = sum(row["draft_n_accepted"] or 0 for row in rows)
    proposed = sum(row["draft_n"] or 0 for row in rows)
    clean = sum(bool(row.get("clean")) for row in rows)
    states: set[str] = set()
    for row in rows:
        for key in ("thermal_state_before", "thermal_state_after"):
            if row.get(key):
                states.add(str(row[key]))
        states.update(str(state) for state in (row.get("thermal_states_during") or []))
    thermal = ",".join(sorted(states)) or "unknown"
    return {
        "label": label,
        "started": data["started_at"],
        "overrides": overrides or "-",
        "cache_state": data["cache_state"],
        "build": data["profile"]["build_id"][:12],
        "fourk_cold_prefill": f"{mean([row['prefill_tok_s'] for row in fourk_cold]):.1f}",
        "fourk_reuse_ttft": f"{mean([row['sse_ttft_seconds'] for row in fourk_reuse]):.3f}",
        "coding_decode": f"{mean([row['decode_tok_s'] for row in coding]):.2f}",
        "coding_tokens_per_cycle": f"{mean([row['tokens_per_cycle'] for row in coding]):.2f}",
        "draft_accepted": str(accepted),
        "draft_proposed": str(proposed),
        "kv_disk_hit_tokens": str(sum(row.get("cache_kv_disk_hit_tokens_delta") or 0 for row in rows)),
        "spill_pages": str(sum(row.get("spill_whole_pages_delta") or 0 for row in rows)),
        "clean_probes": f"{clean}/{len(rows)}",
        "thermal": thermal,
        "notes": describe_extra_group(prefill_rows, ladder_rows),
    }


def normalize_index(index: Path) -> None:
    """Repair an index written before a column existed, so every row is aligned."""
    lines = [line.rstrip("\n").split("\t") for line in index.read_text().splitlines() if line.strip()]
    if not lines:
        return
    header, rows = lines[0], lines[1:]
    if header == list(INDEX_COLUMNS) and all(len(row) == len(INDEX_COLUMNS) for row in rows):
        return
    rows = [list(row) + [""] * (len(INDEX_COLUMNS) - len(row)) for row in rows]
    index.write_text(
        "\n".join(["\t".join(INDEX_COLUMNS)] + ["\t".join(row[: len(INDEX_COLUMNS)]) for row in rows]) + "\n"
    )


def record_run(
    index_dir: Path, run: Path, label: str, overrides: str, note: str = ""
) -> None:
    """Append one experiment row; older rows simply have an empty notes column."""
    index_dir.mkdir(parents=True, exist_ok=True)
    index = index_dir / "index.tsv"
    if index.exists():
        normalize_index(index)
    row = run_summary(run, label, overrides)
    if note:
        row["notes"] = "; ".join(part for part in (row["notes"], note) if part)
    if not index.exists():
        index.write_text("\t".join(INDEX_COLUMNS) + "\n")
    with index.open("a", encoding="utf-8") as handle:
        handle.write("\t".join(row[column] for column in INDEX_COLUMNS) + "\n")


def compare_runs(index_dir: Path) -> None:
    index = index_dir / "index.tsv"
    if not index.exists():
        print("No recorded experiments yet.")
        return
    lines = [line.rstrip("\n").split("\t") for line in index.read_text().splitlines() if line.strip()]
    _, *rows = lines
    widths = {column: len(column) for column in INDEX_COLUMNS}
    for row in rows:
        for column, value in zip(INDEX_COLUMNS, row):
            widths[column] = max(widths[column], len(value))

    def line(values) -> str:
        return "  ".join(str(value).ljust(widths[column]) for column, value in zip(INDEX_COLUMNS, values))

    print(line(INDEX_COLUMNS))
    print(line(tuple("-" * widths[column] for column in INDEX_COLUMNS)))
    for row in rows:
        padded = list(row) + [""] * (len(INDEX_COLUMNS) - len(row))
        print(line(tuple(padded[: len(INDEX_COLUMNS)])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=Path(
        f"/private/tmp/option20-matrix-{time.strftime('%Y%m%d-%H%M%S')}"))
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--group", default="full",
                        choices=["full", "smoke", "4k", "coding", "prefill", "ladder"],
                        help="run one probe group only, e.g. --group coding for a "
                             "thermal-matched speculation repeat, --group prefill for "
                             "prompt-processing scaling, --group ladder for turn reuse")
    parser.add_argument("--sizes", default=",".join(str(s) for s in PREFILL_SIZES),
                        help="prompt token sizes for --group prefill")
    parser.add_argument("--turns", type=int, default=LADDER_TURNS,
                        help="turns in --group ladder")
    parser.add_argument("--turn-step", type=int, default=LADDER_STEP,
                        help="tokens added per turn in --group ladder")
    parser.add_argument("--thermal-gate", default=None, choices=[None, "nominal"],
                        help="require thermal_state=nominal before each probe")
    parser.add_argument("--state-label", default="auto",
                        choices=["auto", "fresh", "longlived"],
                        help="declares how much prior traffic the measured server "
                             "has served; comparison across cache states is invalid")
    parser.add_argument("--record", type=Path, default=None,
                        help="append one row to this experiment index directory")
    parser.add_argument("--compare", action="store_true",
                        help="print the recorded experiment index instead of running probes")
    parser.add_argument("--run", type=Path, default=None, help="run directory recorded with --record")
    parser.add_argument("--label", default=None, help="experiment name for --record")
    parser.add_argument("--overrides", default="", help="override list stored with --record")
    parser.add_argument("--note", default="", help="one-line context stored with --record")
    args = parser.parse_args()

    if args.compare:
        compare_runs(args.out)
        return
    if args.record:
        if not args.run:
            raise SystemExit("--record needs --run")
        label = args.label or args.run.name
        record_run(args.record, args.run, label, args.overrides, args.note)
        return

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    client = Client(args.base, args.model)

    status = client.status()
    profile = profile_of_record(status)
    preflight = {
        "status": status,
        "counters": counters(status),
        "state": scalar_state(status),
    }
    completed = profile["instance"].get("requests_completed")
    completed = completed if completed is not None else deep_get(status, "requests", "completed")
    uptime = time.time() - profile["instance"]["started_at"]
    state_label = args.state_label
    if state_label == "auto":
        state_label = "fresh" if (completed or 0) <= 3 and uptime < 1800 else "longlived"
    print(
        f"server pid={profile['instance']['pid']} model={profile['instance']['model']} "
        f"build={profile['build_id']} state={state_label} "
        f"uptime={int(uptime)}s completed_requests={completed} "
        f"pressure={preflight['state']['memory_pressure']} "
        f"thermal={preflight['state']['thermal_state']} "
        f"kv_free={preflight['state']['kv_pages_free']} "
        f"kv_cache={preflight['state']['kv_pages_cache']} "
        f"disk_used={preflight['state']['disk_used_bytes']}/{profile['disk_limit_bytes']} "
        f"headroom={preflight['state']['host_headroom_bytes']} "
        f"growth_allowed={preflight['state']['growth_allowed']}"
    )
    (out / "preflight.json").write_text(json.dumps({
        "profile": profile,
        "cache_state": state_label,
        "uptime_seconds": round(uptime, 1),
        "requests_completed_at_preflight": completed,
        **preflight,
    }, indent=2))

    groups = [args.group]
    all_rows: list[dict] = []
    per_trial: dict[str, list[dict]] = {}
    prefill_sizes = [int(s) for s in args.sizes.split(",")]
    for trial in range(1, args.trials + 1):
        rows = run_trial(client, out, trial, groups, args.thermal_gate,
                         prefill_sizes=prefill_sizes, ladder_turns=args.turns,
                         ladder_step=args.turn_step)
        per_trial[f"trial{trial}"] = rows
        for row in rows:
            labelled = dict(row)
            labelled["trial"] = trial
            all_rows.append(labelled)

    summary = {
        "complete": True,
        "phase": f"option20-{args.group}-matrix",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "profile": profile,
        "cache_state": state_label,
        "thermal_gate": args.thermal_gate,
        "trials": args.trials,
        "group": args.group,
        "prefill_sizes": prefill_sizes,
        "ladder_turns": args.turns,
        "ladder_step": args.turn_step,
        "prompt_targets": PROMPT_TARGETS,
        "preflight": preflight,
        "rows": all_rows,
    }
    (out / "matrix-results.json").write_text(json.dumps(summary, indent=2))

    lines = [f"# Option 20 {args.group} matrix", "",
             f"cache state: {state_label} | thermal gate: {args.thermal_gate or 'none'} | "
             f"build: {profile['build_id']}", ""]
    for label, rows in per_trial.items():
        lines.append(f"## {label}")
        lines.extend(summarize(rows))
        lines.append("")
    lines.append("## pooled")
    lines.extend(summarize(all_rows))
    (out / "matrix.md").write_text("\n".join(lines) + "\n")
    recorded = run_summary(out, args.label or out.name, "")
    parts = []
    if recorded["coding_decode"] != "0.00":
        parts.append(f"coding decode {recorded['coding_decode']} tok/s")
        parts.append(f"tokens/cycle {recorded['coding_tokens_per_cycle']}")
    if recorded["fourk_cold_prefill"] != "0.0":
        parts.append(f"4k cold {recorded['fourk_cold_prefill']} tok/s")
        parts.append(f"4k reuse TTFT {recorded['fourk_reuse_ttft']} s")
    if recorded.get("notes"):
        parts.append(recorded["notes"])
    parts.append(f"draft acceptance {recorded['draft_accepted']}/{recorded['draft_proposed']}")
    parts.append(f"spill pages {recorded['spill_pages']}")
    parts.append(f"disk KV read-back {recorded['kv_disk_hit_tokens']} tokens")
    parts.append(f"clean {recorded['clean_probes']}")
    parts.append(f"thermal {recorded['thermal']}")
    (out / "summary.txt").write_text(", ".join(parts) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
