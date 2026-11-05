# Mac performance estimates - reviewed November 5, 2026

This is the complete saved estimate document, including historical tables and later measured Air results. Source: `/Users/mymac/MacPerfEstimates.md`; source SHA-256: `ca9b5ada3c2c6f4eae3a15eef2e0a077f5355a48389fe052607f7d058a293cfd`. Repository artifact links have been made relative for publication.

<!-- io-tuning-20261105:start -->
## Option 20 prefill and decode I/O tuning, November 5, 2026

Installed: the validated 16 GiB/10G/131K/automatic-expert/single-request/16G-persistent-cache preset now defaults to 2,048-token prefill. Explicit chunk overrides and other presets retain prior behavior. Four decode read-ahead workers and 512 KiB pieces are retained; both alternatives were slower in these runs. The original native binary is unchanged.

M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2, 131,072 served context, 10 GiB engine cap, INT8 KV, BF16 recurrent state, verification auto, one active request. The full 26.82 GiB n-gram table remains SSD-backed with its existing approximately 64 MiB row cache. Persistent prefix cache quota remains 16 GiB. The engine cap is not a total process-RSS guarantee.

The automatic 2,048 default is scoped to the tested 16 GiB/10G/131K/automatic-expert/one-request/16G-persistent-cache preset. Explicit chunks and other presets keep their previous settings. All 36 launcher regression tests, shell syntax and Ruff checks passed.

### Prefill comparison

The same native binary is used for both chunk sizes. A/B/B/A runs fresh servers with equal 60-second cooldowns, identical 435-token cold/reuse smoke gates and five seconds between requests. Each block times a 4,019-token cold/reuse pair and a 28,589-token cold/reuse pair. Cold prompts use unique cache salts and report zero cached tokens; hardware/OS caches are not flushed. Temperature zero, seed 42, reasoning disabled, exact ORCHID/count-to-30 checks. Prompts use repeated repository-note filler and are not a representative novel codebase.

| Prompt | Metric | 1,024 chunks | 2,048 chunks |
|---:|---|---:|---:|
| 4,019 | Cold prefill tok/s, mean (range) | 202.88 (201.43-204.33) | 400.28 (399.40-401.17) |
| 4,019 | Cold SSE TTFT seconds, mean (range) | 19.82 (19.68-19.96) | 10.05 (10.03-10.07) |
| 4,019 | Expert source GB read, mean | 113.09 | 39.28 |
| 28,589 | Cold prefill tok/s, mean (range) | 170.16 (155.15-185.16) | 241.00 (234.57-247.43) |
| 28,589 | Cold SSE TTFT seconds, mean (range) | 169.38 (154.45-184.32) | 118.76 (115.58-121.93) |
| 28,589 | Expert source GB read, mean | 865.04 | 261.73 |

### Memory and context

| Chunk | Shared prefill GiB | Expert store GiB, including staging | Resident-KV token bound | Served context |
|---:|---:|---:|---:|---:|
| 1,024 | 0.572 | 1.945969 | 196,601 | 131,072 |
| 1,536 | 0.739 | 1.945969 | 180,217 | 131,072 |
| 2,048 | 1.571 | 1.945969 | 114,681 | 131,072 |

At 2,048, a request above the approximately 114K resident-KV bound uses the existing SSD spill path. It still serves 131K. The larger scratch allocation is a memory tradeoff, not free expert-cache memory. Expert-store capacity and n-gram row-cache reservations are unchanged.

### Near-131K validation

The cold request puts ORCHID at the beginning and AMBER at the end, then asks for the initial code and a count to 30. This checks early-context recall. The actual prompt has 130,733 tokens; the output cap is 160. It is near the served limit, not an exactly filled-131,072 test. Immediate replay and a fresh-server persisted replay must reuse the prefix and pass the same exact output check. Cache-restoration validation is separate from the comparative timing blocks. The tokenize-only prompt-length search emitted an oversized-sequence warning; the native inference input was 130,733 tokens, not the oversized search probe.

| Case | Actual prompt | Cached | Prefill tok/s | SSE TTFT seconds | Correct |
|---|---:|---:|---:|---:|---|
| near131k-cold | 130,733 | 0 | 321.84 | 406.358 | True |
| near131k-reuse | 130,733 | 130,720 | 10.68 | 1.239 | True |
| near131k-persisted-replay | 130,733 | 130,720 | 10.31 | 1.467 | True |

### Decode read-ahead comparisons

These changes apply only to decode read-ahead. Prefill retains four workers and 512 KiB pieces; demand reads keep the existing shared SSD-reader pool. All decode timing blocks use 2,048-token prefill and the same 131K/10 GiB profile. Each A/B/B/A block passes cold/reuse smoke checks, then measures three low-reasoning coding probes and a 4K cold/reuse pair. Coding uses a 256-token cap and may end before a complete function; these are throughput probes, not a coding-quality score. Candidate builds pass the full bitwise expert-store Metal suite before serving. The production C++ source is restored after each isolated build.

| Experiment | Setting | Coding tok/s, mean (range) | Expert MB/decode token | Used whole read-ahead count |
|---|---|---:|---:|---:|
| decode reader comparison | 4 workers, 512 KiB | 8.92 (8.52-9.31) | 677.81 | 84.33% |
| decode reader comparison | 2 workers, 512 KiB | 8.21 (7.85-8.63) | 649.87 | 87.39% |
| decode piece comparison | 4 workers, 512 KiB | 8.81 (7.96-9.40) | 674.14 | 83.28% |
| decode piece comparison | 4 workers, 256 KiB | 8.40 (7.83-8.89) | 663.12 | 85.89% |

Whole read-ahead counts are not a byte-waste percentage: expert sizes differ and partial reads are not represented by that ratio. Select changes by end-to-end throughput and actual source bytes per decoded token. No speedup is inferred from that ratio alone.

### Every serving row

#### chunk feasibility

UTC interval: 2026-11-05T11:49:20.371987+00:00 to 2026-11-05T11:51:41.579533+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| feasibility-1536-4k-smoke-cold | 1536 | 4019 | 0 | 246.81 | 12.54 | 16.298 | 496.13 | pass |
| feasibility-1536-4k-smoke-reuse | 1536 | 4019 | 4000 | 11.70 | 12.39 | 1.631 | 496.14 | pass |
| feasibility-2048-4k-smoke-cold | 2048 | 4019 | 0 | 404.91 | 12.77 | 9.939 | 490.68 | pass |
| feasibility-2048-4k-smoke-reuse | 2048 | 4019 | 4000 | 12.45 | 12.72 | 1.534 | 493.09 | pass |

#### prefill comparison

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

#### near-131K validation

UTC interval: 2026-11-05T16:31:53.739888+00:00 to 2026-11-05T16:42:08.365465+00:00.

| Row | Chunk | Prompt | Cached | PP tok/s | Decode tok/s | SSE TTFT s | Expert MB/decode token | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| long-context-4k-smoke-cold | 2048 | 4019 | 0 | 409.50 | 12.80 | 9.828 | 490.53 | pass |
| long-context-4k-smoke-reuse | 2048 | 4019 | 4000 | 12.00 | 12.72 | 1.590 | 493.00 | pass |
| near131k-cold | 2048 | 130733 | 0 | 321.84 | 11.90 | 406.358 | 501.60 | pass |
| near131k-reuse | 2048 | 130733 | 130720 | 10.68 | 11.25 | 1.239 | 533.40 | pass |
| near131k-persisted-replay | 2048 | 130733 | 130720 | 10.31 | 11.20 | 1.467 | 530.76 | pass |

#### decode reader comparison

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

#### decode piece comparison

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

### Conditions, identity and limits

Thermal states: ['fair', 'nominal']. Memory pressure: ['normal', 'warning']. Observed host headroom: 0.000-2.076 GiB. Other desktop activity is uncontrolled. Two cold trials per prompt depth/build establish limited variability; no new other-device speedup is inferred. Effective read rates are engine counters, not a standalone SSD benchmark.

All completed rows have clean request counters, complete SSE, and no per-request Metal or capacity failures. Raw data retain actual outputs, usage, speculation, before/after status, host swap/power samples and exact server commands. Native source/build identities and candidate source snapshots are in the JSON package. These are local working-tree artifacts.

### Installed-launcher validation

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

#### Excluded idle-restoration check

| Case | PP tok/s | SSE TTFT s | Initial queue ms | Output | Treatment |
|---|---:|---:|---:|---|---|
| before-4k-cold | 204.79 | 21.908 | 2273.6 | correct | untimed, excluded |

Full artifacts: [report](qwen38-option20-io-tuning-20261105.md), [JSON results](qwen38-option20-io-tuning-20261105.json). Other-device estimates are unchanged; earlier sections below preserve historical settings and measurements.
<!-- io-tuning-20261105:end -->


<!-- expert-retention-20261105:start -->
## Option 20: shared expert retention, November 5, 2026

Two expert-retention prototypes were implemented and tested. Neither established a throughput gain. The original option-20 runtime and profile remain active; the experimental source changes were removed, and the tested implementation is preserved as a patch.

Revised-matrix UTC interval: 2026-11-05T11:15:02.766377+00:00 to 2026-11-05T11:31:32.127493+00:00.

M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Exact model: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2, 131,072 served context, 10 GiB engine cap, one active request, 1,024-token prefill chunks, INT8 KV, BF16 state, verification auto. The 26.82 GiB n-gram table stays SSD-backed with the existing approximately 64 MiB RAM row cache. Persistent prefix cache: 16 GiB.

### Prototype implementation and validation

Shared formats retain only experts whose packed byte ranges remain intact. Bounded overlap masks choose free slots that discard fewer cached experts, favor decode-reused entries, and age that preference after roughly 32 cycles. Large prefill chunks clear other formats once and bypass per-slot conflict searches. Other stores retain their existing ARC policy. Release and failed-load cleanup also clear the retention metadata.

The new native regression failed on the baseline because format switching discarded sparse experts that fit together. Both candidates passed the complete expert-store Metal suite across four shapes, with bitwise resident-weight comparisons, forced overwrites, mixed quantizations, read failures and release/restore. CPU tests check byte overlaps, absent planes, alignment, bitset boundaries, metadata bounds, reuse preference and existing recycler traces.

### Matched serving results

A/B/B/A uses four fresh server instances, the same serving arguments, one minute idle cooldown before each block and five seconds between requests. Each block passes a 435-token cold/reuse ORCHID/count-to-30 smoke gate before its 4,019-token cold/reuse pair and two short coding probes. Cold means a unique prefix salt with zero cached prompt tokens; SSD/OS caches are not flushed. B2 additionally restores the B1 4K prefix from SSD before its smoke gate; that extra earlier workload is a comparison limitation. Sampling is temperature zero, seed 42. Coding uses low reasoning and a 256-token output cap; these are throughput probes, not completed coding tasks. Each build gets four coding trials and two 4K cold/reuse pairs.

| Metric | Baseline | Revised retention |
|---|---:|---:|
| Coding decode tok/s, mean (range) | 8.37 (7.90-8.98) | 7.98 (7.62-8.43) |
| Coding expert SSD MB/output token | 690.29 (655.64-710.36) | 707.03 (685.79-728.64) |
| Coding routed expert hit fraction | 0.00% | 3.82% |
| Cold 4K prefill tok/s | 203.41 (202.33-204.48) | 192.43 (181.39-203.47) |
| Cold 4K SSE TTFT seconds | 19.77 (19.67-19.88) | 20.96 (19.76-22.16) |
| Reuse 4K SSE TTFT seconds | 1.53 (1.52-1.54) | 1.58 (1.56-1.60) |
| Total expert store cap, including staging/metadata | 1.945969 GiB | 1.949022 GiB |
| Additional retention metadata within expert budget | 0 | 3.1262 MiB |

