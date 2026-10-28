# Qwen3.6 80K context performance — October 28, 2026

Characterization of the existing Splash server, with three rotated cold/cached coding pairs per filled-context depth. The test did not change the server limit or run subagents, so it does not compare 60K/70K/80K configurations or establish a compaction threshold.

| Prompt tokens | Cold PP tokens/s | Cold generation tokens/s | Cold TTFT s | Cold total s | Cached TTFT s | Cached total s | Cached tokens |
|---:|---:|---:|---:|---:|---:|---:|
| 4,012 | 1,254.7 | 38.5 | 3.21 | 6.89 | 0.34 | 3.22 | 4,000 |
| 32,685 | 928.0 | 40.7 | 35.23 | 36.26 | 0.38 | 1.39 | 32,672 |
| 57,259 | 714.2 | 35.2 | 80.17 | 81.52 | 0.31 | 1.70 | 57,248 |

Rates are native status counter deltas summed across trials and divided by summed stage time. TTFT and total times are medians. Cold PP spread was 0.1%, 3.5%, and 6.3%; cold total-time spread was 1.0%, 3.3%, and 6.3%, respectively. At 57K, cold generation speed spread was 8.7% and cached total-time spread was 18.2%, so treat those as variable characterization. Cached PP processes only the uncached suffix; it is not comparable to cold PP. Different coding tasks and output lengths were used at different depths, so total times are not a matched task comparison across depths.

All 18 timed coding responses passed their task check. Readiness, cold/cached cache round-trip, forced tool call and tool result, SSE, and a coding smoke passed before the matrix. Each timed request had an exclusive one-request counter delta. Cold requests had zero cache hits and unique salts; immediate replays reused the prefixes shown above.

Server: Qwen3.6-35B-A3B UD-IQ3_XXS, build `src-7e2e9dc11f019304a5db05390e5a85e0a336ec7c1fb92fe58c337bc75b96d7dc`, binary SHA256 `3a4945b69f19d06968be6149d10d6f1705e5ff7bb9f676b6a47434ab09e0e15d`, 81,920 configured context, INT8 KV, BF16 state, DFlash2, 8 GiB Metal budget, 512 requested prefill chunk, one active request, reasoning off. Apple M5, 16 GiB unified memory. Each pair started nominal; 32K sometimes and 57K always ended fair. Memory pressure was warning. System swap used was 1,926.94 MiB before and after. The same existing server instance was retained, ready and idle after the test; no test server was launched or stopped.

Complete raw requests, responses, status snapshots, system data, and runner: `build/validation/context-performance-20261028/`. Machine-readable aggregate: `build/validation/context-performance-20261028/run.json`.
