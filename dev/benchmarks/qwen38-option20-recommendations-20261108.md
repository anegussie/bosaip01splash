# Option 20 recommendations (2026-11-08)

Ranked action list for the served `qwen3.8-flash-next-iq3-xxs-splash` profile (option 20) on the 16 GB MacBook Air (M5), based on the 2026-11-08 two-trial matrix and its comparison with the 2026-11-06 reference pair.

Sources: [2026-11-08 matrix](qwen38-option20-serving-performance-20261108.md), [2026-11-08 vs 2026-11-06 comparison](qwen38-option20-vs-nov06-comparison-20261108.md), [2026-11-06 telemetry reference](qwen38-option20-telemetry-performance-20261106.md), [2026-11-05 I/O tuning](qwen38-option20-io-tuning-20261105.md), [2026-11-05 expert retention](qwen38-option20-expert-retention-20261105.md).

Every item below is a single-variable experiment with an acceptance criterion measured in tokens/s and seconds, not in hit rates. The 2026-11-05 experiments already established that higher cache hit rates and added SSD work can fail to produce speedups; that rule is respected here.

## What the 2026-11-08 run established

| Finding | Number |
|---|---|
| Cached reuse readback regression | 4K reuse TTFT 1.54 s -> 2.42 s (+57%) with a cache `hit` and only 19-34 uncached prompt tokens in both runs |
| Cause: KV prefix blocks not resident | Nov 6 `cache.kv_disk_hit_tokens` 0 across the whole matrix; Nov 8 +81,600 disk-hit tokens, 22 new demotions |
| Disk quota is the binding constraint | `disk.used_bytes` 17,129,209,856 of `limit_bytes` 17,179,869,184 (99.7%), `taken_back` 4,077 KV blocks / 6.64 GB thrown back to make room for 11.0 GB of offloaded state |
| Restore cost per page | `kv_spill.restores.whole_pages` 4,700 pages, 446 s total, p50 131 ms, p95 262 ms |
| Page economics | `kv_page_bytes` 423,936 for a 32-token INT8 page, so a 4,032-token prefix is 126 pages / 53.4 MB and one page restore costs ~0.13 s |
| Resident prefix capacity today | `kv.pages_cache` 2,060 of 2,560 pages (~0.85 GB, ~65K tokens of KV) while the disk tier holds 14,542 KV blocks (~465K tokens) |
| Coding speculation efficiency dropped | coding decode 10.04 -> 9.32 tok/s (-7.2%); cycles per 128 tokens 26 -> 32.5 and 30 -> 36 at equal or better acceptance, i.e. 3.4-4.0 accepted tokens per cycle vs 4.3-4.9 |
| Uncached short-prompt latency unchanged | code-3 (no cache hit) TTFT 2.226/2.259 -> 2.284 s |
| Long-context prefill within noise | 4K cold 406.91 -> 394.06 tok/s (-3.2%) |
| Memory headroom is the wall on residency | governor charged 10.20 of 11.60 GiB, `growth_allowed: false` because `host_spare_bytes` 2.00 GB is below `host_spare_reserve_bytes` 2.15 GB, `denied_reservations` 17,711 |
| PLE row cache is at capacity | `--ple-memory 64M`: `cached_rows` 504,370 equals `cache_capacity_rows`, 1,628,978 evictions, prefill `stage_ms` p95 65.5 ms and p99 131 ms (the Nov 6 sample showed p95 4.1 ms) |
| Expert store is not the lever | store cap = floor 2,089,468,688, `resident` 27 of 512 slots, `hit_rate` 0.00 on both prefill and decode, `format_evictions` 38.6 M |

Two rows of that table were later corrected by the pinned harness on 2026-11-09, see "What landed on 2026-11-09": the coding speculation gap did not survive identical prompts and complete outputs, and the 4K reuse regression measured smaller (1.99 s rather than 2.42 s) once the probes stopped competing with the live agent.

## R1. Relieve the disk prefix-cache quota before touching anything else