Observed coding mean change: -4.57%; SSD bytes per output token: +2.42%. These are small-sample observations on a passively cooled machine with other desktop activity uncontrolled; ranges, drift and B2's extra persisted replay limit causal conclusions. Cache hits alone do not establish a speedup. Filled-131K inference and other Macs/DGX Spark were not benchmarked here.

All 17 ORCHID/count checks passed; all 25 responses completed SSE with clean request counters. No per-request Metal/capacity failures or server-instance changes. The candidate restart restored the B1 4K prefix from SSD and passed the exact output check. A power sample after B2 showed AC power at 80% and Low Power Mode off. Thermal states: ['fair', 'nominal']; memory pressure: ['normal']; headroom 1.686-2.389 GiB.

### Every serving row

| Row | Prompt | Cached | PP tok/s | Decode tok/s | SSD MB/decode token | Expert hits | Finish | Check |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A1-smoke-cold | 435 | 0 | 90.53 | 12.49 | 500.07 | 0.00% | stop | pass |
| A1-smoke-reuse | 435 | 416 | 11.77 | 12.56 | 497.90 | 0.00% | stop | pass |
| A1-4k-cold | 4019 | 0 | 204.48 | 12.63 | 494.91 | 0.00% | stop | pass |
| A1-4k-reuse | 4019 | 4000 | 12.52 | 12.59 | 496.75 | 0.00% | stop | pass |
| A1-code-1 | 61 | 0 | 20.22 | 8.51 | 684.99 | 0.00% | length | output capped |
| A1-code-2 | 61 | 0 | 20.42 | 8.98 | 655.64 | 0.00% | length | output capped |
| B1-smoke-cold | 435 | 0 | 90.48 | 12.54 | 498.50 | 2.36% | stop | pass |
| B1-smoke-reuse | 435 | 416 | 11.10 | 12.73 | 491.35 | 3.91% | stop | pass |
| B1-4k-cold | 4019 | 0 | 203.47 | 12.53 | 495.98 | 2.25% | stop | pass |
| B1-4k-reuse | 4019 | 4000 | 12.25 | 12.47 | 494.95 | 3.82% | stop | pass |
| B1-code-1 | 61 | 0 | 19.97 | 8.43 | 686.25 | 3.63% | length | output capped |
| B1-code-2 | 61 | 0 | 20.10 | 8.20 | 685.79 | 4.14% | length | output capped |
| B2-persisted-replay | 4019 | 4000 | 11.61 | 12.58 | 496.32 | 1.69% | stop | pass |
| B2-smoke-cold | 435 | 0 | 90.59 | 12.64 | 495.26 | 2.17% | stop | pass |
| B2-smoke-reuse | 435 | 416 | 12.60 | 12.69 | 492.41 | 3.30% | stop | pass |
| B2-4k-cold | 4019 | 0 | 181.39 | 11.86 | 508.24 | 2.25% | stop | pass |
| B2-4k-reuse | 4019 | 4000 | 11.93 | 11.26 | 513.07 | 3.21% | stop | pass |
| B2-code-1 | 61 | 0 | 20.04 | 7.69 | 727.42 | 3.93% | length | output capped |
| B2-code-2 | 61 | 0 | 20.08 | 7.62 | 728.64 | 3.57% | length | output capped |
| A2-smoke-cold | 435 | 0 | 90.46 | 12.53 | 500.36 | 0.00% | stop | pass |
| A2-smoke-reuse | 435 | 416 | 11.78 | 12.58 | 497.87 | 0.00% | stop | pass |
| A2-4k-cold | 4019 | 0 | 202.33 | 12.55 | 495.12 | 0.00% | stop | pass |
| A2-4k-reuse | 4019 | 4000 | 12.38 | 12.31 | 499.15 | 0.00% | stop | pass |
| A2-code-1 | 61 | 0 | 20.37 | 8.08 | 710.36 | 0.00% | length | output capped |
| A2-code-2 | 61 | 0 | 20.63 | 7.90 | 710.19 | 0.00% | length | output capped |

### Initial candidate: every completed serving row

This earlier A/B/B/A used five-second request cooldowns and no additional block cooldown. Its two candidate blocks used count-only retention. These rows are separate from the revised candidate and are not pooled with it.

| Initial candidate metric | Baseline | Count-only retention |
|---|---:|---:|
| Coding decode tok/s, mean | 8.135 | 8.283 |
| Coding expert SSD MB/decode token, mean | 697.35 | 684.15 |
| Routed expert hit fraction | 0.00% | 2.49% |
| Total expert-store cap including staging/metadata | 1.945969 GiB | 1.949022 GiB |
| Additional retention metadata within expert budget | 0 | 3.1256 MiB |

| Row | Prompt | Cached | PP tok/s | Decode tok/s | SSD MB/decode token | Expert hits | Finish | Check |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A1-smoke-cold | 435 | 0 | 90.75 | 12.53 | 500.46 | 0.00% | stop | pass |
| A1-smoke-reuse | 435 | 416 | 11.67 | 12.64 | 495.27 | 0.00% | stop | pass |
| A1-4k-cold | 4019 | 0 | 203.26 | 12.54 | 495.58 | 0.00% | stop | pass |
| A1-4k-reuse | 4019 | 4000 | 12.21 | 12.58 | 496.83 | 0.00% | stop | pass |
| A1-code-1 | 61 | 0 | 20.65 | 8.57 | 702.80 | 0.00% | length | output capped |
| A1-code-2 | 61 | 0 | 20.17 | 8.72 | 684.98 | 0.00% | length | output capped |
| B1-smoke-cold | 435 | 0 | 88.67 | 12.38 | 497.85 | 1.02% | stop | pass |
| B1-smoke-reuse | 435 | 416 | 11.85 | 12.51 | 495.96 | 1.27% | stop | pass |
| B1-4k-cold | 4019 | 0 | 189.80 | 12.47 | 496.17 | 1.02% | stop | pass |
| B1-4k-reuse | 4019 | 4000 | 12.44 | 12.43 | 498.49 | 1.12% | stop | pass |
| B1-code-1 | 61 | 0 | 20.34 | 8.62 | 688.06 | 2.51% | length | output capped |
| B1-code-2 | 61 | 0 | 20.17 | 8.71 | 679.00 | 2.52% | length | output capped |
| B2-persisted-replay | 4019 | 4000 | 12.28 | 12.18 | 499.99 | 1.77% | stop | pass |
| B2-smoke-cold | 435 | 0 | 89.98 | 12.11 | 505.73 | 1.14% | stop | pass |
| B2-smoke-reuse | 435 | 416 | 11.76 | 12.18 | 504.22 | 0.72% | stop | pass |
| B2-4k-cold | 4019 | 0 | 174.54 | 11.96 | 500.95 | 1.18% | stop | pass |
| B2-4k-reuse | 4019 | 4000 | 12.31 | 11.50 | 512.90 | 0.92% | stop | pass |
| B2-code-1 | 61 | 0 | 20.47 | 8.17 | 691.78 | 2.72% | length | output capped |
| B2-code-2 | 61 | 0 | 20.16 | 7.63 | 677.74 | 2.21% | length | output capped |
| A2-smoke-cold | 435 | 0 | 73.26 | 10.99 | 494.92 | 0.00% | stop | pass |
| A2-smoke-reuse | 435 | 416 | 11.57 | 12.21 | 507.47 | 0.00% | stop | pass |
| A2-4k-cold | 4019 | 0 | 175.88 | 9.85 | 486.17 | 0.00% | stop | pass |
| A2-4k-reuse | 4019 | 4000 | 12.17 | 10.95 | 495.77 | 0.00% | stop | pass |
| A2-code-1 | 61 | 0 | 20.44 | 7.53 | 689.27 | 0.00% | length | output capped |
| A2-code-2 | 61 | 0 | 20.40 | 7.72 | 712.36 | 0.00% | length | output capped |

### Identity and evidence

Hashes below were recorded for the prototype build. The production source was restored after the experiment; the complete prototype is preserved in `qwen38-option20-expert-retention-20261105.patch`.

Baseline: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Candidate: `src-092c6cdb9869d5221401024e519b47c87835b236f659c12e4320a2dc1b8a1684`.

| Artifact | SHA-256 |
|---|---|
| `build/splash` | `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` |
| `build/splash.metallib` | `826339b41ce381c8bc5e4823d213e178e8687ac4743c9b4b01fcafb476e583eb` |
| `build/expert-retention-20261105/splash` | `ec70b7e93fdb45d6acdd9d79fdf186ff1848c13efc0999eea4ce0cbc8bf0fadf` |
| `build/expert-retention-20261105/splash.metallib` | `826339b41ce381c8bc5e4823d213e178e8687ac4743c9b4b01fcafb476e583eb` |
| `build/expert-retention-20261105/host-step.metallib` | `8e177c753e2051cd8a31c79bf031b3fae8daf04f5564ced9fc37db064bdfe51a` |
| `runtime/model/SharedExpertArena.hpp` | `dd7110a83b48ed747fa5c998b0114ad387e9e8c5677904f35a840badf06968f9` |
| `runtime/model/ExpertStore.cpp` | `f9bb53657586b37da5843706de1cfea778c734d7fe61a8300a3e8a05548a1155` |
| `runtime/model/SlotRecycler.cpp` | `d11dbe3638485d5e9353d82e6d0430940e9e45ec924ec9e0ac602243466901a5` |

The JSON package contains per-request results, full before/after status, identities and raw-artifact checksums. Raw requests, parsed SSE events, logs and the reproduction are retained under `build/validation/expert-retention-v2-20261105/` and `build/expert-retention-20261105/`.

The initial count-only candidate and its A/B/B/A run remain in `build/validation/expert-retention-20261105/`. That run measured coding 8.135 versus 8.283 tok/s and 697.35 versus 684.15 MB/token, with substantial later-baseline drift; it did not establish a throughput gain. Initial harness-only interpreter, child-reaping and artifact-path failures are archived there and excluded from the completed matrices.

Full artifacts: [report](qwen38-option20-expert-retention-20261105.md), [JSON results](qwen38-option20-expert-retention-20261105.json), [tested patch](qwen38-option20-expert-retention-20261105.patch).

Other-device estimates are unchanged because this experiment established no speedup.
<!-- expert-retention-20261105:end -->


The latest Air measurement completed November 5 is recorded below. Other-device estimates remain the unverified November 4 planning scenarios.

The current revised section records the latest November 4 estimates with n-gram on SSD and explicit expert-memory assumptions. Earlier November 4 and November 3 estimates are preserved below as superseded historical material. The earlier performance-comparison report was published in repository commit `b2754de0`, size/quality evidence in `a0af77ea`, and the earlier log review in `653bea3c`; those publications do not include this local revision.

## Latest measured IQ3_XXS baseline - single-request Air profile

Completed November 5, 2026 through the active one-request option-20 server: M5 Air, 8 GPU cores, 16 GiB RAM; IQ3_XXS with DFlash2, 131,072 served context, 10 GiB ceiling, 1,024-token chunks, INT8 KV/BF16 state, SSD-backed n-gram with a 64 MiB row cache, and a 16 GiB persistent prefix-cache quota.

| Actual prompt tokens | Cold/reuse pairs | Cold prefill tok/s, mean (range) | Cold SSE TTFT, s | Reuse SSE TTFT, s | Counting decode tok/s |
|---:|---:|---:|---:|---:|---:|
| 4,019 | 3 | 204.36 (204.26-204.51) | 19.67 (19.66-19.68) | 1.56 (1.52-1.58) | 12.53 (12.37-12.62) |
| 28,589 | 3 | 183.27 (174.16-195.87) | 156.40 (145.99-164.16) | 1.16 (1.13-1.18) | 11.97 (11.79-12.06) |
| 65,367 | 1 | 162.91 (one trial) | 401.31 (one trial) | 1.73 (one trial) | 10.27 (one trial) |

