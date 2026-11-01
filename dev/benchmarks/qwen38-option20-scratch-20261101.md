# Flash-Next scratch sizing and 1,024-token prefill — 2026-11-01

Flash-Next now sizes its own prefill tensors and QSA block records for the actual runtime chunk, propagating the same row limit through planning, allocation, views and PLE read-ahead. The legacy 2,048-row default is retained for callers that omit the limit; grouped streaming keeps its existing full-size geometry. Oversized prefill chunks are rejected before touching scratch. Decode scratch is unchanged.

At 512 rows, shared prefill memory dropped by 263.875 MiB (679.8125 to 415.9375 MiB) and the planner minimum dropped from 7.66 to 7.41 GiB. This is a measured allocation reduction, not a speed claim.

## Same-build chunk comparison

| Chunk | 4K trials | Mean prefill tok/s | Mean TTFT seconds | Mean decode tok/s | Minimum GiB |
|---:|---:|---:|---:|---:|---:|
| 512 | 3 | 126.72 | 31.72 | 12.53 | 7.41 |
| 1024 | 3 | 186.20 | 21.59 | 12.38 | 7.57 |

1,024-token chunks improved mean 4K prefill by 46.9% against 512 on the revised build. Fixed run order (512 then 1,024), three trials each, 4,019 prompt tokens, unique cold cache salts, 96 output tokens, ten-second cooldowns. Thermals were nominal/fair for 512 and fair for 1,024; pressure was normal at trial ends. This is a local comparison, not a universal speedup.

## Long-context check

The selected 1,024 profile processed 28,589 tokens at 179.65 tok/s. TTFT was 159.17s and decode 11.69 tok/s. The bounded ORCHID/first-ten-counting check passed. Peak Metal memory was 7.20 GiB; pressure normal, thermal fair. Swap used stayed 1,089.88 MiB across the request; this is not proof of no swapping. One long trial was run; the full 32,761-token limit was not filled.

## Configuration and checks

Model ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS, DFlash2, 32,761-token served context, 8 GiB planner cap, INT8 KV, BF16 state, one active request, 64 MiB PLE cache, shared expert arena, SSD prefix cache off. Timed requests used reasoning none, temperature zero, seed 42. Both chunk settings passed cold/repeat smoke and three 4K correctness requests; the selected setting also passed the long check. No capacity or Metal failures were recorded. The previous 512 source/build is not used as the matched baseline.

The full Flash-Next Metal kernel suite passed with shader validation, including new checks for allocation/plan equality, unchanged decode storage, QSA end-of-window coverage, carried chunks and oversize rejection at 128/512/1,024 rows. All 25 launcher tests passed. Build completed before inference, and no rebuild occurred during measurement.

Live build ID: `src-e614e825c94764eb08252f6e7ddb7b3ea9040dd780a4d3444cbde071398677df`.

Raw evidence and exact server commands: `build/validation/option20-scratch-20261101/{512,1024,long}/performance.json`, adjacent request/SSE/status files, kernel and launcher test logs, and `selected-launcher.log`. Option 20 defaults to 1,024-token chunks and remains running at http://127.0.0.1:1235.