The 16 GiB disk quota is fully consumed, and the state tier (11.0 GB offloaded for 177 state entries, ~62 MB each) is displacing KV prefix blocks: 4,077 KV blocks (~130K tokens) have already been taken back. That is the direct mechanism behind the reuse regression, and the volume has 69 GiB free, so quota is a policy choice rather than a shortage. On 2026-11-09 the instance reports 17,179,541,504 of 17,179,869,184 bytes used, which is 327,680 bytes of slack, and `kv_restores` has reached 28,898.

Experiment, single variable. `dev/benchmarks/option20_quota_experiment.sh` stops the running option-20 server, relaunches with the override, runs the pinned matrix twice, and appends one row to the experiment index:

```bash
cd /Users/mymac/splash/splash/dev/benchmarks
./option20_quota_experiment.sh --label quota-24g \
    --set SPLASH_FLASH_NEXT_MAX_CACHE_DISK=24G --trials 2 --yes
./option20_quota_experiment.sh --label stock-control --trials 2 --yes
./option20_quota_experiment.sh --compare
```

`--yes` is required because the option-20 server is also what answers this Mac's Splash agent; stopping it interrupts any agent session that talks to it. The `--label stock-control` run is the same matrix on the stock profile so the two numbers are read under identical conditions, and a second `--label quota-24g` run should follow after the instance has served an hour of real traffic, so the result is measured on a populated instance and not only a fresh one.

Accept: 4K reuse TTFT <= 1.70 s on the long-lived instance, `cache.kv_disk_hit_tokens` delta <= 4,096 tokens for a 4K reuse probe, `disk.taken_back.kv_blocks` stays near zero for two hours of live traffic. Rollback: the quota env var. Cost: about 8 GB more disk on a volume with 69 GiB free; option 21 keeps its own isolated cache directory.

## R2. Give KV a floor inside the shared disk quota

R1 buys room but does not change priority: today the quota is shared by KV pages and offloaded state and is replaced purely by recency (`runtime/engine/Cache.hpp` documents the quota as shared, with `CacheWindowPolicy::trim` and recency ordering). A busy multi-turn agent can evict prefix KV to keep state copies.

Proposed engine change: a bounded minimum share for KV blocks in the disk quota, so state offload can take the rest but cannot reclaim KV below the floor. Anchor points: `runtime/engine/Cache.hpp` (quota accounting, `evictedKv` / `evictedState` steps), `runtime/engine/KvPageTier.hpp` (`demote`, restore batches), `runtime/engine/CacheRecency.hpp` and `RecencyOrder.hpp` (replacement order).

Accept: on the same populated cache directory and the same long-lived instance, 4K reuse TTFT <= 1.70 s without raising `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`, and no regression in the 90K+ token live agent sessions (their TTFT and `state.disk_hits` / `disk_promotions` measured before and after). This is the change that actually protects prefix reuse under real traffic; R1 alone can be re-consumed by state.

## R3. Test PLE row-cache headroom as its own experiment

`--ple-memory 64M` was hardcoded in `startllamacpp.sh` for option 20, and the live counters show the row cache exactly full (504,370 of 504,370 rows, 1.63 M evictions) with prefill stage latency two orders of magnitude worse than the Nov 6 early-life sample.

The knob landed on 2026-11-09 in both the repo launcher and the copy at `~/startllamacpp.sh`: `SPLASH_FLASH_NEXT_PLE_MEMORY` defaults to `64M`, is validated (16M to 2G or `off`), shows in the option-20 menu line, counts as a deliberate deviation in the stock-profile guard that decides whether the 10.8G cap is auto-applied, and two new launcher tests cover it (41 launcher tests pass). The experiment itself still needs a restart:

```bash
cd /Users/mymac/splash/splash/dev/benchmarks
./option20_quota_experiment.sh --label ple-192m \
    --set SPLASH_FLASH_NEXT_PLE_MEMORY=192M --trials 2 --yes
```

Accept: prefill `stage_ms` p95 back under 10 ms, 4K cold prefill >= 405 tok/s, coding decode >= 10.0 tok/s, and `streamed_table.decode.hit_rate` improvement is treated as supporting evidence only. Budget check first: 64 MiB -> 192 MiB costs 128 MiB of the 1.39 GB governor headroom, and `growth_allowed` is currently false, so this may need R5 settled first. If it does not fit, record that fact rather than pushing the cap.

