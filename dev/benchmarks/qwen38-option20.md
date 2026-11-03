# Option 20: Flash-Next GSQ-RCO IQ3_XXS

The profile in `/Users/mymac/startllamacpp.sh` selects `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, with the matching `incoai/Qwen3.8-Flash-Next-DFlash2` draft selected by Splash. It is a text-only profile for the 16 GiB M5. The model downloads on its first real launch, approximately 75.8 GB plus the draft.

```sh
bash /Users/mymac/startllamacpp.sh --direct 20
```

Interactive menu selection `20` starts the same profile. Like the other direct Splash choices, it refuses to launch when the selected port is occupied. Downloads default to the internal home-directory Hugging Face cache, and the prefix cache and logs use a separate option-20 name.

| Setting | Default |
|---|---|
| Server context | 131,072 tokens (the 128K allocation, accepted by the 10 GiB plan) |
| OpenCode context | 129,024 tokens |
| OpenCode output reserve | 1,024 tokens |
| Reasoning effort | low |
| Metal memory cap | 10 GiB (the engine's own ceiling on a 16 GB Mac is about 10.8 GiB) |
| Expert and PLE stores | shared expert arena at its 1,992 MiB floor under `--expert-memory auto`; 64 MiB PLE cache |
| KV / recurrent state | INT8 / BF16 |
| Requested prefill chunk | 1,024 tokens, one Flash-Next chunk at a time |
| Active requests | 1 (option 20 accepts 2 on a machine with room for a second lane) |
| Prefix cache | 8 GiB disk quota, persistent, in its own option-20 directory |
| Input | text only |

Reasoning requests use temperature 1.0 and top-p 0.95 in the synchronized OpenCode profile. Selecting `none` uses temperature 0.7 and top-p 0.80. Existing explicit worker temperatures are preserved. The compaction variant requests no reasoning and at most 2,048 output tokens.

Overrides are independent of the option-18 and option-19 variables:

- `SPLASH_FLASH_NEXT_MAX_CONTEXT`: 4,096-131,072 tokens, default `131072`.
- `SPLASH_FLASH_NEXT_OPENCODE_CONTEXT`: `auto` (server minus 2,048) or a smaller integer context.
- `SPLASH_FLASH_NEXT_MAX_TOKENS`: positive and smaller than the client context; default 1,024; output is reduced automatically for very small contexts.
- `SPLASH_FLASH_NEXT_MAX_MEMORY`: `8G`, `9G`, `10G`, `11G`, `12G`, `16G`, `20G`, `24G`, `32G`, `40G`, `48G`, or `56G`, default `10G`. The launcher refuses a cap that would leave the Mac less than the 2-7 GiB cushion macOS keeps for itself (7% of unified memory), and prints the automatic ceiling when the cap is larger than the engine's own budget, which on a 16 GB Mac is about 10.8 GiB.
- `SPLASH_FLASH_NEXT_EXPERT_MEMORY`: `auto` (default) or a size from `512M` to `8G` for the routed experts' store floor.
- `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS`: 128-2048 in steps of 128, default `1024`.
- `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS`: `1` (default) or `2`. A second active request is admitted only when the machine can carry a second lane: 24 GB or more of unified memory above 65,536 context tokens, 16 GB or more at 65,536 or below.
- `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`: `0` through `8G`, default `8G`. The launcher refuses a quota larger than the free space on the volume that holds the cache.
- `SPLASH_FLASH_NEXT_REASONING_EFFORT`: `none`, `low`, `medium`, or `xhigh`.
- `SPLASH_FLASH_NEXT_PERSISTENT_CACHE`: `0` or `1`, default `1`.
- `SPLASH_FLASH_NEXT_CACHE_DIR`: default `~/Library/Caches/Splash/flash-next-option20-iq3-xxs`.
- `SPLASH_FLASH_NEXT_HF_HUB_CACHE`: absolute download-cache path; default `~/.cache/huggingface/hub`, overriding a different inherited `HF_HUB_CACHE` for this profile.

For a smaller first-run context:

```sh
SPLASH_FLASH_NEXT_MAX_CONTEXT=8K bash /Users/mymac/startllamacpp.sh --direct 20
```

For a bigger expert store on a machine that has the memory for it:

```sh
SPLASH_FLASH_NEXT_MAX_MEMORY=16G SPLASH_FLASH_NEXT_EXPERT_MEMORY=4G \
  bash /Users/mymac/startllamacpp.sh --direct 20
