"""Validate the external option-14 launcher, tools, long context and restart cache.

Run sequentially after native GPU tests; this loads the installed Bonsai model.
Uses temporary launcher logs, client configuration and cache directories.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("build/validation/upstream-merge-live.json")
    )
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="splash-merge-live-"))
    launcher = Path("/Users/mymac/startllamacpp.sh")
    config = root / "opencode.json"
    config.write_text(
        json.dumps(
            {
                "provider": {"local-llama": {"options": {}, "models": {}}},
                "agent": {"general": {"model": "local-llama/old"}},
            }
        )
    )
    env = {
        **os.environ,
        "LLAMA_LOG_DIR": str(root / "logs"),
        "OPENCODE_CONFIG_PATH": str(config),
        "SPLASH_BONSAI_CACHE_DIR": str(root / "cache"),
    }
    base = "http://127.0.0.1:1235"
    results = {
        "artifacts": str(root),
        "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
    }

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        with urllib.request.urlopen(
            urllib.request.Request(
                base + path, data, {"Content-Type": "application/json"}
            ),
            timeout=300,
        ) as response:
            return json.load(response)

    def launch(label):
        log_path = root / (label + ".log")
        log = log_path.open("w")
        process = subprocess.Popen(
            ["bash", str(launcher), "--direct", "14"], env=env, stdout=log, stderr=log
        )
        started = time.monotonic()
        try:
            while time.monotonic() - started < 180:
                if process.poll() is not None:
                    raise RuntimeError(log_path.read_text())
                try:
                    status = request("/status")
                    if status.get("ready"):
                        assert status["maximum_context_tokens"] == 24576, status
                        assert status["prefill_chunk_tokens"] == 512, status
                        assert status["metal"]["healthy"], status
                        results[label + "_startup"] = {
                            "seconds": time.monotonic() - started,
                            "status": status,
                        }
                        print(label, "ready", flush=True)
                        return process, log
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.5)
            raise TimeoutError("option 14 did not become ready")
        except BaseException:
            process.terminate()
            process.wait(timeout=60)
            log.close()
            raise

    def stop(process, log):
        process.send_signal(signal.SIGTERM)
        code = process.wait(timeout=60)
        log.close()
        assert code == 143, code
        try:
            request("/status")
        except urllib.error.URLError:
            return
        raise AssertionError("launcher left the server running")

    def generate(name, prompt, max_tokens):
        started = time.monotonic()
        response = request(
            "/v1/chat/completions",
            {
                "model": "bonsai-27b-splash",
                "temperature": 0,
                "reasoning_effort": "none",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        status = request("/status")
        results[name] = {
            "seconds": time.monotonic() - started,
            "response": response,
            "status": status,
            "swap": subprocess.check_output(
                ["sysctl", "vm.swapusage"], text=True
            ).strip(),
        }
        assert status["metal"]["healthy"] and status["requests"]["failed"] == 0, status
        print(name, response["usage"], response.get("timings"), flush=True)
        return response

    prefix = (
        "Read the records and remember the final code.\n"
        + "\n".join(
            f"Record {i}: the stored code is AMBER and the sequence number is {i}."
            for i in range(220)
        )
        + "\nFinal record: the stored code is ORCHID. State the final code, then count from 1 to 100 separated by commas."
    )
    try:
        process, log = launch("first")
        try:
            subprocess.run(
                [
                    str(Path(".venv/bin/python")),
                    "dev/tests/option14_upstream_smoke.py",
                    "--output",
                    str(root / "tools-and-cache.json"),
                ],
                check=True,
            )
            results["smoke"] = json.loads((root / "tools-and-cache.json").read_text())
            first = generate("before_restart", prefix, 96)
            assert "ORCHID" in first["choices"][0]["message"]["content"], first
        finally:
            stop(process, log)
        process, log = launch("restarted")
        try:
            restored = generate("after_restart", prefix, 96)
            assert "ORCHID" in restored["choices"][0]["message"]["content"], restored
            assert (
                restored["choices"][0]["message"]["content"]
                == first["choices"][0]["message"]["content"]
            ), ("cache restart changed deterministic output", first, restored)
            metrics = results["after_restart"]["status"]["metrics"]
            assert (
                metrics["drafted_tokens"] > 0 and metrics["accepted_draft_tokens"] > 0
            ), metrics
            assert (
                restored["usage"]["prompt_tokens_details"]["cached_tokens"] >= 4800
            ), restored
            long_prompt = (
                "Read this record list. The final record contains the answer.\n"
                + "\n".join(
                    f"Record {i}: the stored code is AMBER and the sequence number is {i}."
                    for i in range(1050)
                )
                + "\nFinal record: the stored code is VIOLET.\nWhat code is in the final record? Answer with that code only."
            )
            long_response = generate("long_context", long_prompt, 32)
            assert 22000 <= long_response["usage"]["prompt_tokens"] < 24576, (
                long_response
            )
            assert "VIOLET" in long_response["choices"][0]["message"]["content"], (
                long_response
            )
        finally:
            stop(process, log)
        assert (
            results["launcher_sha256"]
            == hashlib.sha256(launcher.read_bytes()).hexdigest()
        )
        results["passed"] = True
        print("Option 14 merge validation: PASS", flush=True)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print("Results:", args.output, flush=True)


if __name__ == "__main__":
    main()