## R4. Chase the coding speculation gap with a matched-thermal A/B, then bisect

Status after 2026-11-09: the gap no longer reproduces once the prompts are pinned. The pinned matrix measures coding decode at 11.04 tok/s (10.47-12.26) on the saturated, `fair`-thermal long-lived instance, against the Nov 6 figure of 10.04 tok/s, and the Nov 8 9.32 tok/s number came from a different prompt set (47 / 40 / 38 prompt tokens) cut off at 128 output tokens. The Nov 6 raw rows are cut off too: every coding probe in all four Nov 6 runs stops at 127 output tokens with no `finish_reason`, so cycle counts of 26 / 30 / 26 describe a truncated generation, not a full one. Tokens-per-cycle is therefore not comparable across the two methodologies (the pinned probes finish naturally at 67-136 tokens and average 6.42 tokens per cycle), and the only valid comparison going forward is pinned run against pinned run.

What is left of this item is the thermal variable, not the prompt set:

1. Matched-`nominal`-thermal repeat of the pinned coding group on the current build (`./option20_quota_experiment.sh --label speculation-nominal --group coding --gate nominal --trials 2 --yes`). If pinned coding decode at `nominal` is not clearly above the `fair`-thermal 11.04 tok/s, thermal is not the story and the item can close.
2. If a real gap appears between pinned runs on comparable instances, bisect the engine line between the Nov 6 build (`6a06f0d6...`, and the instrumented `882891f8...`) and HEAD, restricted to speculation and verify-row paths (`runtime/model/DFlashDraft.cpp`, `verify_rows` handling, `runtime/engine/Engine.hpp` draft-context planning).
3. Only after the cause is known, run parameter experiments one at a time: draft block size 16 vs 12 and 20, `--ngram` 4 vs 3 and 5, `verify_rows auto` vs a fixed value.

Accept: pinned coding decode mean >= 11.0 tok/s on a fresh instance at `nominal` thermal, or a documented reason the current shape is correct.

## R5. Make KV pool residency an explicit budget instead of whatever is left

The pool cannot grow on this machine today: charged 10.20 of 11.60 GiB, headroom 1.39 GiB, `growth_allowed: false` because host spare 2.00 GB is below the 2.15 GB reserve, with 17,711 denied reservations. When a reuse hit needs 126 pages and the pool holds 500 free pages of one form, the answer comes from disk at ~131 ms per page.

Work to do:

- Instrument the interaction rather than guess: log `kv.pages_free`, `kv.pages_cache`, `extent_allocations`, `pages_moved`, `extent_compactions` and `denied_reservations` deltas per request, so a reuse miss can be attributed to pool starvation, eviction, or quota.
- Evaluate whether a 16 GiB machine needs `host_spare_reserve_bytes` 2.15 GB while `memory_pressure` is `warning` and `system_pressure` is `normal`, or whether that reserve is what keeps the pool from holding hot prefixes. This is a MemoryGovernor question (`runtime/engine/MemoryGovernor.cpp`, `runtime/engine/MemoryPlan.cpp`), and it needs its own trial with live agent traffic as the correctness test, not just the benchmark.

Accept: with two hours of real traffic, `kv.pages_free` stays above ~1,000 pages (about 414 MB / 32K tokens of KV) and 4K reuse TTFT stays <= 1.70 s, with no new spill and no Metal failure.

## R6. Harden the benchmark so these questions are answerable in one run

Status: landed on 2026-11-09 as `dev/benchmarks/option20_serving_matrix.py` plus `dev/benchmarks/option20_quota_experiment.sh`.

