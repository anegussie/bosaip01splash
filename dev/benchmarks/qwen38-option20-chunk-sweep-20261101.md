# Option 20 chunk comparison — 2026-11-01

| Chunk | 4K prefill tok/s | Mean TTFT | Decode tok/s | Peak Metal GiB |
|---:|---:|---:|---:|---:|
| 128 | 45.54 | 88.26s | 12.53 | 7.14 |
| 256 | 76.46 | 52.57s | 12.37 | 7.13 |
| 512 | 122.41 | 32.84s | 12.36 | 7.20 |

Selected 512 tokens as the option-20 default. Its average prefill rate is 2.69x the 128-token baseline on this workload. Generation remains around 12 tok/s; this change improves prompt processing.

All three settings used the same source/build, model, 32,761-token served context, 8 GiB cap, INT8 KV, BF16 state, 64 MiB PLE cache, shared expert arena, reasoning none, temperature zero, seed 42 and 96 output tokens. Each had a cold and repeated 435-token smoke test, then three 4,019-token trials with unique salts and ten-second cooldowns. Every bounded ORCHID/first-ten-counting check passed and every timed trial reported zero cached prompt tokens. SSD cache was off; the repeat smoke used RAM prefix reuse.

Settings ran sequentially in fixed order (128, 256, 512), each on a fresh server. Thermals were nominal/fair for 128 and fair for 256/512. Memory pressure was normal for 128, included a warning for 256, and normal at the ends of 512 trials. This is a local workload comparison, not a general model-quality or sustained long-context benchmark. The 512 setting reached Ready with the full served context, but filled-28K performance was measured only in the earlier 128 run.

The first setup attempt omitted the served model alias and failed the smoke test with HTTP 404. No timing from that attempt was used; diagnostics remain in `alias-mismatch/`.

Raw results, exact commands, build/status snapshots, swap readings, requests, SSE events, and server logs: `build/validation/option20-chunk-sweep-20261101/{128,256,512}/performance.json` and adjacent files.
