# Option 20 prefill and decode I/O tuning, November 5, 2026

Installed: the validated 16 GiB/10G/131K/automatic-expert/single-request/16G-persistent-cache preset now defaults to 2,048-token prefill. Explicit chunk overrides and other presets retain prior behavior. Four decode read-ahead workers and 512 KiB pieces are retained; both alternatives were slower in these runs. The original native binary is unchanged.

M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2, 131,072 served context, 10 GiB engine cap, INT8 KV, BF16 recurrent state, verification auto, one active request. The full 26.82 GiB n-gram table remains SSD-backed with its existing approximately 64 MiB row cache. Persistent prefix cache quota remains 16 GiB. The engine cap is not a total process-RSS guarantee.

The automatic 2,048 default is scoped to the tested 16 GiB/10G/131K/automatic-expert/one-request/16G-persistent-cache preset. Explicit chunks and other presets keep their previous settings. All 36 launcher regression tests, shell syntax and Ruff checks passed.

## Prefill comparison

The same native binary is used for both chunk sizes. A/B/B/A runs fresh servers with equal 60-second cooldowns, identical 435-token cold/reuse smoke gates and five seconds between requests. Each block times a 4,019-token cold/reuse pair and a 28,589-token cold/reuse pair. Cold prompts use unique cache salts and report zero cached tokens; hardware/OS caches are not flushed. Temperature zero, seed 42, reasoning disabled, exact ORCHID/count-to-30 checks. Prompts use repeated repository-note filler and are not a representative novel codebase.

| Prompt | Metric | 1,024 chunks | 2,048 chunks |
|---:|---|---:|---:|
| 4,019 | Cold prefill tok/s, mean (range) | 202.88 (201.43-204.33) | 400.28 (399.40-401.17) |
| 4,019 | Cold SSE TTFT seconds, mean (range) | 19.82 (19.68-19.96) | 10.05 (10.03-10.07) |
| 4,019 | Expert source GB read, mean | 113.09 | 39.28 |
| 28,589 | Cold prefill tok/s, mean (range) | 170.16 (155.15-185.16) | 241.00 (234.57-247.43) |
| 28,589 | Cold SSE TTFT seconds, mean (range) | 169.38 (154.45-184.32) | 118.76 (115.58-121.93) |
| 28,589 | Expert source GB read, mean | 865.04 | 261.73 |

## Memory and context

| Chunk | Shared prefill GiB | Expert store GiB, including staging | Resident-KV token bound | Served context |
|---:|---:|---:|---:|---:|
| 1,024 | 0.572 | 1.945969 | 196,601 | 131,072 |
| 1,536 | 0.739 | 1.945969 | 180,217 | 131,072 |
| 2,048 | 1.571 | 1.945969 | 114,681 | 131,072 |

At 2,048, a request above the approximately 114K resident-KV bound uses the existing SSD spill path. It still serves 131K. The larger scratch allocation is a memory tradeoff, not free expert-cache memory. Expert-store capacity and n-gram row-cache reservations are unchanged.

## Near-131K validation

The cold request puts ORCHID at the beginning and AMBER at the end, then asks for the initial code and a count to 30. This checks early-context recall. The actual prompt has 130,733 tokens; the output cap is 160. It is near the served limit, not an exactly filled-131,072 test. Immediate replay and a fresh-server persisted replay must reuse the prefix and pass the same exact output check. Cache-restoration validation is separate from the comparative timing blocks. The tokenize-only prompt-length search emitted an oversized-sequence warning; the native inference input was 130,733 tokens, not the oversized search probe.

| Case | Actual prompt | Cached | Prefill tok/s | SSE TTFT seconds | Correct |
|---|---:|---:|---:|---:|---|
| near131k-cold | 130,733 | 0 | 321.84 | 406.358 | True |
| near131k-reuse | 130,733 | 130,720 | 10.68 | 1.239 | True |
| near131k-persisted-replay | 130,733 | 130,720 | 10.31 | 1.467 | True |

## Decode read-ahead comparisons

These changes apply only to decode read-ahead. Prefill retains four workers and 512 KiB pieces; demand reads keep the existing shared SSD-reader pool. All decode timing blocks use 2,048-token prefill and the same 131K/10 GiB profile. Each A/B/B/A block passes cold/reuse smoke checks, then measures three low-reasoning coding probes and a 4K cold/reuse pair. Coding uses a 256-token cap and may end before a complete function; these are throughput probes, not a coding-quality score. Candidate builds pass the full bitwise expert-store Metal suite before serving. The production C++ source is restored after each isolated build.

