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
if mode=='timeout':
 print('runtime bootstrap failed [maximum_prefill]: maximum_prefill threw: Metal command 1095 failed: Caused GPU Timeout Error (00000002:kIOGPUCommandBufferCallbackErrorTimeout)',flush=True)
 sys.exit(1)
if mode in ('context_once', 'context_repeat') and (n==1 or mode=='context_repeat'):
 ceiling=os.environ.get('MOCK_CONTEXT_CEILING','114681')
 requested=sys.argv[sys.argv.index('--max-context')+1]
 print(f'23:49:12 Error · --max-context {requested} exceeds the {ceiling} tokens the model and --max-memory allow; omit it or pass at most {ceiling}',flush=True)
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
            "--expert-memory": "auto",
            "--max-memory": "10G",
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

    def test_option19_legacy_memory_and_larger_chunk_override(self):
        r = self.run_launcher(
            "19",
            SPLASH_QWEN36_IQ3_MAX_MEMORY="8G",
            SPLASH_QWEN36_IQ3_PREFILL_CHUNK_TOKENS="2048",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--max-memory": "8G",
            "--expert-memory": "1900M",
            "--prefill-chunk-tokens": "2048",
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value, flag)

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
            {"SPLASH_QWEN36_IQ3_PREFILL_CHUNK_TOKENS": "513"},
            {"SPLASH_QWEN36_IQ3_PREFILL_CHUNK_TOKENS": "4096"},
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
            env={**self.env, "SPLASH_HOST_MEM_BYTES": str(17179869184)},
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("20) Qwen3.8 Flash-Next GSQ-RCO IQ3_XXS", r.stdout)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")
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
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")
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
            "20",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS="1024",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")

    def test_option20_air_preserves_explicit_10g_cap(self):
        for cap in ("10G", "10.5G"):
            with self.subTest(cap=cap):
                r = self.run_launcher(
                    "20",
                    SPLASH_HOST_MEM_BYTES=str(17179869184),
                    SPLASH_FLASH_NEXT_MAX_MEMORY=cap,
                )
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                args = json.loads((self.root / "argv.json").read_text())
                self.assertEqual(args[args.index("--max-memory") + 1], cap)
                self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")

    def test_option20_streamed_memory_override_holds_cap_and_chunk(self):
        # A streamed store override holds the cap at 10G, and 10G cannot carry
        # 2,048-token chunks: the plan needs 10,940 MiB against a 10,240 MiB
        # budget and the engine refuses to start. The launcher therefore keeps
        # the chunk at 1,024 and now says so, instead of doing it silently.
        for name, value in (
            ("SPLASH_FLASH_NEXT_EXPERT_MEMORY", "4G"),
            ("SPLASH_FLASH_NEXT_PLE_MEMORY", "128M"),
        ):
            with self.subTest(setting=name):
                r = self.run_launcher(
                    "20",
                    SPLASH_HOST_MEM_BYTES=str(17179869184),
                    **{name: value},
                )
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                args = json.loads((self.root / "argv.json").read_text())
                self.assertEqual(args[args.index("--max-memory") + 1], "10G")
                self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")
                self.assertIn("keep the 16 GiB preset", r.stdout)

    def test_option20_streamed_memory_override_accepts_the_raised_cap_pair(self):
        # The measured safe pairing: a 10.8G cap with an explicit 2,048-token
        # chunk starts and serves (dev/benchmarks/option20-experiments).
        r = self.run_launcher(
            "20",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="4G",
            SPLASH_FLASH_NEXT_MAX_MEMORY="10.8G",
            SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS="2048",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")

    def test_option20_fractional_cap_validates_explicit_expert_budget(self):
        r = self.run_launcher(
            "20",
            SPLASH_FLASH_NEXT_MAX_MEMORY="10.8G",
            SPLASH_FLASH_NEXT_EXPERT_MEMORY="3G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")

    def test_option20_air_lower_memory_cap_keeps_smaller_prefill_chunk(self):
        r = self.run_launcher(
            "20",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_MAX_MEMORY="8G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")

    def test_option20_air_cache_disabled_keeps_smaller_prefill_chunk(self):
        r = self.run_launcher(
            "20",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
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

        # An explicit single lane uses the Air's new default cap and context.
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
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")

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

    def test_option21_uses_the_q2_model_the_local_draft_and_its_own_cache(self):
        df = self.root / "bin" / "df"
        df.write_text(
            "#!/bin/sh\n"
            "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
            "echo '/dev/disk9s1 1048576 1 41943040 0% /private/tmp'\n"
        )
        df.chmod(0o755)
        draft = self.root / "draft"
        draft.mkdir()
        (draft / "config.json").write_text("{}")
        (draft / "model.safetensors").write_text("draft weights")

        stock = self.run_launcher("20", SPLASH_HOST_MEM_BYTES=str(17179869184))
        self.assertEqual(stock.returncode, 0, stock.stdout + stock.stderr)
        stock_args = json.loads((self.root / "argv.json").read_text())
        self.assertNotIn("--draft-model", stock_args)
        stock_cache = stock_args[stock_args.index("--cache-dir") + 1]

        r = self.run_launcher(
            "21",
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(draft),
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--model": "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0",
            "--served-model-name": "qwen3.8-flash-next-q2-0-dflash2-bf16-splash",
            "--draft-model": str(draft),
            "--max-context": "131072",
            "--max-memory": "10.8G",
            "--ple-memory": "64M",
            "--prefill-chunk-tokens": "2048",
            "--kv-format": "int8",
            "--state-format": "bf16",
            "--max-cache-disk": str(2 * 1024**3),
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value)
        option21_cache = args[args.index("--cache-dir") + 1]
        self.assertTrue(
            option21_cache.endswith("flash-next-option21-q2-0-bf16-dflash2"),
            option21_cache,
        )
        self.assertNotEqual(option21_cache, stock_cache)

    def test_option22_streams_the_exact_gyro_with_an_isolated_cache(self):
        model = self.root / "gyro.gguf"
        with model.open("wb") as stream:
            stream.truncate(58487015808)
        result = self.run_launcher(
            "22",
            SPLASH_FLASH_NEXT_GYRO_MODEL=str(model),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            SPLASH_HOST_MEM_BYTES=str(17179869184),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        for flag, value in {
            "--model": str(model),
            "--served-model-name": "qwen3.8-flash-next-gyro-s-splash",
            "--draft-model": str(self.root / "bf16-draft"),
            "--prefill-chunk-tokens": "512",
            "--max-memory": "10G",
            "--expert-memory": "auto",
            "--ple-memory": "64M",
            "--max-active-requests": "1",
            "--max-cache-disk": str(2 * 1024**3),
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertTrue(
            args[args.index("--cache-dir") + 1].endswith("flash-next-option22-gyro-s")
        )

    def test_option22_rejects_partial_downloads_before_mutating_config(self):
        model = self.root / "gyro.gguf"
        before = self.config.read_bytes()
        for downloading in (False, True):
            with model.open("wb") as stream:
                stream.truncate(58487015808 if downloading else 128)
            if downloading:
                model.with_suffix(".gguf.aria2").write_bytes(b"download checkpoint")
            result = self.run_launcher("22", SPLASH_FLASH_NEXT_GYRO_MODEL=str(model))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("download is incomplete", result.stderr)
            self.assertEqual(self.config.read_bytes(), before)
            self.assertFalse((self.root / "attempts").exists())

    def test_option21_requires_the_cached_bf16_draft(self):
        r = self.run_launcher(
            "21", SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.root / "absent-draft")
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("BF16 DFlash2 draft", r.stderr)
        self.assertFalse((self.root / "argv.json").exists())

    def draft(self):
        draft = self.root / "bf16-draft"
        draft.mkdir(exist_ok=True)
        (draft / "config.json").write_text("{}")
        (draft / "model.safetensors").write_text("draft weights")
        return draft

    def test_option21_shares_the_raised_pair_option_20_uses(self):
        # The 16 GiB raise (10.8G with 2,048-token chunks) was measured on the
        # IQ3_XXS target, and it holds for the Q2_0 target with the BF16 draft
        # too: 443.7 against 282.3 tok/s cold prefill at 8,204 prompt tokens and
        # 441.4 against 272.2 at 4,108, with decode unchanged (17.56 against
        # 17.68 tok/s). See dev/benchmarks/qwen38-option21-chunk-2048-20261110.md.
        # A 2,048-token chunk puts about 4.6 s of GPU work inside one host step,
        # close to the engine's fixed 5,000 ms Metal event window, so the launch
        # loop keeps a fallback to 10G with 1,024-token chunks.
        host = str(17179869184)
        raised = self.run_launcher("20", SPLASH_HOST_MEM_BYTES=host)
        self.assertEqual(raised.returncode, 0, raised.stdout + raised.stderr)
        raised_args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(raised_args[raised_args.index("--max-memory") + 1], "10.8G")
        self.assertEqual(
            raised_args[raised_args.index("--prefill-chunk-tokens") + 1], "2048"
        )

        r = self.run_launcher(
            "21",
            SPLASH_HOST_MEM_BYTES=host,
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")
        self.assertEqual(args[args.index("--max-active-requests") + 1], "1")
        self.assertIn(
            "Option 21 profile: 10.8G Metal cap with 2048-token prefill chunks",
            r.stdout,
        )
        self.assertIn(
            "retries with 10G and 1,024-token chunks",
            r.stdout,
        )

        listed = subprocess.run(
            ["bash", LAUNCHER, "--list"],
            env={**self.env, "SPLASH_HOST_MEM_BYTES": host},
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        menu = listed.stdout.split("20) Qwen3.8 Flash-Next", 1)[1]
        option20 = menu.split("21) Qwen3.8", 1)[0]
        self.assertIn("10.8G Metal cap", option20)
        self.assertIn("2048-token prefill chunks", option20)
        option21 = listed.stdout.split("21) Qwen3.8 Flash-Next", 1)[1]
        self.assertIn("10.8G Metal cap", option21)
        self.assertIn("2048-token prefill chunks", option21)
        self.assertIn("retries with 10G and 1,024-token chunks", option21)

    def test_option21_falls_back_to_the_stock_chunk_after_a_warmup_timeout(self):
        # The 2,048-token warmup has one documented failure mode: a host step
        # over the engine's fixed 5,000 ms Metal event window, which kills
        # bootstrap with "Caused GPU Timeout Error". The launcher retries that
        # attempt once with 10G and 1,024-token chunks instead of exiting.
        r = self.run_launcher(
            "21",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            MOCK_MODE="timeout",
            SPLASH_BONSAI_STARTUP_RETRY_DELAY="1",
        )
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")
        self.assertEqual(args[args.index("--max-memory") + 1], "10G")
        self.assertEqual(args[args.index("--draft-model") + 1], str(self.draft()))
        self.assertIn("tripped the engine's 5 s Metal event window", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_option21_default_context_retries_at_measured_ceiling(self):
        r = self.run_launcher(
            "21", SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            MOCK_MODE="context_once",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.root / "attempts").read_text(), "2")
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-context") + 1], "114681")
        self.assertEqual(args[args.index("--draft-model") + 1], str(self.draft()))
        config = json.loads(self.config.read_text())
        model = config["provider"]["local-llama"]["models"]["qwen3.8-flash-next-q2-0-dflash2-bf16-splash"]
        self.assertEqual(model["limit"], {"context": 112633, "output": 1024})
        self.assertIn("retrying once with server_context=114681", r.stdout)

    def test_option21_context_fallback_is_bounded(self):
        r = self.run_launcher(
            "21", SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            MOCK_MODE="context_repeat",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual((self.root / "attempts").read_text(), "2")

    def test_option21_context_fallback_preserves_explicit_limits(self):
        for overrides in (
            {"SPLASH_FLASH_NEXT_MAX_CONTEXT": "131072"},
            {"SPLASH_FLASH_NEXT_OPENCODE_CONTEXT": "120000"},
            {"MOCK_CONTEXT_CEILING": "3000"},
        ):
            with self.subTest(overrides=overrides):
                (self.root / "attempts").unlink(missing_ok=True)
                r = self.run_launcher(
                    "21", SPLASH_HOST_MEM_BYTES=str(17179869184),
                    SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
                    MOCK_MODE="context_once", **overrides,
                )
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual((self.root / "attempts").read_text(), "1")

    def test_option21_explicit_raised_pair_still_reaches_the_engine(self):
        # The stock pair is the default, not a ceiling: both settings given
        # explicitly still reach the engine, so the raising experiment is one
        # command away.
        r = self.run_launcher(
            "21",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            SPLASH_FLASH_NEXT_MAX_MEMORY="10.8G",
            SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS="2048",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "10.8G")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "2048")

    def test_option21_explicit_cap_outside_the_stock_set_keeps_the_chunk(self):
        # The chunk raise needs the whole stock profile. A cap the preset never
        # uses (12G) leaves the chunk at its default, so a raised store or an
        # off-profile cap does not silently put 4.6 s of GPU work inside one
        # host step next to the 5 s Metal event window.
        r = self.run_launcher(
            "21",
            SPLASH_HOST_MEM_BYTES=str(17179869184),
            SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
            SPLASH_FLASH_NEXT_MAX_MEMORY="12G",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--max-memory") + 1], "12G")
        self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")

    def test_option21_streamed_override_note_names_the_pair_it_holds(self):
        # A streamed expert or PLE store holds the cap at 10G and the chunk at
        # 1,024 tokens, and the note for both options says how to get the
        # 16 GiB preset back.
        for name, value in (
            ("SPLASH_FLASH_NEXT_EXPERT_MEMORY", "4G"),
            ("SPLASH_FLASH_NEXT_PLE_MEMORY", "128M"),
        ):
            with self.subTest(setting=name):
                r = self.run_launcher(
                    "21",
                    SPLASH_HOST_MEM_BYTES=str(17179869184),
                    SPLASH_FLASH_NEXT_DFLASH2_MODEL=str(self.draft()),
                    **{name: value},
                )
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                args = json.loads((self.root / "argv.json").read_text())
                self.assertEqual(args[args.index("--max-memory") + 1], "10G")
                self.assertEqual(args[args.index("--prefill-chunk-tokens") + 1], "1024")
                self.assertIn("keep the 16 GiB preset", r.stdout)
                self.assertNotIn("option 21 holds that pair", r.stdout)

    def test_failed_startup_drains_the_log_without_a_bash_job_error(self):
        # bash 3.2 cannot wait on a process substitution, so the launcher used
        # to end every startup attempt with
        # "wait: pid N is not a child of this shell" and drained nothing: the
        # engine's last lines could land in the log after the launcher's own.
        # Stopping the pressure watchdog and the monitor also used to `pkill -P`
        # their outstanding sleeps, which made bash append
        # "Terminated: 15 sleep ..." to the run log on every shutdown.
        logs = self.root / "logs"
        r = self.run_launcher("14", MOCK_MODE="memory")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("not a child of this shell", r.stdout + r.stderr)
        self.assertNotIn("Terminated", r.stdout + r.stderr)
        written = sorted(logs.glob("*-*.log"))
        self.assertTrue(written)
        text = "\n".join(path.read_text() for path in written)
        self.assertNotIn("not a child of this shell", text)
        self.assertNotIn("Terminated", text)
        engine_line = text.index("not enough free memory to start")
        launcher_line = text.index("Splash startup needs more free memory")
        self.assertLess(engine_line, launcher_line)

    def test_option20_ple_row_cache_default_and_override_reach_the_engine(self):
        r = self.run_launcher("20")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--ple-memory") + 1], "64M")

        r = self.run_launcher("20", SPLASH_FLASH_NEXT_PLE_MEMORY="192M")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(args[args.index("--ple-memory") + 1], "192M")

    def test_option20_rejects_a_ple_row_cache_below_the_engine_minimum(self):
        r = self.run_launcher("20", SPLASH_FLASH_NEXT_PLE_MEMORY="8M")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SPLASH_FLASH_NEXT_PLE_MEMORY", r.stderr)
        self.assertFalse((self.root / "argv.json").exists())

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
        for args in (["--hermes", "20"], ["--direct", "23"], ["--direct", "9x"]):
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
        drained = (self.root / "out").read_text()
        self.assertIn("Clean shutdown and cache flush", drained)
        # The shutdown must not lean on bash job notices: no
        # "wait: pid N is not a child of this shell" for the log writer, and no
        # "Terminated: 15 sleep ..." for the watchdog or monitor sleeps.
        self.assertNotIn("not a child of this shell", drained)
        self.assertNotIn("Terminated", drained)
        pid = int((self.root / "server.pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
