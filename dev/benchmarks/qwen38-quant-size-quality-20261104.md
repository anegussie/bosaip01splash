# Qwen3.8 quantization size and quality comparison - November 4, 2026

This records the size and quality comparisons following the
[expert-cache estimate review](qwen38-option20-cache-estimates-20261104.md).
Sizes were checked against Hugging Face file metadata. Quality scores below
are publisher-reported results, not local evaluations. No model weights were
downloaded or loaded, and no tests, inference, builds, or restarts were run.

## Flash-Next download sizes

Both variants are from `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF`.
IQ3_XXS is the option 20 artifact used by the local performance reports.
The first shard contains transformer weights, including routed experts; it is
not a measurement of expert weights alone. The second shard contains the
per-layer n-gram embedding table, also called the PLE table.

| Component | IQ3_XXS | Q2_0 | Reduction from IQ3_XXS |
|---|---:|---:|---:|
| Transformer-weight shard | 47.04 GB | 37.62 GB | 20.0% |
| PLE / n-gram shard | 28.80 GB | 28.80 GB | None |
| Total model download | 75.84 GB | 66.42 GB | 12.4% |
| Total in binary units | 70.63 GiB | 61.86 GiB | 8.77 GiB |
| Average transformer bits per weight | 3.00 | 2.40 | 20.0% |

Exact totals are 75,839,998,528 bytes for IQ3_XXS and 66,423,878,624 bytes
for Q2_0, a saving of 9,416,119,904 bytes (9.416 GB / 8.769 GiB).
The n-gram shards are byte-identical by their LFS SHA-256:
`316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113`.

Sources: [IQ3_XXS files](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/main/IQ3_XXS),
[Q2_0 files](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/main/Q2_0),
and the [publisher's model card](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF#memory-requirements).
The companion JSON preserves the metadata entries and exact size arithmetic.

The 20% transformer-shard reduction is more relevant to expert-storage sizing
than the 12.4% whole-download reduction, but it is still an aggregate over both
expert and non-expert tensors. It does not establish the reduction for each
expert format, the number of cache slots, or a throughput multiplier.

With the n-gram table streamed separately, Q2_0's transformer shard is
35.04 GiB on disk versus 43.81 GiB for IQ3_XXS. This could improve residency on
a 64 GB Mac. Repacked weights, the draft, KV, workspace, and caches still need
memory; file size does not prove resident fit. Sizes above exclude the DFlash2
draft and optional vision projector. Splash can stream routed experts as well
as the n-gram table, so the publisher's first-shard residency guidance for its
llama.cpp configuration is not a mandatory Splash allocation.

## Quality, including the requested 27B quant

The exact additional artifact requested is
`unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M`. Scores for that exact quant on the three
benchmarks below were not found in the inspected Unsloth model card and
Dynamic 3.0 documentation. Missing scores are recorded as null, not estimated.

| Benchmark | Flash-Next GSQ-RCO IQ3_XXS | Flash-Next GSQ-RCO Q2_0 | 27B Unsloth UD-Q4_K_M | Original Qwen3.8-27B, reference only |
|---|---:|---:|---|---:|
| Coding: LiveCodeBench v6 | 86.29 | 81.14 | Not found | 90.3 |
| Scientific reasoning: GPQA Diamond | 91.41 | 89.39 | Not found | 89.2 |
| Competition mathematics: AIME25 | 100.00 | 96.67 | Not found | Not found |
| Average of these three | 92.57 | 89.07 | Not available | Not available |

Flash-Next source: [ISTA's quantization evaluation](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF#results).
Original 27B reference source: [Qwen's model card](https://huggingface.co/Qwen/Qwen3.8-27B#evaluation-results).
The exact quant was checked through the
[Unsloth model card](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) and
[Dynamic 3.0 documentation](https://unsloth.ai/docs/basics/dynamic-3.0-ggufs).
This is a bounded source search, not a claim that no evaluation exists anywhere.

Within ISTA's reported evaluation, Q2_0 loses 5.15 percentage points on
LiveCodeBench v6, 2.02 on GPQA Diamond, 3.33 on AIME25, and 3.50 on the
three-task average relative to IQ3_XXS. The coding score reduction is about
6.0% relative to IQ3_XXS. This is a benchmark-score change, not a percentage
loss of general intelligence or a predicted failure rate in a user's codebase.

The original 27B's 90.3 coding score is not a score for the Unsloth quant.
Qwen and ISTA also use separate evaluation setups, so the reference column
does not establish a controlled ranking against the Flash-Next quants.
No missing quant score is filled by subtracting an assumed quantization loss,
and no three-task average is computed from the two available original-27B scores.

For difficult coding, the within-model evidence favors IQ3_XXS over Q2_0.
For memory-constrained deployment, Q2_0 trades smaller transformer weights
for lower reported quality. These results do not establish long-context agent
reliability, tool-use quality, or the exact UD-Q4_K_M ranking.

## Evidence and validation

[The companion JSON](qwen38-quant-size-quality-20261104.json) contains file
sizes and LFS identifiers, source URLs, reported scores, missing-value labels,
and the size/quality differences. Sources were checked November 4, 2026;
the URLs track mutable main/model-card pages, while file LFS identifiers pin
the size evidence to specific content.

Validation was limited to static JSON, arithmetic, recorded-metadata agreement,
Markdown link/path checks, and Git diff checks. No new runtime measurements
are claimed.
