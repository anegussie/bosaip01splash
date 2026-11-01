# Option 20: Flash-Next GSQ-RCO IQ3_XXS

The profile in `/Users/mymac/startllamacpp.sh` selects `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, with the matching `incoai/Qwen3.8-Flash-Next-DFlash2` draft selected by Splash. It is a text-only profile for the 16 GiB M5. The model downloads on its first real launch, approximately 75.8 GB plus the draft.

```sh
bash /Users/mymac/startllamacpp.sh --direct 20
```

Interactive menu selection `20` starts the same profile. Like the other direct Splash choices, it refuses to launch when the selected port is occupied. Downloads default to the internal home-directory Hugging Face cache, and the prefix cache and logs use a separate option-20 name.

| Setting | Default |
|---|---|
| Server context | 32,761 tokens (32K allocation minus 7 speculative tokens) |
| OpenCode context | 30,713 tokens |
| OpenCode output reserve | 1,024 tokens |
| Reasoning effort | medium |
| Metal memory cap | 8 GiB |
| Expert and PLE stores | shared expert arena; 64 MiB PLE cache |
| KV / recurrent state | INT8 / BF16 |
| Requested prefill chunk | 1,024 tokens, one Flash-Next chunk at a time |
| Active requests | 1 |
| Prefix cache | disabled by default |
| Input | text only |

Reasoning requests use temperature 1.0 and top-p 0.95 in the synchronized OpenCode profile. Selecting `none` uses temperature 0.7 and top-p 0.80. Existing explicit worker temperatures are preserved. The compaction variant requests no reasoning and at most 2,048 output tokens.

Overrides are independent of the option-18 and option-19 variables:

- `SPLASH_FLASH_NEXT_MAX_CONTEXT`: 4,096-32,761 tokens, default `32761`.
- `SPLASH_FLASH_NEXT_OPENCODE_CONTEXT`: `auto` (server minus 2,048) or a smaller integer context.
- `SPLASH_FLASH_NEXT_MAX_TOKENS`: positive and smaller than the client context; default 1,024; output is reduced automatically for very small contexts.
- `SPLASH_FLASH_NEXT_MAX_MEMORY`: `8G`, `9G`, `10G`, or `11G`.
- `SPLASH_FLASH_NEXT_REASONING_EFFORT`: `none`, `low`, `medium`, or `xhigh`.
- `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`: `0` through `8G`, default `0`.
- `SPLASH_FLASH_NEXT_PERSISTENT_CACHE`: `0` or `1`, default `1`.
- `SPLASH_FLASH_NEXT_CACHE_DIR`: default `~/Library/Caches/Splash/flash-next-option20-iq3-xxs`.
- `SPLASH_FLASH_NEXT_HF_HUB_CACHE`: absolute download-cache path; default `~/.cache/huggingface/hub`, overriding a different inherited `HF_HUB_CACHE` for this profile.

For a smaller first-run context:

```sh
SPLASH_FLASH_NEXT_MAX_CONTEXT=8K bash /Users/mymac/startllamacpp.sh --direct 20
```

Menu selection, direct selection, default and override arguments, reasoning/sampling synchronization, output reservation, validation failures, occupied-port handling, and existing Splash profiles are covered by `dev/benchmarks/test_bonsai_launcher.py`. These checks use mock servers and isolated temporary configuration. Runtime memory fit and inference throughput require a separate real-model run; the defaults are not a no-swap guarantee.

On 2026-10-31, all 25 launcher tests passed. Both real argument parsers accepted the captured option-20 command, and the selected GGUF headers at revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09` passed format screening and native `model-check`. The two selected shards total 75,839,998,528 bytes. The production runtime was rebuilt with `make -j4 all`; the full model weights were not downloaded or loaded during launcher setup.

The reproducible launcher change is [startllamacpp-option20.patch](startllamacpp-option20.patch). Apply it only to the matching pre-option-20 launcher, after inspecting the diff.

The 8 GiB configuration uses a smaller Flash-Next prefill arena and PLE cache alongside the shared expert arena. This lowers I/O reuse and may reduce prefill and decode speed. The live 4K run reached Ready with a 7.60 GiB planner minimum and returned the requested marker correctly. Full evidence is in `build/validation/option20-10g/8g-status.json` and the smoke response. This is an engine planner budget, not a total process RSS or no-swap guarantee.

The 32K context fits within the memory planner limit reported at 8 GiB. Filled-32K inference performance has not been measured.

The 32K allocation reserves seven speculative rows, leaving a maximum context of 32,761 tokens under the 8 GiB plan. The launcher uses that exact integer to avoid startup rejection.

The latest scratch-sizing revision and 1,024-token default are documented in [the scratch and chunk report](qwen38-option20-scratch-20261101.md). It passed a 28,589-token live request under the same 8 GiB cap.