The three short low-reasoning code probes averaged **8.86 tok/s** (8.73-9.02). These short probes use a 256-token output limit and do not establish completed coding-task latency. All 16 bounded recall/counting checks passed; all 27 responses completed SSE. Thermal states: ['fair', 'nominal']; memory-pressure states: ['warning']. The 65K group has one pair and filled-131K inference remains unmeasured. This run does not establish a controlled speedup over the previous two-request profile.

[Full report](qwen38-option20-air-performance-20261105.md) and [measurement package](qwen38-option20-air-performance-20261105.json). Earlier hardware-upgrade estimates below remain unverified planning scenarios.

### Complete November 5 run tables

These tables represent all 27 smoke/matrix responses. Rates are tokens per second; latency is SSE first-nonempty-content time in seconds. Two untimed READY warmups are separate from these tables.

#### Profile used

| Setting | Value |
| --- | --- |
| Device | M5 MacBook Air, 8 GPU cores, 16 GiB unified memory |
| Model | `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS` |
| Build | `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d` |
| Configured context | 131,072 tokens |
| Active request limit | 1 |
| Engine memory ceiling | 10 GiB |
| KV / recurrent state | INT8 / BF16 |
| Prefill chunk | 1,024 tokens |
| Speculation | DFlash2; verification auto |
| N-gram | 26.82 GiB SSD-backed table; approximately 64 MiB RAM row cache plus staging |
| Expert store | 1.946 GiB including staging; 512 slots |
| Prefix cache | 16 GiB disk quota; persistent |
| Sampling | Temperature 0; seed 42 |
| Counting output | 114 completion tokens per response; reasoning disabled |
| Short code / medium output limits | 256 tokens each |
| Cooldown | 10 seconds between timed requests |

#### Every cold/replay pair

Cold prompts use fresh cache salts and report zero cached tokens. Replays retain the same prompt and salt. Every immediate replay in this run was a RAM-prefix hit; this table is not an independent disk-restoration test.

| Prompt tokens | Trial | Cold prefill | Cold first content | Replay first content | Cold generation | Replay generation | Reused tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 435 | Smoke | 90.05 | 4.83 | 1.65 | 12.55 | 12.25 | 416 |
| 4,019 | 1 | 204.51 | 19.66 | 1.58 | 12.61 | 12.57 | 4,000 |
| 4,019 | 2 | 204.32 | 19.67 | 1.52 | 12.62 | 12.58 | 4,000 |
| 4,019 | 3 | 204.26 | 19.68 | 1.58 | 12.37 | 12.60 | 4,000 |
| 28,589 | 1 | 195.87 | 145.99 | 1.18 | 12.05 | 12.50 | 28,576 |
| 28,589 | 2 | 179.78 | 159.03 | 1.18 | 11.79 | 12.39 | 28,576 |
| 28,589 | 3 | 174.16 | 164.16 | 1.13 | 12.06 | 12.44 | 28,576 |
| 65,367 | 1 | 162.91 | 401.31 | 1.73 | 10.27 | 11.88 | 65,344 |

#### Every short output probe

Generation rates include reasoning tokens. `n/a` means the response reached its token cap entirely in reasoning and produced no visible answer. `Cap` identifies truncation at the output limit, not a transport failure. Coding and agent probes therefore do not establish completed-task latency.

| Probe | Prompt tokens | Prefill | First visible content | Generation | Output tokens | Reasoning tokens | Draft acceptance % | Tokens/cycle | Finish |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| smoke-reasoning-low | 53 | 18.46 | 8.18 | 10.75 | 58 | 52 | 97.92 | 5.700 | Stop |
| smoke-reasoning-medium | 23 | 12.57 | 7.39 | 10.25 | 58 | 52 | 92.16 | 5.700 | Stop |
| style-primes-1 | 25 | 13.68 | 1.83 | 10.24 | 55 | 0 | 95.92 | 7.714 | Stop |
| style-arithmetic-1 | 52 | 21.87 | 2.38 | 8.32 | 16 | 0 | 68.75 | 3.750 | Stop |
| style-code-low-1 | 61 | 20.27 | 18.73 | 9.02 | 256 | 127 | 90.86 | 3.672 | Cap |
| style-code-low-2 | 61 | 20.31 | 20.94 | 8.73 | 256 | 139 | 88.12 | 3.543 | Cap |
| style-code-low-3 | 61 | 20.34 | 19.08 | 8.83 | 256 | 127 | 87.92 | 3.638 | Cap |
| style-prose-none-1 | 26 | 13.77 | 1.89 | 6.89 | 99 | 0 | 68.06 | 2.167 | Stop |
| style-agent-medium-1 | 39 | 15.42 | n/a | 7.22 | 256 | 256 | 70.23 | 2.606 | Cap |
| style-agent-medium-2 | 39 | 15.43 | n/a | 6.99 | 256 | 256 | 67.11 | 2.515 | Cap |
| style-agent-medium-3 | 39 | 15.42 | n/a | 7.17 | 256 | 256 | 70.09 | 2.619 | Cap |

#### Output-style aggregates

| Style | Clean trials | Mean generation | Range | Mean draft acceptance % | Mean tokens/cycle | Finish reasons |
| --- | --- | --- | --- | --- | --- | --- |
| style-primes | 1 | 10.24 | One trial | 95.92 | 7.714 | stop |
| style-arithmetic | 1 | 8.32 | One trial | 68.75 | 3.750 | stop |
| style-code-low | 3 | 8.86 | 8.73-9.02 | 88.97 | 3.618 | length, length, length |
| style-prose-none | 1 | 6.89 | One trial | 68.06 | 2.167 | stop |
| style-agent-medium | 3 | 7.13 | 6.99-7.22 | 69.14 | 2.580 | length, length, length |

#### Validation, memory and cache conditions

| Measure | Result |
| --- | --- |
| Bounded ORCHID/counting correctness | 16/16 passed |
| Complete smoke/matrix SSE responses | 27/27 |
| Contaminated responses | 0 |
| Failed / cancelled matrix requests | 0 / 0 |
| Metal / capacity failures | 0 / 0 |
| Native restarts | 0 |
| Resource suspensions / replayed prompt tokens | 0 / 0 |
| Thermal states | fair, nominal |
| Memory pressure | warning |
| Observed host headroom | 0.00-0.53 GiB |
| Swap used, before / after | 340.25 / 332.25 MiB |
| Metal current bytes, before / after | 7,401,439,232 / 7,509,966,848 |
| Server-lifetime Metal peak counter at end | 8,161,132,544 bytes |
| Expert decode-cache hit rate | 0.00% |
| PLE row-cache evictions during matrix | 0 |
| Prefix-cache reads / writes | 0.00 / 3.07 GiB |
| 65K variability | Not established: one cold/replay pair |
| Filled-131K performance | Not tested |
| Controlled speedup established | No |

Swap snapshots do not establish absence of swapping. The Metal peak is cumulative for the server, not an isolated trial peak or total process RSS. Long prompts use repeated repository-note filler and bounded recall/counting, not a novel codebase. Other desktop activity was not controlled.

[Full report](qwen38-option20-air-performance-20261105.md) and [raw measurement package](qwen38-option20-air-performance-20261105.json).

## Previous measured IQ3_XXS baseline - two-request profile

M5 MacBook Air, **8-core GPU and 16 GiB RAM**, live build `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`; Flash-Next GSQ-RCO IQ3_XXS with DFlash2, INT8 KV, BF16 state, 131,072 served context, 10 GiB engine cap, 1,024-token prefill chunks, and 16 GiB persistent prefix-cache quota. Serial figures exclude observed foreign requests.

| Actual prompt tokens | Clean cold trials | Cold prefill tok/s (mean; range) | Cold SSE TTFT mean, s | Reuse SSE TTFT mean, s | Cold decode tok/s mean |
|---:|---:|---:|---:|---:|---:|
| 4,019 | 3 | 203.93; 203.67-204.24 | 19.713 | 1.535 | 12.58 |
| 28,589 | 3 | 168.69; 164.48-174.28 | 169.601 | 1.148 | 11.84 |
| 65,367 | 1 | 149.40; 149.40-149.40 | 437.618 | 2.110 | 11.18 |

The short code probe with low reasoning produced **8.76 decode tok/s**. Medium-reasoning probes produced **7.11 and 7.73 tok/s**. Those short style probes are length-limited and do not establish long-context coding throughput or completed-task latency. The expert store remained at **1.946 GiB and 512 slots**, with **zero expert-cache hits** in every reviewed row. Thermal state was nominal/fair, memory pressure normal/warning, and swap about 436 MiB. The 65K group has one cold trial; filled-131K inference remains unmeasured.

[Full measured results](qwen38-option20-live-chosen-20261104.md).

## Revised estimates: n-gram on SSD, with explicit expert-memory assumptions

These are the latest planning estimates from the November 4 follow-up. They supersede the earlier five-Mac performance and cache assumptions preserved below. The n-gram table already stayed on SSD in the measured Air baseline; this revision changes the larger-machine expert-residency scenarios, not that baseline.

Only the 16 GB Air IQ3_XXS allocation and its marked speeds are measured. All other allocations and speeds are low-confidence assumptions, not observed allocations, measured speedups, guaranteed ranges, or outputs of a validated cache-hit model.

Assumptions for the Mac rows: Splash with the matching DFlash2 draft, INT8 KV, BF16 state, text-only serving, one busy request, warmed expert caches, and a fast internal SSD comparable to the measured Air. Both M5 Pro minis have 16-core GPUs. The added M5 Max Mac Studio has 128 GB RAM and a 40-core GPU; its rows assume all routed experts resident, with n-gram still on SSD. Prefill concerns an uncached prompt around 30K; generation concerns short coding prompts with low reasoning. These are different workloads, not a matched long-context coding benchmark. Rates include reasoning tokens where generated.

### Applied 16 GB Air profile: November 4 follow-up

The tested launcher is now installed at `/Users/mymac/startllamacpp.sh`, and the live Air option-20 service defaults to **one active request**. The 131,072-token server context, 10 GiB engine ceiling, 1,024-token chunks, INT8 KV/BF16 state, 64 MiB SSD-backed PLE row cache and 16 GiB persistent prefix-cache quota are retained. Hosts with 24 GB or more keep their two-request default; explicit overrides remain available.

Validation passed 33 launcher regressions and six clean live correctness/cache requests. After the clean restart, the next conversation turn restored **4,000 KV tokens and one recurrent state from disk**. A fresh 435-token prompt's immediate repeat reused 416 tokens. The engine binary did not change. These are functional checks, not a new isolated-throughput or coding-quality benchmark; the estimate-table numbers remain unchanged.

