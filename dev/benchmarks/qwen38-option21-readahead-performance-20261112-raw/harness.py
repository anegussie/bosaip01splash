"""Serving probe helpers extracted unchanged for the option-21 benchmark."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location(
    "previous_harness",
    ROOT / "dev/benchmarks/qwen38-option21-performance-20261112-raw/harness.py",
)
h = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h)
OUT = Path(__file__).resolve().parent
MODEL = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0"
MODEL_ROOT = (
    ROOT
    / "install/models/.selections/be19a0828c0f96ac1e4ea064e868e18642917d41b5063d625fb3899718685cab"
)
SOURCE = "\n".join(
    f"def square_{i:03d}(value):\n    return value * value\n" for i in range(32)
)
COPY_PROMPT = (
    "Copy the Python source below exactly, starting with def square_000. Return code only, without markdown.\n\n"
    + SOURCE
)
LONG_SOURCE = "\n".join(
    f"def lookup_{i:03d}():\n    return {1000 + (i * 1783 + 641) % 8000}\n"
    for i in range(256)
)
LONG_PROMPT = (
    "Copy the Python source below exactly, starting with def lookup_000. Return code only, without markdown.\n\n"
    + LONG_SOURCE
)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def system_snapshot():
    result = {}
    for command in (["vm_stat"], ["sysctl", "vm.swapusage"], ["pmset", "-g", "therm"]):
        p = subprocess.run(command, text=True, capture_output=True)
        result[" ".join(command)] = dict(
            exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr
        )
    return result


def wait_nominal(client):
    deadline = time.monotonic() + 240
    announced = False
    while client.status()["thermal_state"] != "nominal":
        if not announced:
            print("Cooling to nominal before the next long-copy probe", flush=True)
            announced = True
        assert time.monotonic() < deadline, "thermal cooldown timed out"
        time.sleep(5)


def probe(client, name, prompt, salt, temperature=0.0):
    before = client.status()
    body = dict(
        model=MODEL,
        messages=[dict(role="user", content=prompt)],
        stream=True,
        stream_options=dict(include_usage=True),
        temperature=temperature,
        seed=1234,
        max_tokens=192 if name == "code-3" else 96,
        chat_template_kwargs=dict(enable_thinking=False),
        cache_salt=salt,
    )
    req = urllib.request.Request(
        client.base + "/v1/chat/completions",
        json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    chunks, parts, samples = [], [], []
    started = time.monotonic()
    first = None
    next_sample = started
    with urllib.request.urlopen(req, timeout=300) as response:
        for raw in response:
            if not raw.startswith(b"data: "):
                continue
            data = raw[6:].strip()
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            chunks.append(chunk)
            for choice in chunk.get("choices", []):
                content = choice.get("delta", {}).get("content") or ""
                if content:
                    if first is None:
                        first = time.monotonic() - started
                    parts.append(content)
            if time.monotonic() >= next_sample:
                samples.append(h.scalar_state(client.status()))
                next_sample = time.monotonic() + 1
    after = client.status()
    text = "".join(parts)
    timings, metrics, usage = {}, {}, {}
    for chunk in chunks:
        timings.update(chunk.get("timings") or {})
        metrics.update(chunk.get("metrics") or {})
        usage.update(chunk.get("usage") or {})
    stripped = re.sub(r"^```(?:python)?\s*\n", "", text).split("```", 1)[0].strip()
    if name.startswith("copy"):
        expected = LONG_SOURCE if name.startswith("copy-long") else SOURCE
        correct = len(stripped) > 100 and expected.startswith(stripped)
    elif name == "code-3":
        correct = h.run_code_check(name, prompt, text)["correct"]
    else:
        correct = h.smoke_gate_ok(text)
    copies = after.get("prompt_copy", {}).get("cycles", 0) - before.get(
        "prompt_copy", {}
    ).get("cycles", 0)
    accepted = after.get("prompt_copy", {}).get("accepted_tokens", 0) - before.get(
        "prompt_copy", {}
    ).get("accepted_tokens", 0)
    record = dict(
        name=name,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        correct=correct,
        wall_seconds=time.monotonic() - started,
        sse_ttft_seconds=first,
        timings=timings,
        metrics=metrics,
        usage=usage,
        samples=samples,
        copy_cycles=copies,
        copy_accepted=accepted,
        status_before=before,
        status_after=after,
    )
    print(
        name,
        "correct",
        correct,
        "PP",
        timings.get("prompt_per_second"),
        "TPS",
        timings.get("predicted_per_second"),
        "copies",
        copies,
        "accepted",
        accepted,
        flush=True,
    )
    return record
