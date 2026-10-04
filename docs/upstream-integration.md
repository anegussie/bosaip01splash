# Upstream integration, 2026-10-03

The local `splashmain` branch includes `incoai/splash` through
`f43509a2f03d83b4442a0fab748e8b0fb49aa817`. The original local tip was
`ecb5d760cea3a50b848adc4e6ab0e5714efe2382`.

The initial merge retained whole local files at conflicts, leaving older
interfaces alongside newer callers. The follow-up repair restores upstream
interfaces and ports the local extensions onto them.

## What is integrated

| Area | Integration |
| --- | --- |
| Resource management | Upstream transactional allocation, reclaim and serving-memory accounting. |
| Prefix cache | Upstream persistent SSD cache, directory locking and recovery. `--persistent-cache` requires a nonzero `--max-cache-disk`. |
| Model loading | Upstream model-directory layout, prepared weights and loader interfaces. |
| Metal kernels | Upstream register and staged decode, prefill and embedding kernels, extended with PTQ1_0. |
| Frontend and launcher | Upstream shared CLI options, package invocation, offline mode and HTTP contracts. |

## Local behavior retained

- PTQ1_0 (GGUF type 143), including preparation, projection, ordinary and
  rotated embeddings, planner admission and reference coverage.
- An idle-system-sleep assertion for a loaded Metal backend, released on
  teardown and failed startup. Display sleep remains available.
- `--resource-wait-timeout SECONDS`, default 30, forwarded to the engine.
- `--max-active-requests`, default 0 for engine concurrency. Use 1 for FIFO
  submission with one active native request. Waiters keep their original
  deadlines and poll HTTP disconnects and streaming heartbeats.
- Request IDs, frontend/native queue timings and PP/decode console metrics.

The earlier sparse-unmap locking patch is obsolete because upstream removed
that sparse-buffer path. The earlier admission/reclaim implementation is
superseded by upstream resource accounting rather than layered onto it.

## Regressions repaired during validation

- Queued HTTP callbacks now run only for waiters and are cleared after
  submission, preventing early HTTP 200 responses on admission failure and
  preventing completed jobs from retaining request-body reservations.
- Launcher assembly records close when `execve` fails or returns in tests.
  Successful execution still inherits the lock descriptor.
- PTQ1_0 trit extraction uses constant divisors. General integer division in
  the Metal decoder produced intermittent incorrect prefill fragments on
  the local Apple10 GPU. Projection tests repeat PTQ1_0 dispatches and include
  a `--prefill` mode for focused reproduction.

## Validation

Validated locally on Apple M5, macOS 26.5.2:

- Production build and native CPU suite: passed.
- Complete native Metal suite with shader validation: passed.
- Python engine discovery: 812 tests, passed with 7 optional tests skipped.
- Server suite: 224 tests, passed.
- Installer/model/metadata/restart and launcher run: 155 tests, passed.
- Five repeated prefill runs, including repeated PTQ1_0 dispatches: passed.
- Architecture checks, Python compilation, lint/format and diff checks: passed.

Run the current gates from the checkout:

```sh
make -j4 all test-engine-cpu test-engine-metal
.venv/bin/python -m unittest discover -s dev/tests/engine -p 'test_*.py'
.venv/bin/python -m unittest dev.tests.test_server
.venv/bin/python -m unittest dev.tests.test_models dev.tests.test_upstream dev.tests.test_gguf_metadata dev.tests.test_installer_restarts
.venv/bin/python dev/tools/check_architecture.py
.venv/bin/ruff check --config dev/ruff.toml server install dev/tools dev/tests dev/benchmarks
.venv/bin/ruff format --check --config dev/ruff.toml server install dev/tools dev/tests dev/benchmarks
git diff --check
```

These gates exercise real Metal kernels with shader validation and HTTP
contracts with controlled native backends. They do not establish real-model
throughput or long-context memory capacity. Full-model inference needs the
separate model-specific smoke and release gates described in DEVELOPMENT.md.