| Experiment | Setting | Coding tok/s, mean (range) | Expert MB/decode token | Used whole read-ahead count |
|---|---|---:|---:|---:|
| decode reader comparison | 4 workers, 512 KiB | 8.92 (8.52-9.31) | 677.81 | 84.33% |
| decode reader comparison | 2 workers, 512 KiB | 8.21 (7.85-8.63) | 649.87 | 87.39% |
| decode piece comparison | 4 workers, 512 KiB | 8.81 (7.96-9.40) | 674.14 | 83.28% |
| decode piece comparison | 4 workers, 256 KiB | 8.40 (7.83-8.89) | 663.12 | 85.89% |

Whole read-ahead counts are not a byte-waste percentage: expert sizes differ and partial reads are not represented by that ratio. Select changes by end-to-end throughput and actual source bytes per decoded token. No speedup is inferred from that ratio alone.

## Every serving row

### chunk feasibility

UTC interval: 2026-11-05T11:49:20.371987+00:00 to 2026-11-05T11:51:41.579533+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| feasibility-1536-4k-smoke-cold | 1536 | 4019 | 0 | 246.81 | 12.54 | 16.298 | 496.13 | pass |
| feasibility-1536-4k-smoke-reuse | 1536 | 4019 | 4000 | 11.70 | 12.39 | 1.631 | 496.14 | pass |
| feasibility-2048-4k-smoke-cold | 2048 | 4019 | 0 | 404.91 | 12.77 | 9.939 | 490.68 | pass |
| feasibility-2048-4k-smoke-reuse | 2048 | 4019 | 4000 | 12.45 | 12.72 | 1.534 | 493.09 | pass |

### prefill comparison

UTC interval: 2026-11-05T11:52:49.819394+00:00 to 2026-11-05T12:30:23.219569+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1-smoke-cold | 1024 | 435 | 0 | 90.59 | 12.52 | 4.807 | 500.28 | pass |
| A1-smoke-reuse | 1024 | 435 | 416 | 12.08 | 12.57 | 1.585 | 497.61 | pass |
| A1-4k-cold | 1024 | 4019 | 0 | 204.33 | 12.65 | 19.680 | 494.83 | pass |
| A1-4k-reuse | 1024 | 4019 | 4000 | 12.08 | 12.63 | 1.580 | 496.58 | pass |
| A1-28k-cold | 1024 | 28589 | 0 | 185.16 | 12.24 | 154.448 | 498.20 | pass |
| A1-28k-reuse | 1024 | 28589 | 28576 | 11.03 | 11.79 | 1.189 | 516.66 | pass |
| B1-smoke-cold | 2048 | 435 | 0 | 90.71 | 12.47 | 4.801 | 499.93 | pass |
| B1-smoke-reuse | 2048 | 435 | 416 | 11.76 | 12.68 | 1.627 | 495.35 | pass |
| B1-4k-cold | 2048 | 4019 | 0 | 401.17 | 12.63 | 10.030 | 491.82 | pass |
| B1-4k-reuse | 2048 | 4019 | 4000 | 12.66 | 12.58 | 1.508 | 493.25 | pass |
| B1-28k-cold | 2048 | 28589 | 0 | 247.43 | 11.80 | 115.584 | 503.55 | pass |
| B1-28k-reuse | 2048 | 28589 | 28576 | 10.63 | 11.65 | 1.235 | 516.80 | pass |
| B2-smoke-cold | 2048 | 435 | 0 | 90.60 | 12.43 | 4.807 | 497.63 | pass |
| B2-smoke-reuse | 2048 | 435 | 416 | 11.90 | 12.67 | 1.607 | 495.42 | pass |
| B2-4k-cold | 2048 | 4019 | 0 | 399.40 | 12.69 | 10.074 | 491.79 | pass |
| B2-4k-reuse | 2048 | 4019 | 4000 | 12.57 | 12.46 | 1.518 | 498.67 | pass |
| B2-28k-cold | 2048 | 28589 | 0 | 234.57 | 11.74 | 121.930 | 506.41 | pass |
| B2-28k-reuse | 2048 | 28589 | 28576 | 11.57 | 11.43 | 1.136 | 517.58 | pass |
| A2-smoke-cold | 1024 | 435 | 0 | 90.37 | 12.54 | 4.818 | 500.33 | pass |
| A2-smoke-reuse | 1024 | 435 | 416 | 11.57 | 12.60 | 1.654 | 497.85 | pass |
| A2-4k-cold | 1024 | 4019 | 0 | 201.43 | 12.51 | 19.963 | 495.02 | pass |
| A2-4k-reuse | 1024 | 4019 | 4000 | 12.57 | 12.20 | 1.519 | 500.55 | pass |
| A2-28k-cold | 1024 | 28589 | 0 | 155.15 | 12.08 | 184.317 | 502.57 | pass |
| A2-28k-reuse | 1024 | 28589 | 28576 | 11.34 | 11.61 | 1.161 | 512.72 | pass |

