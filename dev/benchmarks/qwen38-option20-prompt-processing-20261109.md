# Option 20 prompt processing: where the seconds go (2026-11-09)

Measured on the same long-lived instance as the pinned baseline: pid 92460, model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, build `src-882891f8`, 131,072 served context, 10.8 GiB Metal cap, INT8 KV, BF16 state, DFlash2 draft, 2,048-token prefill chunks, `--expert-memory auto`, `--ple-memory 64M`, 16 GiB persistent prefix cache. Thermal was `fair` throughout (this Mac is actively used); every probe was gated on an idle server and marked clean. ChatML framing adds 12 tokens to every prompt, so a 128-token probe is served as 140 prompt tokens.

Two new probe groups were added to `dev/benchmarks/option20_serving_matrix.py` for this: `--group prefill` (same prompt cold, then warm, at each pinned size) and `--group ladder` (an agent-shaped conversation that grows by one tool block per turn). Raw rows are in `dev/benchmarks/option20-experiments/`:

- `20261109T213553Z-prompt-scaling-1k-8k-longlived`
- `20261109T215843Z-prompt-scaling-128-1k-longlived`
- `20261109T221935Z-prompt-ladder-8-turns-longlived`

```bash
.venv/bin/python dev/benchmarks/option20_serving_matrix.py \
  --group prefill --sizes 128,512,1024,2048,4096,8192 --trials 1
.venv/bin/python dev/benchmarks/option20_serving_matrix.py --group ladder --trials 1
```

## Cold prefill, and what a warm prefix actually saves

| Prompt tokens (served) | Cold TTFT | Cold prefill tok/s | Expert bytes read, cold stage | Warm TTFT | Expert bytes read, warm stage |
|---|---:|---:|---:|---:|---:|
| 140 | 3.665 s | 38.2 | 18.33 GB | 1.099 s | 4.57 GB |
| 524 | 5.193 s | 100.9 | 28.67 GB | 1.147 s | 4.53 GB |
| 1,036 | 5.746 s / 7.092 s | 180.3 / 146.1 | 32.29 / 33.13 GB | 1.128 s / 1.091 s | 4.47 GB |
| 2,060 | 9.066 s | 227.2 | 37.99 GB | 1.116 s | 4.47 GB |
| 4,108 | 13.824 s | 297.2 | 43.02 GB | 1.158 s | 4.44 GB |
| 8,204 | 24.631 s | 333.1 | 79.20 GB | 1.189 s | 4.41 GB |

The warm column is the important one. A warm probe computes **12 new rows** (the chat-template tail) and takes 1.10 to 1.19 seconds no matter whether the cached prefix is 128 tokens or 8,192 tokens. It also reads 4.4-4.6 GB of routed experts from the SSD for those 12 rows. That fixed per-stage cost is the entire warm TTFT: `prompt_ms` for a warm probe is 94-100 ms of work inside a 1.1 s request.

The cold path has a fixed floor too. Fitting the marginal cost from 4,108 to 8,204 rows gives 2.638 ms/token (379 tok/s); 2.638 ms x 8,204 = 21.64 s of the measured 24.63 s. The 140-row probe measures 3.665 s where the same marginal rate predicts 0.37 s. So roughly 3.0-3.8 s of any cold prefill is fixed cost that does not shrink with the prompt.

Marginal dense prefill, in the same run, improves with size: 2.323 ms/token (430 tok/s) from 2,048 to 4,096 rows and 2.638 ms/token (379 tok/s) from 4,096 to 8,192 rows. Cold throughput figures quoted as one number (e.g. "313 tok/s") are therefore mostly a statement about prompt size, not about speed.

## An agent conversation pays the fixed cost every turn

The ladder replays a tool loop: a system prompt, then a user block, a short reply, and a tool result per turn, growing the conversation by roughly 1,180 tokens each turn.

| Turn | Prompt tokens | Cached | Cached % | TTFT | New-row rate | Spill pages | Disk KV read-back |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,188 | 0 | 0% | 8.421 s | 141 tok/s | 0 | 0 |
| 2 | 3,018 | 1,152 | 38% | 10.401 s | 246 tok/s | 0 | 0 |
| 3 | 4,848 | 3,008 | 62% | 9.663 s | 417 tok/s | 0 | 0 |
| 4 | 6,678 | 4,832 | 72% | 9.105 s | 652 tok/s | 0 | 0 |
| 5 | 8,508 | 6,656 | 78% | 8.486 s | 1,013 tok/s | 0 | 0 |
| 6 | 10,338 | 8,480 | 82% | 8.573 s | 1,239 tok/s | 0 | 0 |
| 7 | 12,168 | 10,304 | 85% | 8.488 s | 1,433 tok/s | 0 | 0 |
| 8 | 13,998 | 12,160 | 87% | 8.333 s | 1,672 tok/s | 0 | 0 |

