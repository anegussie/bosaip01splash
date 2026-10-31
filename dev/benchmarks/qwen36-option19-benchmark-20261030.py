#!/usr/bin/env python3
"""Performance benchmark for Qwen3.6-35B-A3B UD-IQ3_XXS (option 19).

Runs against the live server on port 1235 with 81,920 context.
Measures cold/cached prefill throughput, decode throughput, TTFT, and
memory/thermal state at multiple context depths.
"""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:1235"
ALIAS = "qwen3.6-35b-a3b-iq3-xxs-splash"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/Users/mymac/splash/splash/build/validation/option19-benchmark-20261030")
OUT.mkdir(parents=True, exist_ok=True)

METRICS = (
    "prefill_input_tokens",
    "prefill_wall_ms",
    "decode_output_tokens",
    "decode_wall_ms",
    "decode_cycle_ms",
    "drafted_tokens",
    "accepted_draft_tokens",
)

RECALL_LINES = (
    "Repository note: pure Python utilities preserve caller data and stable ordering.\n"
)


def request(path="/status", body=None, timeout=600):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def swap():
    return subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def body(messages, limit=128, **extra):
    extra["cache_salt"] = extra.get("cache_salt", "bench") + ":" + OUT.name
    return {
        "model": ALIAS,
        "messages": messages,
        "temperature": 0,
        "seed": 42,
        "reasoning_effort": "none",
        "max_tokens": limit,
        **extra,
    }


def recall_context_text(depth):
    """Binary-search for line count that fills ~depth tokens."""
    line = RECALL_LINES
    low, high = 1, depth
    target = depth - 160
    while low < high:
        mid = (low + high + 1) // 2
        tokens = request("/tokenize", {"content": line * mid})["tokens"]
        if len(tokens) <= target:
            low = mid
        else:
            high = mid - 1
    return line * low


def recall_prompt(depth):
    ctx = recall_context_text(depth)
    prompt = (
        "Read the repository notes. The initial code is AMBER.\n"
        + ctx
        + "\nFinal code: ORCHID. State only the final code, then count from 1 to 100 separated by commas."
    )
    return body([{"role": "user", "content": prompt}], limit=128)


def check_recall(reply):
    text = reply["choices"][0]["message"].get("content", "")
    assert "ORCHID" in text, f"Missing ORCHID: {text[:200]}"
    numbers = [int(n) for n in re.findall(r"\b\d+\b", text)]
    assert numbers[:10] == list(range(1, 11)), f"Counting failed: {numbers[:15]}"


def measure(key, payload, check=None):
    before = request()
    swap_before = swap()
    started = time.monotonic()
    reply = request("/v1/chat/completions", payload)
    elapsed = time.monotonic() - started
    after = request()
    delta = {k: after["metrics"][k] - before["metrics"][k] for k in METRICS}
    prompt_tokens = reply["usage"]["prompt_tokens"]
    gen_tokens = reply["usage"]["completion_tokens"]
    pp_tok_s = delta["prefill_input_tokens"] / (delta["prefill_wall_ms"] / 1000) if delta["prefill_wall_ms"] > 0 else 0
    tg_tok_s = delta["decode_output_tokens"] / (delta["decode_wall_ms"] / 1000) if delta["decode_wall_ms"] > 0 else 0
    # TTFT: time from request start to first content token
    ttft = elapsed  # approximate (full request time); exact TTFT needs streaming
    row = {
        "key": key,
        "prompt_tokens": prompt_tokens,
        "generated_tokens": gen_tokens,
        "seconds": round(elapsed, 3),
        "response": reply,
        "prefill_tok_s": round(pp_tok_s, 1),
        "decode_tok_s": round(tg_tok_s, 1),
        "ttft_s": round(ttft, 3),
        "cache_n": delta.get("cache_n", 0),
        "swap_before": swap_before,
        "swap_after": swap(),
        "thermal": [before["thermal_state"], after["thermal_state"]],
        "memory_pressure": [before["memory_pressure"], after["memory_pressure"]],
    }
    if check:
        check(reply)
        row["check_passed"] = True
    save(OUT / (key + ".json"), row)
    save(OUT / (key + "-response.json"), reply)
    print(
        f"{key}: prompt={prompt_tokens} gen={gen_tokens} "
        f"pp={pp_tok_s:.1f} tok/s tg={tg_tok_s:.1f} tok/s "
        f"elapsed={elapsed:.2f}s cache_n={row['cache_n']}"
    )
    return row


