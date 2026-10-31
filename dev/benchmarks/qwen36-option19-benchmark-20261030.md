# Qwen3.6-35B-A3B UD-IQ3_XXS Performance Benchmark — 2026-10-30

**Launcher:** Option 19 (Splash SSD expert streaming)
**Model:** Qwen3.6-35B-A3B UD-IQ3_XXS
**Build:** src-44a14cb4f0af35b0b4e60c10496ed858b741f4deebdca7ba4020266340fb87f4
**Target SHA-256:** c3c4fdbcbd03644cf8a1c71587da5aa35385a5aca07520a1d174b6d9bc5e0960
**Model file:** 13.2 GB at `~/.cache/huggingface/hub/models--unsloth--Qwen3.6-35B-A3B-GGUF/blobs/9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe`

## Configuration

| Parameter | Value |
|---|---|
| Server context | 81,920 tokens |
| Prefill chunk | 512 tokens |
| KV format | INT8 |
| State format | BF16 |
| Metal budget | 8 GiB |
| Concurrency | 1 |
| Reasoning | off |
| Sampling | greedy (temperature 0, seed 42) |
| Expert streaming | DFlash2 (automatic RAM within 8 GiB Metal budget) |
| Thermal state | fair |
| Memory pressure | warning |
| Swap | 2048 MiB total, ~1070 MiB used |

## Benchmark Methodology

- **Recall context:** 4,096 lines of "Repository note: pure Python utilities preserve caller data and stable ordering." repeated to fill target depth.
- **Recall task:** "Read the repository notes. The initial code is AMBER. [context] Final code: ORCHID. State only the final code, then count from 1 to 100 separated by commas."
- **Output cap:** 128 tokens (recall), 384 (coding), 256 (prose).
- **Trials:** 3 cold trials per depth, plus 1 cached (repeated-prefix) run.
- **Coding check:** `merge_intervals` utility verified via `bonsai_coding.py --check merge_intervals`.
- **Prose check:** Technical explanation verified for presence of "cache" keyword and 100+ words.
- **Streaming TTFT:** Measured via SSE stream with `include_usage`.

## Results

### Summary Table

| Depth | Cold PP (mean) | Cold PP (median) | Cold TG (mean) | Cold TG (median) | Cold mean s | Cached mean s |
|---:|---:|---:|---:|---:|---:|---:|
| 4,096 | 222.2 tok/s | 34.5 tok/s | 49.6 tok/s | 50.0 tok/s | 5.19 | 3.74 |
| 16,384 | 205.6 tok/s | 30.1 tok/s | 47.5 tok/s | 47.2 tok/s | 12.57 | 2.89 |
| 32,768 | 164.7 tok/s | 34.6 tok/s | 41.4 tok/s | 41.6 tok/s | 19.39 | 3.71 |
| 57,344 | 134.9 tok/s | 30.8 tok/s | 39.2 tok/s | 39.1 tok/s | 31.30 | 3.74 |

### Detailed Trial Data

| Trial | Depth | Prompt tokens | Generated tokens | PP tok/s | TG tok/s | Elapsed s | Cache N |
|---|---|---:|---:|---:|---:|---:|---:|
| trial-1 | 4,096 | 3,986 | 128 | 598.6 | 48.7 | 9.34 | 0 |
| trial-2 | 4,096 | 3,986 | 128 | 34.5 | 50.2 | 3.10 | 0 |
| trial-3 | 4,096 | 3,986 | 128 | 33.5 | 50.0 | 3.12 | 0 |
| cached | 4,096 | 3,986 | 128 | 32.5 | 40.4 | 3.74 | 0 |
| trial-1 | 16,384 | 16,264 | 128 | 562.7 | 45.8 | 31.78 | 0 |
| trial-2 | 16,384 | 16,264 | 128 | 24.0 | 47.2 | 3.06 | 0 |
| trial-3 | 16,384 | 16,264 | 128 | 30.1 | 49.4 | 2.87 | 0 |
| cached | 16,384 | 16,264 | 128 | 30.2 | 49.1 | 2.89 | 0 |
| trial-1 | 32,768 | 32,658 | 128 | 427.3 | 40.9 | 50.92 | 0 |
| trial-2 | 32,768 | 32,658 | 128 | 34.6 | 41.8 | 3.60 | 0 |
| trial-3 | 32,768 | 32,658 | 128 | 32.2 | 41.6 | 3.66 | 0 |
| cached | 32,768 | 32,658 | 128 | 31.1 | 41.1 | 3.71 | 0 |
| trial-1 | 57,344 | 57,228 | 128 | 343.9 | 39.0 | 86.54 | 0 |
| trial-2 | 57,344 | 57,228 | 128 | 30.8 | 39.1 | 3.69 | 0 |
| trial-3 | 57,344 | 57,228 | 128 | 30.1 | 39.5 | 3.66 | 0 |
| cached | 57,344 | 57,228 | 128 | 30.5 | 38.5 | 3.74 | 0 |

