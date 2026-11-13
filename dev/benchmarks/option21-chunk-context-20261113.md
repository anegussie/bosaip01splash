# Option 21: 2,048 vs 1,024 prefill chunks across context sizes

Status: complete.
**Outcome:** 31/32 timed trials passed the semantic gate. The failed 32K cold 2,048-chunk generation returned only ORCHID; it is retained and excluded from speed aggregates.

Observed medians: 1,024-token chunks increased cached decode TPS by 12.8–23.6% and reduced cold PP by 22.7–33.0%. Keep 2,048 chunks as the general profile; 1,024 is an option for workloads dominated by cached-prefix generation. These are conditional observations from an interrupted, small synthetic-workload comparison, not a universal speedup.

Both profiles retained 128K server capacity. The 100K requests used KV spill, and some trials recorded macOS swap-outs. This does not establish RAM-only execution at 128K.

**Protocol interruption:** B1-1024 untimed 363-token warmup returned only ORCHID and stopped. Production restored. Remaining arms use a warmup asking for 30 integers instead of 1000; timed requests remain unchanged. Failed warmup retained separately. Warmup protocol differs from A1 and is a comparison limitation. A2-2048 timed 32K cold returned only ORCHID (4 output tokens) and failed semantic correctness. That failed observation is retained, excluded from throughput aggregates, and not retried as a timed cold trial. Production restored. The final five independent requests run in a fresh A2-2048-resume process; an untimed one-token 32K prefill establishes the prefix before the original cached trial. These interruptions limit attribution.


Same frozen executable and Metal libraries; Q2_0 target and BF16 DFlash2, INT8 KV, BF16 state,
10.8 GiB cap, 131,072 server context, one active request, automatic verification.
The tested indexer profile is `top_k=4096` (780 MiB hot-cache floor); this is separate from the prefill chunk size.
Thinking disabled. Temperature 1.0, top_p 0.95; each counting request has a 512-token budget.
A/B/B/A order; each arm has a new isolated 3 GiB persistent cache.
Cold means no reused prefix, with model/OS caches warmed. Reuse repeats the identical prompt.

Branch: `option20-best-pp-20261106`; repository HEAD: `1d4bf8a824fc3757d99ca95ca590ff9765e50f7a`.
The checkout was dirty; the executable hash and reported build ID identify the tested runtime.

Each value is the median followed by the observed range of valid requests only.
Valid cold/cached sample counts are shown; failed generations remain in the raw results and validity table.
These are not statistical confidence intervals. Actual filled prompts include chat-template tokens.

| Content tokens | Chunk | Filled prompt | Cold PP tok/s | Cold decode TPS | Cold TTFT s | Cached decode TPS | Cached TTFT s | Valid cold/cached |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8,192 | 2048 | 8,204 | 428.92 (421.30–436.54) | 23.94 (23.80–24.07) | 19.13 (18.79–19.47) | 24.16 (24.13–24.18) | 0.89 (0.88–0.90) | 2/2 |
| 8,192 | 1024 | 8,204 | 287.36 (286.03–288.68) | 27.64 (26.61–28.68) | 28.55 (28.42–28.68) | 29.62 (29.60–29.64) | 0.89 (0.84–0.94) | 2/2 |
| 32,768 | 2048 | 32,780 | 319.73 (319.73–319.73) | 18.88 (18.88–18.88) | 102.53 (102.53–102.53) | 22.30 (21.02–23.58) | 0.90 (0.87–0.92) | 1/2 |
| 32,768 | 1024 | 32,780 | 240.30 (226.38–254.21) | 22.36 (21.74–22.99) | 136.88 (128.95–144.80) | 27.56 (26.15–28.98) | 0.85 (0.83–0.87) | 2/2 |
| 65,536 | 2048 | 65,548 | 255.10 (252.53–257.66) | 20.08 (19.94–20.21) | 256.98 (254.40–259.57) | 23.11 (22.80–23.41) | 0.89 (0.88–0.90) | 2/2 |
| 65,536 | 1024 | 65,548 | 197.07 (194.99–199.16) | 22.33 (21.98–22.68) | 332.64 (329.13–336.15) | 26.07 (25.39–26.75) | 0.90 (0.86–0.95) | 2/2 |
| 102,400 | 2048 | 102,412 | 240.83 (234.26–247.41) | 17.90 (17.62–18.17) | 425.56 (413.94–437.18) | 21.83 (21.70–21.96) | 0.96 (0.95–0.97) | 2/2 |
| 102,400 | 1024 | 102,412 | 184.94 (182.61–187.26) | 20.30 (19.02–21.57) | 553.87 (546.89–560.84) | 26.41 (25.81–27.01) | 0.95 (0.94–0.96) | 2/2 |

