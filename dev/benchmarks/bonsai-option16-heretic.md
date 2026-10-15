# Bonsai Heretic, launcher option 16

Installed 2026-10-15 in `/Users/mymac/startllamacpp.sh`. Launch interactively
with option 16, or directly:

```bash
bash /Users/mymac/startllamacpp.sh --direct 16
```

The downloaded file was copied into the same directory as option 14's target:

```text
/Users/mymac/.cache/huggingface/hub/models--prism-ml--Ternary-Bonsai-2-27B-gguf/snapshots/b072e1d3b35a0a630cece372c2127528e0994386/Ternary-Bonsai-2-27B-Uncensored-Heretic-PTQ1_0.gguf
```

Both source and copy are 5,946,648,928 bytes, with SHA-256
`a18c3e17da397838305522b3ee877f9d2cbf4facd04ba01a394b22f3f3a477be`.
The original option-14 GGUF remains selected by its original model ID.

Option 16 selects the local file directly. Splash derives its configuration,
tokenizer and chat template from that GGUF, verifies its supported family and
851 tensor entries, and records its own file digest in a separate assembly.
A local source is checked again at each start, including when its content
changes at the same path. It cannot silently fall back to the original model.

- API alias: `bonsai-heretic-27b-splash`.
- Server context: 24,576; OpenCode context: 22,528; output reserve: 1,024.
- INT8 KV, BF16 state, 512-token prefill chunks, one active request.
- Cache: `~/Library/Caches/Splash/bonsai-option16`, requested quota 8 GiB;
  Splash bounds the effective quota using available disk space.
- Log: `~/.local/state/llama-server/bonsai-heretic-27b-splash-latest.log`.
- Overrides: `SPLASH_HERETIC_MODEL` and `SPLASH_HERETIC_CACHE_DIR`; the shared
  `SPLASH_BONSAI_*` runtime settings also apply.
- DFlash2: the supported Qwen3.8-27B family draft is active. Compatibility and
  successful generation do not establish its performance on altered weights.

The external launcher edit is retained as `startllamacpp-option16.patch`,
applicable to the launcher version before option 16 was added.

## Validation

`make check-python check-source` passed, including the complete Python suite,
Ruff checks, formatting, and the architecture check. All 10 external launcher
tests passed; 32 final focused parser/selection tests also passed.

The real installed launcher passed model listing, arithmetic chat completion,
and a forced `get_weather` tool call at the default 24K context on port 1236.
The runtime reported healthy Metal, zero failed requests, and active DFlash2
speculation. The test used isolated OpenCode configuration and prefix cache;
the primary option-14 server stayed online with its weights released. A guard
would stop the test if the primary received work. The test server then stopped.
This is a functional smoke test, not a representative performance benchmark.

Reproduce while the primary is stopped or idle with its weights released:

```bash
.venv/bin/python dev/benchmarks/bonsai_option16_smoke.py \
  --results build/validation/option16-heretic-new-run
```

Raw evidence: `build/validation/option16-heretic-20261015-retry/`.
The smoke test uses the cached draft offline. Normal launcher runs can resolve
the draft through the Hub, following the existing option-14 behavior.