### near-131K validation

UTC interval: 2026-11-05T16:31:53.739888+00:00 to 2026-11-05T16:42:08.365465+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| long-context-4k-smoke-cold | 2048 | 4019 | 0 | 409.50 | 12.80 | 9.828 | 490.53 | pass |
| long-context-4k-smoke-reuse | 2048 | 4019 | 4000 | 12.00 | 12.72 | 1.590 | 493.00 | pass |
| near131k-cold | 2048 | 130733 | 0 | 321.84 | 11.90 | 406.358 | 501.60 | pass |
| near131k-reuse | 2048 | 130733 | 130720 | 10.68 | 11.25 | 1.239 | 533.40 | pass |
| near131k-persisted-replay | 2048 | 130733 | 130720 | 10.31 | 11.20 | 1.467 | 530.76 | pass |

### decode reader comparison

UTC interval: 2026-11-05T16:56:28.041952+00:00 to 2026-11-05T17:21:28.793457+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1-smoke-cold | 2048 | 435 | 0 | 90.68 | 12.55 | 4.802 | 498.35 | pass |
| A1-smoke-reuse | 2048 | 435 | 416 | 12.38 | 12.46 | 1.546 | 498.25 | pass |
| A1-code-1 | 2048 | 61 | 0 | 20.12 | 8.88 | 19.518 | 686.59 | length (output probe) |
| A1-code-2 | 2048 | 61 | 0 | 20.16 | 9.31 | 17.940 | 649.00 | length (output probe) |
| A1-code-3 | 2048 | 61 | 0 | 20.33 | 8.70 | 20.800 | 697.59 | length (output probe) |
| A1-4k-cold | 2048 | 4019 | 0 | 393.73 | 12.68 | 10.219 | 491.60 | pass |
| A1-4k-reuse | 2048 | 4019 | 4000 | 12.22 | 12.65 | 1.562 | 493.65 | pass |
| B1-smoke-cold | 2048 | 435 | 0 | 90.47 | 11.76 | 4.813 | 484.77 | pass |
| B1-smoke-reuse | 2048 | 435 | 416 | 11.57 | 11.88 | 1.655 | 479.68 | pass |
| B1-code-1 | 2048 | 61 | 0 | 20.33 | 8.30 | 20.595 | 663.58 | length (output probe) |
| B1-code-2 | 2048 | 61 | 0 | 20.36 | 8.24 | 19.993 | 630.24 | length (output probe) |
| B1-code-3 | 2048 | 61 | 0 | 20.19 | 7.85 | 22.868 | 658.70 | length (output probe) |
| B1-4k-cold | 2048 | 4019 | 0 | 267.49 | 11.50 | 15.037 | 474.95 | pass |
| B1-4k-reuse | 2048 | 4019 | 4000 | 12.60 | 11.23 | 1.514 | 486.23 | pass |
| B2-smoke-cold | 2048 | 435 | 0 | 90.53 | 11.76 | 4.810 | 484.65 | pass |
| B2-smoke-reuse | 2048 | 435 | 416 | 12.16 | 11.89 | 1.574 | 479.67 | pass |
| B2-code-1 | 2048 | 61 | 0 | 20.31 | 8.25 | 20.693 | 663.13 | length (output probe) |
| B2-code-2 | 2048 | 61 | 0 | 20.39 | 8.63 | 19.729 | 630.74 | length (output probe) |
| B2-code-3 | 2048 | 61 | 0 | 20.10 | 8.02 | 22.169 | 652.81 | length (output probe) |
| B2-4k-cold | 2048 | 4019 | 0 | 274.66 | 11.54 | 14.645 | 475.35 | pass |
| B2-4k-reuse | 2048 | 4019 | 4000 | 12.40 | 11.25 | 1.542 | 486.76 | pass |
| A2-smoke-cold | 2048 | 435 | 0 | 90.58 | 12.50 | 4.808 | 500.10 | pass |
| A2-smoke-reuse | 2048 | 435 | 416 | 12.02 | 12.63 | 1.591 | 495.15 | pass |
| A2-code-1 | 2048 | 61 | 0 | 20.21 | 8.84 | 19.617 | 688.61 | length (output probe) |
| A2-code-2 | 2048 | 61 | 0 | 20.12 | 9.29 | 17.981 | 648.51 | length (output probe) |
| A2-code-3 | 2048 | 61 | 0 | 20.17 | 8.52 | 20.981 | 696.56 | length (output probe) |
| A2-4k-cold | 2048 | 4019 | 0 | 344.09 | 12.66 | 11.692 | 491.85 | pass |
| A2-4k-reuse | 2048 | 4019 | 4000 | 12.31 | 12.48 | 1.549 | 498.62 | pass |

