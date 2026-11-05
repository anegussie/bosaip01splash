# Option 20: shared expert retention, November 5, 2026

Two expert-retention prototypes were implemented and tested. Neither established a throughput gain. The original option-20 runtime and profile remain active; the experimental source changes were removed, and the tested implementation is preserved as a patch.

Revised-matrix UTC interval: 2026-11-05T11:15:02.766377+00:00 to 2026-11-05T11:31:32.127493+00:00.

M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Exact model: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2, 131,072 served context, 10 GiB engine cap, one active request, 1,024-token prefill chunks, INT8 KV, BF16 state, verification auto. The 26.82 GiB n-gram table stays SSD-backed with the existing approximately 64 MiB RAM row cache. Persistent prefix cache: 16 GiB.

## Prototype implementation and validation

Shared formats retain only experts whose packed byte ranges remain intact. Bounded overlap masks choose free slots that discard fewer cached experts, favor decode-reused entries, and age that preference after roughly 32 cycles. Large prefill chunks clear other formats once and bypass per-slot conflict searches. Other stores retain their existing ARC policy. Release and failed-load cleanup also clear the retention metadata.

The new native regression failed on the baseline because format switching discarded sparse experts that fit together. Both candidates passed the complete expert-store Metal suite across four shapes, with bitwise resident-weight comparisons, forced overwrites, mixed quantizations, read failures and release/restore. CPU tests check byte overlaps, absent planes, alignment, bitset boundaries, metadata bounds, reuse preference and existing recycler traces.

## Matched serving results

A/B/B/A uses four fresh server instances, the same serving arguments, one minute idle cooldown before each block and five seconds between requests. Each block passes a 435-token cold/reuse ORCHID/count-to-30 smoke gate before its 4,019-token cold/reuse pair and two short coding probes. Cold means a unique prefix salt with zero cached prompt tokens; SSD/OS caches are not flushed. B2 additionally restores the B1 4K prefix from SSD before its smoke gate; that extra earlier workload is a comparison limitation. Sampling is temperature zero, seed 42. Coding uses low reasoning and a 256-token output cap; these are throughput probes, not completed coding tasks. Each build gets four coding trials and two 4K cold/reuse pairs.

| Metric | Baseline | Revised retention |
|---|---:|---:|
| Coding decode tok/s, mean (range) | 8.37 (7.90-8.98) | 7.98 (7.62-8.43) |
| Coding expert SSD MB/output token | 690.29 (655.64-710.36) | 707.03 (685.79-728.64) |
| Coding routed expert hit fraction | 0.00% | 3.82% |
| Cold 4K prefill tok/s | 203.41 (202.33-204.48) | 192.43 (181.39-203.47) |
| Cold 4K SSE TTFT seconds | 19.77 (19.67-19.88) | 20.96 (19.76-22.16) |
| Reuse 4K SSE TTFT seconds | 1.53 (1.52-1.54) | 1.58 (1.56-1.60) |
| Total expert store cap, including staging/metadata | 1.945969 GiB | 1.949022 GiB |
| Additional retention metadata within expert budget | 0 | 3.1262 MiB |

Observed coding mean change: -4.57%; SSD bytes per output token: +2.42%. These are small-sample observations on a passively cooled machine with other desktop activity uncontrolled; ranges, drift and B2's extra persisted replay limit causal conclusions. Cache hits alone do not establish a speedup. Filled-131K inference and other Macs/DGX Spark were not benchmarked here.

All 17 ORCHID/count checks passed; all 25 responses completed SSE with clean request counters. No per-request Metal/capacity failures or server-instance changes. The candidate restart restored the B1 4K prefix from SSD and passed the exact output check. A power sample after B2 showed AC power at 80% and Low Power Mode off. Thermal states: ['fair', 'nominal']; memory pressure: ['normal']; headroom 1.686-2.389 GiB.

## Every serving row

