# Performance tests after upstream pull, 2026-10-11

Correctness passed; the end-to-end speed comparison is inconclusive because of thermal and timing drift. Eight of nine MoE GPU timing comparisons pass the repository ABBA rule; B1 is inconclusive.

Baseline: pre-pull `52df938`. Candidate: merged `bfcdad2`. Order: baseline, candidate, candidate, baseline. Each version was built from its own source and uses its own native binary and metallib. The HTTP frontend and request harness were held constant from the candidate checkout. All servers used the same immutable installed model assembly and were stopped after testing. No service was running initially.

Apple M5, 8 GPU cores, 16 GiB RAM, macOS 26.5.2. Bonsai 27B PTQ1_0, target revision `b072e1d3b35a0a630cece372c2127528e0994386`, Qwen3.8-27B DFlash2 revision `015e795645c74b1a0eeef3b570031fb62e769bc5`. INT8 KV, 24,576 declared context, 512-token prefill chunks, one active request, GPU-only prefill, temperature zero, reasoning none, temporary 8 GiB SSD cache per launch. This run tests in-session cache reuse, not persistence across restarts.

## Inference correctness

All 12 generated utility functions passed behavioral checks, including empty input, input mutation, unhashable equality, touching/nested intervals and invalid chunk sizes. All requests were isolated. Each task produced the same text and output token count in all four rounds. Coding draft acceptance is unchanged: merge_intervals 71.43%, stable_unique 66.07%, chunked 78.57%. All eight context requests recalled ORCHID and returned the same text. Every cold context request had zero cached tokens; every repeat reused 4,864 of 4,892 prompt tokens. Metal remained healthy, with no failed requests.

## End-to-end timing

Each build contributes two runs. Decode values below are the reciprocal of the mean milliseconds per token. Prefill values are prompt tokens divided by mean prompt time. They describe the observed run, not a demonstrated speed change.

| Workload | Pre-pull | Merged | ABBA verdict |
| --- | ---: | ---: | --- |
| merge_intervals decode, tok/s | 31.07 | 32.81 | inconclusive |
| stable_unique decode, tok/s | 28.14 | 29.21 | inconclusive |
| chunked decode, tok/s | 33.28 | 33.31 | inconclusive |
| 4,892-token cold prefill, tok/s | 174.45 | 177.80 | inconclusive |
| 96-token counting decode, tok/s | 35.96 | 36.87 | inconclusive |
| Cold context request, seconds | 30.69 | 30.10 | inconclusive |
| Cached context request, seconds | 2.96 | 2.92 | inconclusive |

The repository rule declares comparisons with more than 5% within-build spread inconclusive. Every end-to-end metric exceeded that threshold: 15.45–24.29%. Thermal state was nominal in the first baseline round, changed to fair during the first candidate round, and remained fair. The final baseline slowed as well. No controlled cooldown or other-app workload control was applied. These results support neither a speedup nor a regression claim.

## MoE kernel timing

Synthetic sparse 35B geometry: hidden 2,048, 256 experts, top 8, intermediate 512; Q4_K gate/up, Q5_K down, Q8_0 shared expert, F32 router. This is a GPU kernel benchmark, not Bonsai model throughput. Each of four alternating invocations takes a 20-command median after its initial warmup. Times are mean round medians in milliseconds per layer.

| Shape | Pre-pull ms | Merged ms | Verdict |
| --- | ---: | ---: | --- |
| prefill_2048 | 15.8240 | 15.8355 | pass |
| decode_B1 | 0.6375 | 1.2340 | inconclusive |
| decode_B2 | 0.7985 | 0.7900 | pass |
| decode_B3 | 1.2440 | 1.2380 | pass |
| decode_B4 | 1.4490 | 1.4470 | pass |
| prefill_64 | 3.8310 | 3.8320 | pass |
| prefill_128 | 4.5630 | 4.5535 | pass |
| prefill_256 | 4.9685 | 4.9840 | pass |
| prefill_512 | 6.3120 | 6.2985 | pass |

The eight stable shapes change by between -1.06% and +0.31% in time, providing no material speedup. B1 varied from 0.468–0.807 ms for baseline and 0.453–2.015 ms for candidate, so its apparent difference is invalid.

## Memory and scope

Fixed planned runtime memory: 8466.00 -> 8501.14 MiB (+35.14 MiB). The declared 24K context and planned KV capacity are unchanged. The candidate shifts scratch from shared prefill to decode tape storage. Metal allocation is not process RSS or total host memory.

Host memory pressure was warning throughout. System swap was already in use; per-round values are retained in [the summary](bonsai-performance-20261011.json) and are not attributable to Splash alone. Only about 3.7K coding prompts and the 4.9K context workload were exercised; this does not establish filled-24K performance, multi-client throughput or representative long code-review speed.

Production builds succeeded for both versions. Before this benchmark, the merged model execution-plan test and GDN decode CPU-reference correctness test on Metal passed. The committed summary is [bonsai-performance-20261011.json](bonsai-performance-20261011.json). Benchmark logs, raw replies/status, run.json and summary.json remain locally in `build/validation/performance-20261011/`. All temporary benchmark servers were stopped after testing.

Baseline build ID: `src-b8a04d5e4f7c0f3cfcca6285ea85bcc753c486e5c9f30ec9f7ce668cfb9e1e81`.
Candidate build ID: `src-7549ecf874f174013a970e4b0214830f3f2eb7a0bd5e9607ca376c5ff87beae8`.