```

The ranked performance plan, its restart-gated experiments, and the measured
reason a larger memory cap alone does not help a 16 GB Mac are in
`qwen38-option20-todo-20261103.md`.

Menu selection, direct selection, default and override arguments, reasoning/sampling synchronization, output reservation, validation failures, occupied-port handling, and existing Splash profiles are covered by `dev/benchmarks/test_bonsai_launcher.py`. These checks use mock servers and isolated temporary configuration. Runtime memory fit and inference throughput require a separate real-model run; the defaults are not a no-swap guarantee.

On 2026-10-31, all 25 launcher tests passed. Both real argument parsers accepted the captured option-20 command, and the selected GGUF headers at revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09` passed format screening and native `model-check`. The two selected shards total 75,839,998,528 bytes. The production runtime was rebuilt with `make -j4 all`; the full model weights were not downloaded or loaded during launcher setup.

The launcher defaults later moved to 131,072 context, a 10 GiB cap and `low` reasoning effort without the launcher tests being updated, which left 3 of the 25 option-20 checks failing in the tree. Those expectations now match the launcher again and all 25 pass.

The reproducible launcher change is [startllamacpp-option20.patch](startllamacpp-option20.patch). Apply it only to the matching pre-option-20 launcher, after inspecting the diff.

The 8 GiB configuration was the original option-20 plan. It used a smaller Flash-Next prefill arena and PLE cache alongside the shared expert arena, which lowers I/O reuse and reduces prefill and decode speed. The live 4K run reached Ready with a 7.60 GiB planner minimum and returned the requested marker correctly. Full evidence is in `build/validation/option20-10g/8g-status.json` and the smoke response. This is an engine planner budget, not a total process RSS or no-swap guarantee.

Under that 8 GiB plan the 32K allocation reserved seven speculative rows, which is where the 32,761 ceiling came from, and the launcher used that exact integer to avoid startup rejection. The plan behind the current 10 GiB cap reports `memory_plan.maximum_context_tokens` 204,793 on this 16 GiB M5 against a model maximum of 262,144, so the launcher ceiling is now 131,072 and the 32,761 number is history. Filled-32K inference performance was measured on 2026-11-01 at 179.65 tok/s prefill and 11.9 tok/s decode, and remains the fastest context setting measured so far.

The latest scratch-sizing revision and 1,024-token default are documented in [the scratch and chunk report](qwen38-option20-scratch-20261101.md). It passed a 28,589-token live request under the same 8 GiB cap.

The 131,072-token instance was measured live on 2026-11-02 in [the 131k live report](qwen38-option20-live-131k-20261102.md). Long prefill there is about 10 percent slower than the same chunk profile at 32,761 context (161.02 against 179.65 tok/s at 28,589 prompt tokens, TTFT 177.55 s against 159.17 s) while decode is unchanged at 11.9 tok/s, so the 1,024-token chunk default deserves a re-sweep at the larger served context. DFlash2 acceptance measured 99 to 100 percent on structured output and 72.3 percent on reasoning-on agent output, and a 65,451-token request prefilled at 156.09 tok/s with no capacity or Metal failure.

The follow-up work is ordered in [the tuning plan](qwen38-option20-tuning-plan-20261102.md). It states that decode on this target is SSD-bound (1,154 expert tensors and 2.25 GB read per decode cycle, `hit_rate` 0), that cached prefixes cut a 28,505-token TTFT from 185.47 s to 1.80 s, and lists seven single-variable restart experiments E1 to E7 with acceptance criteria.

The same configuration was measured a second time on 2026-11-02 evening, on the running instance, in [the evening rerun report](qwen38-option20-live-131k-evening-20261102.md). Long prefill fell a further 6 to 7 percent against the morning run on the same build (149.47 against 161.02 tok/s at 28,589 tokens, 146.66 against 156.09 at 65,367) with decode unchanged at 10.8 to 11.6 tok/s, the governor again refused growth (168 denied reservations, 29.5 MB of host spare), and the cold-then-repeat prefix probe reused nothing this time (0 cached tokens, TTFT 6.14 s against 5.70 s) because the instance keeps one state entry, has no disk cache and evicted 84 states. These results support E1 (serve 32,761 instead of 131,072) and E5 (turn the SSD prefix cache on) as the next two runs.

Machine scaling, 2026-11-03: [qwen38-option20-machine-scaling-20261103.md](qwen38-option20-machine-scaling-20261103.md) measures why this profile is fast and slow on this box, 36.1 streamed expert megabytes per prompt token and 452 per emitted token against an SSD supplying 3.6 to 6.3 GB/s, so both phases run at the storage ceiling rather than a compute ceiling. From those two constants it derives throughput for the M5 Air at 16 and 32 GB, M5 Pro 48 GB, M5 Max 36 GB, and Mac mini M5 Pro 64 GB, at today's flags and with a tuned expert store, and shows the cache arithmetic that decides whether extra RAM buys 1.4x or 3x: 263 expert slots per GiB of store at 3.89 MiB per slot, full residency needing about 93 GiB, and 25 to 51 reuses for one cached tile to break even against a 5.89 GB/s stream.
