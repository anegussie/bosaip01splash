# Option 19 postmerge performance comparison

Status: complete. 18/18 timed executable coding checks passed. Three independent current launches each run a cold/cache pair at 4K, 32K and 57K.

Observed arithmetic-mean prefill improved 4.1-16.6%, cold decode 9.6-42.2%, and cached decode 11.4-26.8%. Cold first-token latency decreased 3.9-14.1%. These are historical cross-run observations.

At 32K, cached completion wall time increased 17.7% (1.195 to 1.406 seconds), even though TPS increased, because the valid generated function grew from 48 to 70 tokens. At 57K cached output grew from 48 to 51 tokens; 4K remained 66 tokens and 57K cold remained 48. Throughput, first-token latency and whole-response time therefore answer different questions.

Historical control: November 5 selected 10 GiB / requested 512 profile only. Current characterization: November 18 following the Splash 1.7.0 merge. Same M5 / 16 GiB host, Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2, INT8 KV, BF16 state, 81,920 configured context, automatic expert memory, one active request, verify-rows auto, vision enabled and isolated 2 GiB persistent caches. No production cache is cleared.

The original workload and helper were recovered from session 01a1ad99-024b-7041-9ecd-f1d839ee4792 because the old build/validation runner was gone. Timed requests retain the exact system instruction, repository-note filler, task text, 384-token cap, temperature 0, seed 42 and reasoning none. Cache salts differ to isolate each launch. Filled prompt lengths are asserted equal to the historical values: 4,013 / 32,689 / 57,259. Cold means zero prefix reuse with model/OS caches warm. Cached repeats use the identical prompt and reuse all but the suffix. SSE first-content latency starts before the HTTP request, matching the historical helper.

Arithmetic means and observed ranges are shown, matching the baseline aggregation. These are short executable coding outputs, not sustained generation, broad coding quality, concurrency or full 80K filled-context tests. Different tasks are used at 4K (stable_unique) versus 32K/57K (chunked). Automatic verification can change generated output even with a fixed seed.

| Filled prompt | Build | Cold PP tok/s | Cold decode TPS | Cached decode TPS | Cold TTFT s | Cached TTFT s | Cold wall s | Cached wall s | Valid cold/cache |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4,013 | Before | 1283.58 (1281.98-1285.49) | 58.97 (58.92-59.02) | 69.04 (68.87-69.15) | 3.13 (3.13-3.14) | 0.27 (0.27-0.27) | 4.23 (4.23-4.24) | 1.21 (1.21-1.21) | 3/3 |
| 4,013 | After | 1335.92 (1331.19-1344.03) | 83.82 (83.55-84.05) | 76.89 (76.76-76.98) | 3.01 (2.99-3.02) | 0.19 (0.19-0.19) | 3.78 (3.76-3.80) | 1.03 (1.03-1.03) | 3/3 |
| 32,689 | Before | 907.83 (906.28-910.82) | 54.72 (54.53-54.83) | 53.97 (53.86-54.16) | 36.04 (35.92-36.10) | 0.32 (0.32-0.32) | 36.90 (36.78-36.96) | 1.20 (1.19-1.20) | 3/3 |
| 32,689 | After | 1010.22 (999.33-1027.90) | 59.95 (59.93-59.99) | 60.47 (60.26-60.68) | 32.39 (31.83-32.74) | 0.26 (0.26-0.27) | 33.54 (32.98-33.89) | 1.41 (1.40-1.41) | 3/3 |
| 57,259 | Before | 685.36 (671.67-699.60) | 39.83 (37.43-41.03) | 43.73 (40.34-47.83) | 83.62 (81.90-85.30) | 0.26 (0.24-0.28) | 84.81 (83.05-86.45) | 1.34 (1.23-1.44) | 3/3 |
| 57,259 | After | 799.40 (760.41-836.97) | 52.75 (50.84-54.03) | 55.43 (51.76-57.86) | 71.79 (68.47-75.36) | 0.15 (0.15-0.16) | 72.68 (69.34-76.28) | 1.06 (1.01-1.13) | 3/3 |

## Per-trial correctness and resources