New-row rate divides only the tokens that were not cached by TTFT, which is the number that matters in a loop. Prefix reuse is working well: by turn 8 it reuses 12,160 of 13,998 tokens with zero page spill and zero SSD KV read-back. Yet TTFT stops falling after turn 4 and sits at 8.3-8.5 s, because the new ~1,800 tokens of each turn are prefilled at 220 tok/s against a 12K-token context, slower than the 379 tok/s measured for the same token range in a fresh prompt. Attention over a long resident context, not the cache, sets the floor.

Practical consequence: in this shape the conversation is only as fast as its *new* tokens. Cutting 1,000 tokens of tool output per turn removes about 4.5 s of every turn. Rewriting history destroys the 87% hit that keeps the rest affordable.

## What the fixed cost is made of

Lifetime counters of the running instance, read at 17:42 on 2026-11-09 after the probes below (this instance also serves this agent session, so the totals move between readings; the ratios are what matter):

| Counter | Value |
|---|---|
| Expert store cap / floor | 2,089,468,688 B each (one chunk, no growth) |
| Expert slots resident | 41 of 512 slots, 24,576 experts |
| Routed-expert hit rate | 0.00 prefill, 0.00 decode |
| Expert reads per prompt token (prefill) | 9.8 reads, 19.1 MB |
| Expert reads per output token (decode) | 411 reads, 802 MB |
| Bytes per expert read | 1.95 MB |
| Expert SSD traffic rate | 3.26 GB/s prefill, 5.51 GB/s decode |
| Read-ahead bytes never used | 1.67 TB of 13.02 TB prefill (13%), 20.36 TB of 97.81 TB decode (21%) |
| PLE n-gram row cache | 64 MiB, 504,370 rows, all cached, 5.88M+ evictions |
| PLE row hit rate | 0.900 prefill, 0.614 decode (5.20M decode row reads) |
| KV pages | 2,304 allocated against 5,632 planned (2.39 GB, 180,224 tokens); 369-764 free during probes |
| Disk quota | 17,179,770,880 / 17,179,869,184 B, 98,304 B slack |
| Governor | headroom 0-105 MB, `growth_allowed: false`, host spare reserve 2 GiB |

The prefill stage cost is expert streaming, not table reads. A 12-row warm stage reads 4.4 GB of experts and only 192 PLE rows. Expert residency is effectively zero (41 of 512 slots, hit rate 0.00), so every stage re-streams the experts its rows route.

Read-ahead waste is measurable per probe, not only in lifetime totals: the 8,204-row cold stage read 63.07 GB ahead and used 42.26 GB, so 20.8 GB (33%) of that stage's SSD traffic bought nothing. At the instance's own 3.26 GB/s prefill rate, 20.8 GB is about 6.4 s of the 24.63 s TTFT. The 524-row, 1,036-row and 4,108-row stages wasted 4.7 GB (29%), 6.9 GB (30%) and 8.5 GB (26%).

## Ranked levers, one variable each

Acceptance is always measured in tok/s and seconds, never in hit rates alone. `qwen38-option20-expert-retention-20261105.md` already demonstrated that raising the expert hit fraction by 3.8 points made decode 4.6% *slower* with 2.4% more SSD bytes per output token, so hit-rate improvements are evidence only when they move throughput.

**P1. Do not re-stream the expert store for a stage that computes a handful of rows (engine change).** A warm turn computes 12 rows and pays 4.4-4.6 GB of expert reads, which is the whole 1.1 s warm TTFT. `runtime/model/ExpertStore.cpp` plans the stage and its read-ahead (`startAhead`, `planAhead`); the plan should scale with the rows the stage actually holds instead of charging a chunk-wide working set. Accept: warm 4K reuse TTFT <= 0.50 s (from 1.16 s) and warm expert read bytes <= 1.0 GB (from 4.44 GB), with cold 4K prefill within 2% of 313.5 tok/s and zero capacity or Metal failures. Rollback: revert the patch.

**P2. Make expert read-ahead accurate (engine change).** 13% of prefill read-ahead bytes and 21% of decode read-ahead bytes are never used; per probe, up to 33% of a stage's SSD traffic. Accept: `ahead_used_bytes / ahead_read_bytes` >= 0.95 for prefill stages (0.67 at the 8,204-row probe), 8,204-row cold TTFT <= 20 s (from 24.63 s), cold 4K >= 350 tok/s (from 313.5), no new spill pages on a warm prefix. Rollback: revert the patch. This is about choosing better prefetch targets, not reducing depth: the 2026-11-05 I/O comparisons found shallower read-ahead and fewer workers slower, and `experts_prefill_read` exactly equals `routed` on every probe here, so the wasted bytes are prefetched groups that were evicted or overtaken before use.