- Prompt content pinned to the Nov 6 token counts (351 smoke, 4,019 4K, 33 / 32 / 36 coding). The recorded rows show 363 / 4,031 / 45 / 44 / 48 because the served ChatML wrapper adds exactly 12 tokens to every probe, which is the same offset in both methodologies, so a pinned row is comparable with a Nov 6 row. The coding tasks are the same shape as Nov 6 (write a function, then run asserts on it) and the harness executes the returned code as a correctness gate, so a row that decodes nonsense is not counted.
- Prompt sizing is verified against the server's own `/tokenize` endpoint and lands on the exact target for every random salt, which is what the 2026-11-08 ad-hoc runners could not guarantee.
- Per-probe counter deltas recorded automatically for roughly eighty fields (`kv.pages_*`, `cache.kv_disk_hit_tokens`, `cache.hits`, `disk.kv_demotions`, `disk.taken_back`, `disk.kv_restores`, `kv_spill.restores.ms`, `memory_pressure`, governor charge, host available, Metal peak). A row without them is not comparable.
- A declared cache state per run: `fresh` (engine restarted, pool empty) or `longlived` (uptime and prior request count recorded), plus the build id and the `SPLASH_FLASH_NEXT_*` values in force in `preflight.json`. Compare only like with like.
- Content control: per-probe idle gating before the request, contention sampling during it, and a `clean` flag; the 2026-11-08 single-trial 312 tok/s outlier is exactly the shape this rejects.
- Two trials per matrix with the coding group reversed in the second trial, one probe group at a time via `--group`, and `--thermal-gate nominal` for matched-thermal repeats.
- `summary.txt` per run, `--record` / `--compare` for an append-only `dev/benchmarks/option20-experiments/index.tsv`, so each experiment is one row next to the baseline row.

Accept: the next run answers R1-R5 questions with a single command, and any future number quoted in a doc cites a row with cache state and counter deltas attached. Both conditions now hold for the baseline row.

## What landed on 2026-11-09

R6 and the R3 launcher knob are done, and the pinned baseline row exists.

`dev/benchmarks/option20-experiments/index.tsv` now holds the reference measurement taken on the same long-lived option-20 instance the Nov 8 numbers came from (build `src-882891f8`, 248 completed requests at the start, `fair` thermal throughout):

| Metric | Pinned baseline (long-lived, `fair`) | Nov 6 reference (fresh, `nominal`) |
|---|---|---|
| 4K cold prefill | 313.5 tok/s | 406.91 tok/s |
| 4K reuse TTFT | 1.987 s | 1.539 s |
| Coding decode | 11.04 tok/s (10.47-12.26) | 10.04 tok/s (9.61-10.99) |
| Draft acceptance | 1090/1157 (94.2%) | 1259/1357 (92.8%) |
| Disk KV read-back during the matrix | 192 tokens | 0 tokens |
| Whole-page spill restores during the matrix | 6 pages | 0 pages |
| Probes marked clean | 14/14 | 14/14 |

The two numbers that still lag the Nov 6 reference are long-context prefill (-23%) and cached reuse latency (+29%), which keeps R1, R2, and R5 as the priority list. The coding row no longer lags, which is why R4 dropped in rank.

Two things are blocked rather than deferred:

- R1 and R3 need the server restarted. The option-20 server is the provider this agent session talks to, so the restart has to be run by you, or from a session that is not served by it. `option20_quota_experiment.sh` does the whole sequence, including the rollback-friendly default relaunch.
- R3's memory question is unchanged: 128 MiB more row cache has to come out of a governor that currently reports 1.28 GB headroom (1.39 GB on 2026-11-08) with `growth_allowed: false` and 18,000 denied reservations, so the experiment must record whether the planner absorbed it or shrank KV instead. The launcher now warns when a PLE request exceeds a quarter of the Metal cap, and the engine planner is the authority (`runtime/engine/MemoryPlan.cpp`, `planStreamedMemory`).

Housekeeping, resolved the same day: the launcher actually running on this Mac, `~/startllamacpp.sh`, had drifted from the repo launcher. It carried an option 21 (Q2_0 with a local BF16 DFlash2 draft) and a 150K context variant the repo copy did not have, and `dev/benchmarks/test_bonsai_launcher.py` failed 29 of its tests against that copy while all 41 passed against `startllamacpp.sh` in the repo. Option 21 is now ported into the repo launcher with tests, the 150K variant is dropped (no launcher revision ever carried it and the `build/validation/option20-context150k-20261107` directory holds no published result), and `~/startllamacpp.sh` is byte-identical to the repo copy again. Details and the exact diff are in `option20-launcher-drift-20261109/README.md`. Both copies now pass 43 tests, including the new PLE row-cache guards.