| Pass / filled prompt | Mode | Output tokens | Cached tokens | Prefill tok/s (cached: suffix) | Decode TPS | TTFT s | Wall s | Correct | Thermals | OS swap-out pages | KV disk demotions | Expert slots after |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|
| 1 / 4,013 | cold | 66 | 0 | 1344.03 | 84.05 | 2.990 | 3.764 | True | nominal / nominal | 0 | 0 | 3206 |
| 1 / 4,013 | cached | 66 | 4000 | 71.11 | 76.76 | 0.185 | 1.032 | True | nominal / nominal | 0 | 0 | 3206 |
| 1 / 32,689 | cold | 70 | 0 | 1027.90 | 59.93 | 31.830 | 32.982 | True | nominal / nominal | 0 | 0 | 3206 |
| 1 / 32,689 | cached | 70 | 32672 | 65.94 | 60.68 | 0.263 | 1.400 | True | nominal / nominal | 0 | 0 | 3206 |
| 1 / 57,259 | cold | 48 | 0 | 800.80 | 53.37 | 71.555 | 72.436 | True | nominal / fair | 0 | 64 | 3206 |
| 1 / 57,259 | cached | 51 | 57248 | 79.83 | 57.86 | 0.147 | 1.012 | True | fair / fair | 0 | 0 | 3206 |
| 2 / 4,013 | cold | 66 | 0 | 1332.54 | 83.87 | 3.016 | 3.792 | True | nominal / nominal | 0 | 0 | 3206 |
| 2 / 4,013 | cached | 66 | 4000 | 71.23 | 76.93 | 0.185 | 1.030 | True | nominal / nominal | 0 | 0 | 3206 |
| 2 / 32,689 | cold | 70 | 0 | 1003.42 | 59.99 | 32.607 | 33.758 | True | nominal / nominal | 0 | 0 | 3206 |
| 2 / 32,689 | cached | 70 | 32672 | 65.44 | 60.26 | 0.265 | 1.410 | True | nominal / nominal | 0 | 0 | 3206 |
| 2 / 57,259 | cold | 48 | 0 | 760.41 | 50.84 | 75.356 | 76.281 | True | nominal / fair | 0 | 0 | 3206 |
| 2 / 57,259 | cached | 51 | 57248 | 73.94 | 51.76 | 0.159 | 1.126 | True | fair / fair | 0 | 0 | 3206 |
| 3 / 4,013 | cold | 66 | 0 | 1331.19 | 83.55 | 3.019 | 3.798 | True | nominal / nominal | 0 | 0 | 3206 |
| 3 / 4,013 | cached | 66 | 4000 | 71.10 | 76.98 | 0.186 | 1.030 | True | nominal / nominal | 0 | 0 | 3206 |
| 3 / 32,689 | cold | 70 | 0 | 999.33 | 59.94 | 32.741 | 33.893 | True | nominal / nominal | 0 | 0 | 3206 |
| 3 / 32,689 | cached | 70 | 32672 | 65.06 | 60.47 | 0.266 | 1.408 | True | nominal / fair | 0 | 0 | 3206 |
| 3 / 57,259 | cold | 48 | 0 | 836.97 | 54.03 | 68.467 | 69.337 | True | nominal / fair | 0 | 0 | 3206 |
| 3 / 57,259 | cached | 51 | 57248 | 74.24 | 56.66 | 0.155 | 1.039 | True | fair / fair | 0 | 0 | 3206 |

Current timed requests recorded 0 new system-wide swap-out pages. Full vm_stat snapshots retain the page size; existing swap usage and fresh swap-outs are separate. KV disk demotions can persist idle prefixes and do not prove active-request KV spill. Resource monitors retain active-request state, disk traffic, expert residency, memory pressure and thermals. This target did not report a per-request KV mode, so no residency claim is inferred from that absent field. No RAM-only execution claim is made.

Each timed pair starts after two nominal thermal readings five seconds apart, matching the old runner. The immediate cached request can inherit warmer thermals from cold prefill; per-trial endpoints and two-second monitor samples are retained. Memory pressure and background system conditions can differ across dates.

This is a historical comparison, not a matched causal A/B of the merge. Build identities, automatic expert-cache sizing and recurrent-state allocations differ. The historical runtime was src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d; the current build and frozen artifact hashes are in the contract and binary manifest. Historical expert slots were 3,186; current before/after counts are retained per request.

The initial startup-only attempt was rejected because its harness expected /status.prefill_chunk_tokens to report the requested 512. The merged runtime reports effective warmup geometry of 2,048 rows on this target. RuntimeArenas.hpp already fixed this grouped geometry in the old profile; requested 512 is retained in the command. Attempt 2 checks both independently and preserves the failed attempt without timed data.

Smoke checks before each launch matrix cover exact output, cold/cache reuse, forced tool calls, tool-result continuation, SSE, and executable code. The first pass also validates persistent 4K coding-prefix reuse across a clean restart before subsequent passes. Failed smoke checks block dependent workloads.

Evidence: [contract](option19-postmerge-20261118-raw/attempt-2/contract.json), [full timed rows](option19-postmerge-20261118-raw/attempt-2/rows.json), [binary hashes](option19-postmerge-20261118-raw/attempt-2/binary-sha256.json), [model source manifest](option19-postmerge-20261118-raw/attempt-2/model-manifest.json), [historical summary](qwen36-option19-10g-evaluation-20261105.json). Requests, full responses, SSE events, before/after status and vm_stat snapshots are saved alongside each trial. No builds occur during inference.

All 18 timed requests and 21 per-launch smoke checks passed, plus persisted-prefix restart reuse. The original option 21 service was restored with the same command arguments, model/build identity, production cache, logging and telemetry. Frozen and live binary hashes were unchanged. The four unrelated modified files are preserved. [Final verification](option19-postmerge-20261118-raw/attempt-2/final-verification.json). Runtime logs and resource monitors: [saved evidence](option19-postmerge-20261118-raw/attempt-2/runtime/).
