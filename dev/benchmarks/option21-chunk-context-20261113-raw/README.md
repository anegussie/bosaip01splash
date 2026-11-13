# Option 21 chunk/context experiment — 2026-11-13

The [consolidated report](../option21-chunk-context-20261113.md) contains the
performance table, ranges, request latency, validity counts and workflow model.

The final observations are in `clean-run/results.json`: 32 timed trials,
31 semantic passes and one failed 32K cold generation with 2,048-token chunks.
Failed responses are retained and excluded from throughput aggregates.
`clean-run/verification.json` records the final checks and source hashes.

The initial attempt at this directory's root failed its cold-prefix gate:
the 32K prompt reused 4K of the previous prompt. Those observations are excluded.
See `FAILURE.md`. The corrected experiment gives each context an early distinct
salt and adds a cross-context cold smoke gate for both chunk sizes.

Within `clean-run`, the failed short B1 warmup and failed timed A2 generation
remain in their original directories. `contract.json` describes the interruptions,
shorter warmup instruction and resumed final control. The one-token 32K cache
preload is untimed and is not a replacement successful cold observation.

Each arm includes readiness and command records, server logs, full before/after
status, system swap snapshots, individual request metrics and a two-second
thermal/memory/expert monitor. The workload is synthetic secret recall/counting;
short executable Python is a smoke gate, not a long-context coding benchmark.

## Build identity and reproduction

The tag identifies the launcher profile and saved experiment, not a compiled
engine release. The runtime was an existing frozen build in a dirty checkout;
its reported build ID, target/layout identities and executable/Metal-library
SHA-256 hashes are recorded. Unrelated engine work is not part of this commit.

The frozen binary and two Metal libraries remain locally under
`build/validation/option21-chunk-context-20261113-clean/binaries/`, outside Git.
Model weights and private temporary prefix caches are not published.
The run used Q2_0 with the local BF16 DFlash2 draft and the recorded GGUF layout.
Do not substitute another build or model and describe it as the same experiment.

`run.py`, `resume.py`, and `finish.py` preserve the actual sequence using the
existing `dev/benchmarks/option20_serving_matrix.py` probes. They are historical
runners, not overwrite/resume commands for new work. To repeat the experiment,
use a new output/work directory, inspect the current model/build and idle service,
and preserve a fresh restoration command. Do not rerun these scripts in place.
`summarize.py` safely regenerates the report from saved observations without inference.

`restore_logging.py` restores the captured server command directly, avoiding the
source launcher's automatic rebuild. Normal log paths, JSONL telemetry, monitor
and final process identity are in `clean-run/normal-logging-restored.json`.

## Publication checks

The scoped launcher and regression-test content passed 12 focused option 21
mock-server tests; see `launcher-publication-tests.log`. Shell syntax and staged
whitespace checks passed. These checks do not rerun model inference.
