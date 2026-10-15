# PTQ1_0 decode optimization, 2026-10-15

The selected decoder reduces measured GPU time by **2.35% for gate/up** and
**2.85% for down** on the base M5's single-lane production policy. Every
timed projection produces the baseline's output bits. Retain this small local
kernel improvement. The actual option-14 comparison passes correctness but
does **not** establish an overall request speedup.

## Implementation

`dequant32<FmtPTQ10Lookup>` looks up each packed byte once and selects among
the three scaled ternary values. It preserves finite half scales, their
subnormals, and the sign of zero. Non-finite scales times zero produce NaN.
Accumulation order, splitting policy, model weights and tensor layouts are
unchanged. The 128-row prefill tile retains its integer decoder.

The reference test now also checks positive and negative zero, the smallest
subnormals, the largest subnormals, the smallest normal scales, unit scales,
and the largest finite half scales, with both signs. This caught an early
candidate's fast-math folding of `0 * negative_scale` to positive zero; the
selected implementation preserves the sign explicitly.

## Projection comparison

Apple M5, 8 GPU cores, 16 GiB unified memory. Eight target verification rows
in one lane. PTQ1_0 weights, BF16 inputs/outputs, existing staged S1 policy.
Gate/up is the complete two-pass pair; down includes the residual epilogue.

| Projection | Baseline GPU ms | Selected GPU ms | Time reduction | ABBA spread |
| --- | ---: | ---: | ---: | ---: |
| Gate/up, 17,408 x 5,120 | 2.490588 | 2.432102 | 2.35% | 0.46% |
| Down, 5,120 x 17,408 | 1.294223 | 1.257389 | 2.85% | 0.03% |

Baseline: checkout `567c9130b519daf0465e292df75813acb0efa67f`, native build
`src-b8e108596c65114fc2adc3b8f48a52d36f7269d32bd701a095f0bdeacb55afee`.
Selected build:
`src-c988c87eac16f999a9e5b5df5f0823c8671a3ce7eb6bc32f79090735cd6a8737`.

The comparison uses the existing projection benchmark's random weights,
inputs and ring of 20 weight copies (about 418 MB per backend). Each backend
owns identical buffers. Each of 101 rounds executes baseline, selected,
selected, baseline back to back, checks the output bits after every command,
and records GPU time per projection. The table compares the four phase
medians with `dev/benchmarks/abba.py`. Separate-process sweeps had severe
clock drift and were excluded from the selected measurements.

The byte-lookup-only, wider-store and integer-bit alternatives did not improve
on the selected implementation. A fallback branch also erased its gain.
Those alternatives are retained only as raw experiment logs.

## Actual launcher contract

`bash /Users/mymac/startllamacpp.sh --direct 14`, with an isolated binary
wrapper, port 1236, client configuration and per-phase caches. The wrapper
changes only `install.paths.BINARY`, allowing the actual launcher and server
to execute immutable baseline and selected binary/library pairs. A guard
stops the benchmark if the normal server on port 1235 starts work.

Ternary-Bonsai-2-27B PTQ1_0, target revision
`b072e1d3b35a0a630cece372c2127528e0994386`, target artifact SHA-256
`53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`
(5,946,648,928 bytes). Original Qwen3.8-27B DFlash2 revision
`015e795645c74b1a0eeef3b570031fb62e769bc5`; speculation remains enabled.
Splash Metal, INT8 KV, BF16 recurrent state, 512-token prefill chunks,
24,576-token configured limit, one active request, requested 8 GiB persistent
cache. Effective disk limits are recorded separately in status snapshots.

ABBA uses fresh servers at approximately 4K and 12K filled prompts, greedy
sampling, seed 42, reasoning none, three executable Python utility tasks,
a repeated cached request per depth, and a forced tool-call/result round trip.
The output ceiling is 384 tokens for utilities and 128 for tool requests;
actual outputs can be shorter. Prefixes contain repeated repository notes,
not a complete replay of an OpenCode session.

All **40/40 requests pass**: 32 executable coding checks and eight requests
covering four complete forced tool-call/result round trips. Every matched
coding response and draft-acceptance rate is identical across all four phases.
Every phase reports 10 completed requests, zero failures/cancellations and
healthy Metal.

The geometric aggregate decode-cycle cost is 37.8495 ms/token for baseline
and 36.7323 ms/token for selected, an observed 2.95% reduction. Within-build
aggregate spread is 4.30%, larger than the observed change; this is not an
established speedup. Individual decode spread reaches 11.80%, and request
latency spread reaches 11.27%, exceeding the 5% comparison limit. The
regression checker reporting aggregate `pass` means its regression bound was
not exceeded; it does not select a speed winner.

All four phases begin nominal. The 4K interval-merging request transitions
nominal to fair, and subsequent work runs fair, with matched reported thermal
sequences across builds. Memory pressure is warning throughout. System-wide
swap is already 2,315.31 MiB before phase 1, reaches 3,156.75 MiB at that
phase's end, and is 2,812.75 MiB after phase 4. These figures do not attribute
paging to Splash or establish a zero-swap profile.

Repeated 4K and 12K chunking requests reuse 4,000 and 12,192 prompt tokens,
respectively. Requested disk quota is 8 GiB; effective limits at the measured
phase starts are approximately 6.28, 5.61, 5.28 and 4.96 GiB. Cached requests
save prefill; their latency is not evidence of faster uncached computation.

## Validation and artifacts

- Production-flags dequantization: all formats pass bitwise reference checks;
  both PTQ1_0 decoders pass the additional boundary-scale checks.
- Shader-validated full projection suite: all 44 formats pass, including
  one to four lanes, all split counts, fused projections, epilogues, prefill,
  split-scratch reuse, embedding and buffer extents.
- Shader-validated rotation suite passes, including rotated PTQ1_0 embedding.
- Architecture checks, build identity verification and `git diff --check` pass.

Raw logs, saved baseline/selected builds, the interleaved C++ benchmark,
the actual-launcher runner, responses and status snapshots are under
`build/validation/ptq10-performance-20261015/`. The first projection invocation
used the production library and stopped at the test-only copy kernel; it was
rerun successfully with `production-and-test.metallib`. Intermediate timing
results and rejected candidates do not enter the final table.

All temporary servers stopped, and port 1236 has no listener. Cleanup removed
5,642,158,080 allocated bytes (5.25 GiB) from only the four caches created by
this comparison. Saved builds, runners, logs, responses and status snapshots
remain. The machine-readable result is
[ptq10-performance-20261015.json](ptq10-performance-20261015.json).
