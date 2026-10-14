# Performance on 7e52f39c

Hardware: Apple M5; 8 GPU cores; physical memory 16 GiB.

Three fresh option-14 launcher sessions. Bonsai 27B PTQ1_0 + DFlash2, Splash Metal, GPU-only prefill, INT8 KV, BF16 state, 512-token prefill chunks, 24,576-token context limit, one active request, 8 GiB SSD-cache quota, temperature 0, reasoning none. Coding input: 3,662–3,667 tokens (merge_intervals and stable_unique cold; chunked reuses 3,584 prompt tokens); context input: 4,892 tokens. This is current-build characterization without a matched baseline.

| Workload | Median | Range |
|---|---:|---:|
| chunked decode, tok/s | 37.00 | 36.83–37.28 |
| merge_intervals decode, tok/s | 34.18 | 34.17–34.23 |
| stable_unique decode, tok/s | 31.65 | 31.57–31.80 |
| Cold prefill, tok/s | 181.98 | 181.79–184.98 |
| Cold counting decode, tok/s | 37.14 | 36.96–38.16 |
| Cold request, seconds | 29.46 | 28.94–29.48 |
| Cached counting decode, tok/s | 37.61 | 36.27–38.31 |
| Cached request, seconds | 2.80 | 2.75–2.90 |

| Round | Workload | Input | Cached | PP tok/s | TG tok/s | Seconds | Thermal |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | cold | 4892 | 0 | 184.98 | 38.16 | 28.94 | fair |
| 1 | cached | 4892 | 4864 | 114.89 | 38.31 | 2.75 | fair |
| 2 | cold | 4892 | 0 | 181.79 | 37.14 | 29.48 | fair |
| 2 | cached | 4892 | 4864 | 115.10 | 37.61 | 2.80 | fair |
| 3 | cold | 4892 | 0 | 181.98 | 36.96 | 29.46 | fair |
| 3 | cached | 4892 | 4864 | 111.34 | 36.27 | 2.90 | fair |

Coding checks: 9/9; isolated: True. Recall passed all six cold/cached requests. Metal healthy: True; failed requests: 0. Temporary servers stopped.

Thermal states: fair, nominal. Memory pressure: warning.

Cached prefill rates measure the uncached suffix only. The configured 24K limit does not mean these requests filled 24K. Persistent cache reuse was measured within each session; clean-restart reuse was outside this workload.

Coding decode spread was 0.17–1.20%; cold counting decode spread was 3.20%; cached counting decode spread was 5.45%. Thermal state varied from nominal to fair. No speedup or regression conclusion is supported without a matched baseline.

System swap snapshots (not attributed solely to Splash):

- Round 1 before: vm.swapusage: total = 4096.00M  used = 3379.06M  free = 716.94M  (encrypted)
- Round 1 after: vm.swapusage: total = 4096.00M  used = 3323.00M  free = 773.00M  (encrypted)
- Round 2 before: vm.swapusage: total = 4096.00M  used = 3251.00M  free = 845.00M  (encrypted)
- Round 2 after: vm.swapusage: total = 4096.00M  used = 3112.94M  free = 983.06M  (encrypted)
- Round 3 before: vm.swapusage: total = 4096.00M  used = 3190.88M  free = 905.12M  (encrypted)
- Round 3 after: vm.swapusage: total = 4096.00M  used = 3174.88M  free = 921.12M  (encrypted)

Machine-readable results: [summary](bonsai-performance-7e52f39c.json). Raw replies, status snapshots and launcher logs remain locally in `build/validation/performance-7e52f39c`. Disposable benchmark cache files were pruned on 2026-10-14 to recover disk headroom.

Reproduction: three fresh sessions of `/Users/mymac/startllamacpp.sh --direct 14`, using port 1236, a temporary OpenCode configuration, and a separate empty cache directory per session. Each session runs `dev/benchmarks/bonsai_coding.py --order 0` followed by `dev/benchmarks/bonsai_context.py --records 220`, with `--url http://127.0.0.1:1236` and separate `--results` files. Before each session’s coding workload, wait up to 120 seconds for nominal thermal state.

Model revisions: target `b072e1d3b35a0a630cece372c2127528e0994386`; DFlash2 draft `015e795645c74b1a0eeef3b570031fb62e769bc5`. Build identity: `src-2038304325010bc486149a59040b956e6058d4203647796333cdaf5b83dea621`.
