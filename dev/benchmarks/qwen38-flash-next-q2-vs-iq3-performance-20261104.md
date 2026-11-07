# Flash-Next Q2_0 versus IQ3_XXS performance estimates - November 4, 2026

Historical comparison: its performance estimates are superseded by the
[conservative November 5 six-Mac estimates](qwen38-option20-mac-conservative-20261105.md).
The original dated analysis below is retained for traceability.

This saves the comparison for all five requested Macs. Only the IQ3_XXS
16 GB Air figures and the separately identified publisher Q2_0 reference are
measurements. Every other figure is a low-confidence planning estimate, not a
matched benchmark, a guaranteed range, or a measured speedup.

No tests, inference requests, live server queries, model downloads, builds, or
restarts were performed for this comparison or publication. The sources were
existing local artifacts, repository documentation, source inspection, and
publisher documentation checked November 4, 2026.

## Models and assumptions

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

## Side-by-side comparison

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

## Published measurement used as an anchor

Splash reports the exact Q2_0 artifact on an **M5 Pro with 64 GB and a
20-core GPU**:

| Publisher metric | Measured result |
|---|---:|
| Short-prompt decode | 95 tok/s |
| Cold prefill, 32K bucket | 1,312 tok/s |
| Cached first-token latency, 32K replay | 171 ms |

Source: [Splash README performance table](https://github.com/incoai/splash#performance),
also recorded in the [local README](../../README.md#performance).
The README identifies selected SPEED-Bench coding prompts over HTTP. This is
an external reference on a different GPU configuration, build/release and
workload from the local IQ3_XXS probes; it is not a 16-core-mini measurement.
It also does not prove the residency or cache state of a requested deployment.

The 64 GB near-resident estimates are broad extrapolations from that reference,
with allowance for the smaller GPU and workload differences. There is no fitted
16-core scaling factor. The other Q2_0 ranges are planning judgments guided by
smaller streamed weights and possible additional expert reuse, not outputs of a
validated cache-hit or GPU-performance model.

## Why 64 GB could change the operating mode

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

## Interpretation and limits

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
