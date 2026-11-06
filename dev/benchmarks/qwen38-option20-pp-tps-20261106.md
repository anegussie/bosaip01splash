# Qwen3.8 Flash-Next IQ3_XXS: PP and TPS, November 6, 2026

M5 MacBook Air, 16 GiB unified memory, 10.8 GiB engine cap, 2,048-token prefill chunks, automatic expert memory, one active request, `verify-rows auto`.

## Cold long-prompt baseline

| Prompt tokens | PP (tok/s) | Decode TPS |
|---:|---:|---:|
| 4,019 | 401.40, 406.03 | 12.73, 12.75 |
| 28,589 | 264.60, 340.02 | 12.15, 12.23 |

## Decode read-ahead A/B/B/A

| Block | Read-ahead workers | Cold 4K PP | Coding API TPS | Coding native TPS |
|---|---:|---:|---:|---:|
| A1 | 4 | 402.98 | 10.91 | 11.03 |
| B1 | 8 | 339.51 | 10.90 | 11.02 |
| B2 | 8 | 299.32 | 10.88 | 11.00 |
| A2 | 4 | 294.48 | 10.85 | 10.96 |

The cold 4K PP varied substantially through the run, so the A/B/B/A rows do not isolate a prefill effect. Coding API TPS averaged 10.879 with four workers and 10.893 with eight; this difference is within observed variation. Eight workers did not establish a throughput gain.

Full methodology and raw evidence: [Option 20 stream profile report](qwen38-option20-stream-profile-20261106.md).
