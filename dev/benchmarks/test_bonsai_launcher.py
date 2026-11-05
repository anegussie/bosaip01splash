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
(root/'environment.json').write_text(json.dumps({'HF_HUB_CACHE':os.environ.get('HF_HUB_CACHE')}))
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
                name.startswith(
                    ("SPLASH_BONSAI_", "SPLASH_QWEN36_", "SPLASH_FLASH_NEXT_")
                )
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
            {"SPLASH_QWEN36_MAX_CACHE_DISK": "65G"},
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
            "--max-context": "80K",
            "--expert-memory": "1900M",
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
        self.assertNotIn("--language-only", args)
        self.assertEqual(args[args.index("--max-image-pixels") + 1], "1048576")
        config = json.loads(self.config.read_text())
        self.assertEqual(config["model"], "local-llama/qwen3.6-35b-a3b-iq3-xxs-splash")
        self.assertEqual(
            config["provider"]["local-llama"]["models"][
                "qwen3.6-35b-a3b-iq3-xxs-splash"
            ]["limit"],
            {"context": 79872, "output": 4096},
        )
        self.assertEqual(config["compaction"]["buffer"], 4096)
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
            {"SPLASH_QWEN36_IQ3_MAX_CONTEXT": "81K"},
            {"SPLASH_QWEN36_IQ3_OPENCODE_CONTEXT": "81920"},
            {"SPLASH_QWEN36_IQ3_MAX_TOKENS": "79872"},
            {"SPLASH_QWEN36_IQ3_MAX_CACHE_DISK": "65G"},
            {"SPLASH_QWEN36_IQ3_PERSISTENT_CACHE": "2"},
        ):
            with self.subTest(overrides=overrides):
                r = self.run_launcher("19", **overrides)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.config.read_bytes(), before)
                self.assertFalse((self.root / "attempts").exists())

    def test_option20_defaults_are_independent_and_enable_reasoning(self):
        config = json.loads(self.config.read_text())
        config["agent"]["context_worker"] = {
            "model": "local-llama/old",
            "temperature": 0.4,
        }
        self.config.write_text(json.dumps(config))
        r = self.run_launcher(
            "20",
            SPLASH_QWEN36_MAX_CONTEXT="invalid",
            SPLASH_QWEN36_IQ3_MAX_CONTEXT="invalid",
            SPLASH_BONSAI_MAX_CONTEXT="invalid",
            SPLASH_BONSAI_STATE_FORMAT="fp32",
            SPLASH_BONSAI_MAX_ACTIVE_REQUESTS="3",
            SPLASH_HOST_MEM_BYTES=str(25769803776),
            HF_HUB_CACHE="/Volumes/Untitled/unwanted-inherited-cache",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--model": "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS",
            "--served-model-name": "qwen3.8-flash-next-iq3-xxs-splash",
            "--max-context": "131072",
            "--max-memory": "10G",
            "--expert-memory": "auto",
            "--ple-memory": "64M",
            "--kv-format": "int8",
            "--state-format": "bf16",
            "--prefill-chunk-tokens": "1024",
            "--max-active-requests": "2",
            "--default-reasoning-effort": "low",
            "--max-cache-disk": "17179869184",
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value, flag)
        self.assertIn("--language-only", args)
        self.assertIn("--persistent-cache", args)
        self.assertIn("--cache-dir", args)
        environment = json.loads((self.root / "environment.json").read_text())
        self.assertEqual(
            environment["HF_HUB_CACHE"],
            str(pathlib.Path.home() / ".cache/huggingface/hub"),
        )
        config = json.loads(self.config.read_text())
        alias = "qwen3.8-flash-next-iq3-xxs-splash"
        self.assertEqual(config["model"], "local-llama/" + alias)
        model = config["provider"]["local-llama"]["models"][alias]
        self.assertEqual(model["limit"], {"context": 129024, "output": 1024})
        self.assertEqual(model["modalities"], {"input": ["text"], "output": ["text"]})
        self.assertTrue(model["reasoning"])
        self.assertEqual(
            model["variants"]["bounded-compaction"]["reasoning_effort"], "none"
        )
        self.assertEqual(config["agent"]["general"]["reasoningEffort"], "low")
        self.assertEqual(config["agent"]["general"]["temperature"], 1.0)
        self.assertEqual(config["agent"]["general"]["top_p"], 0.95)
        self.assertEqual(config["agent"]["context_worker"]["temperature"], 0.4)
        self.assertEqual(config["compaction"]["buffer"], 1024)
        self.assertIn("reasoning=low", r.stdout)
        self.assertTrue((self.root / f"logs/{alias}-latest.log").is_symlink())

    def test_option20_interactive_and_help(self):
        r = subprocess.run(
            ["bash", LAUNCHER],
            input="20\n",
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("20) Qwen3.8 Flash-Next GSQ-RCO IQ3_XXS", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10G")
        for flag in ("--list", "--help"):
            r = subprocess.run(
                ["bash", LAUNCHER, flag],
                env=self.env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("20", r.stdout)

    def test_option20_overrides_and_reasoning_off(self):
        hub = self.root / "internal-model-cache"
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_CONTEXT="32761",
            SPLASH_FLASH_NEXT_OPENCODE_CONTEXT="28672",
            SPLASH_FLASH_NEXT_MAX_TOKENS="3072",
            SPLASH_FLASH_NEXT_MAX_MEMORY="9G",
            SPLASH_FLASH_NEXT_REASONING_EFFORT="none",
            SPLASH_FLASH_NEXT_MAX_CACHE_DISK="0",
            SPLASH_FLASH_NEXT_HF_HUB_CACHE=str(hub),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-context") + 1], "32761")
        self.assertEqual(args[args.index("--max-memory") + 1], "9G")
        self.assertEqual(args[args.index("--default-reasoning-effort") + 1], "none")
        self.assertNotIn("--persistent-cache", args)
        self.assertNotIn("--cache-dir", args)
        environment = json.loads((self.root / "environment.json").read_text())
        self.assertEqual(environment["HF_HUB_CACHE"], str(hub))
        config = json.loads(self.config.read_text())
        model = config["provider"]["local-llama"]["models"][
            "qwen3.8-flash-next-iq3-xxs-splash"
        ]
        self.assertEqual(model["limit"], {"context": 28672, "output": 3072})
        self.assertEqual(config["agent"]["general"]["reasoningEffort"], "none")
        self.assertEqual(config["agent"]["general"]["temperature"], 0.7)
        self.assertEqual(config["agent"]["general"]["top_p"], 0.8)

    def test_option20_small_context_reserves_output(self):
        r = self.run_launcher("20", SPLASH_FLASH_NEXT_MAX_CONTEXT="4K")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config = json.loads(self.config.read_text())
        model = config["provider"]["local-llama"]["models"][
            "qwen3.8-flash-next-iq3-xxs-splash"
        ]
        self.assertEqual(model["limit"], {"context": 2048, "output": 1024})

    def test_option20_invalid_settings_preserve_config(self):
        before = self.config.read_bytes()
        for name, values in {
            "SPLASH_FLASH_NEXT_MAX_CONTEXT": ["132097", "0", "999999999999999K"],
            "SPLASH_FLASH_NEXT_OPENCODE_CONTEXT": ["131072", "016384"],
            "SPLASH_FLASH_NEXT_MAX_TOKENS": ["129024", "0"],
            "SPLASH_FLASH_NEXT_MAX_MEMORY": ["7G", "auto", "57G", "10g"],
            "SPLASH_FLASH_NEXT_REASONING_EFFORT": ["invalid", "HIGH"],
            "SPLASH_FLASH_NEXT_MAX_CACHE_DISK": ["65G", "-1"],
            "SPLASH_FLASH_NEXT_PERSISTENT_CACHE": ["2"],
            "SPLASH_FLASH_NEXT_EXPERT_MEMORY": ["invalid", "256M", "33G", "9G"],
            "SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS": ["100", "3072", "auto"],
            "SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS": ["0", "3"],
            "SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE": ["invalid", "2"],
            "SPLASH_FLASH_NEXT_HF_HUB_CACHE": ["relative/cache"],
        }.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    r = self.run_launcher("20", **{name: value})
                    self.assertNotEqual(r.returncode, 0)
                    self.assertEqual(self.config.read_bytes(), before)
                    self.assertFalse((self.root / "attempts").exists())

    def test_option20_air_defaults_to_one_request_and_keeps_prefix_cache(self):
        r = self.run_launcher("20", SPLASH_HOST_MEM_BYTES=str(17179869184))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "1")
        self.assertEqual(args[args.index("--max-context") + 1], "131072")
        self.assertEqual(args[args.index("--max-memory") + 1], "10G")
        self.assertEqual(args[args.index("--ple-memory") + 1], "64M")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")
        self.assertEqual(args[args.index("--max-cache-disk") + 1], "17179869184")
        self.assertIn("--persistent-cache", args)
        self.assertIn("--cache-dir", args)
        listed = subprocess.run(
            ["bash", LAUNCHER, "--list"],
            env={**self.env, "SPLASH_HOST_MEM_BYTES": str(17179869184)},
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        option20 = listed.stdout.split("20) Qwen3.8 Flash-Next", 1)[1]
        self.assertIn("one active request", option20)
        self.assertNotIn("two active requests", option20)


    def test_option20_air_preserves_explicit_smaller_prefill_chunk(self):
        r = self.run_launcher(
            "20", SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS="1024",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")

    def test_option20_air_lower_memory_cap_keeps_smaller_prefill_chunk(self):
        r = self.run_launcher(
            "20", SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_MAX_MEMORY="8G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")


    def test_option20_air_cache_disabled_keeps_smaller_prefill_chunk(self):
        r = self.run_launcher(
            "20", SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_MAX_CACHE_DISK="0",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")
        self.assertNotIn("--persistent-cache", args)

    def test_option20_second_active_request_needs_memory_for_its_lane(self):
        # Macs below 24 GB default to one request instead of competing for
        # expert SSD reads. Explicit two-lane requests still require 16 GB.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="10G",
            SPLASH_HOST_MEM_BYTES=str(12884901888),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("One active request on a 12 GB Mac", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "1")

        # Asking for a second lane below 16 GB is refused.
        (self.root / "attempts").unlink(missing_ok=True)
        before = self.config.read_bytes()
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_FLASH_NEXT_MAX_CONTEXT="32768",
            SPLASH_HOST_MEM_BYTES=str(12884901888),
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("second active request", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

        # 16 GB is enough for a second lane at 65,536 context tokens, and needs no note.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_FLASH_NEXT_MAX_CONTEXT="65536",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("below the 24 GB gate", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "2")
        self.assertEqual(args[args.index("--max-context") + 1], "65536")

        # 24 GB admits the second lane at the full 131,072 context, with no note.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_HOST_MEM_BYTES=str(25769803776),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("below the 24 GB gate", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "2")

    def test_option20_second_lane_below_the_gate_is_an_explicit_override(self):
        # A second lane on 16 GB remains available explicitly, with its
        # host-headroom requirement announced at the large context.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("below the 24 GB gate", r.stdout)
        self.assertIn("memory_governor.growth_allowed", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "2")
        self.assertEqual(args[args.index("--max-context") + 1], "131072")

        # An explicit single-lane override preserves the chosen cap and context.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="1",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("below the 24 GB gate", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-active-requests") + 1], "1")
        self.assertEqual(args[args.index("--max-context") + 1], "131072")
        self.assertEqual(args[args.index("--max-memory") + 1], "10G")

        # Setting the gate back to 0 restores the 24 GB rule.
        (self.root / "attempts").unlink(missing_ok=True)
        before = self.config.read_bytes()
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE="0",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("second active request", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

        # The 16 GB floor never moves.
        before = self.config.read_bytes()
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS="2",
            SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE="1",
            SPLASH_FLASH_NEXT_MAX_CONTEXT="32768",
            SPLASH_HOST_MEM_BYTES=str(12884901888),
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("second active request", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)

        # A bad override value is rejected before the engine is reached.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE="2",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(
            "SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE must be 0 or 1",
            r.stdout + r.stderr,
        )
        self.assertEqual(self.config.read_bytes(), before)

    def test_option20_expert_memory_and_chunk_overrides_reach_the_engine(self):
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="3G",
            SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS="2048",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--expert-memory") + 1], "3G")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")

    def test_option20_larger_expert_store_and_cache_quota_reach_the_engine(self):
        df = self.root / "bin" / "df"
        df.write_text(
            "#!/bin/sh\n"
            "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
            "echo '/dev/disk9s1 1048576 1 41943040 0% /private/tmp'\n"
        )
        df.chmod(0o755)
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="11G",
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="4G",
            SPLASH_FLASH_NEXT_MAX_CACHE_DISK="16G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("over half the 11G cap", r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "11G")
        self.assertEqual(args[args.index("--expert-memory") + 1], "4G")
        self.assertEqual(args[args.index("--max-cache-disk") + 1], "17179869184")

        # A store over half the cap is allowed, and says what it costs the KV pool.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="11G",
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="6G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("over half the 11G cap", r.stdout + r.stderr)

    def test_option20_expert_memory_leaving_too_little_of_the_cap_is_rejected(self):
        before = self.config.read_bytes()
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="10G",
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="9G",
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("leaves less than 2G of the 10G Metal cap", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

    def test_option20_memory_cap_is_bounded_by_the_hosts_own_needs(self):
        before = self.config.read_bytes()
        # 16 GB cannot promise 16G of Metal memory and still keep its cushion.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="16G",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("it keeps for macOS", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

        # A 12G cap on a 16 GB Mac is admitted but names the automatic ceiling.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="12G",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("automatic Metal ceiling", r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "12G")

        # A 32 GB Mac takes a 20G cap without the ceiling note.
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="20G",
            SPLASH_HOST_MEM_BYTES=str(34359738368),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("automatic Metal ceiling", r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "20G")

    def test_option20_cache_quota_larger_than_free_disk_is_rejected(self):
        before = self.config.read_bytes()
        df = self.root / "bin" / "df"
        df.write_text(
            "#!/bin/sh\n"
            "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
            "echo '/dev/disk9s1 1048576 1 1048576 0% /private/tmp'\n"
        )
        df.chmod(0o755)
        r = self.run_launcher("20")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SSD cache quota", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

    def test_option20_occupied_port_preserves_config(self):
        (self.root / "bin/lsof").write_text("#!/bin/sh\nexit 0\n")
        before = self.config.read_bytes()
        r = self.run_launcher("20")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already in use", r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.root / "attempts").exists())

    def test_option20_rejects_hermes_and_out_of_range_selection(self):
        before = self.config.read_bytes()
        for args in (["--hermes", "20"], ["--direct", "21"]):
            r = subprocess.run(
                ["bash", LAUNCHER, *args],
                env=self.env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
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
            "SPLASH_BONSAI_MAX_CACHE_DISK": ["65G", "-1", "8GB"],
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
