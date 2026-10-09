# Splash performance test, 2026-10-09

Current Bonsai median short-coding decode: **21.11 tokens/s**, with **37.96% draft acceptance**. Five isolated requests completed without failures and Metal remained healthy. No end-to-end upstream Bonsai speedup was measured: fetched upstream lacks the local PTQ1_0 path.

## Workload and provenance

Apple M5, GPU family 10, eight GPU cores, 16 GiB unified memory. Current commit `882c6d887c52`; fetched upstream `c35f3eaa01e0`. Live build ID `src-5a54ebc57301fb80a33e2d009aab28419fbdff023c223b4ac4acdea9ed9bb590`.

Bonsai PTQ1_0 and existing DFlash draft, INT8 KV, 24,576-token context, 512-token prefill chunks, one active request, reasoning none, temperature zero, persistent 8 GiB disk-cache quota. The previously stopped endpoint became available during preparation; its model and build were verified before using it. That existing service was left running. Launcher and OpenCode configuration were not changed.

## Live inference

| Request | Prompt / cached tokens | Output tokens | Prefill tok/s | Decode tok/s | Total seconds | Draft acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short_coding_1 | 129 / 96 | 256 | 59.62 | 21.67 | 12.404 | 37.96% |
| short_coding_2 | 129 / 96 | 256 | 59.62 | 21.11 | 12.693 | 37.96% |
| short_coding_3 | 129 / 96 | 256 | 58.05 | 20.78 | 12.897 | 37.96% |
| long_cold | 4917 / 0 | 96 | 177.08 | 37.22 | 30.271 | 91.21% |
| long_cached | 4917 / 4896 | 96 | 44.22 | 37.15 | 3.036 | 91.21% |

Prefill tok/s uses the newly processed tokens. The long cold prompt processed all 4,917 tokens in 27.767 s; the repeat reused 4,896 and processed only the remaining 21. Cache reuse reduced total request time from 30.271 s to 3.036 s; decode stayed about 37.2 tok/s. The short coding prompt reused 96 of 129 prompt tokens, so its roughly 59 tok/s prompt figure is not a cold-prefill benchmark.

All three short responses matched exactly. Cold/cached long responses matched exactly and recalled ORCHID. Every request was isolated (one submitted/completed request between status snapshots). Requests failed: zero; Metal failures: zero. The long counting task is simpler than coding and has higher draft acceptance; its decode rate should not be used as the coding rate.

## Matched kernel comparison

Synthetic Q4_K weights; 17,408 output by 5,120 input columns; nine weight copies of about 50.1 MB, maintaining a DRAM-cold ring. Each process warms up and reports medians of ten rounds; outer build order current/upstream/upstream/current. Table values are the median of the two process medians for each build, on its selected plan. These are GPU projection times, not complete model tokens/s.

| Workload | Current ms | Upstream ms | Upstream time change |
| --- | ---: | ---: | ---: |
| Gate/up decode, 1 lane(s) | 0.9205 | 0.9512 | +3.33% |
| Gate/up decode, 2 lane(s) | 0.8926 | 0.8928 | +0.02% |
| Gate/up decode, 3 lane(s) | 1.1412 | 1.1287 | -1.09% |
| Gate/up decode, 4 lane(s) | 1.1480 | 1.1251 | -1.99% |
| 512-row prefill | 8.1937 | 8.1971 | +0.04% |

Positive time change means slower. On this eight-core M5, the new spread-walk/one-pass dense decode policy (at least 16 cores) is not selected. Prefill was essentially unchanged; one-lane gate/up measured about 3.3% slower. With only two process samples per build and no thermal control, small differences are indicative rather than a robust regression verdict. These trials do not cover fused-prefill dispatch improvements, MLX loading, MoE model throughput or the cache redesign.

## Memory and limits

Memory pressure remained warning. Native device current allocation went from 8.005 to 8.132 GiB. This is Metal allocation, not total process RSS. System swap before: `vm.swapusage: total = 4096.00M  used = 3067.56M  free = 1028.44M  (encrypted)`; after: `vm.swapusage: total = 4096.00M  used = 3043.56M  free = 1052.44M  (encrypted)`. The 24 MiB decrease is system-wide and does not prove Splash experienced no paging.

No controlled thermal cooldown or other-app workload control was applied. The nonce in the cold long prompt prevented prefix reuse, confirmed by zero cached tokens. Only one cold-prefill sample was taken. Historical October 7 figures are not a matched A/B comparison with this run. A merged Bonsai benchmark still requires resolving the format-ID collision and the full-window rebuild versus small-prefill-buffer incompatibility.

## Artifacts

Raw responses, complete status snapshots, model/build identity, native benchmark outputs and runner scripts: `build/validation/performance-20261009/`. No runtime source changes or merge were made.
