# Option 20 expert telemetry performance check, November 6, 2026

The new expert read-ahead and format-eviction counters did not produce a measurable throughput change in this short serving-path check. Fresh servers ran in baseline/instrumented/instrumented/baseline order (A/B/B/A) under warning memory pressure. The small differences below are within run-to-run variation, not a speedup or regression claim. No cache or prefetch policy changed between binaries.

## Matched setup

- M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, target SHA-256 `261aef54bdfbeb8fb5bae01deeef4eb70f820fe19f410e4ed9de46c344969117`. All runs used the same installed model and Metal libraries.
- 131,072 served context; 2,048-token prefill chunks; 10.8G Metal cap (`11,596,411,699` bytes); automatic expert store (1.946 GiB including staging); 64 MiB PLE row cache; INT8 KV; BF16 state; DFlash2 and automatic verify rows; one active request; 16 GiB persistent prefix-cache quota. The server used port 1245 with no other server process.
- Baseline binary SHA-256 `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691`, build ID `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Instrumented binary SHA-256 `a1a2c042f202fc72395157d902a4736a076ec303ec22ce439812c7f720277673`, build ID `src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a`.
- Each fresh server passed a 351-token cold/reuse SSE smoke gate: correct ORCHID/count output, zero cold cached tokens, 320 reused tokens, complete SSE. Only after that gate did the 4,019-token cold/reuse pair and three 128-token-cap coding probes run. Cold requests used distinct cache salts; the repeat used the same salt. Each matched A/B pair's seven outputs were byte-identical, with identical draft acceptance; the second pair's third coding output differed from the first pair under automatic verification. All timed rows were uncontended.
- All four matrices began at `memory_pressure=warning`, `thermal_state=nominal`, `growth_allowed=false`, and the same 8.29 GiB Metal allocation peak. Pressure stayed at warning; the second B and A ended at `thermal_state=fair`, while the first pair remained nominal. Host available memory at matrix start was 2.51-2.58 GB. The runs were serial with cooldowns; OS caches were not flushed.

## Serving-path results

| Probe | Baseline mean (range) | Instrumented mean (range) | Unit |
|---|---:|---:|---|
| 351-token cold smoke prefill | 76.51 (76.49-76.52) | 76.63 (76.60-76.65) | tok/s |
| 4,019-token cold prefill | 406.91 (405.29-408.53) | 408.28 (407.83-408.73) | tok/s |
| 4,019-token cold SSE TTFT | 9.877 (9.838-9.917) | 9.844 (9.833-9.855) | s |
| 4,019-token reuse, 4,000 cached, SSE TTFT | 1.538 (1.519-1.556) | 1.534 (1.478-1.590) | s |
| Coding probe decode mean, three prompts | 10.04 (10.00-10.08) | 10.06 (10.00-10.11) | tok/s |
| Decode expert source reads, five timed requests | 327.425 (326.476-328.373) | 327.408 (326.422-328.394) | GB |

The coding outputs reached the 128-token cap, so identical bytes within each matched pair confirm the matched execution path but do not establish code quality. The 4K correctness prompt checked the exact final code and count sequence. Decode throughput depends on this prompt mix and draft acceptance. Only two trials per build were run; the fair thermal state late in the second pair limits comparisons further.

## New counter observations

| Instrumented matrix delta | B1 prefill | B1 decode | B2 prefill | B2 decode |
|---|---:|---:|---:|---:|
| Expert reads / routed experts | 36,274 / 36,274 | 172,980 / 172,980 | 36,274 / 36,274 | 171,824 / 171,824 |
| Expert source bytes, GB | 73.088 | 328.394 | 73.088 | 326.422 |
| Read-ahead bytes, GB | 32.507 | 107.471 | 32.542 | 107.079 |
| Read-ahead bytes used by routed experts, GB | 24.991 (76.9%) | 89.285 (83.1%) | 25.026 (76.9%) | 88.818 (82.9%) |
| Read-ahead bytes unused by the next load, GB | 7.516 | 18.186 | 7.516 | 18.261 |
| Resident experts evicted on a shared-arena format switch | 34,833 | 173,525 | 34,833 | 172,385 |

The shared arena gives this 16 GiB machine a feasible expert-store floor, but the format switches removed nearly all residency opportunities in these requests. The decode read-ahead delivered most of the bytes it read, so the counters alone do not justify reducing workers or shrinking prefetch. The prior controlled worker and piece-size comparisons in [option-20 I/O tuning](qwen38-option20-io-tuning-20261105.md) were slower. A cache or scheduling change needs its own matched trial before adoption.

Raw SSE request records, per-request timings, and before/after `/status` snapshots are in [qwen38-option20-telemetry-performance-20261106-raw](qwen38-option20-telemetry-performance-20261106-raw/). The local runner is `/private/tmp/option20-perf-20261106.py`; it calls the existing `/private/tmp/perf-flashnext-20261102/perf_lib.py` harness.
