# Option 21 performance — 2026-11-12

Update: [CONTEXT-REPORT.md](CONTEXT-REPORT.md) adds two 64K cold/reuse trials
and 96-token output-budget reruns at 8K/16K, with TPS at every tested context.
The original measurements below remain as historical evidence for this session.

Measured through the real `startllamacpp.sh --direct 21` serving path on Apple M5,
8 GPU cores, 16 GiB RAM, macOS 26.5.2. Target:
`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0`, local BF16 DFlash2 draft,
INT8 KV, BF16 state, automatic verification width, one active request,
10.8 GiB memory cap, 2,048-token prefill chunks. No build or source edits.

The default 131,072-token context failed admission. The launcher automatically
retried successfully at **114,681 tokens**. Persistent cache was configured at
2 GiB but limited to **1.20 GiB** by the volume's 10 GiB free-space reserve.
Existing persistent entries were retained; this is a newly started server with
restored cache, not an empty filesystem cache. Unique prompt text provided zero
cached tokens for all cold smoke, 4K, 8K and 16K requests.

## Results

Two trials per workload; ranges show both observations. Prompt counts include
12 chat-template tokens. TTFT is measured at the streaming client.

| Filled prompt tokens | Cold prefill tok/s | Cold TTFT s | Prefix-reuse TTFT s | Decode tok/s |
|---:|---:|---:|---:|---:|
| 363 | 111.79–111.98 | 3.241–3.247 | 0.902–0.983 | 25.27–27.06 |
| 4,031 | 464.39–469.26 | 8.590–8.680 | 1.514–1.565 | 27.38–27.99 |
| 8,204 | 315.05–436.54 | 18.792–26.040 | 0.589–0.803 | — |
| 16,396 | 326.19–349.43 | 46.921–50.265 | 0.576–0.600 | — |

The 8K/16K probes generate only eight tokens and are for prefill/cache measurement;
their decode timings are not representative sustained decode measurements.
Smoke/4K probes allow 96 output tokens and check ORCHID recall and counting.
Coding probes allow 192 tokens: all six generated functions passed executable
asserts, with **16.63–20.88 decode tok/s**. The second coding trial reused 32
prefix tokens; its TTFT is not a cold comparison. Sampling: temperature 1.0,
top_p 0.95, thinking disabled, launcher reasoning default low. No tuning overrides.

All **22 probes** passed their correctness/stream checks and were clean according
to request completion, failure and contention counters. The smoke cache gate
passed before each dependent serving matrix. Larger cache hits were 8,192 and
16,384 tokens. Larger prefill probes check completed output, not semantic quality.

## Conditions and limits

- Thermal state: nominal initially, fair later. The 8K variation occurred even
  with both trials reporting fair; this is current-condition performance, with
  no speedup claim against prior runs or another model.
- Memory pressure reported warning throughout. Peak Metal allocation recorded
  by the runtime: 9.065 GiB; this excludes other processes and host memory.
- macOS swap used stayed 423.44 MiB; system Swapins and Swapouts both increased
  by zero. Pageouts increased by 622 pages.
- Zero newly spilled KV pages; three whole-page restore counter increments
  occurred. Existing persistent-cache restores mean this is not a no-disk-I/O run.
- Aggregate DFlash accepted/drafted ratio: 94.0% across these workloads.
- Largest filled context tested: 16,396 tokens. The configured 114,681-token
  capacity was not performance-tested at full occupancy.
- Server remained ready on port 1235 after measurement.

## Evidence

`results.json` contains all request metrics, sampled conditions, status snapshots,
responses and correctness diagnostics. `serving/` and `prefill/` contain individual
probe records; `benchmark.log` contains progress and the successful completion.
`profile.json`, `status-before.json`, `status-after.json`, `system-before.json`,
`system-after.json` and `server/` preserve build/model/cache identities, launch
fallback, raw system telemetry and logs. `run.py` and `harness.py` reproduce the run.

Checkout HEAD: `256988ba25650146440aaccf71b295263b227afc`.
Runtime build ID: `src-1ef6dc39d99601da3f23483d61dd79525938de3d02d0f05c50243809fefc66b7`.
Binary and both Metal library SHA256 hashes are saved in the system snapshots.