[Implementation, validation and raw-evidence pointers](qwen38-option20-air-profile-20261104.md). The optional 64K context remains an explicit workload choice, documented in the [option-20 profile](qwen38-option20.md#current-16-gb-air-defaults-2026-11-04-follow-up).

### Verification: optimized Splash with SSD-backed n-gram

Source and saved-evidence audit, November 4, 2026. **The SSD-backed configuration is verified; the larger-Mac performance estimates are not benchmark-verified under it.** No new inference or live server query was performed for this audit.

| Check | Finding | Evidence status |
|---|---|---|
| Option 20 forces an SSD-backed table | The launcher passes `--ple-memory 64M`; this explicit size is below the whole table and does not automatically expand to a resident table when the RAM ceiling rises. | Verified from launcher and planner source |
| Full n-gram table in the measured Air | `streamed_table.table_bytes = 28,800,138,240` bytes; the saved serving snapshots report a streamed table rather than a resident table. | Verified from saved initial/final status |
| Row cache in the measured Air | `cache_bytes = 67,108,844` bytes, just below 64 MiB, plus staging and other working allocations. | Verified from saved initial/final status |
| Every lookup must read SSD | No. Previously read rows can hit the host row cache; misses use source-file reads with `F_NOCACHE`. Rows must be copied/staged into memory for computation. | Verified from row-store/source code and counters |
| DFlash2 and optimized Metal execution still operate | PLE rows for draft proposals are staged inside the verification command, and prefill can read ahead; table streaming does not disable DFlash2 or the model's quantized gather kernels. | Verified source design and measured Air speculation |
| Air IQ3 performance with this configuration | 168.69 prefill tok/s at 28,589 tokens; 8.76 tok/s on the separate short low-reasoning code probe. | Measured; different workloads |
| Publisher Q2 performance anchor | The 95 decode / 1,312 prefill reference identifies model and hardware, but the inspected README and linked performance-details page do not identify its exact PLE placement or row-cache size. | Reported performance; forced-64-MiB PLE mode unconfirmed |
| 64 GB mini and 128 GB Studio fast estimates | The table explicitly assumes SSD-backed PLE, but there are no matching per-device PLE/status/throughput records here that validate those rates. | Unverified estimates; retain low confidence |

The saved Air matrix's initial/final PLE-counter deltas show **95.84% prefill row-cache hits** (52,392 of 54,664 unique-row requests across stages) and **68.64% decode hits** (47,448 of 69,128), with **2,155,680 new source-file row-read bytes** over that snapshot interval. This is the saved synthetic/style/concurrency workload mix, not a novel-code benchmark or a cache-hit forecast for another machine. Repeated row requests across stages can contribute repeatedly to these counters.

The precise assumption is **the whole n-gram table remains SSD-backed while a small RAM row cache and staging buffers are allowed**. A requirement that every row access hit disk, with no RAM reuse, is a different workload and has not been measured. `--ple-memory auto` can load the whole table where it fits, and `--ple-memory off` loads it; neither setting enforces this estimate's SSD-backed mode. Keep the explicit `--ple-memory 64M` when comparing these Splash scenarios. The claimed setting applies to the ISTA GGUF's streamable IQ4_NL table, not every arbitrary PLE representation.

Sources: [option-20 launcher](/Users/mymac/startllamacpp.sh), [planner setting resolution](/Users/mymac/splash/splash/runtime/engine/MemoryPlan.cpp), [uncached source reads](/Users/mymac/splash/splash/runtime/model/WeightSource.cpp), [published measurement package](qwen38-option20-live-chosen-20261104.json), and [official PLE streaming documentation](https://github.com/incoai/splash/blob/main/docs/server.md#ple-table-streaming). The [publisher benchmark](https://github.com/incoai/splash#performance) and [linked performance details](https://github.com/incoai/splash/blob/main/docs/performance.md) were reviewed for PLE-placement evidence; the latter currently provides no Flash-Next-specific placement record.

### Six Macs plus DGX Spark, both quantizations

Memory is in GiB; performance is in tokens per second. Mac rows use requested Splash ceilings, which Metal can clamp lower; these cap Metal allocations, not total process RSS. The Mac launcher defaults to 10G, so larger budgets require an explicit override. The DGX Spark rows instead use a 64 GiB engine-memory planning allowance for CUDA llama.cpp, not an enforced Splash setting or observed allocation. Their target-only generation excludes speculative acceleration; the Mac rows include DFlash2. This is a deployment comparison, not a controlled hardware-only ranking.

| Device | Quant | Runtime | Planned engine budget / cap | RAM allocated to experts | Cold prefill, about 30K | Short-code generation |
|---|---|---|---:|---:|---:|---:|
| M5 Air 16 GB | IQ3_XXS | Splash / DFlash2 | 10 GiB, measured configuration | 1.95, measured | 183.27, measured at 28,589 | 8.86, measured over 3 probes |
| M5 Air 16 GB | Q2_0 | Splash / DFlash2 | 10 GiB | 2-4, estimated | 190-230 | 10-13 |
| M5 Air 32 GB | IQ3_XXS | Splash / DFlash2 | 24 GiB | 12-16, assumed | 180-250 | 11-16 |
| M5 Air 32 GB | Q2_0 | Splash / DFlash2 | 24 GiB | 14-18, assumed | 230-350 | 14-22 |
| M6 mini 32 GB | IQ3_XXS | Splash / DFlash2 | 24 GiB | 12-16, assumed | 180-250 | 11-16 |
| M6 mini 32 GB | Q2_0 | Splash / DFlash2 | 24 GiB | 14-18, assumed | 230-350 | 14-22 |
| M5 Pro mini 48 GB | IQ3_XXS | Splash / DFlash2 | 40 GiB | 26-32, assumed | 250-450 | 15-25 |
| M5 Pro mini 48 GB | Q2_0 | Splash / DFlash2 | 40 GiB | 28-32, assumed | 350-650 | 22-40 |
| M5 Pro mini 64 GB | IQ3_XXS | Splash / DFlash2 | 48 GiB maximum | 38-41.55, conditional near/full residency | 600-900, conditional | 35-60, conditional |
| M5 Pro mini 64 GB | Q2_0 | Splash / DFlash2 | 48 GiB maximum | Approximately 32-34, conditional full residency | 850-1,150, conditional | 65-90, conditional |
| M5 Max Studio 128 GB, 40-core GPU | IQ3_XXS | Splash / DFlash2 | 56 GiB | 41.55, assumed fully resident | 1,200-1,800, estimated | 70-110, estimated |
| M5 Max Studio 128 GB, 40-core GPU | Q2_0 | Splash / DFlash2 | 56 GiB | Approximately 32-34, assumed fully resident | 1,600-2,300, estimated | 100-150, estimated |
| DGX Spark 128 GB, GB10 | IQ3_XXS | CUDA llama.cpp, target-only | 64 GiB allowance, assumed | Approximately 40-44, assumed resident | 500-900, estimated | 20-35, estimated |
| DGX Spark 128 GB, GB10 | Q2_0 | CUDA llama.cpp, target-only | 64 GiB allowance, assumed | Approximately 31-35, assumed resident | 700-1,200, estimated | 25-45, estimated |

For streaming rows, expert memory is the whole store, including slots, staging and bookkeeping. The measured 1.946 GiB Air store contains a 1.233 GiB expert arena and 0.713 GiB staging. For fully resident rows, expert memory means the routed-expert weights loaded directly with the model; no separate streamed-expert cache is needed. Do not add the full resident expert allocation to an additional streaming store.

The ranges for larger caches were not measured or computed by a per-device planner run. They make the revised performance scenarios' assumptions explicit. Cache capacity does not establish the fraction of SSD reads avoided. In particular, the 32/48 GB rows can miss these ranges if Metal clamps the ceiling, other allocations need more room, or host pressure prevents growth. The M6 and M5 Air 32 GB generation estimates are deliberately equal because there is no matched workload evidence for an M6 uplift.

### Added M5 Max Mac Studio, 128 GB

Hardware assumption checked against [Apple's Mac Studio specifications](https://www.apple.com/ca/mac-studio/specs/): the 128 GB M5 Max configuration has an 18-core CPU, 40-core GPU and 614 GB/s memory bandwidth. The 32-core GPU configuration has 460 GB/s and is not the configuration estimated here.

Both Studio rows use a requested **56 GiB total Splash ceiling**, which option 20's existing `SPLASH_FLASH_NEXT_MAX_MEMORY` allowlist accepts. This is a chosen sufficient budget for the SSD-n-gram scenario, not the Studio's maximum available RAM. No launcher or runtime settings were changed. IQ3's metadata-sized 45.373 GiB of complete transformer weights plus draft leaves approximately **10.627 GiB** within that ceiling for KV, recurrent state, workspaces, runtime reserves and the 64 MiB n-gram row cache. The expert allocation is the same 41.555 GiB of resident expert weights, not a larger cache added on top. Q2's approximate resident expert allocation remains unsized by the equivalent metadata check.

The Studio estimates are **1,200-1,800 cold prefill tok/s around 30K and 70-110 short-code generation tok/s for IQ3_XXS**, and **1,600-2,300 prefill tok/s and 100-150 generation tok/s for Q2_0**. They assume fully resident transformer experts, one request, DFlash2, INT8 KV/BF16 state, and n-gram on SSD with its 64 MiB row cache. Requested budget and capacity arithmetic make residency plausible; no Studio memory-plan run confirms it.

These ranges are broad extrapolations from the separately identified publisher Q2 M5 Pro 20-core-GPU/64 GB result, with the larger GPU and bandwidth, removal of expert streaming, and quant-dependent compute costs as considerations. They are planning judgments, not a fitted bandwidth/core-count scaling formula or matched IQ3/Q2 measurements. They do not incorporate results from other runtimes or quantization formats and do not establish filled-131K or simultaneous-request throughput. No Studio inference, download, build, restart or benchmark was performed.

### Added DGX Spark, 128 GB: separate CUDA runtime assumptions

This is one **DGX Spark with GB10 and 128 GB unified memory**, not RTX Spark N1X or a two-Spark system. NVIDIA specifies **273 GB/s memory bandwidth**. [NVIDIA hardware documentation](https://docs.nvidia.com/dgx/dgx-spark/hardware.html).

**Splash and option 20 require Apple Silicon/macOS and Metal**, so the Spark rows are not Splash estimates. They assume a CUDA llama.cpp build that supports the exact ISTA GSQ-RCO quantization types and Flash-Next architecture, text-only serving, one request, fully resident transformer experts, and SSD-backed lazy n-gram lookup. [Splash platform](https://github.com/incoai/splash); [ISTA model card and lazy n-gram guidance](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF#memory-requirements). Exact build/quant compatibility and lazy lookup still need a live startup/correctness check; no command is asserted to work on an untested Spark installation.

The two exact quantizations remain `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS` and `:Q2_0`. The **64 GiB engine-memory allowance** is a capacity-planning assumption, not a llama.cpp allocation limit or a copied Splash flag. Approximately **40-44 GiB of resident expert weights for IQ3** and **31-35 GiB for Q2** are CUDA-layout approximations guided by the transformer shards' sizes. Neither has been sized with a CUDA loader. Do not transfer the Mac's exact 41.555 GiB expert allocation to CUDA as a measurement. These are resident weights, not an additional streaming-expert cache. The full 26.82 GiB n-gram table is excluded from resident-weight sizing; lookup buffers and any OS page cache still consume host memory. The Mac's 64 MiB row-cache setting is not claimed for CUDA.

The Spark main-table ranges are **500-900 cold prefill tok/s around 30K and 20-35 short-code generation tok/s for IQ3_XXS**, and **700-1,200 prefill tok/s and 25-45 generation tok/s for Q2_0**. These are very-low-confidence target-only planning judgments. They assume no DFlash2, no MTP acceleration, BF16 recurrent state and an 8-bit KV implementation where the selected CUDA build supports the required Flash-Next operations; runtime/KV compatibility remains unvalidated. They do not establish filled-131K performance. CUDA quantization kernels, sparse-attention support, PLE latency and KV format can put actual performance outside these ranges. No cross-quant or Mac/Spark speedup is measured.

Separate published anchors, not measurements of these ISTA GGUF estimates:

- A reproducible one-Spark CUDA llama.cpp recipe reports approximately **24.5 tok/s code generation without MTP**, and **47-48 tok/s with MTP**, for **Unsloth UD-Q4_K_XL** plus a separate MTP head. That is a different quant and draft from this table; its configured 131K capacity does not establish filled-131K performance. [Recipe and raw-evidence links](https://github.com/Weschera/Qwen3.8-Flash-Next-1x-DGX-Spark/blob/main/README.md).
- A one-Spark **NVFP4/vLLM/MTP3** deployment reports approximately **1,825 input tok/s on a fresh 32,791-token prompt** and **45.75 code output tok/s** in its separate short-prompt probe, using FP8 KV, BF16 state and staged SSD PLE. These measurements support a separate optimized-runtime option, not performance claims for IQ3/Q2 GGUF. [Author's measurement report and raw samples](https://madeye.github.io/qwen38-flash-next-on-dgx-spark/).

If a validated MTP setup is used with the exact ISTA artifacts, generation may improve; no MTP gain is included in these two table rows. Optimized NVFP4/vLLM/SGLang results cannot be copied into the IQ3_XXS or Q2_0 cells. The GB10's peak FP4 compute rating and its DRAM bandwidth do not directly predict end-to-end GGUF performance.

The Spark rows and supporting section were added from source review only. No Spark access, installation, model download, inference, build, runtime configuration change or benchmark was performed.

### N-gram placement and IQ3 runtime sizing

The entire 26.82 GiB n-gram table stays in its SSD file in every scenario. Option 20 keeps a 64 MiB row cache in RAM; row staging and other working memory also need room. Do not charge the entire n-gram table against the RAM ceiling.

Metadata-only sizing of the installed IQ3_XXS model, using the existing local sizing helpers, produced:

| Component | Bytes | GiB |
|---|---:|---:|
| Other resident weights plus DFlash2 draft | 4,099,522,560 | 3.818 |
| All routed experts | 44,619,270,144 | 41.555 |
| Total weights plus draft, excluding n-gram | 48,718,792,704 | 45.373 |
| Room left under a 48 GiB ceiling | 2,820,814,848 | 2.627 |

The remaining 2.627 GiB must cover KV, recurrent state, workspaces, row caching and runtime reserves. The 48 GiB ceiling therefore makes all or nearly all IQ3 experts resident a plausible but unconfirmed operating scenario. These figures do not establish full residency at option 20's 131,072 served context, and filled-131K performance remains unmeasured. Q2_0's approximate 32-34 GiB resident expert figure has not received the equivalent metadata-only sizing check.

Sizing source: [existing helper source](/Users/mymac/splash/splash/build/validation/option20-10g/sizing.cpp), reading installed model root `/Users/mymac/splash/splash/install/models/.resolved/2f948307da72bd2e3fcf477e593f2f071c0b8df7b364940ffddb455b334f5f32`. The original and candidate sizing helpers agreed on `loaded=4099522560` and `expert_all=44619270144`; their different minimum-streaming-store results are not used as full-residency requirements. No model inference was performed for this sizing check.

### 64 GB mini: alternative IQ3 operating modes under the 48 GiB ceiling

| Operating scenario | Cold prefill, about 30-32K | Short-code generation |
|---|---:|---:|
| All or nearly all experts resident | 600-900 | 35-60 |
| Some recurring expert SSD reads | 300-550 | 20-35 |
| Substantial expert streaming | 200-300 | 13-20 |

These are alternative low-confidence scenarios, not measured confidence intervals. Until the actual memory plan and expert-read counters confirm residency, the cautious planning point is about **500 prefill tok/s and 30 generation tok/s**, or approximately **65 seconds to ingest a cold 32K prompt**. That point is a planning judgment between scenarios, not an independently fitted prediction. No 32K estimate is extended to filled 131K.

### External performance anchor and scope

Splash publishes Q2_0 on an M5 Pro with 20-core GPU and 64 GB: **95 tok/s short-prompt generation**, **1,312 tok/s cold prefill in the 32K bucket**, and **171 ms cached 32K TTFT**, using selected SPEED-Bench coding prompts over HTTP. [Publisher benchmark](https://github.com/incoai/splash#performance).

The publisher anchor has not been verified with the forced 64 MiB SSD-backed PLE setting used in these estimates. Its rates must not be presented as measurements of that setting. The proposed 16-core-mini ranges allow for GPU size, quantization, workload differences and residual expert streaming. No validated scaling formula connects those configurations, and the publisher result does not establish the memory plan or cache hit rate of the requested deployment. The local IQ3 Air probes are not the same workload or build as this Q2 reference. Q2_0 is an alternative artifact; option 20 still selects `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`.

The November 4 estimate revision saved planning scenarios, allocations, metadata-sizing arithmetic and limitations only; the latest Air measurements above were performed separately. It does not update the previously published repository reports or establish new benchmark results. No inference, live server query, model download, build, restart or runtime configuration change was performed to save this revision.

## Cache-effectiveness sensitivity

For an illustrative **12 tok/s** baseline, ideal storage-bound throughput is `12 / (1 - avoided read fraction)`. These are sensitivity calculations, not hardware forecasts.

| Expert SSD traffic avoided | Ideal speedup while SSD-bound | Illustrative generation, tok/s |
|---|---:|---:|
| 0% | 1.00x | 12 |
| 20% | 1.25x | 15 |
| 40% | 1.67x | 20 |
| 50% | 2.00x | 24 |
| 75% | 4.00x | 48 |

GPU computation, staging, attention, KV and PLE reads limit the eventual gain. A larger cache might avoid much more traffic than the conservative assumptions above, especially if it removes shared-format arena evictions. The existing zero-hit runs cannot measure that benefit.

## Model sizes

| Component | IQ3_XXS | Q2_0 | Reduction from IQ3_XXS |
|---|---:|---:|---:|
| Transformer-weight shard | 47.04 GB | 37.62 GB | 20.0% |
| PLE / n-gram shard | 28.80 GB | 28.80 GB | None |
| Total model download | 75.84 GB | 66.42 GB | 12.4% |
| Total in binary units | 70.63 GiB | 61.86 GiB | 8.77 GiB |
| Average transformer bits per weight | 3.00 | 2.40 | 20.0% |

The n-gram shards are identical. Q2_0 saves **9,416,119,904 bytes**, or **8.769 GiB**, entirely in the transformer shard. Shard 1 includes both experts and non-expert weights; its size is not a final Metal allocation or an expert-cache capacity. Sizes exclude the draft and optional vision projector.

## Quality comparison, including the requested 27B quant

| Benchmark | Flash-Next GSQ-RCO IQ3_XXS | Flash-Next GSQ-RCO Q2_0 | 27B Unsloth UD-Q4_K_M | Original Qwen3.8-27B, reference only |
|---|---:|---:|---|---:|
| Coding: LiveCodeBench v6 | 86.29 | 81.14 | Not found | 90.3 |
| Scientific reasoning: GPQA Diamond | 91.41 | 89.39 | Not found | 89.2 |
| Competition mathematics: AIME25 | 100.00 | 96.67 | Not found | Not found |
| Average of these three | 92.57 | 89.07 | Not available | Not available |

Scores for `unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M` on these benchmarks were not found in the inspected publisher sources. The original 27B reference scores are **not** scores for that quant. Qwen and ISTA use different evaluation setups, so they do not establish a controlled cross-model ranking. Within ISTA's evaluation, Q2_0 loses 5.15 points on coding, 2.02 on GPQA, 3.33 on AIME25 and 3.50 on the average versus IQ3_XXS. Those are benchmark-score differences, not a percentage loss of general intelligence.

[Size/quality sources and metadata](qwen38-quant-size-quality-20261104.md).

## Corrections to the historical notes

- The live macOS reserve was **2.00 GiB** (2,147,483,648 bytes), not 2.15 GiB. With the 1 GiB growth margin, normal growth requires about **3.00 GiB spare**, or **4.00 GiB** for recovery after pressure.
- A second admitted request does not guarantee concurrent execution. In the latest chosen 10G/two-lane probe, the child queued about **165 seconds**, with only one prefill/decode running at once. More RAM alone does not establish unconditional concurrency.
- Expert staging is a fixed component; the small store's total bytes cannot be scaled as a constant cost per slot. The historical 93 GiB full-residency calculation is not a validated requirement.
- Different output styles have different traffic and draft acceptance. A single 452 MB-per-token figure does not describe coding and reasoning probes.
- Source uses `F_NOCACHE` for streamed weights; extra macOS file caching is not an established expert-read accelerator. Prefix caching and expert caching are separate mechanisms.

## Earlier November 4 estimates: superseded by the revised section above

The following two sections are retained verbatim for traceability. Their cache allocations and performance scenarios are superseded by the revised estimates above. The original publication notes describe that earlier work, not this local revision.

## IQ3_XXS estimates with larger expert caches

Only the 16 GB Air column is measured. Upgrade columns assume raised engine budgets, comparable SSD throughput, one busy request, and warmed expert caches. Store capacity does not determine traffic hit rate; all upgrade figures are low-confidence scenarios rather than validated predictions.

| Metric | M5 Air 16 GB, measured | M5 Air 32 GB, estimated | M6 mini 32 GB, estimated | M5 Pro mini 48 GB, estimated | M5 Pro mini 64 GB, estimated |
|---|---:|---:|---:|---:|---:|
| Expert-store budget | 1.95 GiB | 8-12 GiB | 8-12 GiB | 16-20 GiB | 24-32 GiB |
| Decode expert SSD traffic avoided | 0%, measured | 10-20%, assumed | 10-20%, assumed | 20-35%, assumed | 30-45%, assumed |
| Cold prefill at 28.6K, tok/s | 168.7 | 175-210 | 175-220 | 190-240 | 210-280 |
| Cold prefill at 65.4K, tok/s | 149.4 | 155-185 | 155-195 | 165-215 | 180-245 |
| Short code probe, low reasoning: decode tok/s | 8.76 | 10-11 | 10-11 | 11-14 | 13-16 |
| Short medium-reasoning probes: decode tok/s | 7.1-7.7 | 8-10 | 8-10 | 9-12 | 10-14 |
| Predictable output at 28.6K: decode tok/s | 11.84 | 13-15 | 13-15 | 15-18 | 17-22 |
| Cold 28.6K prompt: first token | 2.83 min | 2.3-2.7 min | 2.2-2.7 min | 2.0-2.5 min | 1.7-2.3 min |
| Cold 65.4K prompt: first token | 7.29 min | 5.9-7.0 min | 5.6-7.0 min | 5.1-6.6 min | 4.4-6.1 min |

Estimated code/reasoning rates concern short probes. Cold means the conversation prefix is uncached. The decode assumptions are 10-20% avoided expert reads on 32 GB, 20-35% on 48 GB, and 30-45% on 64 GB. Prefill ranges are separate, weaker planning judgments.

[Full cache assumptions and corrections](qwen38-option20-cache-estimates-20261104.md).

## Q2_0 versus IQ3_XXS on all five Macs

This saves the comparison for all five requested Macs. Only the IQ3_XXS
16 GB Air figures and the separately identified publisher Q2_0 reference are
measurements. Every other figure is a low-confidence planning estimate, not a
matched benchmark, a guaranteed range, or a measured speedup.

No tests, inference requests, live server queries, model downloads, builds, or
restarts were performed for this comparison or publication. The sources were
existing local artifacts, repository documentation, source inspection, and
publisher documentation checked November 4, 2026.

### Models and assumptions

- IQ3_XXS: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`.
- Q2_0: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0`.
- Runtime assumption: Splash with the matching DFlash2 draft, INT8 KV, BF16
  recurrent state, text-only serving, one busy request, and a warmed expert
  cache. Larger machines receive raised engine budgets rather than retaining
  the option 20 launcher's 10 GiB default.
- The prefill comparison concerns uncached prompts around 30K tokens. The
  local IQ3_XXS measurement has exactly 28,589 tokens; the publisher Q2_0
  reference uses its 32K bucket. They are not identical prompts or methods.
- Code decode refers to short prompts with reasoning enabled. The local
  IQ3_XXS probe uses low reasoning and is length-limited; the publisher uses
  selected SPEED-Bench coding prompts. These are not completed-task metrics.
- Internal SSD throughput is assumed comparable to the logged Air, except
  that a fully resident transformer largely removes expert SSD reads. Actual
  SSD configuration, memory planning, cache effectiveness, and draft
  acceptance can move results outside the proposed ranges.
- The requested M5 Pro configurations both have a 16-core GPU. The measured
  Air has an 8-core GPU. No workload measurement exists here for the other
  requested configurations.

### Side-by-side comparison

Rates are tokens per second. The 64 GB Q2_0 main row assumes its transformer
weights become fully or nearly resident; its streamed alternative follows.

| Mac | IQ3_XXS cold prefill, about 30K | Q2_0 cold prefill, about 30K | IQ3_XXS short-code decode | Q2_0 short-code decode |
|---|---:|---:|---:|---:|
| M5 Air 16 GB | 169, measured at 28.6K | 190-230, estimated | 8.76, measured | 10-13, estimated |
| M5 Air 32 GB | 175-210, estimated | 220-300, estimated | 10-11, estimated | 12-16, estimated |
| M6 mini 32 GB | 175-220, estimated | 220-320, estimated | 10-11, estimated | 12-16, estimated |
| M5 Pro mini 48 GB, 16-core GPU | 190-240, estimated | 280-450, estimated | 11-14, estimated | 15-22, estimated |
| M5 Pro mini 64 GB, 16-core GPU | 210-280, estimated | 850-1,150, conditional estimate | 13-16, estimated | 65-90, conditional estimate |

If the 64 GB Q2_0 memory plan still streams substantial expert traffic, use
this separate conservative scenario instead of the near-resident row:

| Q2_0 scenario on M5 Pro mini 64 GB, 16-core GPU | Cold prefill, about 30K | Short-code decode |
|---|---:|---:|
| Substantial expert streaming remains, estimated | 350-600 tok/s | 20-32 tok/s |
| Fully or nearly resident transformer, estimated | 850-1,150 tok/s | 65-90 tok/s |

These are alternative operating-mode hypotheses, not measured confidence
intervals. The transition depends on the actual memory plan and retained
experts, not on RAM capacity alone.

### Published measurement used as an anchor

Splash reports the exact Q2_0 artifact on an **M5 Pro with 64 GB and a
20-core GPU**:

| Publisher metric | Measured result |
|---|---:|
| Short-prompt decode | 95 tok/s |
| Cold prefill, 32K bucket | 1,312 tok/s |
| Cached first-token latency, 32K replay | 171 ms |

Source: [Splash README performance table](https://github.com/incoai/splash#performance),
also recorded in the [local README](/Users/mymac/splash/splash/README.md#performance).
The README identifies selected SPEED-Bench coding prompts over HTTP. This is
an external reference on a different GPU configuration, build/release and
workload from the local IQ3_XXS probes; it is not a 16-core-mini measurement.
It also does not prove the residency or cache state of a requested deployment.

The 64 GB near-resident estimates are broad extrapolations from that reference,
with allowance for the smaller GPU and workload differences. There is no fitted
16-core scaling factor. The other Q2_0 ranges are planning judgments guided by
smaller streamed weights and possible additional expert reuse, not outputs of a
validated cache-hit or GPU-performance model.

### Why 64 GB could change the operating mode

| Component | IQ3_XXS | Q2_0 |
|---|---:|---:|
| Transformer-weight shard, including experts | 43.81 GiB | 35.04 GiB |
| Separately streamed n-gram shard | 26.82 GiB | 26.82 GiB |

Source: [recorded exact sizes and metadata](qwen38-quant-size-quality-20261104.md),
verified against the [publisher's model layout](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF#memory-requirements).
Q2_0 saves 8.77 GiB in the transformer shard. The n-gram shards are identical.
These are on-disk sizes, not final Metal allocations or expert-store capacities.

Using the logged Air's approximately 74% recommended working-set fraction and
a 1 GiB margin gives illustrative ceilings of about 22.7 GiB on 32 GB,
34.5 GiB on 48 GB, and 46.4 GiB on 64 GB. These are extrapolations of one
device's policy, not measured limits for the requested Macs. The 35.04 GiB
Q2_0 transformer would already exceed the illustrative 48 GB ceiling before
draft, KV, and workspace, while 64 GB leaves materially more headroom.

That is the reason for considering a large 64 GB Q2_0 improvement: enough
memory may remove expert streaming, rather than merely improve a partial
cache. Repacking, draft, KV, workspace, and driver costs still need to fit.
Neither the file-size calculation nor the publisher reference confirms that
the requested 16-core configuration will select that operating mode.

### Interpretation and limits

- Q2_0's transformer shard is about 20% smaller. If expert traffic scaled
  proportionally, the size-only storage-bound multiplier would be about 1.25x.
  That is an aggregate-weight proxy, not a measured per-expert traffic ratio.
- Improved expert retention could add to that benefit. The local IQ3_XXS
  logs had zero expert-cache hits, so no measured larger-cache hit-rate curve
  is available. Poor reuse can erase much of the estimated improvement.
- The publisher's llama.cpp speed comparisons involve Q2_0 versus IQ2_XS,
  not this Splash IQ3_XXS comparison. Those speedup ratios are not transferred
  to these estimates.
- The IQ3_XXS upgrade columns come from the earlier
  [conditional expert-cache review](qwen38-option20-cache-estimates-20261104.md).
  Their uncertain cache assumptions remain uncertain; they are not matched
  baselines for the publisher's Q2_0 run.
- No figure establishes filled-131K throughput, simultaneous-request
  performance, completed coding-task latency, or a measured cross-quant ratio.
- Q2_0 trades lower published quality for smaller weights; see the
  [quality comparison](qwen38-quant-size-quality-20261104.md#quality-including-the-requested-27b-quant).

Publication checks cover static content, referenced local paths, recorded size
arithmetic, and the Git diff only. They do not validate these performance
estimates or imply a new benchmark was run.

## Historical appendix: superseded November 3 analysis and early November 4 conclusion

The original local document is preserved below verbatim for traceability. Its estimates, confidence statements, slot-cost arithmetic, concurrency guarantees and unit conversions are superseded by the current revised section and measured evidence above. Relative links within the original copy refer to `/Users/mymac/splash/splash/dev/benchmarks/`.

<details>
<summary>Original saved document - historical, not current guidance</summary>

# Option 20 cross-machine throughput estimates (2026-11-03)

> Saved copy of `dev/benchmarks/qwen38-option20-machine-scaling-20261103.md` in
> the splash repo, commits `95e35a27` and `8a7d090b`. Relative links below resolve inside
> `/Users/mymac/splash/splash/dev/benchmarks/`. Measurements were taken on a
> 16 GB M5 MacBook Air, live server on port 1235, engine build `src-6a06f0d6c0d0`,
> git `3c693864`.

Estimates for five machines, derived from measurements taken on this 16 GB
M5 MacBook Air against the live 131k option 20 server (build `src-6a06f0d6c0d0`,
git `3c693864`). Companion reports: [the live 131k benchmark](qwen38-option20-live-131k-20261102.md),
[the evening rerun](qwen38-option20-live-131k-evening-20261102.md), and
[the tuning plan](qwen38-option20-tuning-plan-20261102.md).

Confidence, stated up front:

- the default-flag column is high confidence. Two measured quantities (expert
  bytes per prefill token, expert bytes per decode token) reproduce both
  measured throughputs on this machine to within one percent, so the scaling
  arithmetic is anchored rather than guessed;
- the tuned column is medium to low confidence. It depends entirely on the
  traffic hit rate of a larger expert cache, which has never been measured on
  this profile;
- GPU core counts, GPU memory bandwidth, and SSD bandwidth for M5 Pro and M5
  Max are assumptions. I cannot verify Apple's spec sheets from this machine.
  Only RAM capacity is certain.

## 1. Measured basis on this machine

A controlled decode (110 emitted tokens, reasoning off, `verify_rows auto`)
with `/status` counters diffed before and after:

```text
TTFT 1.87 s, 12.98 tok/s
engine decode wall 8453 ms, engine decode gpu 8443 ms   (99.8% of wall charged to the GPU)
expert routed reads 24,607   physical loads 720   streamed 49.75 GB
per emitted token: 223.7 routed expert reads, 6.5 physical loads, 452 MB streamed
implied sustained read bandwidth during decode: 5.89 GB/s
```

A controlled cold prefill (936 prompt tokens, unique cache salt, 8 output
tokens):

```text
TTFT 6.48 s, 145.9 tok/s prompt processing
engine prefill wall 6420 ms, gpu 6410 ms
expert routed reads 14,014 in 48 physical loads, streamed 33.76 GB
per prompt token: 14.97 routed expert reads, 36.1 MB streamed
implied sustained read bandwidth during prefill: 5.26 GB/s
PLE row cache: prefill hit_rate 0.967, decode hit_rate 0.583
```

The storage device itself, read in 3 GiB sequential chunks out of the 43.8 GiB
Flash-Next blob:

```text
cold  offset 3 GiB   3.64 GB/s
cold  offset 12 GiB  5.51 GB/s
cold  offset 24 GiB  5.51 GB/s
warm  offset 3 GiB   6.10 GB/s
warm  offset 12 GiB  6.28 GB/s
```

Two facts follow. The engine demands 5.26 GB/s in prefill and 5.89 GB/s in
decode, and this Air's SSD supplies 3.6 to 6.3 GB/s, so **both phases run at
the storage ceiling**, not at a compute ceiling. And `ane_ffn.state` is `off`
with reason `the target's FFN layers are not all dense`, so the Neural Engine
cannot carry this model's experts on any M5 machine; extra ANE capacity in a
Pro or Max part does not apply to this workload.

## 2. The scaling law

With streamed bytes per token measured, throughput follows bandwidth directly:

```text
prompt processing tok/s = streamed read bandwidth / streamed MB per prompt token
decode tok/s            = streamed read bandwidth / streamed MB per emitted token

this machine: 5.26 GB/s / 36.1 MB = 145.7 tok/s   (measured 145.9)
              5.89 GB/s / 452 MB  = 13.03 tok/s   (measured 12.98)
```

Prefill and decode differ by 12.5x in bytes per token because a 1,024-token
prefill chunk amortizes each expert load across a thousand tokens, while decode
pays 6.5 physical expert loads per emitted token. That single ratio explains
why this profile measures 146 tok/s in prefill and 13 tok/s in decode.

## 3. Why nothing is resident: the weight-volume budget

The option 20 target downloads 75,839,998,528 bytes (70.6 GiB) of GGUF across
two shards, and the engine keeps only `target_weights_bytes`
5,665,555,216 (5.28 GiB) resident. The rest streams by design:

| volume | size | source |
|---|---|---|
| target GGUF, two shards | 70.6 GiB | `profile.json` `model_files_total_bytes` |
| per-layer token embedding table (`per_layer_token_embd.weight`) | 26.8 GiB | `/status` `streamed_table.table_bytes` 28,800,138,240 |
| expert tiles, implied | 43.8 GiB | 24,576 slots x 2.02 MB per routed read = 49.6 GB, matching 70.6 GiB minus the 26.8 GiB table within 6% |
| resident plan | 9.17 GiB minimum | `memory_plan.minimum_bytes` |

The cross-check matters: 24,576 expert slots at 2.02 MB per routed read is
49.6 GB, which is the model's non-table weight volume to within 6 percent. The
model's full routed-expert working set is therefore about 44 GiB of quantized
tiles, or about 93 GiB once the engine's arena and staging overhead
(3.89 MiB of store budget per slot, 1.93x the 2.02 MB tile) is included. No
Mac below 128 GB can hold it, which is exactly why this profile exists and why
"just load the model into RAM" is not an option here.

## 4. Why host-memory expert caching helps, with the arithmetic

### 4.1 What is actually being paid for

Each routed expert must be materialized before it can be used. The engine
measures this as `streamed_experts`: routed reads, physical loads, and
`read_bytes`. On this machine the store is stuck at its floor:

```text
cap_bytes      2,089,468,688  (1,992 MiB)  == floor_bytes
arena_bytes    1,323,827,200  (1,262 MiB)  resident GPU-side tiles
staging_bytes    765,460,480  (  730 MiB)  host-side staging
slots                  512    of 24,576 experts (2.1% of capacity)
resident                38    (0.15% actually resident)
shrinks 0, regrows 0, hits 0, misses 151,971
streamed_experts.decode.hit_rate 0.00
```

So every expert byte this machine uses comes off the SSD. The store is not
undersized because memory pressure took it away. `--expert-memory auto` never
raised it, and `memory_plan.native_budget` reserves 1,992,415,744 bytes as a
floor with `host_experts_can_move: false`: the floor is a hard reservation that
cannot be handed to the model. The SSD path is the configured budget, not an
accident.

### 4.2 Store size to cache coverage

One slot costs 1,992 MiB / 512 slots = **3.89 MiB** of store budget, which is
1.93x the 2.02 MB quantized tile it holds (the difference is the arena copy
plus the staging copy). Slots therefore scale as 1,024 / 3.89 = **263 slots per
GiB**:

| expert store | slots | coverage of 24,576 experts |
|---|---|---|
| 1.9 GiB (today, auto floor) | 512 | 2.1% |
| 2 GiB | 526 | 2.1% |
| 4 GiB | 1,053 | 4.3% |
| 8 GiB | 2,106 | 8.6% |
| 12 GiB | 3,159 | 12.9% |
| 16 GiB | 4,212 | 17.1% |
| 24 GiB | 6,317 | 25.7% |
| 32 GiB | 8,423 | 34.3% |
| full residency | 24,576 | 100%, needs 93.8 GiB of store budget |

Coverage of slots is not coverage of traffic. If routing were uniform, a cache
holding fraction c of slots would capture fraction c of routed bytes. Routing is
almost never uniform in a top-k MoE, so with skew the traffic hit h exceeds c.
**This is the unknown that decides whether a bigger machine is 1.4x or 3x this
one**, and it has not been measured here because the store has never been large
enough to measure (`hit_rate` 0.00 with 38 resident slots).

### 4.3 Throughput as a function of the traffic hit

With 452 MB streamed per emitted token and a storage bandwidth B:

```text
decode tok/s = B / (452 MB x (1 - h))
prefill tok/s = B / (36.1 MB x (1 - h))
```

| traffic hit h | decode MB per token | decode tok/s at 5.9 GB/s (Air SSD) | decode tok/s at 7.0 GB/s (Pro SSD) | prefill tok/s at 7.0 GB/s |
|---|---|---|---|---|
| 0.00 (today) | 452 | 13.1 | 15.5 | 194 |
| 0.10 | 407 | 14.5 | 17.2 | 215 |
| 0.25 | 339 | 17.4 | 20.6 | 258 |
| 0.45 | 249 | 23.7 | 28.1 | 352 |
| 0.65 | 158 | 37.3 | 44.3 | 555 |
| 0.85 | 68 | 86.8 | 102.9 | 1,310 |

Read the last two rows as ceilings, not promises: they assume the SSD stops
being the limit at all, which requires the cache to absorb the traffic rather
than merely shorten it.

### 4.4 Break-even: how many reuses pay for one cached tile

Cost of a use from storage: 2.02 MB / 5.89 GB/s = **0.343 ms** of SSD time.
Cost of a use from resident memory: 2.02 MB / 150 GB/s (Air GPU-side unified
bandwidth) = **13.5 microseconds**, and about 7 microseconds at 300 GB/s on a
Pro-class part.

```text
break-even reuses on this Air:  0.343 ms / 13.5 us  = 25 uses
break-even reuses on an M5 Pro: 0.343 ms /  6.7 us  = 51 uses
```

Equivalent framing at the token level: this machine spends 1 / 13.03 s = 76.7 ms
of SSD time per emitted token. A cache that captures fraction h of routed
traffic removes h x 76.7 ms per token, so decode tok/s = 1 / (76.7 ms x (1 - h)),
which reproduces the table above (h = 0.25 gives 17.4 tok/s).

Whether an expert clears break-even depends on how often the router picks it. A
hot tile routed once every 25 tokens is reused 25 times in about 50 seconds of
generation at 13 tok/s, which already pays for its own load on an Air and pays
for it half over on a Pro. A tile routed once every 500 tokens never pays.
Because decode routes 223.7 experts per token across the model's MoE layers,
there are 2,904 routed expert evaluations per second on this machine, so the
reuse opportunity is large in aggregate even when any single tile is rare.

### 4.5 What the cache does not fix

- it does not change compute demand: 223.7 expert evaluations per emitted token
  remain 223.7. That demand is tiny compared with the bandwidth demand (about
  31 GFLOP/s at 13 tok/s for a multi-TFLOP GPU), which is why the 99.8%
  `decode.gpu_ms` share is staging and dequant work, not matmul math;
- it does not fix cold-prompt TTFT as much as it fixes decode. Prefill already
  amortizes 36.1 MB per token instead of 452 MB, so the absolute win per token
  is 12.5x smaller. The large TTFT lever is `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`
  (experiment E5), which today is 0 bytes: cold 65k prompts pay full prefill
  every time;
- it can thrash. A store sized for a long-tail routing distribution evicts as
  fast as it fills, and the eviction cost lands back on the SSD. The engine
  exposes `streamed_table.evictions` 2,683,358 and `state.evictions` 152 as
  evidence that eviction pressure is real on this profile, while experts show
  `shrinks 0` because the store never grew past its floor;
- the engine already hides part of the latency: of 29,888,708 routed decode
  reads, 10,779,985 (36.1%) were `prefetched` and 13,604,168 (45.5%) were
  `read_ahead`. A cache's value is proportional to the remaining, non-prefetchable
  tail;
- it competes with the other budgets. On this machine 1,992 MiB of expert floor
  plus 5,665,555,216 target weights plus 614,678,528 shared prefill plus
  183,840,928 shared decode plus 212,336,896 PLE budget is 8.2 GiB of hard
  floors against a 12,713,115,648 byte working set, which is exactly why the
  plan reports `headroom_status: tight` with 29,483,008 bytes spare.

## 5. Memory budget per machine

The engine plans against a working set of about 74% of RAM (measured here:
`recommended_max_working_set_bytes` 12,713,115,648 of 17,179,869,184 = 74.0%).
Fixed resident costs, all measured from `memory_plan`:

| item | bytes | GiB |
|---|---|---|
| target weights (resident portion) | 5,665,555,216 | 5.28 |
| draft weights (DFlash2) | 523,436,032 | 0.49 |
| lane state, per lane | 163,250,176 | 0.15 |
| shared prefill workspace | 614,678,528 | 0.57 |
| shared decode workspace | 183,840,928 | 0.17 |
| KV cache, INT8, 131,072 tokens | 1,736,708,864 (13,248 B/token) | 1.61 |
| KV cache, INT8, 262,144 tokens | 3,473,417,728 | 3.23 |
| PLE row cache (`--ple-memory`) | 67,108,864 today | 0.06 (0.50 if raised) |

Fixed resident sums to 8.8 GiB: 5.28 + 0.49 + 0.15 + 0.57 + 0.17 + 1.61 + 0.50.

| machine | working-set budget | fixed resident (131k, 1 lane, 512 MiB PLE) | room for the expert store | slots | coverage |
|---|---|---|---|---|---|
| M5 Air 16 GB | 11.8 GiB | 8.8 GiB | about 3 GiB | 790 | 3.2% |
| M5 Air 32 GB | 23.7 GiB | 8.8 GiB | about 15 GiB, but plan floor pressure remains | 3,900 | 15.9% |
| M5 Pro 48 GB | 35.5 GiB | 8.8 GiB | about 27 GiB | 7,100 | 28.9% |
| M5 Max 36 GB | 26.6 GiB | 8.8 GiB | about 18 GiB | 4,740 | 19.3% |
| Mac mini M5 Pro 64 GB | 47.4 GiB | 8.8 GiB | about 39 GiB | 10,260 | 41.7% |

Practical settings are one step below the arithmetic ceiling, because macOS,
Metal fragmentation, and the agent itself also live in the same unified memory:
24 GiB on a 64 GB machine, 12 to 16 GiB at 48 GB, 8 to 12 GiB at 36 GB, 4 to
6 GiB at 32 GB.

One launcher constraint applies before any of this: the option 20 profile accepts
only `SPLASH_FLASH_NEXT_MAX_MEMORY` in `8G|9G|10G|11G` (`startllamacpp.sh:1646`)
and caps `SPLASH_FLASH_NEXT_MAX_CONTEXT` at 131,072 (`startllamacpp.sh:1670`). A
64 GB machine gets nothing from its extra RAM until that whitelist is widened
and `--expert-memory` and `--ple-memory` are raised, which is a launcher edit
that must land together with the option 20 launcher tests.

## 6. Estimates at today's exact option 20 flags

10 GiB memory cap, `--expert-memory auto` (store stays at the 1,992 MiB floor,
512 slots, 38 resident), 64 MiB PLE cache, 1,024-token chunks, `--verify-rows
auto`, one active request, disk prefix cache off:

| machine | assumed SSD read bandwidth | PP, 939 to 4,019 tokens | PP, 28,589 to 65,367 tokens | decode, reasoning off | decode, reasoning low or medium | TTFT at 28,589 | TTFT at 65,367 |
|---|---|---|---|---|---|---|---|
| M5 Air 16 GB (measured) | 5.3 to 5.9 GB/s | 142 to 150 | 146 to 161 | 11.5 to 13.0 | 5.5 to 7.0 | 190 s | 420 to 446 s |
| M5 Air 32 GB | 5.3 to 6.0 GB/s | 145 to 155 | 155 to 170 | 11.5 to 13.0 | 5.5 to 7.0 | 170 to 185 s | 385 to 420 s |
| M5 Pro 48 GB (MacBook Pro) | 6.5 to 8 GB/s | 175 to 215 | 175 to 215 | 14 to 18 | 7 to 9 | 135 to 165 s | 305 to 375 s |
| M5 Max 36 GB | 7 to 8.5 GB/s | 185 to 235 | 185 to 230 | 15 to 19 | 7.5 to 9.5 | 125 to 155 s | 285 to 355 s |
| Mac mini M5 Pro 64 GB | 6.5 to 8 GB/s | 180 to 220 | 180 to 225 | 14 to 18 | 7 to 9 | 130 to 160 s | 295 to 365 s |

These are bandwidth arithmetic: 36.1 MB and 452 MB per token held constant,
bandwidth varied. The Mac mini row is the same silicon class as the MacBook Pro
row but with a sustained-cooling envelope instead of an edge-limited one, and
with `memory_pressure` gone entirely, so its prefill does not lose the 4 to 8
percent that this Air loses at 28.5k and 65k context.

## 7. Estimates with the profile tuned for the bigger machine

Settings assumed: `--expert-memory` at the per-machine practical value above,
`--ple-memory 512M`, `SPLASH_FLASH_NEXT_MAX_CACHE_DISK=8G`, `SPLASH_FLASH_NEXT_PREFILL_MAX_TOKENS=2048`,
`--max-active-requests 2`, 131,072 context. Traffic hit h is the unknown, so
each row shows the uniform-routing floor and the moderate-skew expectation.

| machine | expert store | slots (coverage) | decode tok/s at h = coverage (uniform) | decode tok/s at moderate skew | PP tok/s at moderate skew | aggregate decode with 2 lanes |
|---|---|---|---|---|---|---|
| M5 Air 16 GB | 2 to 3 GiB, at 32,761 context | 526 to 790 (2.1 to 3.2%) | 13 to 14 | 14 to 15 | 170 to 185 | 27 to 30 (32k context only) |
| M5 Air 32 GB | 4 to 6 GiB | 1,053 to 1,579 (4.3 to 6.4%) | 13 to 14 | 14 to 17 | 165 to 200 | 28 to 34 (only at 32k context) |
| M5 Max 36 GB | 8 to 12 GiB | 2,106 to 3,159 (8.6 to 12.9%) | 16 to 17 | 18 to 22 | 230 to 290 | 36 to 44 |
| M5 Pro 48 GB | 12 to 16 GiB | 3,159 to 4,212 (12.9 to 17.1%) | 17 to 18 | 20 to 25 | 250 to 320 | 40 to 50 |
| Mac mini M5 Pro 64 GB | 24 to 32 GiB | 6,317 to 8,423 (25.7 to 34.3%) | 20 to 23 | 24 to 34 | 280 to 380 | 48 to 68 |

For the Mac mini at 24 GiB and a 0.35 traffic hit, the arithmetic is explicit:
452 MB x 0.65 = 294 MB per token, 7.0 GB/s / 0.294 GB = 23.8 decode tok/s;
36.1 MB x 0.65 = 23.5 MB per prompt token, 7.0 GB/s / 0.0235 GB = 298 PP tok/s,
which puts a cold 28,589-token prompt at 96 seconds and a cold 65,367-token
prompt at 220 seconds. At 32 GiB and a 0.45 hit the same arithmetic gives 28.1
decode tok/s, 352 PP tok/s, 81 seconds to first token at 28.5k, and 186 seconds
at 65k. With the disk prefix cache on, warm agent turns skip most of that.

The Mac mini has one option no laptop has: Thunderbolt 5 on a Pro-class mini can
carry an external NVMe volume at roughly 3 to 6 GB/s. That does not beat the
internal drive, so the right use is capacity rather than speed: put the GGUF
shards and the 8 GiB disk prefix cache on the external volume so the internal
drive serves only expert streaming.

## 8. What to measure to confirm or kill these numbers

The measurement is two minutes of counter diffing, not a benchmark:

1. start option 20 with `SPLASH_FLASH_NEXT_MAX_MEMORY` raised (widening the
   launcher whitelist first) and `--expert-memory 12G`;
2. snapshot `/status`, run one decode-only request (110 tokens, reasoning off),
   snapshot again, and diff `streamed_experts.decode.{routed, loads, read_bytes}`
   plus `model_timing.decode.{total_wall_ms, total_gpu_ms}`;
3. compute streamed MB per emitted token, physical MB per load, and implied GB/s
   exactly as in section 1, then read `streamed_experts.resident` and
   `streamed_experts.decode.hit_rate`.

Decision rule: if bytes per emitted token fall from 452 toward 250, the tuned
column is real and the machine is worth 2x. If they stay near 450, routing is
uniform, residency is decorative, and the only lever left is storage bandwidth,
at which point a 48 GB M5 Pro is about 1.35x this machine and a 64 GB Mac mini
is about the same, and the purchase is justified by context capacity and lane
count rather than by speed.

## 9. Side by side: prompt processing and decode throughput

Machines as columns, so the comparison is a single glance. Anchor is the measured
M5 Air 16 GB: PP 145.9 at 936 prompt tokens, 146 to 161 at 28.5k to 65k, TPS
12.98, 452 streamed MB per emitted token at 5.89 GB/s against an SSD that
supplies 3.64 to 6.28 GB/s.

### Today's exact option 20 flags

10 GiB cap, `--expert-memory auto` (store pinned at the 1,992 MiB floor), 64 MiB
PLE cache, 1,024-token chunks, `--verify-rows auto`, one active request, disk
prefix cache off.

| metric | M5 Air 16 GB (measured) | M5 Air 32 GB | M5 Pro 48 GB (MacBook Pro) | M5 Max 36 GB | Mac mini M5 Pro 64 GB |
|---|---|---|---|---|---|
| assumed SSD read bandwidth | 5.3 to 5.9 GB/s | 5.3 to 6.0 | 6.5 to 8.0 | 7.0 to 8.5 | 6.5 to 8.0 |
| **PP**, 939 to 4,019 token prompt | **142 to 150** | **145 to 155** | **175 to 215** | **185 to 235** | **180 to 220** |
| **PP**, 28,589 to 65,367 token prompt | **146 to 161** | **155 to 170** | **175 to 215** | **185 to 230** | **180 to 225** |
| **TPS**, reasoning off | **11.5 to 13.0** | **11.5 to 13.0** | **14 to 18** | **15 to 19** | **14 to 18** |
| **TPS**, reasoning low (launcher default) | **5.5 to 7.0** | **5.5 to 7.0** | **7 to 9** | **7.5 to 9.5** | **7 to 9** |
| TTFT at 28,589 prompt tokens | 190 s | 170 to 185 s | 135 to 165 s | 125 to 155 s | 130 to 160 s |
| TTFT at 65,367 prompt tokens | 420 to 446 s | 385 to 420 s | 305 to 375 s | 285 to 355 s | 295 to 365 s |
| PP multiplier vs this Air | 1.00x | 1.06x | 1.27x | 1.35x | 1.32x |
| TPS multiplier vs this Air | 1.00x | 1.00x | 1.31x | 1.39x | 1.31x |

Each column is bandwidth divided by the same two measured constants, 36.1 MB per
prompt token and 452 MB per emitted token. RAM moves nothing here because
`--expert-memory auto` never spends spare RAM on the expert store.

### With the expert store sized to the machine

`--expert-memory` raised to the practical value for that RAM, `--ple-memory 512M`,
`SPLASH_FLASH_NEXT_MAX_CACHE_DISK=8G`, 2,048-token chunks,
`--max-active-requests 2`, 131,072 context.

| metric | M5 Air 16 GB (measured) | M5 Air 32 GB | M5 Max 36 GB | M5 Pro 48 GB | Mac mini M5 Pro 64 GB |
|---|---|---|---|---|---|
| expert store | 2 to 3 GiB | 4 to 6 GiB | 8 to 12 GiB | 12 to 16 GiB | 24 to 32 GiB |
| slots, coverage of 24,576 | 526 to 790, 2.1 to 3.2% | 1,053 to 1,579, 4.3 to 6.4% | 2,106 to 3,159, 8.6 to 12.9% | 3,159 to 4,212, 12.9 to 17.1% | 6,317 to 8,423, 25.7 to 34.3% |
| **TPS**, uniform routing floor | **13 to 14** | **13 to 14** | **16 to 17** | **17 to 18** | **20 to 23** |
| **TPS**, moderate routing skew | **14 to 15** | **14 to 17** | **18 to 22** | **20 to 25** | **24 to 34** |
| **PP**, moderate routing skew | **170 to 185** | **165 to 200** | **230 to 290** | **250 to 320** | **280 to 380** |
| **TPS**, aggregate across 2 lanes | 27 to 30, 32k context only | 28 to 34, 32k context only | 36 to 44 | 40 to 50 | 48 to 68 |
| TTFT at 28,589 prompt tokens | 155 to 168 s | 145 to 175 s | 100 to 125 s | 90 to 115 s | 75 to 102 s |
| TTFT at 65,367 prompt tokens | 355 to 385 s | 325 to 395 s | 225 to 285 s | 205 to 260 s | 172 to 235 s |
| PP multiplier vs this Air | 1.16x | 1.19x | 1.69x | 1.86x | 2.15x |
| TPS multiplier vs this Air | 1.18x | 1.27x | 1.63x | 1.84x | 2.37x |

The first column is this machine, and its tuned configuration is constrained in a
way the others are not. Its working set is 11.8 GiB against 8.8 GiB of fixed
resident cost, so a 2 to 3 GiB expert store only fits by giving context back:
the realistic tuned 16 GB profile is 32,761 served context with `--expert-memory
3G`, which is also experiment E1 and the only 16 GB configuration that measured
faster prefill (179.65 tok/s at 28,589 tokens on 2026-11-01, against 149.47 to
161.02 at 131,072). Two lanes on 16 GB are likewise a 32k-context option, not a
131k option, because the second lane's INT8 KV reservation does not fit beside a
larger store.

The distance between the two tables is the routing-skew assumption alone. If the
top-k router is effectively uniform, the tuned columns collapse onto the default
columns and a 64 GB Mac mini is worth about 1.3x rather than 2.4x. Section 8 is
the two-minute measurement that decides which world the purchase lives in.

## 10. Conclusion 2026-11-04: the configuration chosen on the 16 GB Air

Series V1 to V5b/V5c closed. The profile to run is the launcher default with the two
second-lane overrides:

```sh
SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1 \
  bash /Users/mymac/startllamacpp.sh --direct 20
```

Everything else is the default: a 10G cap, a 16G cache quota, `--expert-memory auto`, a
1,024-token chunk, 131,072 context, BF16 state, `--verify-rows auto`.

Measured expectations on this Mac: a 28,589-token cold prompt in 171.8 s (166.4 tok/s)
at the 10G cap, the same prompt in 1.1 s once cached, decode 11.7 to 11.9 tok/s at
7.4 to 7.5 tokens per draft cycle, and a delegated child admitted 10 s into a running
parent when the host keeps 3.15 GiB spare. Two requests that decode at the same time
each run at 5.17 tok/s, about half a lone request's speed, because both split the same
5 to 6 GB/s the drive supplies.

The cap ladder, all at 131,072 context:

| cap | cold 28,589 prefill | resident KV tokens | host headroom peak | `growth_allowed` |
|---|---|---|---|---|
| 11G | 150.7 to 161.0 tok/s | 262,137 | 0.26 GiB | false |
| 10G | 154.3 to 166.4 tok/s | 196,601 | 0.80 GiB | false |
| 9G | 174.6 to 183.0 tok/s | 114,681 | 0.52 GiB | false, then **true** with Chrome and LM Studio quit |

Two corrections to section 9. First, "two lanes on 16 GB are a 32k-context option, not a
131k option" is wrong: lane state is charged for all four batch positions regardless of
context, and at 131,072 context the only missing thing was host headroom. `growth_allowed`
needs `host_headroom_bytes` at or above `kHostWarningMarginBytes`, 1 GiB above the 2.147
GiB macOS reserve (`MemoryGovernor.hpp:85`), so the host must keep about 3.15 GiB spare.
With Chrome (1.42 GiB) and LM Studio (0.39 GiB) quit, headroom reached 1.13 to 1.28 GiB,
`growth_allowed` went true, and a 20-token child queued 11 s instead of 165 to 186 s.
Second, the "tuned 16 GB profile at 32,761 context with `--expert-memory 3G`" is not what
is run: the served context stays 131,072, and no expert store above its 1,992 MiB floor is
reachable at that context on 16 GB (V2 and V3 both produced the same 512-slot store).

Open items: expert quantization reduction, the only untried lever on decode speed here, and
more memory. 24 GB makes two lanes unconditional; 48 GB is where the expert store starts to
earn its slots.

</details>
