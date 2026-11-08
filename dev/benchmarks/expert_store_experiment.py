#!/usr/bin/env python3
"""Expert store performance experiments for the 16 GB M5 Air.

Experiments:
  2: Elastic expert store growth - observe regrows and expert residency
     during multi-turn sessions on the 1.6.0 binary.
  3: Idle weight release + expert retention - measure warm-turn decode speed
     with different --idle-release values and whether elastic chunks survive.
  4: Smaller context - measure decode TPS at 32K/65K contexts where headroom
     allows a larger expert store.

Each experiment starts a server, runs scripted conversations, observes /status,
and reports metrics. Use with the existing launcher profile (option 20).

Usage:
  python3 dev/benchmarks/expert_store_experiment.py --experiment 2 --port 1299
  python3 dev/benchmarks/expert_store_experiment.py --experiment 3 --port 1299
  python3 dev/benchmarks/expert_store_experiment.py --experiment 4 --port 1299
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The default model and binary paths matching the option-20 launcher.
MODEL = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS"
DRAFT_MODEL = (
    "/Users/mymac/.cache/huggingface/hub/"
    "models--incoai--Qwen3.8-Flash-Next-DFlash2/"
    "snapshots/a22a1744e85c17364dcc54a6a420af7135d4c7f6"
)
BINARY = ROOT / "build" / "splash"
MODEL_ROOT = ROOT / "install" / "models"
CACHE_BASE = Path.home() / "Library" / "Caches" / "Splash"

COOLDOWN_SECONDS = 10
SAMPLE_INTERVAL = 5
MAX_TURNS = 8


def fetch_status(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=10) as r:
        return json.load(r)


def chat(port: int, messages: list[dict], max_tokens: int = 200) -> dict:
    body = json.dumps({
        "model": "qwen3.8-flash-next-iq3-xxs-splash",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def expert_store_summary(status: dict) -> dict:
    e = status["streamed_experts"]
    return {
        "slots": e["slots"],
        "resident": e["resident"],
        "regrows": e["regrows"],
        "shrinks": e["shrinks"],
        "chunks": e["chunks"],
        "cap_chunks": e["cap_chunks"],
        "cap_bytes": e["cap_bytes"],
        "floor_bytes": e["floor_bytes"],
        "hit_rate_decode": e["decode"]["hit_rate"],
        "prefetched_decode": e["decode"]["prefetched"],
        "routed_decode": e["decode"]["routed"],
        "ahead_used_bytes": e["decode"]["ahead_used_bytes"],
        "ahead_read_bytes": e["decode"]["ahead_read_bytes"],
        "cycle_ahead_predicted": e["decode"].get("cycle_ahead_predicted", 0),
        "cycle_ahead_hits": e["decode"].get("cycle_ahead_hits", 0),
    }


def decode_summary(status: dict) -> dict:
    m = status["metrics"]
    return {
        "decode_tps": m["decode_tokens_per_second"],
        "itl_p50_ms": m["itl_ms"]["p50"],
        "decode_tokens": m["decode_output_tokens"],
        "decode_wall_ms": m["decode_wall_ms"],
        "acceptance_rate": m["draft_acceptance_rate"],
        "cycles": m["decode_batches_by_width"]["b1"],
    }


def start_server(port: int, context: int = 150000, idle_release: int = 600,
                 expert_memory: int | None = None, label: str = "experiment"):
    """Start a splash server with the given configuration."""
    cache_dir = CACHE_BASE / f"experiment-{label}-{port}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", str(ROOT / "server" / "server.py"),
        str(MODEL_ROOT / ".selections" / "e461880d7561045428f295aff63cde5d4925b5637bb5e22eaa7ebbeac3edf4cc"),
        "--model", MODEL,
        "--binary", str(BINARY),
        "--port", str(port),
        "--max-active-requests", "1",
        "--max-memory", "11596411699",
        "--max-context", str(context),
        "--ple-memory", "67108864",
        "--state-format", "bf16",
        "--max-cache-disk", "17179869184",
        "--persistent-cache",
        "--cache-dir", str(cache_dir),
        "--served-model-name", "qwen3.8-flash-next-iq3-xxs-splash",
        "--default-reasoning-effort", "low",
        "--prefill-chunk-tokens", "2048",
        "--resource-wait-timeout", "60",
    ]
    if expert_memory:
        cmd += ["--expert-memory", str(expert_memory)]

    print(f"  Starting server: context={context}, idle_release={idle_release}")
    proc = subprocess.Popen(
        cmd, preexec_fn=os.setsid,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Wait for ready
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            status = fetch_status(port)
            if status.get("ready"):
                print(f"  Server ready (pid={status['instance']['pid']})")
                return proc, status
        except Exception:
            pass
        time.sleep(2)
    stop_server(proc)
    raise RuntimeError("Server failed to start")


def stop_server(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGINT)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)


def cooldown(seconds=COOLDOWN_SECONDS):
    print(f"  Cooling down {seconds}s...")
    time.sleep(seconds)


def experiment_2(port: int):
    """Observe elastic expert store growth during a multi-turn session."""
    print("\n=== Experiment 2: Elastic expert store growth ===")
    proc, status = start_server(port, context=150000, idle_release=600,
                                label="elastic-growth")
    print(f"\n  Initial state: {expert_store_summary(status)}")

    turn_prompts = [
        "What is the capital of France?",
        "Explain photosynthesis in simple terms.",
        "Write a haiku about autumn.",
        "What are the prime factors of 2024?",
        "Summarize the plot of Romeo and Juliet.",
        "How does a hash table work?",
        "Write a short joke about programming.",
        "What is the difference between TCP and UDP?",
    ]

    messages = []
    for i, prompt in enumerate(turn_prompts):
        messages.append({"role": "user", "content": prompt})
        print(f"\n  Turn {i+1}: {prompt[:40]}...")
        try:
            response = chat(port, messages, max_tokens=150)
            assistant_msg = response["choices"][0]["message"]["content"]
            messages.append({"role": "assistant", "content": assistant_msg})
            usage = response.get("usage", {})
            print(f"    tokens: {usage.get('completion_tokens', '?')}")
        except Exception as e:
            print(f"    ERROR: {e}")

        status = fetch_status(port)
        es = expert_store_summary(status)
        ds = decode_summary(status)
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}, "
              f"chunks={es['chunks']}/{es['cap_chunks']}, "
              f"hit_rate={es['hit_rate_decode']:.3f}")
        print(f"    decode: {ds['decode_tps']:.2f} TPS, ITL={ds['itl_p50_ms']:.0f}ms")
        time.sleep(SAMPLE_INTERVAL)

    final_status = fetch_status(port)
    print(f"\n  Final state: {expert_store_summary(final_status)}")
    print(f"  Decode: {decode_summary(final_status)}")
    stop_server(proc)


def experiment_3(port: int):
    """Measure warm-turn decode speed with different idle-release settings."""
    print("\n=== Experiment 3: Idle weight release + expert retention ===")

    configs = [
        {"idle_release": 600, "label": "baseline_600s"},
        {"idle_release": 60, "label": "short_60s"},
        {"idle_release": 1, "label": "aggressive_1s"},
    ]

    results = []
    for cfg in configs:
        print(f"\n  Config: idle_release={cfg['idle_release']}s")
        proc, status = start_server(port, context=150000,
                                    idle_release=cfg["idle_release"],
                                    label=cfg["label"])
        cooldown()

        # Turn 1: cold start
        print("  Turn 1 (cold):")
        messages = [{"role": "user", "content": "Explain how neural networks learn."}]
        t0 = time.time()
        response = chat(port, messages, max_tokens=200)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        status = fetch_status(port)
        ds = decode_summary(status)
        es = expert_store_summary(status)
        cold_tps = usage.get("completion_tokens", 0) / elapsed if elapsed > 0 else 0
        print(f"    cold TPS: {cold_tps:.2f}, elapsed: {elapsed:.1f}s")
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}, "
              f"released={status['weights']['released']}")
        results.append({"config": cfg["label"], "turn": 1, "tps": cold_tps, "es": es})

        # Wait for idle-release threshold
        wait = cfg["idle_release"] + 5
        print(f"  Waiting {wait}s for idle-release to trigger...")
        time.sleep(wait)
        status = fetch_status(port)
        print(f"    After idle: released={status['weights']['released']}, "
              f"restores={status['weights']['restores']}")

        # Turn 2: after weight release
        print("  Turn 2 (after idle-release):")
        messages = [{"role": "user", "content": "What is quantum entanglement?"}]
        t0 = time.time()
        response = chat(port, messages, max_tokens=200)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        status = fetch_status(port)
        ds = decode_summary(status)
        es = expert_store_summary(status)
        warm_tps = usage.get("completion_tokens", 0) / elapsed if elapsed > 0 else 0
        print(f"    warm TPS: {warm_tps:.2f}, elapsed: {elapsed:.1f}s")
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}")
        results.append({"config": cfg["label"], "turn": 2, "tps": warm_tps, "es": es})

        # Turn 3: immediately after (warm)
        print("  Turn 3 (warm, immediate):")
        messages = [{"role": "user", "content": "Write a poem about the sea."}]
        t0 = time.time()
        response = chat(port, messages, max_tokens=200)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        status = fetch_status(port)
        es = expert_store_summary(status)
        warm2_tps = usage.get("completion_tokens", 0) / elapsed if elapsed > 0 else 0
        print(f"    warm2 TPS: {warm2_tps:.2f}, elapsed: {elapsed:.1f}s")
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}")
        results.append({"config": cfg["label"], "turn": 3, "tps": warm2_tps, "es": es})

        stop_server(proc)
        cooldown(15)

    # Summary table
    print("\n  === Summary ===")
    print(f"  {'config':<20} {'turn':>5} {'TPS':>8} {'resident':>8} {'regrows':>7}")
    for r in results:
        print(f"  {r['config']:<20} {r['turn']:>5} {r['tps']:>8.2f} "
              f"{r['es']['resident']:>8} {r['es']['regrows']:>7}")


def experiment_4(port: int):
    """Measure decode TPS at smaller contexts where headroom allows larger stores."""
    print("\n=== Experiment 4: Smaller context, larger expert store ===")

    contexts = [
        {"context": 150000, "label": "150K"},
        {"context": 65536, "label": "65K"},
        {"context": 32768, "label": "32K"},
    ]

    results = []
    for cfg in contexts:
        print(f"\n  Context: {cfg['label']}")
        proc, status = start_server(port, context=cfg["context"],
                                    idle_release=600, label=f"context-{cfg['label']}")
        cooldown()

        # Check initial memory plan
        mem = status["memory_governor"]
        accounts = {a["name"]: a for a in mem["accounts"]}
        print(f"    expert store cap: {accounts['experts']['cap_bytes'] / 1e9:.2f} GiB")
        print(f"    expert store floor: {accounts['experts']['floor_bytes'] / 1e9:.2f} GiB")
        print(f"    headroom: {accounts['experts'].get('headroom_bytes', 0) / 1e9:.2f} GiB")
        print(f"    dynamic budget: {status['memory_plan']['budget']['dynamic_budget_bytes'] / 1e9:.2f} GiB")
        es = expert_store_summary(status)
        print(f"    slots: {es['slots']}, chunks: {es['chunks']}/{es['cap_chunks']}")

        # Run decode test
        print("  Decode test (count to 50):")
        messages = [{"role": "user", "content": "Count from 1 to 50, one per line."}]
        t0 = time.time()
        response = chat(port, messages, max_tokens=200)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        status = fetch_status(port)
        ds = decode_summary(status)
        es = expert_store_summary(status)
        tps = usage.get("completion_tokens", 0) / elapsed if elapsed > 0 else 0
        print(f"    decode TPS: {tps:.2f}")
        print(f"    ITL p50: {ds['itl_p50_ms']:.1f} ms")
        print(f"    acceptance: {ds['acceptance_rate']:.2%}")
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}, "
              f"chunks={es['chunks']}/{es['cap_chunks']}")

        # Longer context test
        print("  Longer context test (summarize 3 paragraphs):")
        long_text = " ".join([
            "The quick brown fox jumps over the lazy dog. " * 100,
            "Pack my box with five dozen liquor jugs. " * 100,
            "How vexingly quick daft zebras jump! " * 100,
        ])
        messages = [{"role": "user", "content": f"Summarize: {long_text}"}]
        t0 = time.time()
        response = chat(port, messages, max_tokens=150)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        status = fetch_status(port)
        es = expert_store_summary(status)
        tps_long = usage.get("completion_tokens", 0) / elapsed if elapsed > 0 else 0
        print(f"    prompt tokens: {usage.get('prompt_tokens', '?')}")
        print(f"    decode TPS: {tps_long:.2f}")
        print(f"    experts: resident={es['resident']}, regrows={es['regrows']}")

        results.append({
            "context": cfg["label"],
            "tps_short": tps,
            "tps_long": tps_long,
            "itl_p50": ds["itl_p50_ms"],
            "expert_cap": accounts['experts']['cap_bytes'],
            "chunks": es["chunks"],
        })
        stop_server(proc)
        cooldown(15)

    print("\n  === Summary ===")
    print(f"  {'context':<8} {'TPS short':>10} {'TPS long':>10} {'ITL p50':>9} {'cap GiB':>8} {'chunks':>7}")
    for r in results:
        print(f"  {r['context']:<8} {r['tps_short']:>10.2f} {r['tps_long']:>10.2f} "
              f"{r['itl_p50']:>9.1f} {r['expert_cap']/1e9:>8.2f} {r['chunks']:>7}")


def main():
    parser = argparse.ArgumentParser(description="Expert store performance experiments")
    parser.add_argument("--experiment", type=int, required=True, choices=[2, 3, 4],
                        help="Experiment number (2, 3, or 4)")
    parser.add_argument("--port", type=int, default=1299, help="Port for test server")
    args = parser.parse_args()

    # Verify binary exists
    if not BINARY.exists():
        print(f"ERROR: Binary not found: {BINARY}")
        sys.exit(1)

    experiments = {2: experiment_2, 3: experiment_3, 4: experiment_4}
    experiments[args.experiment](args.port)


if __name__ == "__main__":
    main()
