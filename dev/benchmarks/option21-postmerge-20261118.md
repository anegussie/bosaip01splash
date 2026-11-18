# Option 21 postmerge performance comparison

All 16/16 timed requests passed full-output, cache, contention and thinking-off checks. All generated 512 tokens. Production was restored with its original arguments, model/build identity, protected cache, normal logs and telemetry; frozen/live binaries and the four preexisting modified files are unchanged.

Observed median prefill improved 3.9-8.1%, cold decode 9.3-26.9%, and cached decode 4.6-17.0% versus the historical results. Cached first-token latency fell 35.6-41.7%. These are descriptive cross-run changes.

Status: complete. Historical November 13 measurements compared with November 18 after merge `13bfb096`.

Qwen3.8-Flash-Next Q2_0 target, BF16 DFlash2 and state, INT8 KV; 10.8 GiB limit, 131,072 server context, 2,048-token chunks, one active request and 3 GiB persistent cache quota. Thinking off; temperature 1.0, top_p 0.95; 512 output tokens. Same pinned ORCHID recall/counting prompt, filler, early context salt and request parameters. Cold means zero prefix reuse with warm model/OS caches. Each current pass starts with its own empty cache. Production cache is preserved. Two independent current passes provide two cold and two cached samples per size.

Historical comparison, not a matched causal A/B of the merge. The baseline predates intervening local changes, had interruptions, and checks only a 400-character output excerpt. Current trials save and validate full outputs. The current runtime uses a 1,170 MiB KV hot-cache floor versus the historical 780 MiB floor, with 1,572 expert slots versus 1,512; expert residency and cache/prepared model identities also differ. Automatic verification and unseeded sampling can produce different generations.

Values are medians (observed minimum-maximum), not confidence intervals. Actual prompts include 12 chat-template tokens. Baseline 32K cold has one valid sample; its failed ORCHID-only generation remains excluded.

| Content / filled tokens | Build | Cold PP tok/s | Cold TPS | Cold TTFT s | Cached TPS | Cached TTFT s | Cold wall s | Cached wall s | Valid cold/cache |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 8,192 / 8,204 | Before | 428.92 (421.30-436.54) | 23.94 (23.80-24.07) | 19.13 (18.79-19.47) | 24.16 (24.13-24.18) | 0.89 (0.88-0.90) | 40.48 (40.26-40.71) | 22.05 (22.02-22.08) | 2/2 |
| 8,192 / 8,204 | After | 445.75 (436.84-454.65) | 26.15 (25.79-26.51) | 18.41 (18.04-18.78) | 26.62 (26.60-26.64) | 0.58 (0.57-0.58) | 37.95 (37.32-38.59) | 19.77 (19.75-19.79) | 2/2 |
| 32,768 / 32,780 | Before | 319.73 (319.73-319.73) | 18.88 (18.88-18.88) | 102.53 (102.53-102.53) | 22.30 (21.02-23.58) | 0.90 (0.87-0.92) | 129.59 (129.59-129.59) | 23.89 (22.54-25.23) | 1/2 |
| 32,768 / 32,780 | After | 345.50 (329.19-361.80) | 23.96 (23.57-24.35) | 95.09 (90.60-99.57) | 26.09 (25.87-26.32) | 0.57 (0.57-0.58) | 116.42 (111.59-121.26) | 20.16 (19.99-20.33) | 2/2 |
| 65,536 / 65,548 | Before | 255.10 (252.53-257.66) | 20.08 (19.94-20.21) | 256.98 (254.40-259.57) | 23.11 (22.80-23.41) | 0.89 (0.88-0.90) | 282.44 (279.69-285.19) | 23.01 (22.70-23.31) | 2/2 |
| 65,536 / 65,548 | After | 274.49 (267.02-281.96) | 22.91 (22.35-23.48) | 238.98 (232.48-245.48) | 24.17 (23.01-25.33) | 0.57 (0.57-0.57) | 261.29 (254.24-268.34) | 21.76 (20.74-22.77) | 2/2 |
| 102,400 / 102,412 | Before | 240.83 (234.26-247.41) | 17.90 (17.62-18.17) | 425.56 (413.94-437.18) | 21.83 (21.70-21.96) | 0.96 (0.95-0.97) | 454.13 (442.07-466.20) | 24.37 (24.24-24.50) | 2/2 |
| 102,400 / 102,412 | After | 251.58 (249.31-253.85) | 21.85 (20.79-22.91) | 407.10 (403.43-410.78) | 25.16 (25.16-25.16) | 0.56 (0.56-0.56) | 430.55 (425.74-435.37) | 20.87 (20.87-20.87) | 2/2 |

