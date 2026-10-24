#!/usr/bin/env python3
"""Test the external Splash launcher profiles using a mock server and temporary config.

Run with OPTION14_LAUNCHER=/path/to/startllamacpp.sh python3 this_file.py.
"""

import json
import os
import pathlib
import signal
import subprocess
import tempfile
import time
import unittest

LAUNCHER = os.environ.get("OPTION14_LAUNCHER", "/Users/mymac/startllamacpp.sh")


class Option14(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="option14-", dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        tools = self.root / "bin"
        tools.mkdir()
        for name in ("curl", "lsof"):
            p = tools / name
            p.write_text("#!/bin/sh\nexit 1\n")
            p.chmod(0o755)
        self.mock = self.root / "server.py"
        self.mock.write_text("""#!/usr/bin/env python3
import json,os,signal,sys,time
from pathlib import Path
root=Path(os.environ['MOCK_ROOT'])
count=root/'attempts'
n=int(count.read_text())+1 if count.exists() else 1
count.write_text(str(n))
(root/'argv.json').write_text(json.dumps(sys.argv[1:]))
(root/'server.pid').write_text(str(os.getpid()))
mode=os.environ.get('MOCK_MODE','exit')
if mode=='memory':
 print('runtime bootstrap failed: not enough free memory to start',flush=True)
 sys.exit(1)
if mode=='error':
 print('Metal backend failed',flush=True)
 sys.exit(2)
if mode=='hold':
 def stop(*_):
  (root/'stopped').write_text('TERM received')
  print('Clean shutdown and cache flush',flush=True)
  sys.exit(0)
 signal.signal(signal.SIGTERM,stop)
 while True: time.sleep(.1)
print('Ready test server',flush=True)
""")
        self.mock.chmod(0o755)
        self.config = self.root / "opencode.json"
        self.config.write_text(
            json.dumps(
                {
                    "provider": {"local-llama": {"options": {}, "models": {}}},
                    "agent": {"general": {"model": "local-llama/old"}},
                }
            )
        )
        self.env = {
            **os.environ,
            "PATH": str(tools) + ":" + os.environ["PATH"],
            "SPLASH_BIN": str(self.mock),
            "MOCK_ROOT": str(self.root),
            "LLAMA_LOG_DIR": str(self.root / "logs"),
            "OPENCODE_CONFIG_PATH": str(self.config),
            "SPLASH_BONSAI_STARTUP_RETRY_DELAY": "1",
        }
        for name in list(self.env):
            if (
                name.startswith(("SPLASH_BONSAI_", "SPLASH_QWEN36_"))
                and name != "SPLASH_BONSAI_STARTUP_RETRY_DELAY"
            ):
                del self.env[name]

    def run_launcher(self, choice="14", **overrides):
        return subprocess.run(
            ["bash", LAUNCHER, "--direct", choice],
            env={**self.env, **overrides},
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_default_wiring(self):
        r = self.run_launcher()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertIn("--persistent-cache", args)
        self.assertEqual(args[args.index("--state-format") + 1], "bf16")
        self.assertEqual(args[args.index("--max-context") + 1], "24K")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "512")
        self.assertEqual(args[args.index("--max-cache-disk") + 1], "8589934592")
        config = json.loads(self.config.read_text())
        self.assertEqual(
            config["provider"]["local-llama"]["models"]["bonsai-27b-splash"]["limit"],
            {"context": 22528, "output": 4096},
        )
        self.assertEqual(config["compaction"]["keep"]["tokens"], 1536)
        self.assertEqual(config["compaction"]["buffer"], 4096)

    def test_output_override_updates_compaction_reserve(self):
        r = self.run_launcher(SPLASH_BONSAI_MAX_TOKENS="1024")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config = json.loads(self.config.read_text())
        self.assertEqual(
            config["provider"]["local-llama"]["models"]["bonsai-27b-splash"]["limit"][
                "output"
            ],
            1024,
        )
        self.assertEqual(config["compaction"]["buffer"], 1024)

    def test_option16_uses_local_weights_and_separate_alias_cache_and_log(self):
        model = self.root / "Heretic model.gguf"
        model.write_bytes(b"GGUF")
        cache = self.root / "heretic-cache"
        r = self.run_launcher(
            "16", SPLASH_HERETIC_MODEL=str(model), SPLASH_HERETIC_CACHE_DIR=str(cache)
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--model") + 1], str(model))
        self.assertEqual(args[args.index("--cache-dir") + 1], str(cache))
        self.assertEqual(
            args[args.index("--served-model-name") + 1], "bonsai-heretic-27b-splash"
        )
        config = json.loads(self.config.read_text())
        self.assertEqual(config["model"], "local-llama/bonsai-heretic-27b-splash")
        self.assertIn(
            "Uncensored Heretic",
            config["provider"]["local-llama"]["models"]["bonsai-heretic-27b-splash"][
                "name"
            ],
        )
        self.assertTrue(
            (self.root / "logs/bonsai-heretic-27b-splash-latest.log").is_symlink()
        )

    def test_option16_missing_model_fails_before_config_mutation(self):
        before = self.config.read_bytes()
        r = self.run_launcher(
            "16", SPLASH_HERETIC_MODEL=str(self.root / "missing.gguf")
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

    def test_option18_streaming_and_independent_profile(self):
        cache = self.root / "qwen-cache"
        r = self.run_launcher(
            "18",
            SPLASH_QWEN36_CACHE_DIR=str(cache),
            SPLASH_BONSAI_MAX_CONTEXT="24K",
            SPLASH_BONSAI_MAX_TOKENS="4096",
            SPLASH_BONSAI_STATE_FORMAT="fp32",
            SPLASH_BONSAI_MAX_ACTIVE_REQUESTS="3",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--model": "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL",
            "--served-model-name": "qwen3.6-35b-a3b-q2-splash",
            "--max-context": "24K",
            "--expert-memory": "auto",
            "--max-memory": "8G",
            "--kv-format": "int8",
            "--state-format": "bf16",
            "--max-active-requests": "1",
            "--prefill-chunk-tokens": "512",
            "--max-cache-disk": "2147483648",
            "--cache-dir": str(cache),
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value, flag)
        self.assertIn("--language-only", args)
        self.assertIn("--persistent-cache", args)
        config = json.loads(self.config.read_text())
        self.assertEqual(config["model"], "local-llama/qwen3.6-35b-a3b-q2-splash")
        self.assertEqual(
            config["provider"]["local-llama"]["models"]["qwen3.6-35b-a3b-q2-splash"][
                "limit"
            ],
            {"context": 22528, "output": 2048},
        )
        self.assertEqual(config["compaction"]["buffer"], 2048)
        self.assertTrue(
            (self.root / "logs/qwen3.6-35b-a3b-q2-splash-latest.log").is_symlink()
        )

    def test_option18_menu_and_interactive_selection(self):
        r = subprocess.run(
            ["bash", LAUNCHER],
            input="18\n",
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("18) Qwen3.6 35B A3B UD-Q2_K_XL", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--expert-memory") + 1], "auto")

    def test_option18_overrides_and_cache_opt_out(self):
        r = self.run_launcher(
            "18",
            SPLASH_QWEN36_MAX_CONTEXT="16K",
            SPLASH_QWEN36_OPENCODE_CONTEXT="12288",
            SPLASH_QWEN36_MAX_TOKENS="3072",
            SPLASH_QWEN36_MAX_CACHE_DISK="0",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-context") + 1], "16K")
        self.assertNotIn("--persistent-cache", args)
        self.assertNotIn("--cache-dir", args)
        config = json.loads(self.config.read_text())
        self.assertEqual(
            config["provider"]["local-llama"]["models"]["qwen3.6-35b-a3b-q2-splash"][
                "limit"
            ],
            {"context": 12288, "output": 3072},
        )

    def test_option18_invalid_context_and_output_do_not_mutate_config(self):
        before = self.config.read_bytes()
        for overrides in (
            {"SPLASH_QWEN36_MAX_CONTEXT": "25K"},
            {"SPLASH_QWEN36_OPENCODE_CONTEXT": "24576"},
            {"SPLASH_QWEN36_MAX_TOKENS": "22528"},
            {"SPLASH_QWEN36_MAX_CACHE_DISK": "9G"},
            {"SPLASH_QWEN36_PERSISTENT_CACHE": "2"},
        ):
            with self.subTest(overrides=overrides):
                r = self.run_launcher("18", **overrides)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.config.read_bytes(), before)
                self.assertFalse((self.root / "attempts").exists())

    def test_option19_iq3_profile_is_independent_of_option18(self):
        r = self.run_launcher(
            "19",
            SPLASH_QWEN36_MAX_CONTEXT="invalid",
            SPLASH_QWEN36_MAX_TOKENS="invalid",
            SPLASH_QWEN36_PERSISTENT_CACHE="0",
            SPLASH_QWEN36_CACHE_DIR=str(self.root / "option18-cache"),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--model": "unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS",
            "--served-model-name": "qwen3.6-35b-a3b-iq3-xxs-splash",
            "--max-context": "24K",
            "--expert-memory": "auto",
            "--max-memory": "8G",
            "--kv-format": "int8",
            "--state-format": "bf16",
            "--max-active-requests": "1",
            "--prefill-chunk-tokens": "512",
            "--max-cache-disk": "2147483648",
            "--default-reasoning-effort": "none",
            "--cache-dir": str(
                pathlib.Path.home() / "Library/Caches/Splash/qwen36-option19-iq3-xxs"
            ),
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value, flag)
        self.assertIn("--persistent-cache", args)
        self.assertIn("--language-only", args)
        config = json.loads(self.config.read_text())
        self.assertEqual(config["model"], "local-llama/qwen3.6-35b-a3b-iq3-xxs-splash")
        self.assertEqual(
            config["provider"]["local-llama"]["models"][
                "qwen3.6-35b-a3b-iq3-xxs-splash"
            ]["limit"],
            {"context": 22528, "output": 2048},
        )
        self.assertEqual(config["compaction"]["buffer"], 2048)
        self.assertTrue(
            (self.root / "logs/qwen3.6-35b-a3b-iq3-xxs-splash-latest.log").is_symlink()
        )

    def test_option19_interactive_selection_and_overrides(self):
        r = subprocess.run(
            ["bash", LAUNCHER],
            input="19\n",
            env={
                **self.env,
                "SPLASH_QWEN36_IQ3_MAX_CONTEXT": "16K",
                "SPLASH_QWEN36_IQ3_OPENCODE_CONTEXT": "12288",
                "SPLASH_QWEN36_IQ3_MAX_TOKENS": "3072",
                "SPLASH_QWEN36_IQ3_MAX_CACHE_DISK": "0",
            },
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("19) Qwen3.6 35B A3B UD-IQ3_XXS", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-context") + 1], "16K")
        self.assertNotIn("--persistent-cache", args)
        self.assertNotIn("--cache-dir", args)
        config = json.loads(self.config.read_text())
        self.assertEqual(
            config["provider"]["local-llama"]["models"][
                "qwen3.6-35b-a3b-iq3-xxs-splash"
            ]["limit"],
            {"context": 12288, "output": 3072},
        )

    def test_option19_invalid_settings_do_not_mutate_config(self):
        before = self.config.read_bytes()
        for overrides in (
            {"SPLASH_QWEN36_IQ3_MAX_CONTEXT": "25K"},
            {"SPLASH_QWEN36_IQ3_OPENCODE_CONTEXT": "24576"},
            {"SPLASH_QWEN36_IQ3_MAX_TOKENS": "22528"},
            {"SPLASH_QWEN36_IQ3_MAX_CACHE_DISK": "9G"},
            {"SPLASH_QWEN36_IQ3_PERSISTENT_CACHE": "2"},
        ):
            with self.subTest(overrides=overrides):
                r = self.run_launcher("19", **overrides)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.config.read_bytes(), before)
                self.assertFalse((self.root / "attempts").exists())

    def test_state_and_chunk_overrides(self):
        r = self.run_launcher(
            SPLASH_BONSAI_STATE_FORMAT="fp32",
            SPLASH_BONSAI_PREFILL_CHUNK_TOKENS="1024",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--state-format") + 1], "fp32")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")
        self.assertIn("state=fp32 prefill_chunk=1024", r.stdout)

    def test_smaller_context_auto_sync(self):
        r = self.run_launcher(SPLASH_BONSAI_MAX_CONTEXT="4K")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config = json.loads(self.config.read_text())
        self.assertEqual(
            config["provider"]["local-llama"]["models"]["bonsai-27b-splash"]["limit"][
                "context"
            ],
            2048,
        )
        self.assertEqual(config["compaction"]["keep"]["tokens"], 512)
        self.assertEqual(config["compaction"]["buffer"], 1024)

    def test_cache_opt_out(self):
        for overrides in (
            {"SPLASH_BONSAI_PERSISTENT_CACHE": "0"},
            {"SPLASH_BONSAI_MAX_CACHE_DISK": "0"},
        ):
            with self.subTest(overrides=overrides):
                r = self.run_launcher(**overrides)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn(
                    "--persistent-cache",
                    json.loads((self.root / "argv.json").read_text()),
                )

    def test_bad_overrides_fail_before_mutation(self):
        before = self.config.read_bytes()
        for name, values in {
            "SPLASH_BONSAI_MAX_CONTEXT": [
                "25K",
                "18446744073709555712",
                "999999999999999999999999K",
            ],
            "SPLASH_BONSAI_OPENCODE_CONTEXT": [
                "24576",
                "012288",
                "18446744073709551618",
            ],
            "SPLASH_BONSAI_PREFILL_CHUNK_TOKENS": ["129", "18446744073709551744"],
            "SPLASH_BONSAI_STATE_FORMAT": ["fp16", "BF16", "auto"],
            "SPLASH_BONSAI_STARTUP_MAX_RETRIES": ["4", "-1"],
            "SPLASH_BONSAI_PERSISTENT_CACHE": ["2"],
            "SPLASH_BONSAI_MAX_CACHE_DISK": ["9G", "-1", "8GB"],
        }.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    r = self.run_launcher(**{name: value})
                    self.assertNotEqual(r.returncode, 0)
                    self.assertEqual(self.config.read_bytes(), before)
                    self.assertFalse((self.root / "attempts").exists())

    def test_bounded_memory_retries(self):
        r = self.run_launcher(MOCK_MODE="memory")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual((self.root / "attempts").read_text(), "3")
        self.assertIn("stopped after 2 retries", r.stdout)

    def test_runtime_error_no_retry(self):
        r = self.run_launcher(MOCK_MODE="error")
        self.assertEqual(r.returncode, 2)
        self.assertEqual((self.root / "attempts").read_text(), "1")

    def test_term_reaches_server_and_drains_logs(self):
        with (self.root / "out").open("w") as out:
            p = subprocess.Popen(
                ["bash", LAUNCHER, "--direct", "14"],
                env={**self.env, "MOCK_MODE": "hold"},
                stdout=out,
                stderr=out,
            )
            try:
                deadline = time.monotonic() + 8
                while (
                    not (self.root / "server.pid").exists()
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                self.assertTrue((self.root / "server.pid").exists())
                time.sleep(0.2)
                p.send_signal(signal.SIGTERM)
                self.assertEqual(p.wait(timeout=8), 143)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
        self.assertTrue((self.root / "stopped").exists())
        self.assertIn("Clean shutdown and cache flush", (self.root / "out").read_text())
        pid = int((self.root / "server.pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