**P3. Chunk size A/B, 1,024 against the current 2,048 (config, reversible). Closed on 2026-11-10: 1,024 is worse, see the ablation table below.** The engine caps `--prefill-chunk-tokens` at 2,048 and option 20 already uses the cap, so the only direction left is smaller. If stage cost is chunk-wide, halving the chunk should cut the fixed cost of the short stages that dominate agent turns, at the price of more stages on long cold prompts. Accept: 140-token cold TTFT <= 2.2 s (from 3.665 s) and 8,204-row cold TTFT <= 27 s (no more than 10% worse than 24.63 s). Rollback: drop the override.

```bash
cd /Users/mymac/splash/splash/dev/benchmarks
./option20_quota_experiment.sh --label chunk-1024 \
  --set SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=1024 --group prefill \
  --matrix-args "--sizes 128,512,1024,2048,4096,8192" --trials 1 --yes
./option20_quota_experiment.sh --label ladder-chunk-1024 --group ladder --trials 1 --yes
```

**P4. Raise the disk quota to 24 GiB (config). Closed on 2026-11-10: raising it changed nothing, see the ablation table below.** Unchanged from R1 in `qwen38-option20-recommendations-20261108.md`, and still the fix for the *long-lived* reuse path: the quota is now 98,304 bytes from full with 28,898 KV page restores and 4,077 KV blocks taken back for state copies. Accept: 4K reuse TTFT <= 1.70 s on a fresh instance, `kv.pages_free` stays above ~1,000 pages through two hours of real traffic, restore count grows by less than 25%. Rollback: unset `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`.

**P5. Expert memory floor, `SPLASH_FLASH_NEXT_EXPERT_MEMORY=3G`, measured as a trade (config). Closed on 2026-11-10: the planner clamps the store, so the knob cannot be tested this way, see the ablation table below.** `auto` gave the expert store exactly 2.09 GB, one chunk, floor equal to cap, 36 resident slots, zero hits. A larger floor buys SSD reads per token by taking memory from the KV pool, which the ladder shows is currently comfortable (764 pages free at 14K context) but which the governor already refuses to grow. Accept: expert reads per prefill token <= 15 MB (from 19.1), 4K cold >= 350 tok/s, warm 4K reuse TTFT <= 1.30 s, KV pages allocated >= 2,300, decode mean >= 11.0 tok/s. Rollback immediately if decode falls, which is what the 2026-11-05 retention experiment predicted.

**P6. PLE row cache 192M is a decode lever, not a prompt lever.** Prefill already hits 0.900 of row requests and a warm stage touches 192 rows; decode hits 0.614 and has read 5.20M rows from a 28.8 GB table. Accept: decode row hit >= 0.75 and coding decode mean >= 11.6 tok/s (from 11.04) with 4K prefill within 3%. Rollback: unset `SPLASH_FLASH_NEXT_PLE_MEMORY`.

**P7. Prompt shape on the agent side (no engine change, works today).** New tokens cost 4-8 ms each depending on context length; cached tokens cost nothing. Keep tool blocks small, keep the transcript append-only so prefix hits stay above ~85%, and avoid pasting whole files when a range will do. Trimming 1,000 tokens per turn saves about 4.5 s per turn at the shapes measured here.

**P8. Make KV pool residency an explicit budget.** 2,304 pages are allocated against the 5,632 the plan allows, with `growth_allowed: false`, 0-105 MB headroom and a 2 GiB host spare reserve on a 16 GiB machine. This is R5 from the recommendations document and it gates any experiment that wants both a bigger expert store and a resident KV pool. Accept: `kv.pages_free` stays above ~1,000 pages through two hours of real traffic without capacity failures.

## Closed on 2026-11-10: the one-variable runs, and which build this actually is

Every run below is the same build (`src-882891f8`), the same 131,072 context, and one changed variable at a time. `option20_quota_experiment.sh` restarts the server with the override, gates on an idle server, and records the row in `option20-experiments/index.tsv`; `stock-control-24g-after` was the stock re-run that follows each override, and it reprints the same baseline every time.