| Row | Prompt | Cached | PP tok/s | Decode tok/s | SSD MB/decode token | Expert hits | Finish | Check |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A1-smoke-cold | 435 | 0 | 90.53 | 12.49 | 500.07 | 0.00% | stop | pass |
| A1-smoke-reuse | 435 | 416 | 11.77 | 12.56 | 497.90 | 0.00% | stop | pass |
| A1-4k-cold | 4019 | 0 | 204.48 | 12.63 | 494.91 | 0.00% | stop | pass |
| A1-4k-reuse | 4019 | 4000 | 12.52 | 12.59 | 496.75 | 0.00% | stop | pass |
| A1-code-1 | 61 | 0 | 20.22 | 8.51 | 684.99 | 0.00% | length | output capped |
| A1-code-2 | 61 | 0 | 20.42 | 8.98 | 655.64 | 0.00% | length | output capped |
| B1-smoke-cold | 435 | 0 | 90.48 | 12.54 | 498.50 | 2.36% | stop | pass |
| B1-smoke-reuse | 435 | 416 | 11.10 | 12.73 | 491.35 | 3.91% | stop | pass |
| B1-4k-cold | 4019 | 0 | 203.47 | 12.53 | 495.98 | 2.25% | stop | pass |
| B1-4k-reuse | 4019 | 4000 | 12.25 | 12.47 | 494.95 | 3.82% | stop | pass |
| B1-code-1 | 61 | 0 | 19.97 | 8.43 | 686.25 | 3.63% | length | output capped |
| B1-code-2 | 61 | 0 | 20.10 | 8.20 | 685.79 | 4.14% | length | output capped |
| B2-persisted-replay | 4019 | 4000 | 11.61 | 12.58 | 496.32 | 1.69% | stop | pass |
| B2-smoke-cold | 435 | 0 | 90.59 | 12.64 | 495.26 | 2.17% | stop | pass |
| B2-smoke-reuse | 435 | 416 | 12.60 | 12.69 | 492.41 | 3.30% | stop | pass |
| B2-4k-cold | 4019 | 0 | 181.39 | 11.86 | 508.24 | 2.25% | stop | pass |
| B2-4k-reuse | 4019 | 4000 | 11.93 | 11.26 | 513.07 | 3.21% | stop | pass |
| B2-code-1 | 61 | 0 | 20.04 | 7.69 | 727.42 | 3.93% | length | output capped |
| B2-code-2 | 61 | 0 | 20.08 | 7.62 | 728.64 | 3.57% | length | output capped |
| A2-smoke-cold | 435 | 0 | 90.46 | 12.53 | 500.36 | 0.00% | stop | pass |
| A2-smoke-reuse | 435 | 416 | 11.78 | 12.58 | 497.87 | 0.00% | stop | pass |
| A2-4k-cold | 4019 | 0 | 202.33 | 12.55 | 495.12 | 0.00% | stop | pass |
| A2-4k-reuse | 4019 | 4000 | 12.38 | 12.31 | 499.15 | 0.00% | stop | pass |
| A2-code-1 | 61 | 0 | 20.37 | 8.08 | 710.36 | 0.00% | length | output capped |
| A2-code-2 | 61 | 0 | 20.63 | 7.90 | 710.19 | 0.00% | length | output capped |

## Initial candidate: every completed serving row

This earlier A/B/B/A used five-second request cooldowns and no additional block cooldown. Its two candidate blocks used count-only retention. These rows are separate from the revised candidate and are not pooled with it.

| Initial candidate metric | Baseline | Count-only retention |
|---|---:|---:|
| Coding decode tok/s, mean | 8.135 | 8.283 |
| Coding expert SSD MB/decode token, mean | 697.35 | 684.15 |
| Routed expert hit fraction | 0.00% | 2.49% |
| Total expert-store cap including staging/metadata | 1.945969 GiB | 1.949022 GiB |
| Additional retention metadata within expert budget | 0 | 3.1256 MiB |

