# PTQ1_0 decode lookup on the 16 GiB M5

Measured 2026-10-05 on the existing option-14 profile: Ternary Bonsai 2 27B
PTQ1_0 with the installed Qwen3.8-27B DFlash2 draft, Apple M5 with eight GPU
cores, macOS 26.5.2, INT8 KV, 24,576 server context, 512-token prefill chunks,
one active request, and the existing 8 GiB persistent prefix cache.

## Implementation

A 512-byte constant table maps each packed byte to five ternary digits.
`FmtPTQ10Lookup` uses this table in the stages owned by one SIMD group, replacing
repeated integer division. These stages serve decode tiles and prefill chunks
of up to 32 rows. The seven-byte prepared group layout, quantization, scale
arithmetic, model weights, scratch allocation, and sampling policy are retained.
The shared 128-row prefill stage and scalar embedding decoder retain the
original integer decoder.

Applying the lookup to the shared prefill stage failed numerical bounds on
Apple10, despite exact standalone dequantization. That broader candidate was
rejected before serving it. The final path selection passed the complete
projection suite, including both staging paths, mixed formats, residual and
gate epilogues, FP32 logits, batches 1-4, and split/reused scratch checks.

## Matched live measurements

The code-review task used the same 3,715-token prompt, 384-token output budget,
temperature 0.7, top_p 0.8, top_k 20, seed 42, and two requests per build.
Every output was identical between builds; each sample drafted 840 tokens and
accepted 264 (31.4%). Comparing response-specific decode time isolates the
decoder from cold prefill, frontend queueing, and weight restoration.

| Workload | Baseline decode tok/s | Candidate decode tok/s | Change |
| --- | ---: | ---: | ---: |
| Code review, weighted two-sample rate | 14.31 | 16.71 | +16.83% |
| Merge intervals, sampled functions | 33.86 | 43.35 | +28.05% |
| Stable uniqueness, sampled functions | 23.39 | 30.90 | +32.11% |
| List chunking, sampled functions | 24.65 | 32.19 | +30.58% |

All twelve generated function outputs, including temperature-zero comparisons,
were identical to baseline and passed execution-based correctness tests. The
function measurements use response-specific timings because other client
requests overlapped the earliest baseline samples; their aggregate draft-counter
windows are marked as non-isolated. Temperature-zero results did not justify
changing the existing sampling defaults.

Reported allocated and peak Metal buffers for the matched review were identical
between builds: 8,730,373,184 allocated bytes and 8,791,900,160 peak bytes. This
comparison does not measure process RSS or guarantee no system swap.

The production one-lane PTQ1_0 gate/up kernel on a 17,408 x 5,120 projection
fell from 1.3115 to 1.0395 ms in the cold-weight-ring benchmark: 20.7% less
time. Each phase measured medians of seven rounds across a 384 MiB weight ring.
The library variants were measured sequentially; this microbenchmark does not
replace the live comparisons.

Baseline build:
`src-c7953fb2d3a3a5096c53fa6d3f9861537d70bd5fb1ea2e9e1f4059e6aac36227`.
Candidate build:
`src-20656440f49058922d7b4c8541c370702efcf868aacb095a51b8cc3061b08cb2`.

## Validation and limits

- Exhaustive table test: all 256 bytes and 1,280 digit values match the integer
  decoder, including the complete byte domain.
- GPU dequantization: both PTQ1_0 decoders exactly matched 262,144 FP16 reference
  values; every other supported GGUF format passed too.
- Full GPU projection numerical suite with shader validation: passed.
- Full native CPU suite, architecture, source/build identity, and whitespace:
  passed.
- Actual option-14 streaming and non-streaming tools, thinking-option validation,
  prefix reuse, and 4,892-token counting request: passed.
- Fresh 12,264-token prompt plus 96 output tokens, zero cached input: correct
  final code; 186.47 prefill tok/s and 42.03 decode tok/s. This repetitive workload
  is distinct from coding throughput.
- All 20 final-build native requests completed without failure; Metal remained
  healthy. Memory pressure remained present.

These are small synthetic workloads and two samples per build/mode, without
randomized order or thermal control. They establish a useful measured gain and
unchanged tested outputs, not a universal throughput guarantee or new context
capacity. Draft acceptance remains workload-dependent.

Summary data: [bonsai-ptq-decode.json](bonsai-ptq-decode.json). Full response and
status captures are under `build/validation/bonsai-{review,coding-policy}-*.json`
and `build/validation/option14-ptq-*.json`.

With option 14 running, reproduce the code-review workload with:

```sh
.venv/bin/python dev/benchmarks/bonsai_coding.py \
  --tasks review_intervals --order 0.7,0.7 --results /private/tmp/bonsai-review.json
```