| Run | Changed variable | 4K cold tok/s | 4K reuse TTFT | Spill pages | Disk KV read-back |
|---|---|---:|---:|---:|---:|
| `pinned-baseline-fresh-quota-saturated` | none, fresh instance | 331.3 | 1.988 s | 6 | 192 tokens |
| `20261109-pinned-baseline-longlived` | none, 248 prior requests | 313.5 | 1.987 s | 6 | 192 tokens |
| `stock-control-24g-after` | none, control | 288.7 | 1.952 s | 6 | 192 tokens |
| `quota-24g` | quota 16 GiB -> 24 GiB, cap and chunk pinned | 292.4 | 2.062 s | 6 | 192 tokens |
| `expert-4g-cap-108` | `SPLASH_FLASH_NEXT_EXPERT_MEMORY=4G`, cap pinned 10.8G, chunk 2048 | 300.4 | 1.954 s | 0 | 192 tokens |
| `expert-4g` | same store request, launcher kept the 10G cap and dropped to 1,024-token chunks | 188.0 | 1.993 s | 0 | 128 tokens |
| `restored-best-pp-build-check` | none, 2026-11-10, `fair` thermal | 254.6 | 2.025 s | 3 | 96 tokens |

P4 is closed. A 24 GiB quota on a fresh instance produced a *worse* 4K reuse TTFT (2.062 s against 1.952 s for the stock control that followed it) with byte-identical spill behaviour: 6 whole-page restores and 192 KV read-back tokens in both runs. The pinned 4K workload never reached the quota wall, so the quota is not what makes a warm turn slow. `kv.pages_free` and the 17.42 GB directory at a 16 GiB cap stay as observation, not as a lever.

P5 is closed for a different reason: the request is not granted. With the cap and chunk pinned so that only the store changes, `expert-4g-cap-108` is within noise of stock (300.4 against 288.7 tok/s, 1.954 against 1.952 s). The engine planner clamps the streamed store to `cap_bytes == floor_bytes == 2,089,468,688`, 512 slots, one chunk, 36-38 resident, whatever `--expert-memory` asks for. The only way to make a 4G store request observable was the coupling it drags along: through the launcher it held the Metal cap at 10 GiB and fell back to 1,024-token chunks, and that combination costs a third of cold prompt throughput (188.0 against 288.7 tok/s). `expert-4g` measured the coupling, not the store.

P3 is closed the same way as P4, in the unfavourable direction. `chunk-1024-prefill-scaling` re-ran the size ladder with 1,024-token chunks: the 8,204-row cold stage took 41.75 s against 24.63 s at 2,048, and read 232 GB of routed experts against 79.20 GB for the same 8,204 rows. Stage cost is not chunk-wide, so halving the chunk multiplies stages without shrinking any of them. Chunk 2,048 is the right setting and the engine maximum.

One configuration cannot boot, which is why the coupling exists. A 4G expert store asked against the 10 GiB cap with 2,048-token chunks plans 11,471,548,576 B (10,940 MiB) of floors against a 10,737,418,240 B (10,240 MiB) budget, a 734 MiB deficit, and the engine refuses to start. `startllamacpp.sh` now keeps the 1,024-token chunk whenever a streamed memory override holds the cap at its default, prints `SPLASH_FLASH_NEXT_CAP_NOTE` saying so, and still raises both when `SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G` and `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048` are pinned together. `test_option20_streamed_memory_override_holds_cap_and_chunk` and `test_option20_streamed_memory_override_accepts_the_raised_cap_pair` cover both sides; all 45 launcher tests pass.

The build is the interesting result. `dev/tools/build_identity.py` hashes `runtime/**` plus the Makefile flags, so a binary can be traced back to a commit. Hashing the candidate trees gives:

| Source state | Build id |
|---|---|
| `0025f309` (2026-11-06, "Record Qwen3.8 PP and TPS results"), `3e2e1ebc`, `c72fe592` (identical `runtime/` trees) | `src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a` |
| `2b52116b`, current `splashmain` tip (186 runtime files different, 16,607 insertions: the 1.6 memory rule, elastic expert store, kernel selection, cycle-ahead and its disable) | `src-81529c7c97580f531418c1c0ec9bf09bfd5997452ca96d8d0b8071fa40c86a6a` |

The engine that has served every measurement on this Mac since 2026-11-08 20:17 is `src-882891f8`, which hashes from the 2026-11-06 line, and `qwen38-option20-telemetry-performance-20261106.md` records that same id for the instrumented pair that measured 408.28 tok/s 4K cold and 1.536 s 4K reuse. `src-81529c7c`, the current `splashmain` tip, has never been built or measured here. The repo was left in a half-finished interactive rebase of `splashmain` onto `c72fe592` (2 of 7 commits applied, HEAD reset three times between 18:54 and 20:17 on 2026-11-08); that rebase is aborted, `splashmain` is back at `2b52116b` in step with `origin/splashmain`, and the machine now runs branch `option20-best-pp-20261106` at `0025f309`, whose runtime tree hashes to exactly the build id the live server reports. Nothing was dropped: `c72fe592`, `df746b99` and the rest stay reachable from `splashmain`, and the binary itself is kept as `build/splash-src882891f8.bak`.

