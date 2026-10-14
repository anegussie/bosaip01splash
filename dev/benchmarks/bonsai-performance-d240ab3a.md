# Performance on d240ab3a

Hardware: Apple M5; 8 GPU cores; physical memory 16 GiB.

Three fresh option-14 launcher sessions. Bonsai 27B PTQ1_0 + DFlash2, Splash Metal, GPU-only prefill, INT8 KV, BF16 state, 512-token prefill chunks, 24,576-token context limit, one active request, 8 GiB requested SSD-cache quota (effective volume-limited values below), temperature 0, reasoning none. Coding input: 3,662–3,667 tokens (chunked reuses 3,584 prompt tokens); context input: 4,892 tokens. This is current-build characterization without a matched baseline.

| Workload | Median | Range |
|---|---:|---:|
| chunked decode, tok/s | 36.83 | 36.72–38.14 |
| merge_intervals decode, tok/s | 34.23 | 33.95–34.48 |
| stable_unique decode, tok/s | 31.68 | 31.27–32.02 |
| Cold prefill, tok/s | 181.74 | 181.09–188.33 |
| Cold counting decode, tok/s | 37.16 | 37.13–38.02 |
| Cold request, seconds | 29.48 | 28.48–29.58 |
| Cached counting decode, tok/s | 37.16 | 36.97–39.16 |
| Cached request, seconds | 2.83 | 2.68–2.85 |

| Round | Workload | Input | Cached | PP tok/s | TG tok/s | Seconds | Thermal |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | cold | 4892 | 0 | 188.33 | 38.02 | 28.48 | nominal |
| 1 | cached | 4892 | 4864 | 121.37 | 39.16 | 2.68 | nominal |
| 2 | cold | 4892 | 0 | 181.09 | 37.16 | 29.58 | fair |
| 2 | cached | 4892 | 4864 | 116.32 | 37.16 | 2.83 | fair |
| 3 | cold | 4892 | 0 | 181.74 | 37.13 | 29.48 | fair |
| 3 | cached | 4892 | 4864 | 114.25 | 36.97 | 2.85 | fair |

Coding checks: 9/9; isolated: True. Recall passed all six cold/cached requests. Metal healthy: True; failed requests: 0. Temporary servers stopped.

Thermal states: fair, nominal. Memory pressure: warning.

Cached prefill rates measure the uncached suffix only. The configured 24K limit does not mean these requests filled 24K. Persistent cache reuse was measured within each session; clean-restart reuse was outside this workload.

Cached counting decode spread was 5.79%; thermal state varied between nominal and fair. No speedup/regression conclusion is supported without a matched baseline.

Effective SSD cache at the start of each round (the volume can reduce the requested quota):

- Round 1: capacity=8589934592 bytes, limit=1013490688 bytes, volume_available=14791372800 bytes.
- Round 2: capacity=8589934592 bytes, limit=836324352 bytes, volume_available=14082707456 bytes.
- Round 3: capacity=8589934592 bytes, limit=650570752 bytes, volume_available=13339693056 bytes.

System swap snapshots (not attributed solely to Splash):

- Round 1 before: vm.swapusage: total = 4096.00M  used = 2902.94M  free = 1193.06M  (encrypted)
- Round 1 after: vm.swapusage: total = 4096.00M  used = 2902.94M  free = 1193.06M  (encrypted)
- Round 2 before: vm.swapusage: total = 4096.00M  used = 2932.62M  free = 1163.38M  (encrypted)
- Round 2 after: vm.swapusage: total = 4096.00M  used = 2900.62M  free = 1195.38M  (encrypted)
- Round 3 before: vm.swapusage: total = 4096.00M  used = 2900.62M  free = 1195.38M  (encrypted)
- Round 3 after: vm.swapusage: total = 4096.00M  used = 2884.62M  free = 1211.38M  (encrypted)

Startup times: 59.13 s, 39.63 s, 24.98 s.

Machine-readable results: [summary](bonsai-performance-d240ab3a.json). Raw replies, status snapshots and launcher logs remain locally in `build/validation/performance-d240ab3a`. Disposable benchmark cache files were pruned on 2026-10-14 to recover disk headroom.

Reproduction: three fresh sessions of `/Users/mymac/startllamacpp.sh --direct 14`, using port 1236, a temporary OpenCode configuration, and a separate empty cache directory per session. Each session runs `dev/benchmarks/bonsai_coding.py --order 0` followed by `dev/benchmarks/bonsai_context.py --records 220`, with `--url http://127.0.0.1:1236` and separate `--results` files. Before each session’s coding workload, wait up to 120 seconds for nominal thermal state.

Model revisions: target `b072e1d3b35a0a630cece372c2127528e0994386`; DFlash2 draft `015e795645c74b1a0eeef3b570031fb62e769bc5`. Build identity: `src-5159947989ec508eb1eb5551d0af4330a893a0f72948c141a82b60b4a99a901b`.