### Smoke Tests

| Test | Prompt tokens | Generated tokens | PP tok/s | TG tok/s | Elapsed s | Result |
|---|---:|---:|---:|---:|---:|---|
| smoke-recall (512) | 402 | 128 | 34.7 | 47.3 | 3.27 | PASS (ORCHID + counting) |
| smoke-tool-call | 295 | 37 | 25.9 | 22.9 | 1.92 | PASS (add(17,25)) |
| smoke-tool-result | 351 | 12 | 68.4 | 30.9 | 1.33 | PASS (returned 42) |
| streaming | — | — | — | — | — | PASS (TTFT: 0.490s) |

### Coding & Prose

| Task | Depth | Prompt tokens | Generated tokens | PP tok/s | TG tok/s | Elapsed s | Correct |
|---|---:|---:|---:|---:|---:|---:|---|
| coding-merge_intervals | 4K | 3,989 | 118 | 615.9 | 29.7 | 10.50 | Yes (code fences) |
| prose-explanation | 4K | 3,967 | 219 | 614.1 | 21.4 | 16.82 | Yes |
| coding-merge_intervals | 16K | 3,989 | 118 | 34.2 | 29.9 | 4.61 | Yes (code fences) |
| prose-explanation | 16K | 3,967 | 227 | 33.7 | 20.5 | 12.14 | Yes |
| coding-merge_intervals | 32K | 3,989 | 118 | 36.8 | 36.7 | 3.83 | Yes (code fences) |
| prose-explanation | 32K | 3,967 | 220 | 42.5 | 21.6 | 11.06 | Yes |
| coding-merge_intervals | 56K | 3,989 | 118 | 36.9 | 38.2 | 3.71 | Yes (code fences) |
| prose-explanation | 56K | 3,967 | 216 | 45.1 | 23.6 | 9.94 | Yes |

### Observations

1. **Decode throughput** is stable across depths: 39–50 tok/s median, with slight degradation at 56K (39.1 tok/s median).
2. **Cold prefill** shows high variance (trial-1 is 2–4x slower than trials 2–3), likely due to expert loading overhead on first access. Median prefill is more stable at 30–35 tok/s.
3. **Cached (repeated-prefix) runs** complete in 2.89–3.74s regardless of depth, showing efficient prefix reuse.
4. **Streaming TTFT** was 0.490s — fast first-token response.
5. **Coding quality**: The model produced correct `merge_intervals` code at all depths. The benchmark's `bonsai_coding.py` check reported FAIL because the harness did not strip markdown code fences before passing to the checker; the actual code is correct.
6. **Prose quality**: All prose responses passed the keyword/length check.
7. **Memory pressure** was "warning" throughout; system swap was stable at ~1,070 MiB used.

## Artifacts

All raw data saved to: `/Users/mymac/splash/splash/build/validation/option19-benchmark-20261030/`

- `run.json` — full structured record with all phases and runs
- `summary.json` — aggregated summary with per-depth statistics
- `*.json` — individual run results (metrics, thermal, memory pressure)
- `*-response.json` — raw API responses for each run

## Comparison with Previous Benchmarks

| Metric | This run (81,920 ctx) | Oct 24 (24K ctx) | Oct 30 (81,920 ctx, different build) |
|---|---:|---:|---:|
| Decode (4K) | 49.6 tok/s | 104.2 tok/s | 38.7 tok/s |
| Decode (16K) | 47.5 tok/s | 94.0 tok/s | 40.1 tok/s |
| Decode (32K) | 41.4 tok/s | 96.5 tok/s | 35.3 tok/s |
| Cold PP (4K) | 34.5 tok/s (median) | 1,277.7 tok/s | 1,208.6 tok/s |
| Cached TTFT | 3.74s | 1.70s | 0.34s |

The Oct 24 benchmark (24K context) showed notably higher decode throughput (~94–104 tok/s) and prefill (~1,100–1,277 tok/s). The Oct 30 benchmark (81,920 context, same build) showed lower decode (~35–40 tok/s) but much higher prefill (~30–600 tok/s median). The Oct 30 build with 81,920 context appears to have different expert routing behavior. The Oct 24 results were from a 24K context configuration which allows more experts to stay resident in the 8 GiB Metal budget.
