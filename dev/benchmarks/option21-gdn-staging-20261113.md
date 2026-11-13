# Option 21 GDN staging optimization — 2026-11-13

The GDN prefill scan now stages its already-BF16 Q/K/V inputs in BF16
threadgroup memory and widens them at the FP32 recurrence. Gates, accumulation,
and the recurrence stay FP32; configured recurrent-state storage is unchanged.
Threadgroup arrays shrink from 17,536 to 8,832 bytes per group. No context,
chunk, quantization, cache, or launcher defaults change in this kernel work.

## Performance summary

Measured on Apple M5, option 21 Q2_0 with BF16 DFlash2, an 8K content prompt,
128 output tokens, and a 102,400-token server limit. Serving values are means
of two runs per version; the kernel value is a warmed scan-only median.

| Performance | Original | Optimized |
| --- | ---: | ---: |
| Prompt processing | 424.97 tok/s | 429.59 tok/s (+1.09%) |
| First token, uncached | 19.305 s | 19.097 s |
| Decode, uncached | 22.29 tok/s | 22.29 tok/s |
| Total request time, uncached | 25.003 s | 24.794 s |
| First token, cached | 0.815 s | 0.850 s |
| Decode, cached | 24.55 tok/s | 24.61 tok/s |
| GDN scan, 2048 rows | 7.990 ms | 7.051 ms (11.7% less time) |

The serving gain is modest; cached latency shows no gain. All correctness
checks pass. No new system Swapouts or KV demotions occur at the tested 8K
fill. The optimized kernel is validated in isolation and is not deployed;
the original 100K production server remains active.

## Correctness and focused timing

The baseline and candidate are isolated under
`build/validation/option21-gdn-staging-20261113/`. Their executables and host-step
libraries match; only their main Metal libraries differ. The baseline was built
before editing GDN, from the existing dirty worktree. It is a control for this
change, not a reconstruction of the older running production build. SHA-256
manifests and commands are retained in the raw directory.

Both libraries pass the existing GDN CPU-reference suite, including captured
states and split-prefill checks. Cross-library comparisons are byte-identical
for convolution state, recurrent state, recurrent rows, and hidden output in
112 cases: four model-family shapes, BF16/FP32 normalization weights,
BF16/FP32 recurrent-state storage, and 1/15/16/17/37/1000/2048 rows.

Three warmed ABBA rounds yield these median scan-only GPU times on Apple M5
for the Flash-Next shape (packed width 16,512), with BF16 recurrent-state
storage and BF16 normalization weights:

| Rows | Baseline ms | Candidate ms | Time reduction |
| --- | ---: | ---: | ---: |
| 1000 | 3.9078 | 3.4390 | 12.0% |
| 2048 | 7.9897 | 7.0513 | 11.7% |

Across all timed shape/state combinations, median scan time decreases
10.1–12.5%. These are kernel timings, not whole-model throughput gains.
The cross-library run and model profile cause no increase in system Swapouts;
existing swap usage stays at 749.81 MiB. This does not establish full-context
residency or change the existing 100K spill limits.

## Benchmark corrections and model profile

`attention-sweep` now defaults to 1,024 selected four-token blocks, matching
this checkpoint's `top_k=4096`. `--qsa-top-blocks` supports explicit alternate
profiles, and its CLI validation passes. The indexer/attention path passes
at 8,192, 32,768, and 102,400 history tokens with this selection count.

`gguf-moe-benchmark flash-next` now defaults to Q2_0 routed gate/up/down
weights. Shared gate/up/down formats can be selected independently. Q2_0 and
an actual mixed shared-format combination both pass smoke runs. The checkpoint
has 36 distinct shared-format triples across 48 layers, so one synthetic
combination cannot stand in for the complete model. See the saved metadata
manifest and the actual-model profile.

The baseline actual-model profile uses 8,192 prompt tokens, 2,048-token chunks,
INT8 KV, BF16 recurrent state, a 2 GiB expert budget, and one lane. Fused prefill
GPU time is 21,004 ms. Separately submitted dispatches attribute 6.3% to GDN
scan, 18.4% to expert-load kernels, 24.9% to the three main routed MoE matrix
pipelines, and 8.7% to sparse attention. These percentages are diagnostic
replay attribution, not serving wall-time fractions. The profiler's expert
budget differs from the production memory planner.

The indexer score/select work is small in this 8K profile. A global indexer or
MoE K-step change is not included: it needs separate mixed-format correctness,
occupancy, and serving measurements.

## Serving validation and scope

Serving evidence is retained alongside the GPU evidence. The first serving
smoke stops on the unchanged baseline: it replies only `ORCHID`, failing the
ordered-counting requirement. This is not a candidate failure. The retry uses
an explicit sequence-copy task and retains the strict output gate.
Both versions then pass cold and reused requests, executable Python output,
and persistent-cache restoration after restart at the 102,400-token server
setting. The smoke prompt has 2,048 content tokens; it does not fill 100K.
The first timed warmup used a 64-token output cap, which truncated the correct
sequence before the gate's required 20 integers. That attempt stopped and
restored production before either arm was timed. The timed retry uses the
validated 96-token warmup cap and reuses the passing smoke evidence.

The completed serving ABBA uses two measurements per version for each request
mode, 8,192 content tokens (8,204 with the chat template), 128 output tokens,
temperature 1.0/top-p 0.95, and separate temporary persistent caches. Cold
means zero reused prefix with warmed weights/filesystem, not a cold SSD boot.
The production 10.8 GiB memory cap, INT8 KV, BF16 state, single-request limit,
and 2,048-token chunk size are preserved. Requests start at nominal thermals;
some finish at fair. Memory pressure reduces both versions' expert cache.

| Run | Cold PP tok/s | Cold TTFT s | Cold decode tok/s | Reuse TTFT s | Reuse decode tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 baseline | 426.54 | 19.233 | 22.29 | 0.820 | 24.53 |
| B1 candidate | 431.42 | 19.015 | 22.31 | 0.860 | 24.56 |
| B2 candidate | 427.76 | 19.178 | 22.27 | 0.840 | 24.66 |
| A2 baseline | 423.40 | 19.376 | 22.29 | 0.810 | 24.57 |
| Baseline mean | 424.97 | 19.305 | 22.29 | 0.815 | 24.55 |
| Candidate mean | 429.59 | 19.097 | 22.29 | 0.850 | 24.61 |

Observed cold PP increases **1.09%** and cold TTFT decreases **1.08%**.
Decode is effectively unchanged; reused requests show no latency gain.
Two measurements per version support a modest local result, not a broad
speedup claim across workloads or filled context sizes. All eight timed
requests pass the strict semantic/contention gates. Reused requests recover
8,192 tokens. All twelve warmup/timed requests have zero new system Swapouts;
the eight timed requests have zero KV demotions. Neither version fills 100K
in this test, so these results make no full-context SSD-spill claim.

The original production service is restored in a `finally` block after every
validation attempt, with its captured executable, model, 102,400-token context,
2,048-token chunks, identity, persistent cache, and logging. This source change
has not been installed over that production binary.

Raw evidence: [option21-gdn-staging-20261113-raw](option21-gdn-staging-20261113-raw/).
