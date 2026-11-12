# Option 21 serving performance through 100K — 2026-11-12

[Detailed results, conditions and raw evidence](qwen38-option21-performance-20261112-raw/CONTEXT-REPORT.md).


Two trials per context, on the same live Q2_0 + BF16 DFlash2 server.
Output budget: 96 tokens; thinking disabled, temperature 1.0, top_p 0.95.
Prompt counts include 12 chat-template tokens. Cold means zero reused prefix tokens,
with the model and operating-system caches already warm. Prefix reuse uses the identical prompt.

| Filled prompt tokens | Cold PP tok/s | Cold TPS | Cold TTFT s | Cached TPS | Cached TTFT s |
|---:|---:|---:|---:|---:|---:|
| 363 | 111.79–111.98 | 25.27–27.06 | 3.241–3.247 | 28.48–28.97 | 0.902–0.983 |
| 4,031 | 464.39–469.26 | 27.38–27.99 | 8.590–8.680 | 23.84–24.49 | 1.514–1.565 |
| 8,204 | 436.02–445.07 | 25.87–27.60 | 18.433–18.815 | 24.13–25.87 | 0.871–0.902 |
| 16,396 | 310.72–392.82 | 24.31–27.15 | 41.738–52.767 | 21.90–27.90 | 0.825–0.838 |
| 65,548 | 276.27–345.20 | 22.77–23.56 | 189.884–237.264 | 21.13–21.32 | 0.856–0.890 |
| 102,412 | 264.92–306.83 | 22.05–23.88 | 333.780–386.576 | 21.62–23.36 | 0.803–0.900 |

TPS measures decode only; PP measures fresh prompt processing. Ranges contain both observations.
0.35K/4K results are from the original run. 8K/16K results here replace the
original eight-token probes with 96-token output-budget reruns. All requests
finish naturally or at that budget; actual output counts are in raw records.

## Added runs: validation and conditions

### context64k

Four clean requests; ORCHID recall/counting and full-prefix cache gates passed.
Actual output tokens: [96, 85, 96, 85].
Thermal states: ['fair', 'nominal']; memory pressure: ['warning'].
Peak Metal allocation: 9.065 GiB.
System swap-out delta: 0 pages; swap-in delta: 16 pages.
Before: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
After: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
KV spilled-page delta: 0; whole-page restore delta: 0.

### context8192

Four clean requests; ORCHID recall/counting and full-prefix cache gates passed.
Actual output tokens: [85, 96, 96, 96].
Thermal states: ['fair', 'nominal']; memory pressure: ['warning'].
Peak Metal allocation: 9.065 GiB.
System swap-out delta: 0 pages; swap-in delta: 0 pages.
Before: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
After: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
KV spilled-page delta: 0; whole-page restore delta: 0.

### context16384

Four clean requests; ORCHID recall/counting and full-prefix cache gates passed.
Actual output tokens: [85, 85, 85, 85].
Thermal states: ['fair']; memory pressure: ['warning'].
Peak Metal allocation: 9.065 GiB.
System swap-out delta: 0 pages; swap-in delta: 0 pages.
Before: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
After: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
KV spilled-page delta: 0; whole-page restore delta: 0.

### context102400

Four clean requests; ORCHID recall/counting and full-prefix cache gates passed.
Actual output tokens: [96, 85, 85, 85].
Thermal states: ['fair', 'nominal']; memory pressure: ['warning'].
Peak Metal allocation: 9.461 GiB.
System swap-out delta: 0 pages; swap-in delta: 16 pages.
Before: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
After: vm.swapusage: total = 2048.00M  used = 423.44M  free = 1624.56M  (encrypted)
KV spilled-page delta: 0; whole-page restore delta: 0.

## Configuration and evidence

Apple M5, 8 GPU cores, 16 GiB RAM; 10.8 GiB cap, 2,048-token chunks,
INT8 KV, BF16 state, automatic verification width, one active request.
Configured context remains 114,681 tokens after the launcher fallback.
Largest context actually filled: 102,412 tokens. No full-capacity claim.
Persistent cache quota is subject to available disk space; see per-run status snapshots.
This is a current-condition measurement; thermal/cache state differs across time.

Each context directory contains request metrics, responses, correctness checks,
sampled conditions, profile/build identity, status and system snapshots.
`64k.log`, `8192.log`, `16384.log` and `102400.log` preserve progress and completion.
`run64k.py` and `run-context.py` reproduce the added runs.
The original report, raw results and build hashes remain beside this file.

The raw snapshot excludes Python bytecode, log symlinks and the continuously growing monitoring status log. Per-request status samples and runtime telemetry are retained.

Reproduce from the repository root (with the correct option 21 server running):

```sh
BENCH=dev/benchmarks/qwen38-option21-performance-20261112-raw
.venv/bin/python "$BENCH/run.py"
.venv/bin/python "$BENCH/run64k.py"
.venv/bin/python "$BENCH/run-context.py" 8192
.venv/bin/python "$BENCH/run-context.py" 16384
.venv/bin/python "$BENCH/run-context.py" 102400
.venv/bin/python "$BENCH/summarize-context.py"
```
