# Option 20: Flash-Next GSQ-RCO IQ3_XXS

Latest planning update: [revised estimates for all six Macs](qwen38-option20-mac-rebase-20261105.md), based on the November 5 2,048-chunk measurements. The combined prefill and generation table is below and in the [performance documentation](../../docs/performance.md#option-20-mac-performance). Larger-Mac scenarios require explicit chunk, memory and active-request overrides.

The profile in `/Users/mymac/startllamacpp.sh` selects `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, with the matching `incoai/Qwen3.8-Flash-Next-DFlash2` draft selected by Splash. It is a text-only profile for the 16 GiB M5. The model downloads on its first real launch, approximately 75.8 GB plus the draft.

```sh
bash /Users/mymac/startllamacpp.sh --direct 20
```

Interactive menu selection `20` starts the same profile. Like the other direct Splash choices, it refuses to launch when the selected port is occupied. Downloads default to the internal home-directory Hugging Face cache, and the prefix cache and logs use a separate option-20 name.

| Setting | Default |
|---|---|
| Server context | 131,072 tokens |
| OpenCode context | 129,024 tokens |
| OpenCode output reserve | 1,024 tokens |
| Reasoning effort | low |
| Metal memory cap | 10.8 GiB for the validated 16 GiB preset; 10 GiB for other presets (the engine's ceiling on this 16 GB Mac is about 10.8 GiB) |
| Expert and PLE stores | automatic expert memory (the measured Air store is 1.946 GiB including staging); 64 MiB PLE row cache with the table on SSD |
| KV / recurrent state | INT8 / BF16 |
| Requested prefill chunk | 2,048 for the validated 16 GiB preset; 1,024 for other presets; explicit overrides win |
| Active requests | 1 below 24 GB; 2 on larger Macs. Explicit two-request overrides remain available on 16 GB, subject to headroom |
| Prefix cache | 16 GiB disk quota, persistent, in its own option-20 directory |
| Input | text only |

## Prefill and generation estimates for all six Macs

PP is cold prefill around 30K prompt tokens; TPS is short-code generation.
All rates are tokens per second. Only the **16 GB Air IQ3_XXS** figures are
measured; every other figure is a conditional planning estimate.

| Mac | IQ3_XXS PP | IQ3_XXS TPS | Q2_0 PP | Q2_0 TPS |
| --- | ---: | ---: | ---: | ---: |
| M5 Air 16 GB, 8-core GPU | **241** | **8.81-8.92** | 260-330 | 10-13 |
| M5 Air 32 GB | 250-360 | 11-16 | 320-500 | 14-22 |
| M6 mini 32 GB | 250-360 | 11-16 | 320-500 | 14-22 |
| M5 Pro mini 48 GB, 16-core GPU | 290-530 | 15-25 | 410-770 | 22-40 |
| M5 Pro mini 64 GB, 16-core GPU | 600-900 | 35-60 | 850-1,150 | 65-90 |
| M5 Max Studio 128 GB, 40-core GPU | 1,200-1,800 | 70-110 | 1,600-2,300 | 100-150 |

The Air's 241 PP measurement used 2,048 chunks and a 10G cap; the generation
figures are means from two separate short-code baseline blocks. The current
10.8G preset was validated separately. Larger-Mac estimates assume explicit
2,048 chunks, one active request and larger memory caps. The 64 GB and Studio
fast ranges assume near/full expert residency. The cautious 64 GB IQ3 planning
point remains about 500 PP and 30 TPS. Q2_0 is an unmeasured alternative;
option 20 selects IQ3_XXS. No generation uplift or filled-131K performance is
established by these estimates.

The [full rebase report](qwen38-option20-mac-rebase-20261105.md) records the
transfer assumptions, requested caps, expert allocations and source evidence.

## Launcher settings and earlier cache evidence

Historically, measured on 2026-11-03 with the 8 GiB quota live
(`qwen38-option20-v1-20261103.md`): a 28,589-token prompt costs 185-192 seconds
cold and 1.2 seconds when its KV is read back from the disk tier, and cold
prefill and decode are unchanged. The spill freed about 1 GiB of Metal memory and
lifted host spare above the 2.15 GiB the memory governor reserves for macOS.

Reasoning requests use temperature 1.0 and top-p 0.95 in the synchronized OpenCode profile. Selecting `none` uses temperature 0.7 and top-p 0.80. Existing explicit worker temperatures are preserved. The compaction variant requests no reasoning and at most 2,048 output tokens.

Overrides are independent of the option-18 and option-19 variables:

- `SPLASH_FLASH_NEXT_MAX_CONTEXT`: 4,096-131,072 tokens, default `131072`.
- `SPLASH_FLASH_NEXT_OPENCODE_CONTEXT`: `auto` (server minus 2,048) or a smaller integer context.
- `SPLASH_FLASH_NEXT_MAX_TOKENS`: positive and smaller than the client context; default 1,024; output is reduced automatically for very small contexts.
- `SPLASH_FLASH_NEXT_MAX_MEMORY`: `8G`, `9G`, `10G`, `10.5G`, `10.8G`, `11G`, `12G`, `16G`, `20G`, `24G`, `32G`, `40G`, `48G`, or `56G`. Default `10.8G` for the 16 GiB/131K/automatic-expert/single-request/16G-persistent-cache preset; `10G` otherwise. Explicit caps are preserved. `10.8G` is 11,596,411,699 whole bytes. The launcher refuses a cap that would leave the Mac less than the 2-7 GiB cushion macOS keeps for itself (7% of unified memory), and prints the automatic ceiling when the cap is larger than the engine's own budget, about 10.8 GiB on this 16 GB Mac. With 2,048-token prefill, the allocation bound is 180,217 at 10.8G, 155,641 at 10.5G and 114,681 at 10G. These allocation bounds exclude the SSD tier's admission reserves. At 10.5G, actual resident admission held about 128,416 tokens before output projection, and a 130,733-token request still selected spill. The earlier 1,024-chunk measurements in `qwen38-option20-v5c-20261104.md` use less scratch and have different resident limits.
- `SPLASH_FLASH_NEXT_EXPERT_MEMORY`: `auto` (default) or a size from `512M` to `32G`. The size sets the **least** RAM for streamed routed experts. Both `auto` and an explicit size let the cap take what the memory plan leaves; the size fixes the floor the store can shrink to. The launcher rejects a size that leaves less than 2G of the Metal cap for weights, KV and state, and says so when the store is over half the cap.
- `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS`: 128-2048 in steps of 128. Automatic default `2048` for the validated 16 GiB/10G-or-10.5G-or-10.8G/131K/automatic-expert/single-request/16G-persistent-cache preset; `1024` otherwise. Explicit values are preserved.
- `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS`: `1` or `2`; when unset, defaults to `1` below 24 GB and `2` on larger Macs. Explicit `2` is allowed from 16 GB where the context gate permits it, and is rejected below 16 GB. The menu and direct launch resolve the same host default. Options 14, 16, 18 and 19 remain single-lane.
- `SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE`: `0` or `1`, default `1`. For an explicit `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2` override, this admits a second request on a Mac with at least 16 GB at any context the profile allows, with a host-memory notice above 65,536 tokens on 16-23 GB machines. Setting it to `0` restores the 24 GB admission gate above 65,536 tokens; 16 GB remains enough at smaller contexts. Admission does not guarantee execution: the engine still requires `memory_governor.growth_allowed`. On this 16 GB M5, growth needs 3.00 GiB host spare (1 GiB above the 2.00 GiB macOS reserve), or 4.00 GiB to reopen after pressure. V4, V5 and V5c admitted two requests but serialized their work with browser-class apps open. V5b at the 9G cap proved overlap after Chrome and LM Studio were quit: the child queued 11 s instead of 165-186 s, and the first `b2` decode batches appeared (`qwen38-option20-v5b-20261104.md`). Two requests decoding together each ran at about half speed (5.17 tok/s against 11.4-11.9 alone). The chosen 10G cap with browser-class apps closed combines V5's resident KV allowance with V5b's host-headroom finding; that combination was chosen without a separate measured V5e row.
- `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`: `0` through `64G`, default `16G`. The launcher refuses a quota larger than the free space on the volume that holds the cache, with a message that says to lower the quota or free disk space. The default was 8G until 2026-11-03: a few long benchmark prompts filled that quota (`used_bytes` 8,547,762,176 of 8,589,934,592) and 16G then filled too (`used_bytes` 17,165,451,264 of 17,179,869,184 with 13.42 GiB of cache taken back over 12,553 KV blocks) against 67 GB free on this Mac, so a long-context workflow wants the 16G default and a heavier one wants more.
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

On this 16 GB Mac that command buys nothing at 131,072 context, and `2G` and `4G` behave the same:
the plan sizes the resident KV allowance against the model's 262,144-token window (startup line
`resident 262137`, 3.47 GiB of `kv_capacity_bytes`), and the store is then rounded down to its
1,992 MiB floor of 512 slots, with `growth_allowed` false at runtime because the host has no spare
against its 2.15 GiB reserve. The flag raises a floor, not a ceiling. Measurements in
`qwen38-option20-v2-20261103.md` and `qwen38-option20-v3-20261103.md`.

## Current 16 GB Air defaults (2026-11-05)

Option 20 admits **one active request by default on hosts below 24 GB**. The current validated 16 GiB preset uses 131,072-token server context, 129,024-token OpenCode context, a 10.8 GiB cap, 16 GiB persistent prefix-cache quota, automatic expert memory, 2,048-token prefill chunks, INT8 KV, BF16 state, low reasoning and the 64 MiB PLE row cache. The full n-gram table remains on SSD. `verify-rows auto` remains the engine default. Other presets retain 10G/1,024-chunk defaults; explicit overrides win. The earlier [single-request profile validation](qwen38-option20-air-profile-20261104.md) used 10G and 1,024 chunks before the November 5 tuning and budget changes.

This prevents an additional client from becoming a competing active request on a memory-constrained host. It does not establish faster isolated generation, and it deliberately queues delegated requests behind the current request. An explicit `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2` retains the prior opt-in behavior; 24 GB and larger hosts retain their two-request default.

The smaller-context recommendation remains an explicit workload choice, preserving the validated 131K default. To try 64K when the workload fits:

```sh
SPLASH_FLASH_NEXT_MAX_CONTEXT=65536 bash /Users/mymac/startllamacpp.sh --direct 20
```

This override synchronizes the OpenCode context to 63,488 tokens. It is not a measured speedup. The persistent cache stays enabled; keeping the system/tools and other long prompt prefixes stable across turns lets it reuse their KV and recurrent state. Prefix reuse improves prompt latency, not the SSD-bound decode rate. Changing context leaves the validated preset, so set `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048` explicitly to retain the larger chunk. No throughput improvement is established for that combination.

The [November 5 single-request performance run](qwen38-option20-air-performance-20261105.md) measures three cold/reuse pairs at 4K and 28.6K, one pair at 65.4K, and repeated short coding/reasoning probes. It preserves full raw evidence and does not establish a controlled speedup from the request-admission change.

## Historical two-request configuration on this 16 GB M5 (2026-11-04)

The V1 to V5c series previously selected a two-request configuration. Its measurements below are historical; reproduce that configuration explicitly with:

```sh
SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 bash /Users/mymac/startllamacpp.sh --direct 20
```

That is 131,072 context, a 10 GiB Metal cap, a 16 GiB persistent prefix cache, `--expert-memory auto`,
a 1,024-token prefill chunk, BF16 state, `--verify-rows auto`, and two active requests. Expect a
28,589-token cold prompt in about 172 s (166 tok/s), the same prompt in about 1.1 s once its KV is in
the cache, and 11.7 to 11.9 tok/s of decode at 7.4 to 7.5 tokens per draft cycle, based on V5.
V5b measured a delegated child starting about 10 s into a running parent at the 9G cap after Chrome
and LM Studio were closed. Prompt child execution at the chosen 10G cap remains conditional on host
headroom and has no separate measured row. Keep those apps closed when using delegation; a held
second request still waits when host memory is too tight. Set
`SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=1` to return to one lane.

Rejected on measurement, all at 131,072 context on this Mac:

| Setting | Measured result |
|---|---|
| `MAX_MEMORY=11G` | slowest cold prefill (150.7-161.0 tok/s), host spare 1.83 GiB, headroom peak 0.26 GiB |
| `MAX_MEMORY=9G` | fastest cold prefill (174.6-183.0 tok/s) but resident KV 114,681 tokens, below the served 131,072, and headroom peak 0.52 GiB - worse than 10G, because the spill floors cost 669 MiB plus a 409 MiB hot block cache plus 145 MiB of staging |
| `EXPERT_MEMORY=2G` or `4G` | no change: the store stays at its 1,992 MiB floor of 512 slots |
| `MAX_CACHE_DISK=8G` | fills during long-context work; 16G pays for itself in restored cache (`qwen38-option20-v3-20261103.md`) |
| one active request | a delegated child queues 165-186 s behind the parent, which is what ended three subagent runs on timeout |

The series is closed. V3b was not run; the 1,024-token chunk stays. V6 quantization reduction remains
an untried lever for decode speed and needs a new experiment reason and correctness checks before
speed testing. More RAM can ease the host-memory constraint and permit a larger expert store.

The ranked performance plan, its restart-gated experiments, and the measured
reason a larger memory cap alone does not help a 16 GB Mac are in
`qwen38-option20-todo-20261103.md`.

Menu selection, direct selection, default and override arguments, reasoning/sampling synchronization, output reservation, validation failures, occupied-port handling, and existing Splash profiles are covered by `dev/benchmarks/test_bonsai_launcher.py`. These checks use mock servers and isolated temporary configuration. Runtime memory fit and inference throughput require a separate real-model run; the defaults are not a no-swap guarantee.

On 2026-10-31, all 25 launcher tests passed. Both real argument parsers accepted the captured option-20 command, and the selected GGUF headers at revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09` passed format screening and native `model-check`. The two selected shards total 75,839,998,528 bytes. The production runtime was rebuilt with `make -j4 all`; the full model weights were not downloaded or loaded during launcher setup.

The launcher defaults later moved to 131,072 context, a 10 GiB cap and `low` reasoning effort without the launcher tests being updated, which left 3 of the 25 option-20 checks failing in the tree. Those expectations now match the launcher again and all 25 pass.

The reproducible launcher change is [startllamacpp-option20.patch](startllamacpp-option20.patch). Apply it only to the matching pre-option-20 launcher, after inspecting the diff.

The 8 GiB configuration was the original option-20 plan. It used a smaller Flash-Next prefill arena and PLE cache alongside the shared expert arena, which lowers I/O reuse and reduces prefill and decode speed. The live 4K run reached Ready with a 7.60 GiB planner minimum and returned the requested marker correctly. Full evidence is in `build/validation/option20-10g/8g-status.json` and the smoke response. This is an engine planner budget, not a total process RSS or no-swap guarantee.

Under that 8 GiB plan the 32K allocation reserved seven speculative rows, which is where the 32,761 ceiling came from, and the launcher used that exact integer to avoid startup rejection. The later 10 GiB plan reported `memory_plan.maximum_context_tokens` 204,793 on this 16 GiB M5 against a model maximum of 262,144, allowing the launcher ceiling to rise to 131,072. Filled-32K inference performance was measured on 2026-11-01 at 179.65 tok/s prefill and 11.9 tok/s decode. These are historical measurements; the current 2,048-chunk results are recorded above.

The November 1 scratch-sizing revision and then-current 1,024-token default are documented in [the scratch and chunk report](qwen38-option20-scratch-20261101.md). It passed a 28,589-token live request under the same 8 GiB cap.

The 131,072-token instance was measured live on 2026-11-02 in [the 131k live report](qwen38-option20-live-131k-20261102.md). Long prefill there is about 10 percent slower than the same chunk profile at 32,761 context (161.02 against 179.65 tok/s at 28,589 prompt tokens, TTFT 177.55 s against 159.17 s) while decode is unchanged at 11.9 tok/s, so the 1,024-token chunk default deserves a re-sweep at the larger served context. DFlash2 acceptance measured 99 to 100 percent on structured output and 72.3 percent on reasoning-on agent output, and a 65,451-token request prefilled at 156.09 tok/s with no capacity or Metal failure.

The follow-up work is ordered in [the tuning plan](qwen38-option20-tuning-plan-20261102.md). It states that decode on this target is SSD-bound (1,154 expert tensors and 2.25 GB read per decode cycle, `hit_rate` 0), that cached prefixes cut a 28,505-token TTFT from 185.47 s to 1.80 s, and lists seven single-variable restart experiments E1 to E7 with acceptance criteria.

The same configuration was measured a second time on 2026-11-02 evening, on the running instance, in [the evening rerun report](qwen38-option20-live-131k-evening-20261102.md). Long prefill fell a further 6 to 7 percent against the morning run on the same build (149.47 against 161.02 tok/s at 28,589 tokens, 146.66 against 156.09 at 65,367) with decode unchanged at 10.8 to 11.6 tok/s, the governor again refused growth (168 denied reservations, 29.5 MB of host spare), and the cold-then-repeat prefix probe reused nothing this time (0 cached tokens, TTFT 6.14 s against 5.70 s) because the instance keeps one state entry, has no disk cache and evicted 84 states. These results support E1 (serve 32,761 instead of 131,072) and E5 (turn the SSD prefix cache on) as the next two runs.

Machine scaling, 2026-11-03: [qwen38-option20-machine-scaling-20261103.md](qwen38-option20-machine-scaling-20261103.md) measures why this profile is fast and slow on this box, 36.1 streamed expert megabytes per prompt token and 452 per emitted token against an SSD supplying 3.6 to 6.3 GB/s, so both phases run at the storage ceiling rather than a compute ceiling. From those two constants it derives throughput for the M5 Air at 16 and 32 GB, M5 Pro 48 GB, M5 Max 36 GB, and Mac mini M5 Pro 64 GB, at today's flags and with a tuned expert store, and shows the cache arithmetic that decides whether extra RAM buys 1.4x or 3x: 263 expert slots per GiB of store at 3.89 MiB per slot, full residency needing about 93 GiB, and 25 to 51 reuses for one cached tile to break even against a 5.89 GB/s stream.

## Expert-retention experiment, November 5, 2026

Two retention prototypes passed bitwise Metal correctness and real-serving cache checks, but neither established a speedup. The revised coding probes averaged 8.37 tok/s on the baseline and 7.98 tok/s on the candidate, with substantial variability. Candidate expert hits reached 3.82%, while SSD reads per decode token rose from 690.29 to 707.03 MB. The active binary/profile were preserved and the experimental runtime changes removed.

[All 50 serving rows, memory accounting and limitations](qwen38-option20-expert-retention-20261105.md) and the [tested prototype patch](qwen38-option20-expert-retention-20261105.patch) are saved for review. These results do not justify increasing other-device estimates.

## Prefill and read-ahead tuning, November 5, 2026

The validated 16 GiB preset uses 2,048-token prefill chunks. Matched cold-prefill means improved from 202.88 to 400.28 tok/s at 4,019 tokens and from 170.16 to 241.00 tok/s at 28,589 tokens. These are repeated-filler workloads; decode is not claimed to improve. Four decode read-ahead workers and 512 KiB pieces are retained because two workers and 256 KiB pieces were slower in their comparisons.

In this tuning experiment, shared prefill scratch rose from 0.572 to 1.571 GiB, while the expert-store cap remained 1.946 GiB including staging. The tested engine cap was 10 GiB and the served context was 131,072. Requests above its approximately 114K resident-KV bound used the existing SSD KV tier. A 130,733-token initial-code recall request passed cold, immediate-reuse and persisted-restart checks. The subsequent budget increases below raise the current default to 10.8 GiB. Explicit chunk overrides, lower caps, cache-disabled modes and other presets retain their previous defaults.

[All tuning results and memory tables](qwen38-option20-io-tuning-20261105.md) and [packaged raw metrics](qwen38-option20-io-tuning-20261105.json).

The [complete Mac estimate snapshot](qwen38-option20-mac-estimates-20261105.md) preserves the saved cross-machine tables and subsequent Air measurements.

## Exact 10.5 GiB Air budget, November 5, 2026

At this stage, the 16 GiB/131K/automatic-expert/single-request/16G-persistent-cache preset defaulted to `--max-memory 10.5G`, exactly 11,274,289,152 bytes. It keeps 2,048-token prefill, the 1.946 GiB expert store including staging and the SSD-backed n-gram table with its approximately 64 MiB row cache. Explicit memory caps remain authoritative, including an explicit `10G`; other presets retain their previous defaults. All 38 launcher checks passed.

This increase raises allocation capacity but does not eliminate near-131K spill. The live 130,733-token request selected spill. With SSD-tier admission reserves included, the resident budget at 10.5 GiB holds about 128,416 tokens before output projection. The reported 155,641-token allocation bound excludes those reserves. The earlier estimate based on allocation capacity alone overstated spill-free context. Host memory pressure can also force conversion from resident to spill.

[Budget, memory accounting and live validation](qwen38-option20-budget105-20261105.md) and [packaged results](qwen38-option20-budget105-20261105.json). That report records the previous 10.5 GiB cap; the later 10.8 GiB change is described below.

## 10.8 GiB Air budget, November 5, 2026

The current Air preset defaults to `10.8G`, parsed as 11,596,411,699 whole bytes. Both launchers match and the live service applies the budget without clamping. Prefill stays at 2,048 tokens, context at 131,072, the expert store at 1.946 GiB including staging, and the SSD-backed n-gram row cache at approximately 64 MiB. Explicit caps and other presets are preserved. All 38 launcher tests passed.

Resident admission now has 2,023,571,351 bytes, about 152,736 tokens before output projection. A 130,733-token persisted replay reused 130,720 tokens and passed correctness while remaining resident, with zero spill admissions or conversions. This validates the cached replay path; cold near-131K residency and absence of OS swap are not established. Host pressure can still force spill. Prefix restoration, n-gram and expert streaming continue to use SSD.

[All serving checks and memory table](qwen38-option20-budget108-20261105.md) and [packaged results](qwen38-option20-budget108-20261105.json).
