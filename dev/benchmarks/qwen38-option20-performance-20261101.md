# Option 20 live performance — 2026-11-01

Completed through the existing option-20 launcher/server on the 16 GiB Apple M5. This is current-condition characterization, without a matched baseline or a speedup claim.

| Workload | Trials | Prompt tokens | Prefill tok/s | TTFT seconds | Decode tok/s |
|---|---:|---:|---:|---:|---:|
| 1024 target | 3 | 939 | 41.50 (41.43–41.54) | 22.63 | 12.53 |
| 4096 target | 3 | 4,019 | 45.65 (45.62–45.69) | 88.04 | 12.72 |
| 28672 target | 1 | 28,589 | 42.47 (42.47–42.47) | 673.12 | 11.65 |

The two 435-token smoke requests passed. Repeating the same prompt reused 416 tokens in RAM and reduced measured TTFT from 11.93 s to 1.35 s. Each timed cold trial used a distinct cache salt and reported zero cached tokens. SSD prefix caching was disabled; this is not a persistent-cache restart test.

All nine responses produced ORCHID and the expected first ten counting numbers. Each request allowed 96 output tokens. This is a bounded recall/counting check, not a general coding or model-quality evaluation. One 28,589-token trial establishes this filled-context run only; the full 32,761-token limit was not filled.

Configuration: ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS; served context 32,761 tokens; 8 GiB planner cap; INT8 KV / BF16 recurrent state; 128-token prefill chunks, one Flash-Next chunk at a time; 64 MiB PLE cache; shared 1,262 MiB expert arena; one active request; DFlash2; timed reasoning none, temperature 0, seed 42. Ten-second inter-trial cooldowns. No build or other benchmark ran during measurement.

Build: `src-b979053e53d106d076879ab22d26987d3c2d5e75e50e19149b88b9faeaff0951`. Git HEAD: `456195a4c17e0dda26cbec8091289cb72a73567a` (working tree includes local modifications). Launcher SHA256: `a072688465361af818905f87a3fcd4e83d88becdcb345d57ea255ac8b52ce88e`.

Thermals began nominal and ended fair. Memory pressure began normal and ended warning; the server temporarily paused memory growth during the long run. Swap used decreased from 1,113.88 MiB to 1,097.88 MiB; this does not imply no swapping. End-of-run Metal allocated/current/peak bytes were {'allocated_bytes': 7680410544, 'current_bytes': 7697907712, 'peak_bytes': 7729364992}. The planner cap is not total process RSS. No failed or cancelled requests, capacity failures, or Metal failures were reported.

Raw requests, SSE events, timings, per-request status, swap snapshots, and aggregate run: `build/validation/option20-performance-20261101/performance.json` and adjacent artifacts. The existing server remains running at http://127.0.0.1:1235.