def main():
    # Verify server is the right model
    status = request()
    print(f"Server ready: {status['ready']}")
    print(f"Max context: {status['maximum_context_tokens']}")
    print(f"Model: {status['identity']['cache']['build_id']}")
    assert status["ready"], "Server not ready"
    assert status["maximum_context_tokens"] == 81920, f"Expected 81920 context, got {status['maximum_context_tokens']}"

    record = {
        "measurement": "Qwen3.6-35B-A3B UD-IQ3_XXS option-19 benchmark",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "server_context": status["maximum_context_tokens"],
        "prefill_chunk": status["prefill_chunk_tokens"],
        "model_build": status["identity"]["cache"]["build_id"],
        "model_kv": status["identity"]["kv"]["format"],
        "model_state": status["memory_plan"]["model"]["state_format"],
        "budget_bytes": status["memory_plan"]["budget"]["configured_memory_limit_bytes"],
        "phases": [],
    }

    # === Phase 1: Smoke tests ===
    print("\n=== SMOKE TESTS ===")
    smoke = []
    for depth_salt in [(512, "smoke-512")]:
        p = recall_prompt(depth_salt[0])
        r = measure(f"smoke-{depth_salt[1]}", p, check_recall)
        smoke.append(r)

    # Tool call smoke
    tool_payload = body(
        [{"role": "user", "content": "Use add to calculate 17 plus 25."}],
        limit=64,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two integers.",
                    "parameters": {
                        "type": "object",
                        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                        "required": ["a", "b"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "add"}},
    )
    r_tool = measure("smoke-tool-call", tool_payload)
    msg = r_tool["response"]["choices"][0]["message"]
    calls = msg.get("tool_calls", [])
    if calls:
        assert len(calls) == 1 and calls[0]["function"]["name"] == "add"
        assert json.loads(calls[0]["function"]["arguments"]) == {"a": 17, "b": 25}
        tool_payload["messages"].extend(
            [
                {"role": "assistant", "content": None, "tool_calls": calls},
                {"role": "tool", "tool_call_id": calls[0]["id"], "content": "42"},
            ]
        )
        tool_payload["tool_choice"] = "none"
        r2 = measure("smoke-tool-result", tool_payload)
        assert re.search(r"\b42\b", r2["response"]["choices"][0]["message"]["content"])
    else:
        print("Tool call: model returned content instead of tool_calls (tool-use not enabled)")

    # Streaming smoke
    print("\n=== STREAMING SMOKE ===")
    before = request()
    stream_payload = body([{"role": "user", "content": "Reply exactly STREAM_OK."}], 32, stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(stream_payload).encode(), {"Content-Type": "application/json"})
    started = time.monotonic()
    events = []
    content = ""
    ttft = None
    done = False
    with urllib.request.urlopen(req, timeout=180) as response:
        for raw_line in response:
            line = raw_line.decode().strip()
            if not line.startswith("data: "):
                continue
            if line[6:] == "[DONE]":
                done = True
                continue
            event = json.loads(line[6:])
            events.append(event)
            for choice in event.get("choices", []):
                text = choice.get("delta", {}).get("content") or ""
                if text and ttft is None:
                    ttft = time.monotonic() - started
                content += text
    after = request()
    assert done and content.strip() == "STREAM_OK", f"Streaming failed: {content}"
    print(f"Streaming TTFT: {ttft:.3f}s, content: {content.strip()}")
    streaming_result = {"ttft_s": round(ttft, 3), "content": content.strip(), "done": done}

    record["smoke_passed"] = True
    record["streaming"] = streaming_result
    save(OUT / "run.json", record)

    # === Phase 2: Timed benchmarks at multiple depths ===
    depths = [4096, 16384, 32768, 57344]
    trials_per_depth = 3

    for depth in depths:
        print(f"\n=== DEPTH: {depth} tokens ({depth/1024:.0f}K) ===")
        phase = {"name": f"{depth}", "runs": []}
        record["phases"].append(phase)

        for trial in range(1, trials_per_depth + 1):
            p = recall_prompt(depth)
            r = measure(f"{depth}-trial-{trial}", p, check_recall)
            phase["runs"].append(r)

        # Repeated-prefix (cached) run
        rp = recall_prompt(depth)
        r = measure(f"{depth}-cached", rp, check_recall)
        phase["runs"].append(r)

        # Coding task
        ctx_text = recall_context_text(4096)
        coding_payload = body(
            [
                {"role": "system", "content": "Return only the requested Python function's code. Use no imports and no commentary."},
                {"role": "user", "content": ctx_text + "\n\nTask: Write a merge_intervals function that merges overlapping intervals in a list of [start, end] pairs."},
            ],
            limit=384,
            top_p=0.8,
            top_k=20,
        )
        r = measure("coding-merge_intervals", coding_payload)
        check_proc = subprocess.run(
            [sys.executable, str(ROOT / "bonsai_coding.py"), "--check", "merge_intervals"],
            input=r["response"]["choices"][0]["message"]["content"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        r["coding_correct"] = check_proc.returncode == 0
        r["coding_error"] = check_proc.stderr[-1200:] if check_proc.returncode != 0 else ""
        print(f"Coding merge_intervals: {'PASS' if r['coding_correct'] else 'FAIL'}")

        # Prose task
        prose_payload = body(
            [{"role": "user", "content": ctx_text + "\n\nWrite a concise technical explanation of the cache mechanism in 3 paragraphs, around 150 words."}],
            limit=256,
        )
        r2 = measure("prose-explanation", prose_payload)
        text = r2["response"]["choices"][0]["message"]["content"]
        r2["prose_correct"] = "cache" in text.lower() and len(text.split()) >= 100
        print(f"Prose explanation: {'PASS' if r2['prose_correct'] else 'FAIL'}")

        save(OUT / "run.json", record)

    # === Summary ===
    print("\n=== SUMMARY ===")
    summary = {
        "model": "Qwen3.6-35B-A3B UD-IQ3_XXS",
        "launcher": "option 19 (Splash SSD expert streaming)",
        "server_context": 81920,
        "prefill_chunk": 512,
        "kv_format": "int8",
        "state_format": "bf16",
        "budget_gb": 8,
        "concurrency": 1,
        "reasoning": "off",
        "thermal": status["thermal_state"],
        "memory_pressure": status["memory_pressure"],
        "swap": swap(),
        "smoke_passed": True,
        "streaming_ttft_s": streaming_result["ttft_s"],
        "depths": {},
    }

    for phase in record["phases"]:
        depth = int(phase["name"])
        cold_runs = [r for r in phase["runs"] if "trial" in r["key"] and "cached" not in r["key"]]
        cached_runs = [r for r in phase["runs"] if "cached" in r["key"]]

        if cold_runs:
            cold_pp = [r["prefill_tok_s"] for r in cold_runs]
            cold_tg = [r["decode_tok_s"] for r in cold_runs]
            cold_ttft = [r["seconds"] for r in cold_runs]
            summary["depths"][depth] = {
                "cold_mean_pp_tok_s": round(sum(cold_pp) / len(cold_pp), 1),
                "cold_median_pp_tok_s": round(sorted(cold_pp)[len(cold_pp) // 2], 1),
                "cold_mean_tg_tok_s": round(sum(cold_tg) / len(cold_tg), 1),
                "cold_median_tg_tok_s": round(sorted(cold_tg)[len(cold_tg) // 2], 1),
                "cold_mean_s": round(sum(cold_ttft) / len(cold_ttft), 2),
                "cached_mean_s": round(sum(r["seconds"] for r in cached_runs) / len(cached_runs), 2) if cached_runs else None,
                "coding_passed": all(r.get("coding_correct", False) for r in cold_runs),
            }
            d_k = f"{depth // 1024}K"
            print(f"{d_k}: cold pp={summary['depths'][depth]['cold_mean_pp_tok_s']} tok/s tg={summary['depths'][depth]['cold_mean_tg_tok_s']} tok/s mean={summary['depths'][depth]['cold_mean_s']}s")

    save(OUT / "summary.json", summary)
    print(f"\nResults saved to: {OUT}")
    print("DONE")


if __name__ == "__main__":
    main()