## Current-run validity and resource conditions

| Pass / content | Mode | Output tokens | Cache tokens | Correct / clean | Thermals | Swap-out pages | KV spilled-page delta |
|---|---|---:|---:|---|---|---:|---:|
| 1 / 8,192 | cold | 512 | 0 | True / True | fair,nominal | 0 | 0 |
| 1 / 8,192 | reuse | 512 | 8192 | True / True | nominal | 0 | 0 |
| 1 / 32,768 | cold | 512 | 0 | True / True | fair,nominal | 1584 | 0 |
| 1 / 32,768 | reuse | 512 | 32768 | True / True | nominal | 748 | 0 |
| 1 / 65,536 | cold | 512 | 0 | True / True | fair,nominal | 18160 | 0 |
| 1 / 65,536 | reuse | 512 | 65536 | True / True | nominal | 5916 | 0 |
| 1 / 102,400 | cold | 512 | 0 | True / True | fair,nominal | 13880 | 0 |
| 1 / 102,400 | reuse | 512 | 102400 | True / True | nominal | 0 | 0 |
| 2 / 8,192 | cold | 512 | 0 | True / True | fair,nominal | 0 | 0 |
| 2 / 8,192 | reuse | 512 | 8192 | True / True | nominal | 0 | 0 |
| 2 / 32,768 | cold | 512 | 0 | True / True | fair,nominal | 0 | 0 |
| 2 / 32,768 | reuse | 512 | 32768 | True / True | nominal | 0 | 0 |
| 2 / 65,536 | cold | 512 | 0 | True / True | fair,nominal | 104 | 0 |
| 2 / 65,536 | reuse | 512 | 65536 | True / True | nominal | 0 | 0 |
| 2 / 102,400 | cold | 512 | 0 | True / True | fair,nominal | 44180 | 0 |
| 2 / 102,400 | reuse | 512 | 102400 | True / True | nominal | 0 | 0 |

Current timed requests recorded 84,572 system swap-out pages of 16,384 bytes each, and 0 KV spilled-page counter increase. Thermals included nominal and fair; memory pressure remained warning.

Swap-out pages are system-wide deltas during each request, with the page size saved in vm_stat. Existing swap usage does not establish new swapping. KV spill counters and OS swap are distinct; this report makes no RAM-only full-context claim.

The first restart smoke used a 363-token prompt below the runtime persistence threshold of 2,048 tokens and was rejected. Attempt 2 returned only ORCHID with a 96-token cap and a request for 1,000 integers. Both failures are retained. Attempt 3 uses the established 30-integer smoke with a 4K prefix, validates executable code and persistent reuse across restart, then restores the original timed workload.

Evidence: [contract](option21-postmerge-20261118-raw/attempt-3/contract.json), [raw rows](option21-postmerge-20261118-raw/attempt-3/rows.json), [model source manifest](option21-postmerge-20261118-raw/model-manifest.json), [frozen binary SHA256](option21-postmerge-20261118-raw/attempt-3/binary-sha256.json), full request JSON/SSE/output and system snapshots alongside each trial. Runtime server logs and two-second resource monitors are saved in [runtime evidence](option21-postmerge-20261118-raw/attempt-3/runtime/). Production restoration is recorded in `attempt-3/production-restored.json`. No build occurred during inference.

Final restoration and preservation checks: [verification](option21-postmerge-20261118-raw/attempt-3/final-verification.json).
