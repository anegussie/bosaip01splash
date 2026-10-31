# Splash 57K prefill repeat — 2026-10-31

Measured 2026-10-31T04:23:24Z to 2026-10-31T04:30:40Z against the existing launcher service at `127.0.0.1:1235`. All 6 timed coding responses passed behavioral checks. Readiness, cold/cached reuse, forced tool call/result, SSE, and streaming coding smoke checks passed. The service was retained without restart.

| Filled prompt | Cold PP tok/s (range) | Decode tok/s (range) | Cold TTFT | Cached TTFT |
|---:|---:|---:|---:|---:|
| 57,259 | 728.4 (709.7–747.8) | 33.8 (31.6–35.7) | 78.61s | 0.33s |

Three cold/cached pairs at 57,259 filled prompt tokens, synthetic repository notes followed by the chunked coding task. Temperature 0, seed 42, reasoning off, output limit 384 tokens, concurrency 1. Each pair began at nominal thermals; cached requests followed cold requests immediately. Cold cache hits were zero, and cached hits were within 64 tokens of the filled prompt. Throughput aggregates stage tokens over stage time; decode excludes each response’s first token. TTFT was measured from SSE content arrival.

Apple M5, 8 GPU cores, 16 GiB; Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2; INT8 KV, BF16 states, 81,920-token server context, 512-token prefill chunks, 8 GiB memory limit, 1,992,294,400-byte expert-memory setting. Existing persistent SSD cache: 2 GiB, with pre-existing contents; per-pair cache salts isolated benchmark prefixes. No disk-cache clearing or model reload was performed.

Current source commit: `3d5ebf1d91bf32dc7b506862a4199de7830b6d2e`. Running engine and current source fingerprint match: `src-44a14cb4f0af35b0b4e60c10496ed858b741f4deebdca7ba4020266340fb87f4`. Binary SHA256: `b10ca9af72c0c9a6045cfd214503153fc9d3b2be26d53817a1fa91657edf82aa`. Exact target/draft revisions and installed-file digests are saved in `run.json`.

Observed thermal states: fair, nominal. Observed memory-pressure states: normal, warning. System swap before: `vm.swapusage: total = 2048.00M  used = 637.00M  free = 1411.00M  (encrypted)`; after: `vm.swapusage: total = 2048.00M  used = 629.00M  free = 1419.00M  (encrypted)`. Full per-request VM, memory governor, swap, cache and status snapshots are retained.

Request-counter delta including smoke checks: `{"cancelled": 0, "completed": 13, "failed": 0, "submitted": 13}`. No service-instance change or unrelated request was detected during the checked request windows. This characterizes the existing service under current machine and cache conditions; it does not establish a speedup over an older build.

Raw requests, responses, SSE events, status snapshots, harness, source identity, summary and logs: `/Users/mymac/splash/splash/build/validation/prefill57k-repeat-20261031`. The authorized harness output is in `runner.log`. Existing unrelated untracked work was preserved.

Individual cold trials:

| Trial | Prompt tokens | Prefill tok/s | Prefill seconds | SSE TTFT seconds |
|---:|---:|---:|---:|---:|
| 1 | 57,259 | 747.8 | 76.57 | 76.57 |
| 2 | 57,259 | 728.8 | 78.57 | 78.57 |
| 3 | 57,259 | 709.7 | 80.68 | 80.69 |

Weighted cold prefill: 728.4 tok/s; +5.3% versus the preceding live run (692.0 tok/s), and +2.2% versus October 30 (712.6 tok/s). The earlier 669.8 tok/s trial was not reproduced. Conditions remain uncontrolled between sessions; no cause or source speedup is established.
