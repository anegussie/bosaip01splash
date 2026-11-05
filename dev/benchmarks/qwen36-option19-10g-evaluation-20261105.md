# Option 19: 10 GiB memory and chunk-size evaluation, November 5, 2026

Selected profile: **10 GiB memory cap, automatic expert cache, requested 512-token chunks**. The larger budget improves decode on these short coding fixtures, while cold prefill is largely unchanged. The 1024 follow-up measured about 2.5% higher cold prefill at 57K (702.5 versus 685.4 tok/s), with higher but variable decode: 41.5-50.9 tok/s in the two 1024 trials versus 37.4-41.0 in the three 512 controls. At 4K and 32K, decode was essentially unchanged. This limited follow-up does not establish a reliable overall advantage, so 512 is retained conservatively. Requested 2048-token chunks also showed no consistent overall advantage. All three chunk settings allocate 805.14 MiB of shared prefill workspace and start with 3,186 expert slots at 10 GiB, versus 1,730 slots at 8 GiB.

Matched real-launcher comparison on Apple M5 / 16 GiB. Configuration: Qwen3.6-35B-A3B UD-IQ3_XXS, 81,920 server context, INT8 KV, BF16 state, DFlash2, verify-rows auto, one active request, reasoning none, temperature 0, seed 42, and a separate 2 GiB persistent prefix cache per launch.

Order: 8G/512, 10G/512, 10G/2048, 10G/2048, 10G/512, 8G/512. The requested 1024-token follow-up then ran as two further independent 10G/1024 launches with the same artifact, prompts, cache isolation, correctness checks and thermal controls. A further fresh 10G/512 control followed both 1024 launches. The 1024 follow-up was not fully interleaved with the other settings, so small differences can reflect condition drift. The legacy 8G profile uses the 1900M expert-memory floor; the 10G profiles use automatic expert memory so the extra budget can hold more experts. This comparison evaluates the complete memory profiles, including their expert-cache choices.

Cells report arithmetic means of per-request metrics; parentheses give the request-time range.

| Memory / requested chunk | Filled prompt | Mode | Trials | PP tok/s | Decode tok/s | SSE TTFT s | Request s (min-max) |
|---|---:|---|---:|---:|---:|---:|---:|
| 8G / 512 | 4,013 | cached | 2 | suffix only | 47.0 | 0.343 | 1.727 (1.718-1.736) |
| 8G / 512 | 4,013 | cold | 2 | 1256.8 | 44.6 | 3.198 | 4.656 (4.642-4.670) |
| 8G / 512 | 32,689 | cached | 2 | suffix only | 35.5 | 0.455 | 1.969 (1.737-2.201) |
| 8G / 512 | 32,689 | cold | 2 | 905.5 | 36.7 | 36.132 | 37.415 (37.080-37.749) |
| 8G / 512 | 57,259 | cached | 2 | suffix only | 34.3 | 0.332 | 1.791 (1.751-1.831) |
| 8G / 512 | 57,259 | cold | 2 | 685.3 | 33.2 | 83.601 | 85.018 (84.935-85.102) |
| 10G / 512 | 4,013 | cached | 3 | suffix only | 69.0 | 0.269 | 1.211 (1.209-1.214) |
| 10G / 512 | 4,013 | cold | 3 | 1283.6 | 59.0 | 3.131 | 4.234 (4.228-4.239) |
| 10G / 512 | 32,689 | cached | 3 | suffix only | 54.0 | 0.324 | 1.195 (1.193-1.196) |
| 10G / 512 | 32,689 | cold | 3 | 907.8 | 54.7 | 36.037 | 36.896 (36.777-36.956) |
| 10G / 512 | 57,259 | cached | 3 | suffix only | 43.7 | 0.263 | 1.344 (1.226-1.443) |
| 10G / 512 | 57,259 | cold | 3 | 685.4 | 39.8 | 83.624 | 84.807 (83.048-86.449) |
| 10G / 1024 | 4,013 | cached | 2 | suffix only | 69.0 | 0.268 | 1.210 (1.205-1.215) |
| 10G / 1024 | 4,013 | cold | 2 | 1285.5 | 58.9 | 3.126 | 4.231 (4.231-4.232) |
| 10G / 1024 | 32,689 | cached | 2 | suffix only | 54.7 | 0.324 | 1.185 (1.168-1.202) |
| 10G / 1024 | 32,689 | cold | 2 | 922.8 | 54.7 | 35.461 | 36.321 (35.801-36.840) |
| 10G / 1024 | 57,259 | cached | 2 | suffix only | 50.5 | 0.235 | 1.170 (1.107-1.234) |
| 10G / 1024 | 57,259 | cold | 2 | 702.5 | 46.2 | 81.559 | 82.589 (82.519-82.659) |
| 10G / 2048 | 4,013 | cached | 2 | suffix only | 69.2 | 0.269 | 1.209 (1.206-1.212) |
| 10G / 2048 | 4,013 | cold | 2 | 1284.9 | 59.0 | 3.130 | 4.231 (4.229-4.232) |
| 10G / 2048 | 32,689 | cached | 2 | suffix only | 54.6 | 0.379 | 1.241 (1.161-1.321) |
| 10G / 2048 | 32,689 | cold | 2 | 910.5 | 54.9 | 35.934 | 36.789 (36.610-36.969) |
| 10G / 2048 | 57,259 | cached | 2 | suffix only | 47.7 | 0.278 | 1.266 (1.229-1.304) |
| 10G / 2048 | 57,259 | cold | 2 | 695.1 | 43.4 | 82.511 | 83.599 (80.972-86.225) |

Cold means zero prefix reuse, with warm model/OS caches. Cached requests reuse all but the short suffix and do not measure full-prompt prefill. Every timed response is streamed and checked using the existing executable coding fixtures. Readiness, exact output, cold/cache round trip, forced tool call, tool-result continuation and SSE are smoke-tested before each phase. Timed pairs begin after two consecutive nominal thermal readings.

The source in runtime/model/RuntimeArenas.hpp forces fixed 2,048-row geometry for grouped streamed experts on this target. All requested chunks therefore share the same prefill allocation. The requested setting is not proof of different effective chunk geometry.

Two trials per cell, plus one additional 512 control, provide a limited current-condition comparison. DFlash2 automatic verification can vary generated token counts even with greedy sampling. These are short coding outputs (48-66 tokens), not sustained long-generation tests. Different tasks are used at 4K versus 32K/57K, so compare settings within each depth. No concurrency or full 80K filled-context performance claim is made. Thermal states, memory pressure, Metal peaks and system-wide swap are retained in the JSON; system-wide swap is not attributable solely to this benchmark.

Build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Binary SHA-256: `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691`.

Complete: True. Timed checks passed: 54.

[Machine-readable summary](qwen36-option19-10g-evaluation-20261105.json). Full requests, responses, SSE events, statuses, logs and runner are retained locally under `build/validation/option19-10g-20261105/` and `build/validation/option19-10g-1024-20261105/` and `build/validation/option19-10g-control-20261105/`.