### decode piece comparison

UTC interval: 2026-11-05T17:27:22.027082+00:00 to 2026-11-05T17:45:58.887677+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1-smoke-cold | 2048 | 435 | 0 | 90.52 | 12.50 | 4.812 | 500.08 | pass |
| A1-smoke-reuse | 2048 | 435 | 416 | 11.74 | 12.56 | 1.629 | 497.60 | pass |
| A1-code-1 | 2048 | 61 | 0 | 20.47 | 8.85 | 19.571 | 688.64 | length (output probe) |
| A1-code-2 | 2048 | 61 | 0 | 20.48 | 9.40 | 18.331 | 647.34 | length (output probe) |
| A1-code-3 | 2048 | 61 | 0 | 20.62 | 9.00 | 18.528 | 672.59 | length (output probe) |
| A1-4k-cold | 2048 | 4019 | 0 | 295.99 | 12.56 | 13.590 | 491.84 | pass |
| A1-4k-reuse | 2048 | 4019 | 4000 | 12.32 | 12.57 | 1.549 | 492.16 | pass |
| B1-smoke-cold | 2048 | 435 | 0 | 90.34 | 12.09 | 4.820 | 493.86 | pass |
| B1-smoke-reuse | 2048 | 435 | 416 | 11.88 | 12.29 | 1.611 | 491.93 | pass |
| B1-code-1 | 2048 | 61 | 0 | 20.55 | 8.63 | 19.883 | 672.64 | length (output probe) |
| B1-code-2 | 2048 | 61 | 0 | 20.57 | 8.89 | 19.145 | 638.18 | length (output probe) |
| B1-code-3 | 2048 | 61 | 0 | 20.36 | 8.04 | 22.163 | 669.35 | length (output probe) |
| B1-4k-cold | 2048 | 4019 | 0 | 239.79 | 11.74 | 16.773 | 485.32 | pass |
| B1-4k-reuse | 2048 | 4019 | 4000 | 12.43 | 11.40 | 1.538 | 502.50 | pass |
| B2-smoke-cold | 2048 | 435 | 0 | 90.32 | 12.22 | 4.825 | 494.38 | pass |
| B2-smoke-reuse | 2048 | 435 | 416 | 12.00 | 12.33 | 1.596 | 489.59 | pass |
| B2-code-1 | 2048 | 61 | 0 | 20.29 | 8.63 | 19.847 | 672.81 | length (output probe) |
| B2-code-2 | 2048 | 61 | 0 | 20.38 | 8.38 | 20.191 | 650.20 | length (output probe) |
| B2-code-3 | 2048 | 61 | 0 | 20.10 | 7.83 | 23.370 | 675.52 | length (output probe) |
| B2-4k-cold | 2048 | 4019 | 0 | 230.67 | 11.61 | 17.435 | 486.19 | pass |
| B2-4k-reuse | 2048 | 4019 | 4000 | 12.73 | 11.16 | 1.500 | 504.70 | pass |
| A2-smoke-cold | 2048 | 435 | 0 | 90.61 | 12.40 | 4.806 | 499.51 | pass |
| A2-smoke-reuse | 2048 | 435 | 416 | 12.22 | 12.60 | 1.567 | 497.48 | pass |
| A2-code-1 | 2048 | 61 | 0 | 20.58 | 8.80 | 19.581 | 688.96 | length (output probe) |
| A2-code-2 | 2048 | 61 | 0 | 20.60 | 8.86 | 19.408 | 660.75 | length (output probe) |
| A2-code-3 | 2048 | 61 | 0 | 20.60 | 7.96 | 22.825 | 686.56 | length (output probe) |
| A2-4k-cold | 2048 | 4019 | 0 | 216.26 | 12.00 | 18.596 | 502.24 | pass |
| A2-4k-reuse | 2048 | 4019 | 4000 | 12.59 | 11.45 | 1.521 | 513.05 | pass |

