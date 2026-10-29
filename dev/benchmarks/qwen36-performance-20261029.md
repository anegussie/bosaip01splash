# Qwen3.6 performance, October 29, 2026

Three rotated cold/cached coding pairs per context depth on the existing option-19 service. All 18 timed responses passed behavioral coding checks. Readiness, cache reuse, forced tool call, tool result, SSE and coding smoke checks passed before the matrix. Each timed request had exclusive native counter deltas.

| Prompt tokens | Cold PP tok/s | Cold generation tok/s | Cold TTFT s | Cold total s | Cached TTFT s | Cached total s | Cached tokens |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4,012 | 1141.4 | 37.3 | 3.69 | 7.47 | 0.34 | 3.99 | 4,000 |
| 32,685 | 953.9 | 41.5 | 34.51 | 35.48 | 0.37 | 1.36 | 32,672 |
| 57,259 | 727.7 | 35.5 | 79.01 | 80.33 | 0.31 | 1.69 | 57,248 |

Rates use summed native stage tokens divided by summed stage elapsed time; latency and total time are medians. Different tasks and output lengths across depths prevent a matched task-time comparison across depths. Cold prompts used unique salts; replays reused the immediate prefix.

Cold total-time spreads at 4K/32K/57K: 6.5%, 3.1%, 2.9%. Cold generation-rate spreads: 1.7%, 3.9%, 8.8%. These characterize this service; no controlled speedup comparison was performed.

Running build: `src-a4d13f05b5a167a5ee9fe8b3f9b08f198fb609bf7ed1eb4a570c079cf93afa96`. Current source fingerprint: `src-0a847ba4fd83ab824aeef0ad5165fec71351bd79778103bcbe26d2c7f18d8182`. They differ; this run does not validate the newly merged source build. Binary SHA256: `f20d7ae11c941d6fdb600aafa11b30efc57ae545f79dbde9c5362e163dfa1e24`.

Model: unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS, DFlash2, INT8 KV, BF16 state, 81,920 configured context, 512 requested prefill chunk, 8 GiB engine budget, one request at a time, reasoning off. Apple M5, 16 GiB unified memory. The existing 2 GiB persistent cache was retained. No test server was started or stopped.

System swap before: `vm.swapusage: total = 2048.00M  used = 983.88M  free = 1064.12M  (encrypted)`. After: `vm.swapusage: total = 2048.00M  used = 983.88M  free = 1064.12M  (encrypted)`.

Thermal states: fair, nominal. Memory pressure: normal, warning. Final Metal healthy: True. Existing service left ready and idle.

Raw requests, responses, SSE events, native status snapshots, system memory data, runner and summary: `/Users/mymac/splash/splash/build/validation/context-performance-20261029`.
