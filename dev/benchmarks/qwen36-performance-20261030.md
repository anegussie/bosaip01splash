# Splash performance — 2026-10-30

Merged source commit `54819b3a`; running build `src-44a14cb4f0af35b0b4e60c10496ed858b741f4deebdca7ba4020266340fb87f4`. Binary SHA256: `b10ca9af72c0c9a6045cfd214503153fc9d3b2be26d53817a1fa91657edf82aa`.

All 18 timed coding responses passed behavioral checks. Readiness, cold/cached reuse, forced tool call/result, SSE and streaming coding smoke checks passed. Three rotated cold/cached pairs at each depth. Throughput aggregates stage tokens over stage time; decode excludes the first token. TTFT values are means.

| Filled prompt | Cold PP tok/s | Decode tok/s (range) | Cold TTFT | Cached TTFT |
|---:|---:|---:|---:|---:|
| 4,012 | 1208.6 | 38.7 (36.3–42.6) | 3.32s | 0.34s |
| 32,685 | 919.4 | 40.1 (38.1–43.4) | 35.56s | 0.37s |
| 57,259 | 712.6 | 35.3 (31.9–37.2) | 80.37s | 0.32s |

Apple M5, 16 GiB. Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2, INT8 KV, BF16 states, 81,920 context, 512-token prefill chunks, 8 GiB Metal limit, concurrency 1, reasoning off, greedy temperature 0 / seed 42. Isolated server using the installed model; temporary 2 GiB SSD cache, no persistent cache. Existing launcher configuration was not modified.

Memory pressure was warning at start and end, with fluctuating growth admission. System swap was 0 MiB at both endpoints. Each new pair began at nominal thermals after cooldown; some large-prefill/cached runs ended at fair. These results characterize current conditions; they do not establish a speedup against an older build.

Raw requests/responses, SSE events, counter snapshots, VM and swap records, harness and logs: `/Users/mymac/splash/splash/build/validation/context-performance-20261030`. Temporary test server stopped after completion.
