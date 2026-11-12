# Option 21 experimental read-ahead evidence

See the [performance report](../qwen38-option21-readahead-performance-20261112.md)
for the workload, results and decision to retain the original production engine.
The new read-ahead prototype was removed from the working runtime source after
its A/B/B/A comparison showed no consistent improvement. Its source snapshot
and build/cache identities remain here for review.

Versioned evidence includes request bodies and responses, timings, sampled
status, startup/final status, system snapshots, logs, source snapshots and SHA256
manifests. Executables, Metal libraries, prepared model-weight cache payloads
and Python bytecode remain local and are excluded from Git. No source model
weights are part of this publication.

`run.py` records the real serving experiment. It requires the local model
assembly, archived binaries, prepared cache and cache-enabled experimental HTTP
wrapper used for these measurements. That pre-existing experimental cache work
is not introduced into the default runtime by this commit, so this is not a
standalone benchmark for a clean checkout. The runner refuses to overwrite an
existing evidence directory. For a new local run, copy `run.py` and `harness.py`
to a fresh sibling directory and supply the same local experimental prerequisites.
The request, timing and correctness helpers were extracted unchanged beside the
runner for publication; `helper-provenance.json` records the identity check.

`summarize.py` regenerates the report from the versioned JSON without inference
or the local binary/cache payloads:

```sh
.venv/bin/python dev/benchmarks/qwen38-option21-readahead-performance-20261112-raw/summarize.py
```

The default-cache-disabled controls and production restoration are recorded
separately. `production-restored.json` confirms that the original model/build,
131,072 configured context and 2,048-token prefill profile were restored on
port 1235. The user's production prefix cache was preserved.

`production-restored.log` is a fixed startup/readiness snapshot. Ongoing service
output goes to `build/validation/<evidence-directory-name>/production-live.log`
so it cannot keep changing the published evidence after the benchmark exits.