## Conditions, identity and limits

Thermal states: ['fair', 'nominal']. Memory pressure: ['normal', 'warning']. Observed host headroom: 0.000-2.076 GiB. Other desktop activity is uncontrolled. Two cold trials per prompt depth/build establish limited variability; no new other-device speedup is inferred. Effective read rates are engine counters, not a standalone SSD benchmark.

All completed rows have clean request counters, complete SSE, and no per-request Metal or capacity failures. Raw data retain actual outputs, usage, speculation, before/after status, host swap/power samples and exact server commands. Native source/build identities and candidate source snapshots are in the JSON package. These are local working-tree artifacts.

## Installed-launcher validation

The real home launcher was installed and started with its default settings. The final server selected 2,048-token chunks, the same native build identity, 131K context, 10 GiB cap, one active request and unchanged n-gram/expert reservations. Old 1,024-chunk prefixes remained reusable. A fresh 2,048-chunk prefix survived a second real-launcher restart and was restored from SSD. Before/after coding checks below are installation sanity checks, not a controlled speedup estimate. Explicit untimed warmups precede them. An earlier correctly answered request after 600 seconds of idle incurred 2.27 seconds of weight restoration; that excluded attempt is archived under `build/validation/option20-io-install-20261105/initial-idle-restore/`.

| Case | Chunk | Prompt | Cached | Decode tok/s | SSE TTFT s | Check |
|---|---:|---:|---:|---:|---:|---|
| baseline-resource-warmup | 1024 | 16 | 0 | 2.38 | 1.304 | warmup |
| before-4k-cold | 1024 | 4019 | 0 | 12.61 | 19.713 | pass |
| before-4k-reuse | 1024 | 4019 | 4000 | 12.56 | 1.531 | pass |
| before-4k-reuse-again | 1024 | 4019 | 4000 | 12.58 | 1.581 | pass |
| before-code-1 | 1024 | 61 | 0 | 9.12 | 18.931 | output probe |
| before-code-2 | 1024 | 61 | 0 | 8.92 | 20.610 | output probe |
| installed-resource-warmup | 2048 | 16 | 0 | 2.35 | 1.254 | warmup |
| installed-cross-chunk-prefix | 2048 | 4019 | 4000 | 12.55 | 1.583 | pass |
| installed-4k-cold | 2048 | 4019 | 0 | 12.68 | 12.100 | pass |
| installed-4k-reuse | 2048 | 4019 | 4000 | 12.38 | 1.542 | pass |
| installed-code-1 | 2048 | 61 | 0 | 9.10 | 19.258 | output probe |
| installed-code-2 | 2048 | 61 | 0 | 8.67 | 20.808 | output probe |
| restarted-resource-warmup | 2048 | 16 | 0 | 2.37 | 1.263 | warmup |
| installed-persisted-replay | 2048 | 4019 | 4000 | 12.11 | 1.571 | pass |

The timed chunk comparison and the later installation canary are separate observations. The installed 4K cold canary reached 332.22 prefill tok/s, versus the matched comparison's 400.28 mean; sustained activity and thermal/host conditions changed during the session. The installation sanity checks do not establish an additional speedup.

| Active artifact | Value |
|---|---|
| Native build ID | `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d` |
| Native binary SHA-256 before / after | `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` / `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` |
| Installed launcher SHA-256 | `db5f00fb14b979f5f26947923a69f43e4fc3637683169ca0a4495da4808c18e3` |

### Excluded idle-restoration check

| Case | PP tok/s | SSE TTFT s | Initial queue ms | Output | Treatment |
|---|---:|---:|---:|---|---|
| before-4k-cold | 204.79 | 21.908 | 2273.6 | correct | untimed, excluded |