## End-to-end request time

Wall seconds include prefill and generation, with the same 512-token output budget.
They exclude the preceding idle/thermal wait. Actual generated token counts are retained in the raw rows.

| Content tokens | Chunk | Cold wall seconds | Cached wall seconds |
|---:|---:|---:|---:|
| 8,192 | 2048 | 40.48 (40.26–40.71) | 22.05 (22.02–22.08) |
| 8,192 | 1024 | 47.06 (46.23–47.88) | 18.14 (18.10–18.18) |
| 32,768 | 2048 | 129.59 (129.59–129.59) | 23.89 (22.54–25.23) |
| 32,768 | 1024 | 159.75 (151.18–168.31) | 19.44 (18.51–20.37) |
| 65,536 | 2048 | 282.44 (279.69–285.19) | 23.01 (22.70–23.31) |
| 65,536 | 1024 | 355.54 (351.67–359.41) | 20.52 (20.05–20.98) |
| 102,400 | 2048 | 454.13 (442.07–466.20) | 24.37 (24.24–24.50) |
| 102,400 | 1024 | 579.15 (573.76–584.54) | 20.31 (19.86–20.76) |

## Assumed workflow: 70% of elapsed time in prompt processing

This is a model using the measured medians, not a measured end-to-end user workflow.
Assume 70% of the 2,048-chunk inference time is fresh prompt processing and 30% is decode.
For the same work, the estimated 1,024-chunk time ratio is
`0.70 * (PP_2048 / PP_1024) + 0.30 * (cached_TPS_2048 / cached_TPS_1024)`.
Using cached decode gives the smaller chunk its favorable observed decode regime.
The assumption concerns time, not token or request counts. Queueing, tools and other work are excluded.

| Content tokens | Estimated extra elapsed time with 1,024 chunks |
|---:|---:|
| 8,192 | +29.0% |
| 32,768 | +17.4% |
| 65,536 | +17.2% |
| 102,400 | +16.0% |

## Conditions and validity

| Arm | Timed requests | Correct/clean | Expert slots observed | Thermals during requests | Memory pressure | Swap-out pages | Spilled requests | KV spilled-page delta |
|---|---:|---|---|---|---|---:|---:|---:|
| A1-2048 | 8 | True | [1512] | ['fair', 'nominal'] | ['warning'] | 41540 | 2 | 3024 |
| B1-1024-retry1 | 8 | True | [2176] | ['fair', 'nominal'] | ['warning'] | 51076 | 2 | 3024 |
| B2-1024 | 8 | True | [2176] | ['fair', 'nominal'] | ['warning'] | 0 | 2 | 3024 |
| A2-2048 | 3 | False | [1512] | ['fair', 'nominal'] | ['warning'] | 0 | 0 | 0 |
| A2-2048-resume | 5 | True | [1512] | ['fair', 'nominal'] | ['warning'] | 471 | 2 | 3024 |

## Limits and evidence

The primary context workload is synthetic recall/counting. Executable Python correctness is checked
in the short smoke gates; these results do not establish representative coding throughput.
Counting correctness checks the saved output excerpt (up to 400 characters), including the secret
and ordered integers; a final partial integer is ignored. It does not validate every generated token.
Automatic verification can produce different outputs even with matching request settings.
Full request metrics, before/after status, system snapshots, server logs and a two-second
memory/thermal/expert-residency monitor are saved beside this runner.
Smoke gates cover both chunk sizes, cold and cached requests, executable code and restart restore.
An earlier attempt was rejected at 32K after it reused a 4K prefix from the 8K prompt.
It is excluded here. Context-specific early salts and a cross-context cold smoke gate fixed it;
[the failure record is retained](option21-chunk-context-20261113-raw/FAILURE.md).
Production restoration is recorded in `production-restored.json`.

Normal log links, JSONL telemetry and the performance monitor were restored without rebuilding;
see `normal-logging-restored.json` for their paths and process identifiers.

[Raw evidence](option21-chunk-context-20261113-raw/clean-run/).
