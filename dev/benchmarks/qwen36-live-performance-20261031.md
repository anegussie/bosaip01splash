# Splash live-service performance — 2026-10-31

Measured 2026-10-31T03:58:40Z to 2026-10-31T04:14:06Z against the existing launcher service at `127.0.0.1:1235`. All 18 timed coding responses passed behavioral checks. Readiness, cold/cached reuse, forced tool call/result, SSE, and streaming coding smoke checks passed. The service was retained without restart.

| Filled prompt | Cold PP tok/s (range) | Decode tok/s (range) | Cold TTFT | Cached TTFT |
|---:|---:|---:|---:|---:|
| 4,012 | 1250.8 (1242.8–1255.0) | 39.1 (36.9–41.9) | 3.21s | 0.34s |
| 32,685 | 933.9 (918.4–949.1) | 40.6 (39.5–41.9) | 35.01s | 0.40s |
| 57,259 | 692.0 (669.8–705.8) | 32.7 (30.9–35.2) | 82.77s | 0.36s |

Three rotated cold/cached pairs per depth, synthetic repository notes followed by merge_intervals (4K), stable_unique (32K), or chunked (57K). Temperature 0, seed 42, reasoning off, output limit 384 tokens, concurrency 1. Each pair began at nominal thermals; cached requests followed cold requests immediately. Cold cache hits were zero, and cached hits were within 64 tokens of the filled prompt. Throughput aggregates stage tokens over stage time; decode excludes each response’s first token. TTFT was measured from SSE content arrival. Different tasks across depths mean these rows are workload characterizations rather than a pure context scaling comparison.

Apple M5, 8 GPU cores, 16 GiB; Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2; INT8 KV, BF16 states, 81,920-token server context, 512-token prefill chunks, 8 GiB memory limit, 1,992,294,400-byte expert-memory setting. Existing persistent SSD cache: 2 GiB, with pre-existing contents; per-pair cache salts isolated benchmark prefixes. No disk-cache clearing or model reload was performed.

Current source commit: `3d5ebf1d91bf32dc7b506862a4199de7830b6d2e`. Running engine and current source fingerprint match: `src-44a14cb4f0af35b0b4e60c10496ed858b741f4deebdca7ba4020266340fb87f4`. Binary SHA256: `b10ca9af72c0c9a6045cfd214503153fc9d3b2be26d53817a1fa91657edf82aa`. Exact target/draft revisions and installed-file digests are saved in `run.json`.

Observed thermal states: fair, nominal. Observed memory-pressure states: normal, warning. System swap before: `vm.swapusage: total = 2048.00M  used = 653.00M  free = 1395.00M  (encrypted)`; after: `vm.swapusage: total = 2048.00M  used = 645.00M  free = 1403.00M  (encrypted)`. Full per-request VM, memory governor, swap, cache and status snapshots are retained.

Request-counter delta including smoke checks: `{"cancelled": 0, "completed": 25, "failed": 0, "submitted": 25}`. No service-instance change or unrelated request was detected during the checked request windows. This characterizes the existing service under current machine and cache conditions; it does not establish a speedup over an older build.

Raw requests, responses, SSE events, status snapshots, harness, source identity, summary and logs: `/Users/mymac/splash/splash/build/validation/live-performance-20261030-2359`. The initial sandbox-only localhost denial is retained in `runner.log`; the authorized run is in `runner-live.log`. Existing unrelated untracked work was preserved.
