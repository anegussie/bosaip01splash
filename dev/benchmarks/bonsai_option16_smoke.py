#!/usr/bin/env python3
"""Smoke-test the actual option-16 launcher with isolated config and cache.

An idle primary may stay online after releasing its weights. Abort this test
if it resumes, using the same guard as the DFlash2 benchmark.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

if __package__:
    from .dflash2_tuning import guard_primary, released_primary, request, save, stop
else:
    from dflash2_tuning import guard_primary, released_primary, request, save, stop

ROOT = Path(__file__).resolve().parents[2]
ALIAS = "bonsai-heretic-27b-splash"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--launcher", type=Path, default=Path("/Users/mymac/startllamacpp.sh")
    )
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--port", type=int, default=1236)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.port == 1235:
        parser.error("use a valid port separate from the primary port 1235")
    released_primary()
    args.results = args.results.resolve()
    args.results.mkdir(parents=True, exist_ok=False)
    config = args.results / "opencode.json"
    save(
        config,
        {"provider": {"local-llama": {"options": {}, "models": {}}}, "agent": {}},
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SPLASH_BONSAI_", "SPLASH_HERETIC_"))
    }
    env.update(
        LLAMA_PORT=str(args.port),
        LLAMA_HOST="127.0.0.1",
        LLAMA_LOG_DIR=str(args.results / "logs"),
        OPENCODE_CONFIG_PATH=str(config),
        SPLASH_HERETIC_CACHE_DIR=str(args.results / "cache"),
        HF_HUB_OFFLINE="1",
        SPLASH_BONSAI_STARTUP_MAX_RETRIES="0",
    )
    url = f"http://127.0.0.1:{args.port}"
    report = {"launcher": str(args.launcher), "port": args.port, "checks": []}
    with (args.results / "launcher.log").open("w") as log:
        process = subprocess.Popen(
            ["bash", str(args.launcher), "--direct", "16"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            with guard_primary(process, True):
                start = time.monotonic()
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("option 16 exited; inspect launcher.log")
                    try:
                        status = request(url)
                        if status["ready"]:
                            break
                    except OSError:
                        pass
                    if time.monotonic() - start > 600:
                        raise RuntimeError("option 16 readiness timed out")
                    time.sleep(1)
                report["startup_seconds"] = time.monotonic() - start
                save(args.results / "status-before.json", status)
                assert status["maximum_context_tokens"] == 24576
                assert status["memory_plan"]["model"]["state_format"] == "bf16"
                assert status["prefill_chunk_tokens"] == 512
                assert status["identity"]["kv"]["format"] == "int8"
                listing = request(url, "/v1/models")
                assert ALIAS in [row["id"] for row in listing["data"]]
                report["checks"].append("model listing and runtime profile")
                plain = request(
                    url,
                    "/v1/chat/completions",
                    {
                        "model": ALIAS,
                        "temperature": 0,
                        "max_tokens": 64,
                        "messages": [
                            {
                                "role": "user",
                                "content": "What is 17 plus 25? Reply with only the number.",
                            }
                        ],
                    },
                )
                save(args.results / "chat.json", plain)
                assert plain["choices"][0]["message"]["content"].strip() == "42"
                report["checks"].append("chat completion")
                tool = request(
                    url,
                    "/v1/chat/completions",
                    {
                        "model": ALIAS,
                        "temperature": 0,
                        "max_tokens": 128,
                        "messages": [
                            {"role": "user", "content": "Call get_weather for Toronto."}
                        ],
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "description": "Get city weather",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {"city": {"type": "string"}},
                                        "required": ["city"],
                                        "additionalProperties": False,
                                    },
                                },
                            }
                        ],
                        "tool_choice": {
                            "type": "function",
                            "function": {"name": "get_weather"},
                        },
                    },
                )
                save(args.results / "tool.json", tool)
                call = tool["choices"][0]["message"]["tool_calls"][0]["function"]
                assert call["name"] == "get_weather"
                assert json.loads(call["arguments"])["city"] == "Toronto"
                report["checks"].append("forced tool call")
                final = request(url)
                save(args.results / "status-after.json", final)
                assert final["metal"]["healthy"]
                assert final["requests"]["failed"] == 0
                assert final["metrics"]["drafted_tokens"] > 0
                report["checks"].append("healthy Metal and active DFlash2 speculation")
                report["metrics"] = final["metrics"]
        except BaseException as error:
            report["error"] = repr(error)
            raise
        finally:
            stop(process)
            report["stopped"] = process.poll() is not None
            save(args.results / "report.json", report)
    print(
        json.dumps({"checks": report["checks"], "results": str(args.results)}, indent=2)
    )


if __name__ == "__main__":
    main()
