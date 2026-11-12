# Option 21 read-ahead performance comparison - 2026-11-12

The candidate did not deliver a consistent prefill or decode improvement. All observed
fresh-throughput ranges overlap. Keep the original production engine and prepared caching
disabled by default; these results do not justify enabling the candidate for speed.
That decision has been applied: the original engine remains live, prepared caching is off,
and only the new read-ahead prototype edits were restored to their pre-experiment source.
The launcher fix for retaining 2,048-token chunks with custom context/cache settings remains useful.

Original and candidate binaries were frozen before the run. The primary comparison
uses the same immutable, warmed prepared-expert cache in A1/B1/B2/A2 order.
Each cell reports the median of two trials with its observed range.

| Filled prompt | Engine | Fresh PP tok/s | Fresh decode TPS | Cold first token s | Cached decode TPS | Cached first token s |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 4,108 | Original | 412.48 (411.76-413.21) | 23.99 (23.97-24.01) | 9.965 (9.948-9.982) | 23.36 (23.33-23.40) | 0.895 (0.848-0.943) |
| 4,108 | Candidate | 412.69 (410.38-414.99) | 24.49 (23.95-25.02) | 9.960 (9.904-10.016) | 24.04 (23.25-24.83) | 0.875 (0.828-0.921) |
| 8,204 | Original | 440.32 (440.25-440.39) | 22.85 (22.84-22.86) | 18.639 (18.635-18.642) | 23.47 (23.46-23.47) | 0.751 (0.749-0.753) |
| 8,204 | Candidate | 439.19 (437.53-440.85) | 22.86 (22.80-22.92) | 18.688 (18.616-18.760) | 23.41 (23.37-23.45) | 0.748 (0.748-0.749) |
| 16,396 | Original | 412.90 (400.06-425.73) | 23.22 (23.02-23.43) | 39.763 (38.526-41.000) | 23.13 (23.06-23.20) | 0.905 (0.883-0.927) |
| 16,396 | Candidate | 408.03 (390.36-425.70) | 22.92 (22.74-23.10) | 40.279 (38.540-42.018) | 23.31 (23.22-23.41) | 0.894 (0.889-0.900) |

## Candidate change relative to original

| Content tokens | Fresh PP | Fresh decode TPS | Cold first token | Cached decode TPS | Cached first token |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4,096 | +0.05% | +2.09% | -0.05% | +2.91% | -2.29% |
| 8,192 | -0.26% | +0.05% | +0.27% | -0.24% | -0.37% |
| 16,384 | -1.18% | -1.30% | +1.30% | +0.78% | -1.16% |

Higher throughput and lower latency are better. Two observations per engine/context
show repeatability limits; these percentage differences are not statistical confidence bounds.

## Default path controls

The normal path, with prepared caching disabled, was checked once per engine at 8K.
These are controls, not a repeated performance comparison.

| Engine | Fresh PP tok/s | Fresh decode TPS | Cold first token s | Cached decode TPS | Cached first token s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 440.76 | 22.95 | 18.622 | 22.90 | 0.758 |
| Candidate | 439.99 | 23.10 | 18.654 | 22.87 | 0.756 |

## Correctness, memory and conditions

| Arm | Timed requests | Correct | New swap-out pages | Thermal states | Pressure | Expert slots | Draft acceptance |
| --- | ---: | --- | ---: | --- | --- | --- | ---: |
| A1 | 7 | Yes | 0 | fair, nominal | warning | 1512 | 96.87% |
| B1 | 7 | Yes | 0 | fair, nominal | warning | 1512 | 96.87% |
| B2 | 7 | Yes | 0 | fair, nominal | normal, warning | 1512, 1786 | 96.87% |
| A2 | 7 | Yes | 0 | fair, nominal | normal, warning | 1512, 1786 | 96.20% |
| native-baseline | 3 | Yes | 0 | fair, nominal | normal, warning | 1512, 1786 | 94.63% |
| native-candidate | 3 | Yes | 0 | fair, nominal | warning | 1512 | 94.63% |

## Expert I/O and host-step work

Mean reported counters per seven-request arm, excluding warmup:

| Engine | Native source reads GiB | Prepared payload reads GiB | Prefill host-step work s | Decode host-step work s |
| --- | ---: | ---: | ---: | ---: |
| Original | 364.01 | 5.94 | 7.475 | 15.713 |
| Candidate | 360.81 | 7.09 | 7.521 | 15.489 |

The smoke gates verified fresh and reused-prefix requests, a restart restore of the
persistent prefix, prepared-cache hits with zero new writes/errors/corruptions,
and executable Python output on both engines before the timed matrix.
Every recall/counting completion used 96 output tokens; code used a 192-token budget
and was executed against assertions. Thinking was disabled, temperature 0, seed 1234.
Automatic verification matches option 21's serving profile and can produce different
greedy outputs between requests; executable/recall correctness is checked independently.

Both engines used the Q2_0 target and the same BF16 DFlash2 draft, INT8 KV, BF16 state,
131,072 server context, 10.8G cap, 2,048-token chunks, automatic expert memory,
64M PLE, one active request, and isolated 3G persistent prefix caches on the 16 GiB M5.
Requests were submitted sequentially. The test transport used its default concurrency
cap rather than production's explicit cap of one; no overlapping inference was observed.
The largest prompt actually filled was 16,396 tokens; this does not measure full 131K throughput.
The prepared cache's exact existing footprint was its quota, preventing writes and eviction.
Cold means zero reused prefix tokens, with model/OS caches already warm. All timed
requests started at nominal thermals; sampled states and memory pressure appear above.
All 34 timed requests passed, with no new macOS swap-outs and no KV spill. Peak Metal
allocation was 8.622 GiB.
Host pressure changed expert residency during some shorter requests in B2 and A2; every
16K cold request used 1,512 slots. This limits attribution of the small throughput differences.
The frozen cache holds 372 of 24,576 experts (about 1.5%); these results apply to that
bounded cache and do not establish the behavior of a larger prepared-expert working set.
The benchmark's temporary prefix caches were removed only after their servers stopped;
the user's production prefix cache and model files were preserved.

The original service was restored on port 1235 with matching model/build identity,
context and chunk settings. No production binary was replaced.

## Evidence

[Raw results, requests, responses, status, system snapshots and reproduction scripts](qwen38-option21-readahead-performance-20261112-raw/).
`contract.json` records the workload, `binaries/*/sha256.json` pins both builds,
and each arm's `ready.json` records the loaded model/build identity and memory plan.
`frozen-cache-manifest.json` pins cache entries; its content was checked after every arm.
`summary.json` includes I/O and host-step work deltas, draft acceptance, KV spill and memory.
I/O deltas can include forecasts crossing request boundaries. Host-step work does not
separately identify CPU execution, SSD waits or the fused GPU critical path. Native source
bytes already include native read-ahead; prepared payload bytes have separate counters.
The power snapshot records AC power and Low Power Mode disabled.
`production-restored.json` records final service readiness.
The large executables, Metal libraries and prepared-cache payloads are retained locally
and excluded from Git; their manifests are versioned. The runner requires the original
cache-enabled experimental wrapper and archived artifacts, as explained in the raw README.
