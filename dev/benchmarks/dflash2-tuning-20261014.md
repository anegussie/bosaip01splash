# Bonsai DFlash2 tuning, 2026-10-14

Decision: retain the original draft and kernel policy. Compatibility and
profiling changes are built and validated. Both ABBA comparisons and the
kernel sweeps are complete, with no proven general speedup. A consistent greedy
workload regression rejects the candidate; sampled timing drift also prevents
adoption. All 120 generated workload requests passed their checks.

## Fixed workload contract

Apple M5, 8 GPU cores, 16 GiB unified memory. Actual launcher option 14:
Ternary-Bonsai-2-27B PTQ1_0, Splash Metal, INT8 KV, BF16 state, 512-token
prefill chunks, 24,576-token server limit, one active request, 8 GiB persistent
cache. The comparison uses approximately 4K, 12K and 20K filled prompts,
greedy and temperature-0.7 sampling, 384-token utility output ceilings,
a 768-token review ceiling in the sampled run, and a forced tool-call/result
round trip. Sampled requests use top-p 0.8, top-k 20 and seed 42.
An output ceiling is not necessarily the number of output tokens generated.
Filled context is padded with repeated repository notes. Executable utilities,
code reviews and forced tool calls check behavior; this is not a replay of a
complete OpenCode agent session.

Baseline draft: `incoai/Qwen3.8-27B-DFlash2`, installed revision
`015e795645c74b1a0eeef3b570031fb62e769bc5`. Target revision:
`b072e1d3b35a0a630cece372c2127528e0994386`.

Candidate: `naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2`, pinned revision
`0059b38aa255698b1a87305eb3fbb5a3cfd616e2`. Its downloaded BF16 checkpoint is
3,848,817,904 bytes and has 81 tensors. Configurations match exactly; tensor
types and shapes match after normalizing the two selector-codebook names.
Candidate files and provenance are under
`build/validation/dflash2-tuning-20261014/`.
The installed draft artifact digests are
`67fc76d68dc5a9415511a4f394ef744d67510cd20e93b37cc2cc7d28e4bab65c`
(original) and
`eb141d0fb8621cf7a7c81047b83810fa19b8093543bd05529e9478d9555cb8f1`
(candidate). Thus these are different draft weights paired with the same target.

## Changes

- Draft preparation accepts the canonical codebook name or its `.weight`
  alias, validates its existing BF16 type and shape, and rejects two definitions.
  The original and suffixed fixtures reproduce the same prepared-image goldens.
- `SPLASH_DRAFT_MODEL` supplies the launcher's draft default, allowing the
  existing option-14 wrapper to select a pinned local checkpoint. An explicit
  `--draft-model` wins; invalid environment values are rejected before loading.
- Decode profiling attributes dispatches to draft forward, draft vocabulary,
  selector, target verification, acceptance and draft-context commit. The
  production command shapes and numerical operations are unchanged. These are
  separate-dispatch attributions, not fused per-stage latency measurements.
- `dflash2_tuning.py` runs A/B/B/A through the actual launcher, isolates client
  configuration and caches, checks executable coding outputs and tool calls,
  and records output, acceptance, thermal state, swap, memory pressure and I/O.
  Changed greedy outputs, task regressions, unmatched thermal states, or more than 5%
  within-checkpoint spread prevent selecting a winner.

The target file digest is
`53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`
(5,946,648,928 bytes). The assembled selection identity changes with the draft;
the comparison therefore checks the actual target artifact digest, together
with build identity, rather than treating the assembly identity as the GGUF hash.
Both ABBA runs use build
`src-b8e108596c65114fc2adc3b8f48a52d36f7269d32bd701a095f0bdeacb55afee`.

## Reproduction

The comparison requires exclusive model execution. Normally it refuses to
start while the normal server on port 1235 is online. Alternatively,
`--allow-released-primary` accepts an idle server whose weights are released,
checks it every half-second and terminates only the benchmark process group if
the normal server receives work or restores its weights. This guard's resume
and termination behavior is tested. These runs used this mode.

```sh
.venv/bin/python dev/benchmarks/download_bonsai_draft.py \
  --directory build/validation/dflash2-tuning-20261014 \
  --revision 0059b38aa255698b1a87305eb3fbb5a3cfd616e2

build/engine-tests/decode-profile build/splash.metallib \
  install/models/.selections/531506f85c1ab2c6b161082230f8171157f237e9395a982e56113f2f3d23bbb2 \
  --prompt-tokens 4096 --cycles 5 --max-lanes 1 \
  --kv-format int8 --state-format bf16 --prefill-chunk-tokens 512

.venv/bin/python dev/benchmarks/dflash2_tuning.py \
  --baseline /Users/mymac/.cache/huggingface/hub/models--incoai--Qwen3.8-27B-DFlash2/snapshots/015e795645c74b1a0eeef3b570031fb62e769bc5 \
  --candidate build/validation/dflash2-tuning-20261014/draft \
  --results build/validation/dflash2-tuning-20261014/abba-host \
  --profile-root install/models/.selections/531506f85c1ab2c6b161082230f8171157f237e9395a982e56113f2f3d23bbb2 \
  --allow-released-primary
```

