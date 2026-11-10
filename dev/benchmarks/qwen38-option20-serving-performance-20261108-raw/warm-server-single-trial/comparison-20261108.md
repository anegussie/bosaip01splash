# Option 20 side-by-side: 2026-11-08 run vs the 2026-11-06 reference

Machine in both runs: Apple M5 MacBook Air, 8 GPU cores, 16 GiB unified memory, 10.8 GiB Metal cap, 2,048 prefill chunk, INT8 KV, BF16 state, DFlash2 `--ngram 4 --draft 16`.

## Per-probe numbers

| probe | Nov 6 prefill tok/s (2 trials) | Nov 8 | delta | Nov 6 TTFT s | Nov 8 | delta | Nov 6 decode tok/s | Nov 8 | delta | Nov 6 draft acc | Nov 8 draft acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| smoke-cold | 76.52 / 76.49 | 87.04 | +13.8% | 4.590 / 4.591 | 4.426 | -3.6% | 12.32 / 12.34 | 12.54 | +1.7% | 98.8% | 100.0% (83/83) |
| smoke-reuse | 14.47 / 14.63 | 15.23 | +4.7% | 2.151 / 2.131 | 2.178 | +1.7% | 12.37 / 12.39 | 12.42 | +0.3% | 98.8% | 98.8% (83/84) |
| 4k-cold | 408.53 / 405.29 | 312.15 | -23.3% | 9.842 / 9.921 | 13.040 | +32.0% | 12.64 / 12.67 | 11.55 | -8.7% | 98.8% | 94.2% (81/86) |
| 4k-reuse | 12.23 / 12.52 | 13.99 | +13.1% | 1.558 / 1.521 | 2.511 | +63.1% | 12.46 / 12.48 | 11.19 | -10.3% | 98.8% | 89.0% (81/91) |
| code-1 | 15.64 / 15.37 | 18.94 | +22.2% | 2.113 / 2.150 | 2.487 | +16.7% | 9.61 / 9.62 | 9.17 | -4.6% | 83.6% | 85.0% (96/113) |
| code-2 | 15.73 / 15.63 | 16.92 | +7.9% | 2.037 / 2.049 | 2.368 | +15.9% | 9.68 / 9.66 | 9.66 | -0.1% | 83.2% | 82.1% (87/106) |
| code-3 | 16.13 / 16.27 | 17.06 | +5.3% | 2.236 / 2.215 | 2.231 | +0.2% | 10.71 / 10.96 | 10.07 | -7.1% | 94.4% | 95.4% (104/109) |

Nov 6 baseline pair: draft acceptance 1259/1357 = 92.8%
Nov 8: draft acceptance 615/672 = 91.5%
coding decode mean: Nov 6 10.04 (9.61-10.96), Nov 8 9.63 (9.17-10.07), delta -4.1%
4K cold prefill mean: Nov 6 406.91, Nov 8 312.15, delta -23.3%
4K reuse TTFT mean: Nov 6 1.539 s, Nov 8 2.511 s, delta +63.1%

Prompt sizes differ: Nov 6 351 / 4,019 / 33-36 tokens; Nov 8 385 / 4,067 / 38-47 tokens. Longer prompts slightly *inflate* prefill tok/s, so the 4K gap is understated.

## Run conditions

| item | Nov 6 (reference) | Nov 8 (this run) |
| --- | --- | --- |
| server | fresh launch on `127.0.0.1:1245`, 2 prior requests | same long-lived launch on `127.0.0.1:1235`, ~2h40m uptime, 28 prior requests (including a 30k-token probe at 20:18) |
| engine build | `src-6a06f0d6...` (Nov 5 baseline binary, reused Nov 6) | `src-882891f8...` (Nov 6 instrumented line, HEAD 3e2e1ebc) |
| trials | 2 complete matrix trials, A/B then B/A order | 1 trial (smoke gate first) |
| memory pressure | warning | warning |
| thermal | nominal, drifting to fair only late in the second pair | fair for the entire run |
| Metal allocated / peak | 7.875 / 8.290 GiB | 8.482 / 8.498 GiB |
| host available / spare | 2.51-2.58 GB / ~2.2 GB | 2.47 GB / 2.11-2.32 GB |
| governor headroom | 536 MB before, 611-671 MB after | 0 MB before, 655-671 MB after (`growth_allowed: false`) |
| KV pool state at start | freshly allocated 1,792 pages (57,344 tokens) | 1,792 pages with 1,555 already cached, only 237 free |
| persistent prefix cache | empty after a fresh launch | 8.54 GB of 11.17 GB cacheable at cap (76%) already resident |