| Row | Prompt | Cached | PP tok/s | Decode tok/s | SSD MB/decode token | Expert hits | Finish | Check |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A1-smoke-cold | 435 | 0 | 90.75 | 12.53 | 500.46 | 0.00% | stop | pass |
| A1-smoke-reuse | 435 | 416 | 11.67 | 12.64 | 495.27 | 0.00% | stop | pass |
| A1-4k-cold | 4019 | 0 | 203.26 | 12.54 | 495.58 | 0.00% | stop | pass |
| A1-4k-reuse | 4019 | 4000 | 12.21 | 12.58 | 496.83 | 0.00% | stop | pass |
| A1-code-1 | 61 | 0 | 20.65 | 8.57 | 702.80 | 0.00% | length | output capped |
| A1-code-2 | 61 | 0 | 20.17 | 8.72 | 684.98 | 0.00% | length | output capped |
| B1-smoke-cold | 435 | 0 | 88.67 | 12.38 | 497.85 | 1.02% | stop | pass |
| B1-smoke-reuse | 435 | 416 | 11.85 | 12.51 | 495.96 | 1.27% | stop | pass |
| B1-4k-cold | 4019 | 0 | 189.80 | 12.47 | 496.17 | 1.02% | stop | pass |
| B1-4k-reuse | 4019 | 4000 | 12.44 | 12.43 | 498.49 | 1.12% | stop | pass |
| B1-code-1 | 61 | 0 | 20.34 | 8.62 | 688.06 | 2.51% | length | output capped |
| B1-code-2 | 61 | 0 | 20.17 | 8.71 | 679.00 | 2.52% | length | output capped |
| B2-persisted-replay | 4019 | 4000 | 12.28 | 12.18 | 499.99 | 1.77% | stop | pass |
| B2-smoke-cold | 435 | 0 | 89.98 | 12.11 | 505.73 | 1.14% | stop | pass |
| B2-smoke-reuse | 435 | 416 | 11.76 | 12.18 | 504.22 | 0.72% | stop | pass |
| B2-4k-cold | 4019 | 0 | 174.54 | 11.96 | 500.95 | 1.18% | stop | pass |
| B2-4k-reuse | 4019 | 4000 | 12.31 | 11.50 | 512.90 | 0.92% | stop | pass |
| B2-code-1 | 61 | 0 | 20.47 | 8.17 | 691.78 | 2.72% | length | output capped |
| B2-code-2 | 61 | 0 | 20.16 | 7.63 | 677.74 | 2.21% | length | output capped |
| A2-smoke-cold | 435 | 0 | 73.26 | 10.99 | 494.92 | 0.00% | stop | pass |
| A2-smoke-reuse | 435 | 416 | 11.57 | 12.21 | 507.47 | 0.00% | stop | pass |
| A2-4k-cold | 4019 | 0 | 175.88 | 9.85 | 486.17 | 0.00% | stop | pass |
| A2-4k-reuse | 4019 | 4000 | 12.17 | 10.95 | 495.77 | 0.00% | stop | pass |
| A2-code-1 | 61 | 0 | 20.44 | 7.53 | 689.27 | 0.00% | length | output capped |
| A2-code-2 | 61 | 0 | 20.40 | 7.72 | 712.36 | 0.00% | length | output capped |

## Identity and evidence

Hashes below were recorded for the prototype build. The production source was restored after the experiment; the complete prototype is preserved in `qwen38-option20-expert-retention-20261105.patch`.

Baseline: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Candidate: `src-092c6cdb9869d5221401024e519b47c87835b236f659c12e4320a2dc1b8a1684`.

| Artifact | SHA-256 |
|---|---|
| `build/splash` | `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` |
| `build/splash.metallib` | `826339b41ce381c8bc5e4823d213e178e8687ac4743c9b4b01fcafb476e583eb` |
| `build/expert-retention-20261105/splash` | `ec70b7e93fdb45d6acdd9d79fdf186ff1848c13efc0999eea4ce0cbc8bf0fadf` |
| `build/expert-retention-20261105/splash.metallib` | `826339b41ce381c8bc5e4823d213e178e8687ac4743c9b4b01fcafb476e583eb` |
| `build/expert-retention-20261105/host-step.metallib` | `8e177c753e2051cd8a31c79bf031b3fae8daf04f5564ced9fc37db064bdfe51a` |
| `runtime/model/SharedExpertArena.hpp` | `dd7110a83b48ed747fa5c998b0114ad387e9e8c5677904f35a840badf06968f9` |
| `runtime/model/ExpertStore.cpp` | `f9bb53657586b37da5843706de1cfea778c734d7fe61a8300a3e8a05548a1155` |
| `runtime/model/SlotRecycler.cpp` | `d11dbe3638485d5e9353d82e6d0430940e9e45ec924ec9e0ac602243466901a5` |

The JSON package contains per-request results, full before/after status, identities and raw-artifact checksums. Raw requests, parsed SSE events, logs and the reproduction are retained under `build/validation/expert-retention-v2-20261105/` and `build/expert-retention-20261105/`.

The initial count-only candidate and its A/B/B/A run remain in `build/validation/expert-retention-20261105/`. That run measured coding 8.135 versus 8.283 tok/s and 697.35 versus 684.15 MB/token, with substantial later-baseline drift; it did not establish a throughput gain. Initial harness-only interpreter, child-reaping and artifact-path failures are archived there and excluded from the completed matrices.