So the 1.95-2.06 s warm turn is not a code regression and no branch switch will move it. The same build id measured 1.536-1.539 s reuse and 406.91-408.28 tok/s cold on 2026-11-06 under `nominal` thermal with a 256-page KV pool (10 pages cache-resident) and 15.94 GiB of prefix cache; it measures 1.95-2.03 s and 254.6-331.3 tok/s now under `fair` thermal with 2,048 allocated pages, 1,690 lifetime whole-page KV restores and a 17.42 GB directory against a 16 GiB cap. The remaining prompt-side work is P1 and P2 in this document, both engine changes over this build.

## Not a lever

- **More PLE row cache for faster prompt processing.** Prefill row hits are already 0.900 and warm stages touch 192 rows; prompt time is expert bytes, not table rows.
- **Expert retention policies.** Tested on 2026-11-05 (`qwen38-option20-expert-retention-20261105.md`): hit fraction 0.00% to 3.82%, coding decode -4.57%, SSD bytes per output token +2.42%. Hit rate is not the lever; bytes per token and seconds are.
- **Neural Engine prefill.** `ane_ffn.state` is `off` with reason "the target's FFN layers are not all dense". There is no ANE path for this model.
- **Bigger prefill chunks.** 2,048 is the engine maximum and option 20 already runs at it.
- **Quoting a single cold-prefill tok/s number.** It moves 38 to 333 tok/s across 140 to 8,204 prompt tokens on one build with one profile.

## Also fixed while measuring

- `dev/benchmarks/option20_quota_experiment.sh` waited for `model_name` in `/status`, which does not exist at the top level; it now waits for `ready` plus `instance.model`. Its stock run (no `--set`) also crashed under bash 3.2, which refuses to expand an empty array with `set -u`; both array expansions are now guarded. It gained `--matrix-args` so a run can pass `--sizes` or `--turn-step` to the harness.
- `dev/benchmarks/option20_quota_experiment.sh` can no longer race or leave junk behind. It takes a directory mutex (`option20-experiments/.experiment.lock`, released by a trap), reads `/status` and refuses to create a run directory when the server is not the option-20 instance, and preserves the logs of a run that fails by renaming its directory to `*-FAILED` (the boot failure above is `20261110T051444Z-expert-4g-cap10g-cannot-boot-FAILED`). The index gained a `--note` column and `normalize_index()` pads the rows written before it existed.
- `dev/benchmarks/option20_serving_matrix.py` salts the first ladder prompt with a random token, so `--group ladder` starts cold the way an agent conversation does and repeats produce the same cold/warm split. The unsalted form is still useful as a deliberate warm-prefix replay: `ladder-warm-replay-fresh-quota-saturated` re-sent the same 8-turn conversation and paid 437 whole-page restores and 13,984 KV read-back tokens for TTFTs of 0.75-2.66 s, which is far cheaper than the 8.2-10 s of dense prefill and about 0.7 s dearer than the 1.1 s stage floor.
- `dev/benchmarks/option20_serving_matrix.py` applied the smoke correctness gate to every probe, so prompt-processing probes were reported `correct=False`; each kind now gets its own gate (`pre-*` and `turn-*` must complete the stream and produce tokens). The experiment index gained a `notes` column that records prefill scaling and ladder means for runs that do not run the pinned 4K and coding groups.

**Which engine line is fastest is settled as well.** The `splashmain` tip line (`src-81529c7c`, the 186-file engine rewrite) was built in a scratch checkout and measured against the running `src-882891f8` line in one session, each with its own empty 16 GiB prefix cache: cold prefill 199.53 / 242.10 / 294.50 tok/s at 2,048 / 4,096 / 8,192 tokens against 215.66 / 268.51 / 324.27 tok/s, so the tip line is 8-11% slower at every prompt size, with the same warm reuse (1.10-1.17 s) and the same decode (11.05 against 11.23 tok/s). The ladder is the prompt-side target any future engine change has to beat. See `qwen38-option20-engine-line-comparison-20261110.md`.

See also `qwen38-option20-serving-performance-20261108.md`, `qwen38-option20-vs-nov06-comparison-20261108.md`, `qwen38-option20-recommendations-20261108.md`, and `option20-launcher-drift-20261109/README.md`.