## Later on 2026-11-09: the prompt-processing questions were measured

`qwen38-option20-prompt-processing-20261109.md` answers where prompt processing time goes, with a new `--group prefill` size ladder and a new `--group ladder` agent turn shape, both recorded in `option20-experiments/index.tsv`. Three results change the ordering above:

- Cold prefill is expert streaming, and it has a 3.0-3.8 s fixed floor that does not shrink with prompt size (140 tokens takes 3.67 s; 8,204 tokens takes 24.63 s). The two engine items there, P1 (stop re-streaming a 4.4 GB expert working set for a stage that computes 12 rows) and P2 (read-ahead that targets the experts a stage will route), are the prompt-side priorities; P1 is the larger prize because a warm turn's whole 1.10-1.19 s TTFT is that fixed read.
- Cached reuse has a hard floor of about 1.1 s at any prefix size, so R1 and R2 still matter but cannot take a warm turn below that floor until P1 lands.
- In a tool loop, prefix reuse already reaches 87% of tokens with zero spill, and the turn cost stops falling after about 6,700 prompt tokens because new rows prefill at 220 tok/s against a 12K-token context. That is the argument for the agent-side prompt policy (P7 in that document) and it needs no restart or engine change.

R3 is reframed: it is a decode-side experiment, not a prompt-side one. Prefill row hits are 0.900 and a warm stage touches 192 rows, while decode hits 0.614 and has read 5.20M rows. Judge R3 by coding tok/s, not by prefill.

## Closed on 2026-11-10: R1 is out, R5 loses its prompt-side argument, and the build is the Nov 6 one

The three config experiments that needed a restart have run, one variable at a time, on fresh instances of the same build, with a stock control re-run after each override. The full table and the counters are in `qwen38-option20-prompt-processing-20261109.md`; the verdicts are:

- **R1 (24 GiB quota) is closed as a speed lever.** 4K reuse TTFT 2.062 s against 1.952 s for the stock control, with identical spill counters (6 whole-page restores, 192 KV read-back tokens) and identical quota behaviour in both runs. The pinned workload never touches the quota wall, so quota headroom is not what makes a warm turn slow. Keep 16 GiB.
- **R5 keeps its engineering argument and loses its measurement one.** KV residency is still worth an explicit budget, but nothing in these runs shows the KV pool limiting prompt time: spill and read-back are byte-identical across quota settings, and a warm turn's 1.10-1.19 s is expert streaming, not KV. R5 is now justified by capacity safety (`growth_allowed: false`, 0-105 MB headroom, 2 GiB host spare reserve), not by latency.
- **The store-size experiment cannot be run as a launcher override.** The planner clamps the streamed expert store to 2,089,468,688 bytes (`cap == floor`, 512 slots, one chunk) whatever `--expert-memory` requests. `expert-4g-cap-108` (cap 10.8G and chunk 2,048 pinned, so only the store changes) is within noise of stock: 300.4 against 288.7 tok/s, 1.954 against 1.952 s. A raised store has to be an engine change to the clamp in `runtime/engine/MemoryPlan.cpp` (`planStreamedMemory`), not a launcher value.
- **Chunk 1,024 is worse, confirmed.** The 8,204-row cold stage took 41.75 s and 232 GB of expert reads against 24.63 s and 79.20 GB at 2,048. Stage cost is not chunk-wide; P3 is closed.
- **The machine is running the 2026-11-06 build, and no branch switch changes that.** `src-882891f8`, the build that has served every option-20 number since 2026-11-08 20:17, hashes from the `0025f309` / `3e2e1ebc` line (identical `runtime/` trees, recorded in `qwen38-option20-telemetry-performance-20261106.md` as the instrumented reference pair at 408.28 tok/s cold and 1.536 s reuse). The current `splashmain` tip `2b52116b` hashes to `src-81529c7c`, a 186-file engine rewrite that has never been built or measured on this Mac. A half-finished interactive rebase of `splashmain` onto `c72fe592` (2 of 7 commits) was aborted; `splashmain` is back at `2b52116b` in step with `origin/splashmain`, the serving tree is branch `option20-best-pp-20261106` at `0025f309`, and the binary is kept as `build/splash-src882891f8.bak`. That removes the code-regression hypothesis for the reuse gap: 1.539 s then against 1.95-2.03 s now is `nominal` thermal with a 256-page pool and 15.94 GiB of cache versus `fair` thermal with 2,048 pages, 1,690 lifetime KV restores and 17.42 GB against a 16 GiB cap.

