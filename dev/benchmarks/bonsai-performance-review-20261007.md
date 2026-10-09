# Bonsai option 14 performance experiments, 2026-10-07

No tested candidate demonstrated a safe end-to-end improvement. All runtime
experiments were reverted and the original launcher profile was restored and
verified live. This report is the only retained repository change.

## Workload and machine

Apple M5, eight GPU cores, 16 GiB unified memory. Splash served
`prism-ml/Ternary-Bonsai-2-27B-gguf:PTQ1_0` with its existing DFlash draft,
24,576 server context, INT8 KV, one active request, reasoning none,
temperature zero and an 8 GiB persistent disk cache. The restored build ID is
`src-5a54ebc57301fb80a33e2d009aab28419fbdff023c223b4ac4acdea9ed9bb590`.

The short coding request reviewed a range-merging function: 129 prompt tokens,
256 output tokens, 96 cached prompt tokens. Three baseline and three split-rule
requests were sequential; final restoration was checked with two further runs.

The prefill comparison used record lists with different early benchmark labels
to prevent prefix reuse across settings. Both prompts had 4,909 input tokens,
96 output tokens, and zero cached tokens on their cold requests. Both correctly
recalled ORCHID. Their repeats reused 4,896 tokens.

macOS reported warning memory pressure during the requests. A system-wide
snapshot showed about 5 GiB of swap in use; this does not establish active
Splash paging. Trials were sequential on a fanless Mac without thermal control
or randomized ordering. Small timing differences are indicative.

## Candidates and rejection evidence

| Candidate | Measurement | Decision |
| --- | --- | --- |
| Expand lookup digits into two packed 32-bit words | PTQ1_0 17,408 x 5,120, one lane, staged S1: 0.5121 to 0.5456 ms | Reverted: about 6.5% slower despite exact dequantized weights |
| Larger PTQ1_0 decode split grids | Individual projections improved about 5-17%; coding decode median 21.59 to 18.61 tok/s | Reverted: output changed and draft acceptance fell from 37.96% to 30.69% |
| Copy/sign-flip FP16 scale bits for ternary values | Staged S1: 0.5515 ms; exhaustive finite-scale test found 31,744 mismatching scale cases | Reverted: signed-zero parity failure and no speed benefit |
| Two-step PTQ1_0 weight prefetch | Staged S1: 0.5211 ms | Reverted: no demonstrated improvement over 0.5121 ms baseline |
| Prefill chunks 512 to 1,024 | Cold prefill 199.48 to 196.33 tok/s | Reverted: no speed benefit and 63.16 MiB more fixed prefill workspace |

Projection benchmark values are medians of six DRAM-cold rounds at each
configuration. Register-tile timings remained approximately stable across the
staged-kernel comparisons. Microbenchmark gains alone were insufficient to
justify a change to the actual speculative workload.

## Prefill comparison

| Metric | 512-token chunks | 1,024-token chunks |
| --- | ---: | ---: |
| Cold prefill | 24.61 s | 25.00 s |
| Cold prefill throughput | 199.48 tok/s | 196.33 tok/s |
| Cold total request | 26.69 s | 27.12 s |
| Cached total request | 2.47 s | 2.51 s |
| Shared prefill workspace | 187.45 MiB | 250.61 MiB |

## Validation and final state

The split-rule candidate passed the full native CPU suite and the full GGUF
projection suite with `MTL_SHADER_VALIDATION=1`, including numerical bounds,
split scratch visibility, fused projections, gate/up pairs and embeddings.
The live coding benchmark nevertheless rejected it. The sign-bit candidate's
additional exhaustive scale test rejected that candidate. Rejected tests and
production changes were both removed.

The final server was restarted through `/Users/mymac/startllamacpp.sh --direct 14`
with the original 512-token chunks. Its build ID, 24K context, INT8 KV, healthy
Metal status, and original generated coding text were verified. Final decode
rates were 21.78 and 21.26 tok/s, with the original 37.96% draft acceptance and
zero request failures. The launcher file was not edited; `bash -n` passed.

Raw responses, complete status snapshots, benchmark scripts and validation logs
are saved in `build/validation/performance-review-20261007/` (ignored build
artifacts). Further optimization should begin with a per-dispatch model profile
and multiple representative coding prompts; no overall speedup is claimed here.
