"""Option-21 serving performance: old/new scheduler, frozen prepared cache, ABBA."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("existing_probe", OUT / "harness.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
# Keep every recall/counting completion at the 96-token budget for matched decode work.
b.h.SMOKE_TAIL = "\nReturn the secret code, then list the integers from 1 through 100 in order. No explanation."
SIZES = (4096, 8192, 16384)
MODEL = b.MODEL
BASELINE = OUT / "binaries/baseline/splash"
CANDIDATE = OUT / "binaries/candidate/splash"
CACHE = OUT / "frozen-expert-cache"
PREVIOUS = ROOT / "build/validation/option21-read-ahead-20261112"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_manifest():
    return {
        str(p.relative_to(CACHE)): [p.stat().st_size, sha(p)]
        for p in sorted(CACHE.rglob("*.plane"))
    }


def status():
    with urllib.request.urlopen("http://127.0.0.1:1235/status", timeout=5) as r:
        return json.load(r)


def snapshot_binaries():
    for name, source in (
        ("baseline", ROOT / "build"),
        ("candidate", ROOT / "build/option21-readahead-candidate"),
    ):
        dest = OUT / "binaries" / name
        dest.mkdir(parents=True, exist_ok=True)
        for filename in ("splash", "splash.metallib", "host-step.metallib"):
            shutil.copy2(source / filename, dest / filename)
        save(
            dest / "sha256.json",
            {p.name: sha(p) for p in dest.iterdir() if p.name != "sha256.json"},
        )
    shutil.copy2(PREVIOUS / "before/ExpertStore.cpp", OUT / "baseline-ExpertStore.cpp")
    shutil.copy2(
        ROOT / "runtime/model/ExpertStore.cpp", OUT / "candidate-ExpertStore.cpp"
    )
    shutil.copytree(PREVIOUS / "prepared-cache", CACHE)
    manifest = cache_manifest()
    assert manifest
    save(OUT / "frozen-cache-manifest.json", manifest)
    # Exact existing footprint: no write allowance and no startup eviction.
    quota = sum(size for size, digest in manifest.values())
    save(
        OUT / "contract.json",
        {
            "model": MODEL,
            "contexts": list(SIZES),
            "server_context": 131072,
            "max_memory": "10.8G",
            "prefill_chunk": 2048,
            "state": "bf16",
            "kv": "int8",
            "expert_memory": "auto",
            "verify_rows": "auto",
            "active_requests": 1,
            "prefix_cache_quota": "3G",
            "prepared_cache_bytes": quota,
            "recall_output_budget": 96,
            "code_output_budget": 192,
            "temperature": 0.0,
            "seed": 1234,
            "thinking": False,
            "sequence": ["A1", "B1", "B2", "A2"],
            "cold_definition": "zero reused prefix tokens; model/OS caches warm",
        },
    )
    return quota


def delta(before, after):
    result = {}
    for phase in ("prefill", "decode"):
        a, z = before["streamed_experts"][phase], after["streamed_experts"][phase]
        result[phase] = {
            key: z[key] - a[key]
            for key in (
                "read",
                "routed",
                "prefetched",
                "read_ahead",
                "read_bytes",
                "ahead_read_bytes",
                "ahead_used_bytes",
            )
        }
        result[phase]["host_step_work_seconds"] = (
            z["host_steps"]["work_ms"]["total"] / 1000
            - a["host_steps"]["work_ms"]["total"] / 1000
        )
    return result


def check_row(row, expected_cache=None):
    assert row["correct"], row["text"]
    assert row["status_after"]["requests"]["failed"] == 0
    assert row["status_after"]["metal"]["healthy"]
    if expected_cache is False:
        assert row["timings"]["cache_n"] == 0
    if expected_cache is True:
        assert row["timings"]["cache_n"] >= row["usage"]["prompt_tokens"] - 32
    if row["name"] != "code-3":
        assert row["usage"]["completion_tokens"] == 96
    pc = row["status_after"]["streamed_experts"]["plane_cache"]
    if pc["enabled"]:
        assert pc["errors"] == pc["corruptions"] == pc["writes"] == 0, pc


def arm(
    label,
    binary,
    quota,
    *,
    sizes,
    prepared=True,
    smoke=False,
    prefix_path=None,
    restart=False,
):
    directory = OUT / label
    directory.mkdir(exist_ok=True)
    flags = [
        "--model",
        MODEL,
        "--model-root",
        str(b.MODEL_ROOT),
        "--binary",
        str(binary),
        "--max-context",
        "131072",
        "--max-memory",
        "10.8G",
        "--max-cache-disk",
        "3G",
        "--prefill-chunk-tokens",
        "2048",
        "--ple-memory",
        "64M",
        "--state-format",
        "bf16",
        "--verify-rows",
        "auto",
        "--startup-timeout",
        "180",
    ]
    if prepared:
        flags += ["--expert-cache", str(CACHE), "--expert-cache-disk", str(quota)]
    args = b.smoke.parse_args(flags)
    b.smoke.hold_model_root(args)
    save(
        directory / "identity.json",
        {"binary": str(binary), "sha256": sha(binary), "flags": flags},
    )
    save(directory / "system-before.json", b.system_snapshot())
    rows = []
    with b.smoke.serving(args, cache_dir=prefix_path) as server:
        client = b.h.Client(f"http://127.0.0.1:{server.port}", MODEL)
        try:
            ready = client.status()
            save(directory / "ready.json", ready)
            assert ready["prefill_chunk_tokens"] == 2048
            assert ready["maximum_context_tokens"] == 131072
            assert ready["memory_plan"]["model"]["state_format"] == "bf16"
            assert ready["memory_plan"]["model"]["kv_format"] == "int8"
            if not restart:
                prompt, _ = b.h.build_prompt(client, "pre-4096", "read-ahead-warmup")
                row = b.probe(client, "warmup", prompt, label + "-warmup")
                check_row(row, False)
                save(directory / "warmup.json", row)
            for size in sizes:
                b.wait_nominal(client)
                prompt, n = b.h.build_prompt(
                    client, f"pre-{size}", "read-ahead-matched"
                )
                save(
                    directory / f"prompt-{size}.json",
                    {
                        "text": prompt,
                        "tokens": n,
                        "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    },
                )
                salt = ("smoke-candidate" if restart else label) + f"-context-{size}"
                modes = ("reuse",) if restart else ("cold", "reuse")
                for mode in modes:
                    b.wait_nominal(client)
                    row = b.probe(client, f"{size}-{mode}", prompt, salt)
                    row["expert_io_delta"] = delta(
                        row["status_before"], row["status_after"]
                    )
                    save(directory / f"{size}-{mode}.json", row)
                    check_row(row, mode == "reuse")
                    rows.append(row)
            if not restart:
                b.wait_nominal(client)
                row = b.probe(
                    client, "code-3", b.h.CODE_TASKS["code-3"][0], label + "-code"
                )
                row["expert_io_delta"] = delta(
                    row["status_before"], row["status_after"]
                )
                save(directory / "code-3.json", row)
                check_row(row, False)
                rows.append(row)
            final = client.status()
            save(directory / "final.json", final)
            if prepared:
                pc = final["streamed_experts"]["plane_cache"]
                assert pc["enabled"] and pc["hits"] > 0 and pc["writes"] == 0
                assert pc["errors"] == pc["corruptions"] == 0
            server.stop()
        finally:
            shutil.copyfile(server.log.name, directory / "server.log")
            save(directory / "system-after.json", b.system_snapshot())
    assert cache_manifest() == json.loads(
        (OUT / "frozen-cache-manifest.json").read_text()
    )
    save(directory / "results.json", {"complete": True, "rows": rows})
    print("ARM COMPLETE", label, flush=True)
    return rows


def restore(command, before):
    command[0] = str(ROOT / ".venv/bin/python")
    live_log = ROOT / "build/validation" / OUT.name / "production-live.log"
    live_log.parent.mkdir(parents=True, exist_ok=True)
    with live_log.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    save(
        OUT / "restored-process.json",
        {"pid": process.pid, "command": command, "live_log": str(live_log)},
    )
    for _ in range(180):
        if process.poll() is not None:
            shutil.copyfile(live_log, OUT / "production-restored.log")
            raise RuntimeError("Production restart failed; see production-restored.log")
        try:
            after = status()
            if after["ready"]:
                assert after["identity"] == before["identity"]
                for key in ("maximum_context_tokens", "prefill_chunk_tokens"):
                    assert after[key] == before[key]
                assert after["instance"]["model"] == before["instance"]["model"]
                save(OUT / "production-restored.json", after)
                shutil.copyfile(live_log, OUT / "production-restored.log")
                print(
                    "Original service restored on port 1235 with matching identity",
                    flush=True,
                )
                return
        except OSError:
            pass
        time.sleep(1)
    shutil.copyfile(live_log, OUT / "production-restored.log")
    raise RuntimeError("Production readiness timeout")


def main():
    assert not (OUT / "contract.json").exists(), (
        "Use a fresh output directory; do not overwrite evidence"
    )
    quota = snapshot_binaries()
    before = status()
    assert before["instance"]["model"] == MODEL and not before["active_requests"]
    assert before["http"]["requests"]["active"] <= 1
    save(OUT / "production-before.json", before)
    pid = before["instance"]["pid"]
    command = shlex.split(
        subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="], text=True
        ).strip()
    )
    save(OUT / "restore-command.json", command)
    native = subprocess.check_output(["pgrep", "-P", str(pid)], text=True).split()
    try:
        os.kill(pid, signal.SIGINT)
        for _ in range(120):
            if not any(
                subprocess.run(
                    ["ps", "-p", p, "-o", "pid="], capture_output=True
                ).stdout.strip()
                for p in native
            ):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(
                "Original native process did not stop; no benchmark launched"
            )
        print("Original service stopped; starting smoke gates", flush=True)
        # Scratch prefix caches are owned only by this run and removed after shutdown.
        with tempfile.TemporaryDirectory(prefix="prefix-smoke-", dir=OUT) as scratch:
            arm(
                "smoke-candidate",
                CANDIDATE,
                quota,
                sizes=(4096,),
                smoke=True,
                prefix_path=Path(scratch),
            )
            arm(
                "smoke-restart",
                CANDIDATE,
                quota,
                sizes=(4096,),
                smoke=True,
                restart=True,
                prefix_path=Path(scratch),
            )
        with tempfile.TemporaryDirectory(
            prefix="prefix-baseline-smoke-", dir=OUT
        ) as scratch:
            arm(
                "smoke-baseline",
                BASELINE,
                quota,
                sizes=(4096,),
                smoke=True,
                prefix_path=Path(scratch),
            )
        save(
            OUT / "smoke-passed.json",
            {
                "complete": True,
                "candidate_sha256": sha(CANDIDATE),
                "baseline_sha256": sha(BASELINE),
            },
        )
        for label, binary in (
            ("A1", BASELINE),
            ("B1", CANDIDATE),
            ("B2", CANDIDATE),
            ("A2", BASELINE),
        ):
            with tempfile.TemporaryDirectory(
                prefix="prefix-" + label + "-", dir=OUT
            ) as scratch:
                arm(label, binary, quota, sizes=SIZES, prefix_path=Path(scratch))
        for label, binary in (
            ("native-baseline", BASELINE),
            ("native-candidate", CANDIDATE),
        ):
            with tempfile.TemporaryDirectory(
                prefix="prefix-" + label + "-", dir=OUT
            ) as scratch:
                arm(
                    label,
                    binary,
                    quota,
                    sizes=(8192,),
                    prepared=False,
                    prefix_path=Path(scratch),
                )
        save(OUT / "complete.json", {"complete": True})
        print("PERFORMANCE MATRIX COMPLETE", flush=True)
    finally:
        restore(command, before)


if __name__ == "__main__":
    main()