The profiler's synthetic prompt is suitable for attribution, not a coding
throughput verdict. Repeat attribution at 12,288 and 20,480 prompt tokens.
The A/B comparison supplies behavioral and actual-launcher measurements.
For the sampled comparison, use a fresh results directory, omit
`--profile-root`, and add `--temperature 0.7
--tasks chunked,merge_intervals,stable_unique,review_intervals`.

## Validation

Full Python discovery: 1,298 total tests, 1,291 passed and 7 skipped.
The final benchmark guard suite has 12 passing tests.
Full native CPU and Metal suites passed; final CPU and instrumented-backend
checks passed after making profiler labels allocation-free enums.
Ruff lint/format, architecture checks and build identity verification passed.
Logs are under `build/validation/dflash2-tuning-20261014/`.

## Measurements

| Filled prompt | Fused cycle median | Target verification attribution |
| --- | ---: | ---: |
| 4,096 | 175.22 ms | 89.9% |
| 12,288 | 240.73 ms | 90.2% |
| 20,480 | 265.04 ms | 90.2% |

At 4K, the remaining separate-dispatch attribution is 5.6% draft forward,
3.8% draft vocabulary, 0.1% selector and 0.6% context commit.
The fused and attributed runs use different decode cycles and can have
different clock/thermal conditions; their absolute times are not comparable
as a dispatch-overhead measurement or a performance-change verdict.

Greedy ABBA: all 52 requests passed, including 48 executable coding checks and
one forced tool call per phase. The later sampled run adds the tool-result
round trip. Coding outputs were identical across checkpoints. The geometric
aggregate decode cost is
37.80 ms/token for the original and 38.08 ms/token for the candidate, with
5.66% within-checkpoint spread. This aggregate is inconclusive.

The 4K chunking case is a clear regression: decode cost rises from
22.64 to 25.77 ms/token (13.8%), acceptance falls from 93.9% to 80.4%, and the
cached request increases from 1.492 to 1.651 seconds (10.7%). Its decode spread
is only 1.1%. Other cases improve, but they do not justify making this checkpoint
the general default. The original raw run predates the artifact-digest field;
`greedy-run-with-artifacts.json` records the subsequently checked target
artifact digest for reanalysis with the final comparator.

Two 31-round PTQ1_0 gate/up sweeps reject the single-pass alternatives. At one
lane the staged baseline is 1.025/1.041 ms; single-pass spread is 1.205/1.240 ms
and single-pass plain is 1.226/1.252 ms, approximately 18-20% slower. Existing
staged split-2 is approximately 4% faster in isolation, but changes reduction
order and has no matched end-to-end acceptance/latency validation. No kernel
policy was changed.

Sampled ABBA at temperature 0.7: all 68 requests passed, including 60 coding
checks and four complete forced tool/result round trips. The review checks
require both the requested issue descriptions and an executable corrected
function. Text can differ between sampled runs; behavior is checked separately.
Aggregate decode cost is 43.60 ms/token for the original and 43.81 ms/token for
the candidate, with 10.17% within-checkpoint spread. This is inconclusive and
fails the adoption criteria. Several individual cases have 8-24% decode spread;
the apparent 4K stable-ordering improvement also has unmatched thermal states.
These observations do not establish a checkpoint speed improvement.

Raw artifacts: `abba-host/`, `greedy-summary.json`, `abba-sampled/`, and
`kernel-sweep/`, all under `build/validation/dflash2-tuning-20261014/`.
Sampled rows report warning memory pressure and healthy Metal; system swap
was already in use before model execution (3,915.50 MiB at the first phase's
start, 3,890.38 MiB at the last phase's end, reaching 4,128.56 MiB at a phase
boundary). System swap figures do not isolate this process's paging. These runs do
not establish a zero-swap profile. Thermal transitions and timing spread remain
part of the adoption decision.

## Operational state

The benchmark server on port 1236 stopped after each phase and has no listener
after the final run. The normal option-14 server on port 1235 remains ready,
weight-released and Metal-healthy: 443 submitted, 441 completed, 2 cancelled and
zero failed requests. The launcher script and global OpenCode configuration
were not edited. The normal server still runs its existing
`src-72b36c8b19251b1d90f22e4355358e3885c5241cb5201728bbcafd120b94dc32`
process; the new build was validated through actual option 14 on the isolated
port and will be used on a subsequent normal launch. No forced restart occurred.

## Follow-up decisions

Shorter/adaptive verification and prompt lookup require runtime changes.
Splash currently executes eight draft and eight target rows per cycle; lowering
an output cap only changes the commit count. Adding a nominal 3/5/7 setting
without changing the graph would not establish a compute saving. Neither a
nominal depth knob nor prompt lookup was added. Further optimization should
target the measured PTQ1_0 verification bottleneck, with actual row/graph
changes if testing adaptive depth. Retain a future change only after matched
correctness, admission, acceptance, decode and full-request latency checks.