Both runs recorded zero capacity failures, zero Metal failures, zero KV spill, and zero competing requests during probes.

## What moved

1. Short-prompt cold prefill got *faster* (smoke 87.04 vs 76.51, code prompts 16.9-18.9 vs 15.4-16.3 tok/s).
2. The 4K path is where the loss is: cold prefill 312.15 vs 406.91 tok/s (-23%, TTFT 13.04 vs 9.84 s), reuse readback TTFT 2.511 vs 1.558 s (+63%) even with 4,032/4,067 tokens cached.
3. Decode is down only on the long-context probes (4K -8.7% / -10.3%), unchanged on smoke (12.54/12.42 vs 12.32/12.37), and down 4% on coding (9.63 vs 10.04 mean).
4. Draft acceptance is the same overall (91.5% vs 92.7%) but the shape changed: Nov 6 4K probes accepted 83/84 (98.8%), this run accepted 81/86 and 81/91 (94% / 89%).

## Most likely causes

- Cache-state difference is the leading candidate. Nov 6 ran on a freshly launched engine with an empty KV pool; this run inherited a nearly full pool (237 free pages of 1,792, 1,555 cached, 8.54 GB already on disk). The 4K probes must reclaim and promote pages before they can compute, which matches the pattern exactly: long-context prefill and reuse readback regress, short prompts unaffected or better.
- Sustained `fair` thermal instead of `nominal` explains part of the long-prefill and 4K-decode gap on an 8-core Air, but not the smoke decode staying flat, and not the reuse-TTFT jump.
- Metal footprint is 0.61 GiB higher than Nov 6 (8.482 vs 7.875 GiB allocated), leaving less staging room for a 4K chunk.

## Not comparable on these numbers

- The engine line is different (instrumented `882891f8` vs baseline `6a06f0d6`), and the reported model identity digests differ (`loaded_model_layout_sha256` 92020136... vs b7f2417c..., `target_model_sha256` f22d21e0... vs 261aef54...). The GGUF blobs themselves are untouched (HF revision `dbba1494...`, blobs dated Oct 31; a full-file sha256 matches neither digest), so these digests are internal prepared-layout ids rather than model file hashes.
- One trial vs two, and `fair` vs `nominal` thermal, means the deltas are indicative, not decision-grade.
## Fixed per-request prompt-phase floor

The server's `prompt_ms` covers the whole prompt phase (cache readback included), and `prompt_per_second` is computed over the *uncached* tokens only, so the reuse rates above are comparable but are not raw compute rates.

| probe (uncached tokens) | Nov 6 prompt_ms | Nov 8 prompt_ms |
| --- | --- | --- |
| smoke-cold (351 / 385) | 4,587 / 4,589 ms | 4,422 ms |
| smoke-reuse (31 / 33 cached 320 / 352) | 2,143 / 2,119 ms | 2,167 ms |
| 4k-cold (4,019 / 4,067) | 9,838 / 9,917 ms | 13,029 ms |
| 4k-reuse (19 / 35, cached 4,000 / 4,032) | 1,553 / 1,518 ms | 2,501 ms |
| code-1 (33 / 47) | 2,110 / 2,147 ms | 2,482 ms |
| code-2 (32 / 40) | 2,035 / 2,048 ms | 2,363 ms |
| code-3 (36 / 38) | 2,232 / 2,213 ms | 2,228 ms |

Tiny prompts pay a ~0.35 s higher fixed floor on the 16 GiB Air today (2.36-2.48 s vs 2.03-2.15 s), while the 4K probes lose about 2.9-3.2 s more than that floor can explain.

## Fields this run did not capture

`metrics.speculation.cycles` and `metrics.decode.tokens` are per-request fields this runner did not record, so cycles and tokens-per-cycle cannot be compared against the Nov 6 rows (`cycles: 13`, `tokens_per_cycle: 7.385`). Drafted/accepted counts and acceptance rates are directly comparable (verified against the `/status` counter deltas for each probe).

