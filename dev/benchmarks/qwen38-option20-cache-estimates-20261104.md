# Flash-Next expert-cache estimates reviewed against the November 4 logs

Historical estimates: superseded by the
[conservative November 5 six-Mac estimates](qwen38-option20-mac-conservative-20261105.md).
The original dated analysis below is retained for traceability.

These are conditional planning estimates for larger Macs, not measurements of
those machines. They supersede the cross-machine estimates in
[the November 3 report](qwen38-option20-machine-scaling-20261103.md). No tests,
inference requests, live server queries, restarts, or builds were performed for
this review. Only existing logs, saved status snapshots, published results,
launcher settings, and source were inspected.

For the Q2_0 versus IQ3_XXS file sizes and quality scores, including the
requested Unsloth 27B quant and its missing exact-quant results, see the
[size and quality comparison](qwen38-quant-size-quality-20261104.md).

## Measured basis

Source: [chosen-configuration report](qwen38-option20-live-chosen-20261104.md)
and [published measurement package](qwen38-option20-live-chosen-20261104.json).
The review recalculated traffic for 20 clean matrix rows from their saved
before/after counters; the source report also contains two smoke rows.

The measured host is an M5 MacBook Air with **8 GPU cores and 16 GiB RAM**.
The live engine was `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`.
The workload was `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`
with DFlash2, INT8 KV, BF16 state, 131,072 served context, 1,024-token prefill
chunks, a 10 GiB engine cap, and a 16 GiB persistent prefix-cache quota. Two
request lanes were configured; the serial results below exclude observed
foreign requests.

| Actual prompt tokens | Clean cold trials | Mean prefill, tok/s | Mean cold first-content latency, s | Mean predictable decode, tok/s |
|---:|---:|---:|---:|---:|
| 4,019 | 3 | 203.93 | 19.713 | 12.58 |
| 28,589 | 3 | 168.69 | 169.601 | 11.84 |
| 65,367 | 1 | 149.40 | 437.618 | 11.18 |

The short code probe with low reasoning produced 8.76 decode tok/s. Two
medium-reasoning probes produced 7.11 and 7.73 tok/s. These style probes had
39-61 prompt tokens and length-limited outputs; they do not measure completed
coding tasks or long-context coding throughput. Decode counts include reasoning
tokens, not just visible answers.

Measured expert reads were approximately 495-518 decimal MB per predictable
output token, 679 MB per code-probe token, and 776-803 MB per medium-reasoning
token. Read bytes divided by model decode wall time imply roughly 5.7-6.2 GB/s
for these cases. That ratio is an effective workload rate, not an independent
SSD benchmark or proof that every millisecond was storage time.

The expert store remained at 2,089,468,688 bytes (1.946 GiB), with 512 slots,
a 1.233 GiB arena, and 0.713 GiB of staging. Every reviewed row had zero routed
expert-cache hits. Startup reported one shared arena: switching expert formats
evicts the previous format's cached experts. A larger store could remove this
restriction, so its benefit need not scale smoothly from the small-store case.

Thermal state was nominal/fair, memory pressure normal/warning, and recorded
swap usage was about 436 MiB before and after the matrix. The 65K group has one
cold trial. Filled-131K inference was not measured.

## Conditional side-by-side estimates

Assume the same model, draft, KV/state formats, and prefill chunk size, one busy
request, a warmed expert cache, and internal SSD throughput comparable to the
measured Air. The larger Macs require raised engine budgets; the launcher's
default 10 GiB cap does not provide the expert stores assumed here. Store sizes
include their staging and tables and remain subject to the actual memory plan.
The M5 Pro columns both refer to the 16-core GPU configuration.

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

All upgrade columns have low confidence. Cache capacity does not establish the
fraction of traffic avoided. These are conservative scenarios, not guaranteed
lower or upper bounds. Poor reuse could leave throughput near the measured
baseline; a concentrated hot expert set could produce much larger gains.

The decode scenarios use `baseline tok/s / (1 - avoided read fraction)`, rounded
to planning ranges. They hold output shape, draft acceptance, and effective SSD
rate fixed and omit residual compute and staging costs; they are approximate
storage-bound ceilings for each assumed fraction. They do not establish the
probability of achieving that fraction on any machine.

Prefill ranges are weaker planning judgments rather than fitted predictions:
the measured 28.6K and 65.4K baselines are separate, batch routing already shares
expert reads, and neither larger-cache prefill reuse nor a GPU scaling factor
has been measured. The decode hit fractions are not applied directly to
prefill. Estimated first-token ranges are rounded prompt-token/rate arithmetic
without queueing or startup, not measured SSE distributions.

[Apple's Mac mini specifications](https://www.apple.com/ca/mac-mini/specs/),
checked November 4, list 170 GB/s memory bandwidth for M6 with 32 GB and
307 GB/s for the 16-core-GPU M5 Pro, with 48/64 GB configurations. Higher GPU
memory bandwidth does not imply a proportional expert-streaming speedup. No
separate M6 decode uplift is assigned without workload evidence.

## Sensitivity to expert reuse

This is arithmetic for a hypothetical 12 tok/s baseline, not a forecast for
any particular machine:

| Expert SSD traffic avoided | Ideal speedup while SSD-bound | Illustrative generation, tok/s |
|---|---:|---:|
| 0% | 1.00x | 12 |
| 20% | 1.25x | 15 |
| 40% | 1.67x | 20 |
| 50% | 2.00x | 24 |
| 75% | 4.00x | 48 |

GPU computation, staging, PLE reads, attention, and KV work eventually limit
these gains. A cache that retains the repeatedly selected experts could produce
a substantial improvement; the existing zero-hit measurements cannot tell us
how often a larger cache will do so.

## Corrections to earlier estimates

- Do not use 452 MB per generated token for every output style. The latest
  code and reasoning probes read substantially more per token and accept fewer
  draft tokens per cycle than the predictable-output probes.
- Do not treat a chosen cache size as a measured hit rate, or the assumed
  45-60% avoided traffic previously used for 64 GB as an established result.
- Do not scale the entire small-store budget linearly per slot. Staging is a
  fixed component, as the expert-store implementation accounts for explicitly.
- Do not assume macOS file caching accelerates streamed expert reads:
  [WeightSource](../../runtime/model/WeightSource.cpp) opens sources with
  `F_NOCACHE`. The effective runtime expert store is the relevant cache here.
- Do not double aggregate generation merely because two requests are admitted.
  Both share resources; the chosen-profile concurrency probe serialized them.
- Prefix-cache reuse and expert-cache reuse are separate. Immediate prefix
  reuse reduced first-content latency to 1.15 s at 28.6K and 2.11 s at 65.4K;
  it did not eliminate decode expert reads.

[The companion JSON](qwen38-option20-cache-estimates-20261104.json) records
per-row counter differences, model/build identity, source package checksum,
the decode scenario arithmetic, and the estimate table. Validation was limited
to static content, arithmetic, JSON, and link/path checks. No new performance
measurements are claimed.
