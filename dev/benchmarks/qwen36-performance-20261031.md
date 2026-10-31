# Splash performance - 2026-10-31

Merged source commit `ffa16f216f8bcad1241b205603555c2538a474f3`; running build `src-c20b51c2ec02b78548efef7b95e02ccddb2ba9636e67fc14235e171d78db4e57`.
Binary SHA256: `481959b9cfab5fc512b5f6bdc17a9c7e979fd2e84447061f32352c4837a48fcc`.

All 18 timed coding responses passed behavioral checks. Readiness, exact output, cold/cached reuse, forced tool call/result, SSE, and streaming coding smoke checks passed. Three rotated cold/cached pairs ran at each depth. Request throughput divides tokens within each measured interval by total interval time, using the response timing fields; decode excludes the initial emission. Native stage counter rates are saved separately in summary.json. TTFT measures the first streamed content and is reported as a mean.

| Filled prompt | Cold PP tok/s | Decode tok/s (range) | Cold TTFT | Cached TTFT |
|---:|---:|---:|---:|---:|
| 4,012 | 1204.3 | 39.2 (35.9-41.4) | 3.33s | 0.35s |
| 32,685 | 901.8 | 38.2 (36.9-40.4) | 36.26s | 0.39s |
| 57,259 | 693.2 | 35.5 (33.3-38.1) | 82.62s | 0.32s |

Apple M5, 16 GiB. Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2, INT8 KV, BF16 state, 81,920 context, 512-token prefill chunks, 8 GiB Metal limit, concurrency 1, reasoning off, temperature 0 and seed 42. The test used the production HTTP server and the separately built merged native binary, on port 1236, with a temporary 2 GiB SSD cache and no persistent prefix cache. The explicit `--expert-memory 1900M` matches the current option-19 launcher; upstream now treats it as the expert-store floor, allowing the store to grow into available headroom.

Thermal states observed at timed-request boundaries: fair, nominal. Memory pressure: warning. Each new cold/cached pair waited for two nominal thermal samples. Full VM and swap observations and counter snapshots are saved with each request.
Swap observations: vm.swapusage: total = 2048.00M  used = 551.44M  free = 1496.56M  (encrypted); vm.swapusage: total = 2048.00M  used = 863.69M  free = 1184.31M  (encrypted).

Startup took 184.77s including first-use Metal pipeline preparation; startup is excluded from request timing. The existing port-1235 server remained online with its weights released, received no inference requests, and retained its instance and counters. The temporary test server was stopped after the run.

These results characterize the merged build under the recorded host conditions. They do not establish a speedup against the prior report: no matched baseline was rerun, and expert-store policy and host memory conditions differ.

Raw requests/responses, SSE events, model metadata, hashes, lifecycle records, VM and swap samples, harness, and logs: `/Users/mymac/splash/splash/build/validation/context-performance-20261031`. `summary.json` includes ranges for prefill and cold/cached TTFT.
