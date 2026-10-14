# Performance on 60939903

Hardware: Apple M5; 8 GPU cores; physical memory 16 GiB.

Three fresh option-14 launcher sessions. Bonsai 27B PTQ1_0 + DFlash2, Splash Metal, GPU-only prefill, INT8 KV, BF16 state, 512-token prefill chunks, 24,576-token context limit, one active request, 8 GiB requested SSD-cache quota (effective volume-limited values below), temperature 0, reasoning none. Coding input: 3,662–3,667 tokens (chunked reused 3,584 prompt tokens); context input: 4,892 tokens. This is current-build characterization without a matched baseline.

| Workload | Median | Range |
|---|---:|---:|
| chunked decode, tok/s | 36.52 | 36.46–37.62 |
| merge_intervals decode, tok/s | 33.78 | 33.65–34.25 |
| stable_unique decode, tok/s | 31.35 | 31.23–31.92 |
| Cold prefill, tok/s | 177.93 | 177.60–185.07 |
| Cold counting decode, tok/s | 36.65 | 35.63–38.08 |
| Cold request, seconds | 30.15 | 28.93–30.17 |
| Cached counting decode, tok/s | 37.12 | 34.67–38.68 |
| Cached request, seconds | 2.86 | 2.73–3.03 |

| Round | Workload | Input | Cached | PP tok/s | TG tok/s | Seconds | Thermal |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | cold | 4892 | 0 | 185.07 | 38.08 | 28.93 | fair |
| 1 | cached | 4892 | 4864 | 114.54 | 38.68 | 2.73 | fair |
| 2 | cold | 4892 | 0 | 177.60 | 36.65 | 30.15 | fair |
| 2 | cached | 4892 | 4864 | 101.86 | 37.12 | 2.86 | fair |
| 3 | cold | 4892 | 0 | 177.93 | 35.63 | 30.17 | fair |
| 3 | cached | 4892 | 4864 | 105.43 | 34.67 | 3.03 | fair |

Coding checks: 9/9; isolated: True. Recall passed all six cold/cached requests. Metal healthy: True; failed requests: 0. Temporary servers stopped. Replies for each coding task and the context workload matched across all three rounds.

Thermal states: fair, nominal. Memory pressure: warning.

Cached prefill rates measure the uncached suffix only. The configured 24K limit does not mean these requests filled 24K. Persistent cache reuse was measured within each session; clean-restart reuse was outside this workload.

Cached counting decode spread was 10.89%; thermal states included nominal and fair. No speedup/regression conclusion is supported without a matched baseline.

Effective SSD cache at each round start:

- Round 1: capacity=8589934592 bytes, limit=810146816 bytes, volume_available=13977997312 bytes.
- Round 2: capacity=8589934592 bytes, limit=624423936 bytes, volume_available=13235105792 bytes.
- Round 3: capacity=8589934592 bytes, limit=462388224 bytes, volume_available=12586962944 bytes.

System swap snapshots (not attributed solely to Splash):

- Round 1 before: vm.swapusage: total = 4096.00M  used = 3449.19M  free = 646.81M  (encrypted)
- Round 1 after: vm.swapusage: total = 4096.00M  used = 3425.19M  free = 670.81M  (encrypted)
- Round 2 before: vm.swapusage: total = 4096.00M  used = 3415.81M  free = 680.19M  (encrypted)
- Round 2 after: vm.swapusage: total = 4096.00M  used = 3371.44M  free = 724.56M  (encrypted)
- Round 3 before: vm.swapusage: total = 4096.00M  used = 3363.44M  free = 732.56M  (encrypted)
- Round 3 after: vm.swapusage: total = 4096.00M  used = 3363.44M  free = 732.56M  (encrypted)

Observed Metal buffer allocation: 7.80 GiB at Ready and 7.93 GiB after the workload in every round. Planned fixed runtime: 8.23 GiB. These are runtime measurements, not total system memory use. Optional cache growth was paused by host memory pressure throughout the recorded snapshots.

Startup memory-admission waits: round 1: 1, round 2: 1, round 3: 1.

Startup times: 23.08 s, 21.05 s, 23.07 s.

Reproduction: three fresh `/Users/mymac/startllamacpp.sh --direct 14` sessions on port 1236, a temporary OpenCode config, separate empty persistent-cache directories, `bonsai_coding.py --order 0`, and `bonsai_context.py --records 220`. Allow up to 120 seconds for nominal thermal state before each coding round.

Model revisions: target `b072e1d3b35a0a630cece372c2127528e0994386`; DFlash2 draft `015e795645c74b1a0eeef3b570031fb62e769bc5`. Build identity: `src-72b36c8b19251b1d90f22e4355358e3885c5241cb5201728bbcafd120b94dc32`.

Machine-readable results: [summary](bonsai-performance-60939903.json). Raw replies, status snapshots and launcher logs remain in `build/validation/performance-60939903/`. Disposable benchmark cache files were pruned on 2026-10-14 to recover disk headroom.
