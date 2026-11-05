# Option 20 Air performance - completed November 5, 2026

Measured through the already running option-20 HTTP server on the M5 MacBook Air, **8 GPU cores and 16 GiB unified memory**. The matrix ran from 2026-11-04T23:55:00.828489-05:00 to 2026-11-05T00:20:45.553676-05:00 (Toronto local time). This run used the existing server without a build or restart and started no other benchmark. Other desktop activity was not controlled. This characterizes current conditions and does not establish a speedup from the single-request default.

## Configuration and method

`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2 draft, 131,072 served context, 10 GiB engine ceiling, one admitted active request, 1,024-token prefill chunks, INT8 KV, BF16 state, `verify-rows auto`, 64 MiB PLE row-cache reservation with the full n-gram table SSD-backed, and a 16 GiB persistent prefix-cache quota. The host cache/staging allocations mean SSD-backed does not imply a disk read for every lookup.

One untimed READY warmup precedes each phase. The smoke gate checks cold/reused prompts, exact ORCHID/count-to-30 output, complete SSE, native speculation and low/medium reasoning modes before the matrix. Timed rows use temperature zero, seed 42 and ten-second cooldowns. Cold rows use unique cache salts and must report zero cached prompt tokens; SSD/OS caches are not flushed. Long prompts use repeated benign repository-note filler followed by an ORCHID/counting task, rather than a novel codebase. Each replay keeps the prompt and salt unchanged. Native prefill/decode rates and SSE first-nonempty-content latency are distinct metrics. Request counters and native queues identify contamination, and every row retains its actual output, usage, timings, parsed SSE events and before/after status.

## Cold and immediate-prefix-reuse results

Rates are tokens/second; latency is seconds. Values show mean and min-max for repeated trials. Decode here is predictable counting output with reasoning disabled, not coding throughput.

| Actual prompt tokens | Clean cold/reuse pairs | Cold prefill tok/s | Cold SSE TTFT | Reuse SSE TTFT | Cold decode tok/s |
|---:|---:|---:|---:|---:|---:|
| 4,019 | 3 | 204.36 (204.26-204.51) | 19.67 (19.66-19.68) | 1.56 (1.52-1.58) | 12.53 (12.37-12.62) |
| 28,589 | 3 | 183.27 (174.16-195.87) | 156.40 (145.99-164.16) | 1.16 (1.13-1.18) | 11.97 (11.79-12.06) |
| 65,367 | 1 | 162.91 (one trial) | 401.31 (one trial) | 1.73 (one trial) | 10.27 (one trial) |

The 65K group has one pair and establishes no variability. Filled-131K inference was not tested. Reuse timings are immediate-prefix replays; disk-hit counter deltas are retained in the package and must not be mistaken for an independent cold-disk/restart benchmark. The separate implementation validation previously checked a clean restart and disk restoration.

## Short output styles

These use short prompts, not the long-context counting prompts. Coding uses low reasoning and the agent-style probe uses medium reasoning. The code and medium probes each have a 256-token output budget. Rates include reasoning tokens, and length-limited responses are not completed coding or agent tasks. The prose/arithmetic/prime probes are output-shape checks rather than semantic-quality evaluations.

| Style | Clean trials | Decode tok/s | Mean draft acceptance | Mean tokens/cycle | Finish reasons |
|---|---:|---:|---:|---:|---|
| style-primes | 1 | 10.24 (one trial) | 0.959 | 7.714 | stop |
| style-arithmetic | 1 | 8.32 (one trial) | 0.688 | 3.750 | stop |
| style-code-low | 3 | 8.86 (8.73-9.02) | 0.890 | 3.618 | length, length, length |
| style-prose-none | 1 | 6.89 (one trial) | 0.681 | 2.167 | stop |
| style-agent-medium | 3 | 7.13 (6.99-7.22) | 0.691 | 2.580 | length, length, length |

16 bounded ORCHID/counting checks passed. All 27 measured/smoke responses completed SSE. Contaminated rows: `[]`. Reasoning-only output caps in medium probes: 3; a null visible-answer TTFT for that explicitly length-capped case is not a transport failure.

## Identity and conditions

Live build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Checkout HEAD: `b2754de09ae7d729fd7ff25096027a20fae18011`; the working tree includes the uncommitted launcher/profile work. These are different identities: the benchmark measures the live binary, not a newly built checkout. Engine SHA-256: `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691`; metallib SHA-256: `826339b41ce381c8bc5e4823d213e178e8687ac4743c9b4b01fcafb476e583eb`. Both remained unchanged. Launcher SHA-256: `f5ae8056bc0d39a2cc748a1217f502d7300e9f94b1747ed21957f52933cc525d`.

Matrix UTC interval: 2026-11-05T04:55:00.828489+00:00 to 2026-11-05T05:20:45.553676+00:00. Thermal states: ['fair', 'nominal']; memory-pressure states: ['warning']. Observed host headroom: 0.00-0.53 GiB. Failure deltas: `{'metal_failures': 0, 'capacity_failures': 0}`; native restarts: 0. Request-counter deltas, including the phase warmup: `{'submitted': 24, 'completed': 24, 'failed': 0, 'cancelled': 0}`.

Swap before: `vm.swapusage: total = 2048.00M  used = 340.25M  free = 1707.75M  (encrypted)`. Swap after: `vm.swapusage: total = 2048.00M  used = 332.25M  free = 1715.75M  (encrypted)`. These snapshots do not establish the absence of swapping. Observed Metal memory at start/end: `{'allocated_bytes': 7383942064, 'current_bytes': 7401439232, 'peak_bytes': 7829061632}` / `{'allocated_bytes': 7492469680, 'current_bytes': 7509966848, 'peak_bytes': 8161132544}`. Peak counters are cumulative for the running server, not isolated trial peaks or total process RSS.

The expert store ended at 1.946 GiB with 512 slots and cumulative decode hit rate 0.0000. PLE-cache evictions during the matrix: 0. Resource suspensions: 0; replayed prompt tokens: 0. Prefix-cache counters increased by 0.00 GiB read and 3.07 GiB written; these are native cache counters, separate from expert-weight reads and not an independent SSD benchmark.

The first smoke attempt failed in an added request-logging hook before any HTTP request or inference. The hook was corrected and the full smoke gate passed before the matrix. The initial helper source and diagnostic remain in the raw folder. No timed workload was hidden or discarded for that error.

[Saved measurement package](qwen38-option20-air-performance-20261105.json) preserves all matrix/smoke rows, identity, conditions, initial/final status and SHA-256 values of raw artifacts. Full payloads, parsed SSE events, per-row status, harness source and progress/results remain in `build/validation/option20-air-performance-20261104-single/`. No commit or push was performed. The service remains on http://127.0.0.1:1235 with the same profile.