## Engine-line A/B on 2026-11-10: the line we run is the faster one

`src-81529c7c` has since been built and measured, so the last open prompt-side question is closed. Against the running `src-882891f8` line, in the same session, each with its own empty 16 GiB prefix cache and every other flag identical, cold prefill at 2,048 / 4,096 / 8,192 tokens was 199.53 against 215.66, 242.10 against 268.51, and 294.50 against 324.27 tok/s: the tip line is 8-11% slower at every prompt size and won nothing, while warm reuse (1.10-1.17 s) and coding decode (11.05 against 11.23 tok/s) were the same. `splashmain` keeps the memory and safety work; it does not hold a faster prompt path. The table, the protocol, and the cache-root eviction trap are in `qwen38-option20-engine-line-comparison-20261110.md`.

## Not recommended now

- Do not enlarge the expert store as a first move. It sits at its 2,089,468,688 byte floor with 41 of 512 slots resident and `hit_rate` 0.00 on both phases, and the 2026-11-05 retention experiment already produced 3.82% routed hits with no speedup and more SSD bytes per token. The 2026-11-09 measurements supply the mechanism that was missing (19.1 MB of expert reads per prompt token, 4.4-4.6 GB re-streamed for a 12-row warm stage), but that argues for P1 and P2 in `qwen38-option20-prompt-processing-20261109.md`, which cost no Metal. Treat the store-size experiment (P5 there) as last, with decode tok/s as the rollback trigger.
- Do not shrink read-ahead or workers to reduce SSD load. The 2026-11-05 I/O comparisons were slower. Read-ahead waste is real and larger than the lifetime average suggests (`ahead_used_bytes` / `ahead_read_bytes` is 0.67 for the 8,204-token probe stage, 0.87 lifetime prefill, 0.79 lifetime decode), but the fix is better targeted prefetch, not less depth.
- Do not raise the Metal cap as a first move. Governor headroom exists but growth is already blocked by the host spare reserve, and pressure is `warning`; a cap change without the residency work in R5 buys nothing.
- Do not enable a second active request or concurrent lanes for these numbers. They add SSD work, which the 2026-11-06 report already flagged as needing measured controls.
- Do not read `cache.hit_rate` or `streamed_table.hit_rate` movement as progress. Judge by 4K reuse TTFT, 4K cold prefill tok/s, and coding decode tok/s.
- Do not rebuild this Mac onto `2b52116b` to chase prompt speed. It is now measured, not just unmeasured: `src-81529c7c` ran 8-11% slower cold prefill than the `src-882891f8` line at every prompt size tested. If it is built again for the memory work, keep the current binary (`build/splash-src882891f8.bak`) and re-run the pinned pair before anything is called a result.

## Suggested order

For the reuse path the order has changed: R1 is closed by measurement, so the reuse path is now P1 (scale the expert working set to the rows a stage actually computes) with R2 and R5 kept as engine work for capacity and for KV residency rather than for latency. For the prompt path, P1 then P2, both engine changes over `src-882891f8`; P3 is closed and P5 needs the planner clamp removed before it can be measured at all. P7, the agent-side prompt policy, needs neither a restart nor an engine change and can be applied while the rest waits: new tokens cost 4-8 ms each and cached tokens cost nothing.
