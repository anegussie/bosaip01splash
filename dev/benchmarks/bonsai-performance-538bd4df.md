# Performance on 538bd4df

**Partial benchmark: two rounds completed; the third could not start after the launcher exhausted its memory-admission retries. Near-full-context and clean-restart persistence checks were not reached.**

Live `/Users/mymac/startllamacpp.sh --direct 14` on Apple M5 (8 GPU cores), 16 GiB, macOS 26.5.2. Each measured round used a fresh launcher session and empty separate persistent cache. A short cold/cached smoke test passed before timing. No matched baseline was run.

Bonsai 27B PTQ1_0 + DFlash2; Splash Metal; GPU prefill; INT8 KV; BF16 state; 512-token prefill chunks; 24,576-token server / 22,528-token client context; one active request; greedy sampling; reasoning none. Requested SSD cache: 8 GiB, limited by available volume space. Coding output allowance: 384 tokens; context output: 96 tokens. The measured requests filled 3,662–4,892 tokens, not the 24K server limit.

| Workload | Median PP tok/s | Median decode tok/s | Decode range | Median request s |
|---|---:|---:|---:|---:|
| merge_intervals | 191.31 | 35.89 | 35.59–36.19 | 22.17 |
| stable_unique | 182.47 | 32.85 | 32.67–33.04 | 21.46 |
| chunked | 139.03 | 36.87 | 35.44–38.29 | 2.04 |
| cold | 171.82 | 36.71 | 34.19–39.23 | 31.08 |
| cached | 99.07 | 36.36 | 36.28–36.43 | 2.91 |

Cached PP measures the uncached suffix plus restore overhead. Prefix reuse saves prefill work; it is not a full-prompt compute-throughput measurement.

| Phase | Workload | Prompt | Cached | Output | PP tok/s | Decode tok/s | Seconds | Thermal |
|---|---|---:|---:|---:|---:|---:|---:|---|
| round-1 | merge_intervals | 3662 | 0 | 109 | 190.71 | 36.19 | 22.20 | see phase snapshots |
| round-1 | stable_unique | 3663 | 0 | 46 | 183.68 | 33.04 | 21.32 | see phase snapshots |
| round-1 | chunked | 3667 | 3584 | 53 | 135.46 | 35.44 | 2.11 | see phase snapshots |
| round-1 | cold | 4892 | 0 | 96 | 173.87 | 39.23 | 30.57 | fair |
| round-1 | cached | 4892 | 4864 | 96 | 93.02 | 36.43 | 2.92 | fair |
| round-2 | merge_intervals | 3662 | 0 | 109 | 191.91 | 35.59 | 22.14 | see phase snapshots |
| round-2 | stable_unique | 3663 | 0 | 46 | 181.26 | 32.67 | 21.60 | see phase snapshots |
| round-2 | chunked | 3667 | 3584 | 53 | 142.60 | 38.29 | 1.97 | see phase snapshots |
| round-2 | cold | 4892 | 0 | 96 | 169.78 | 34.19 | 31.60 | fair |
| round-2 | cached | 4892 | 4864 | 96 | 105.13 | 36.28 | 2.91 | fair |

Coding checks: 6/6; isolated requests: True. Context recall and cold/cached output equality passed in both completed rounds. Zero reasoning tokens in every measured response. Metal healthy: True; failed inference requests in completed rounds: 0. Benchmark listener stopped; primary server request counters unchanged.

Peak Metal allocation observed in status snapshots: 7.97 GiB. Thermal states: fair, nominal. Memory pressure: warning. Startup memory-admission refusals: 4 (one during the smoke launch, three during round 3). The smoke eventually started in 161.26 s. Completed timed session startups: 21.10 s, 29.06 s.

The final startup refusal reported 1,523 MiB reclaimable with 1,638 MiB protected for macOS, under warning pressure. The memory limits were left unchanged. Startup reliability is a separate failure from the successful inference requests.

This is current-build characterization. Cold-request decode spread exceeds 5%, thermal state changes, and the third session failed to start. These results do not establish an upstream-merge speedup or regression. A rerun with more free memory is needed to complete near-full-context and clean-restart checks; a matched baseline is needed for a speed comparison.

System swap snapshots are not attributed solely to Splash:

- round-1 before: vm.swapusage: total = 7168.00M  used = 6336.31M  free = 831.69M  (encrypted)
- round-1 after: vm.swapusage: total = 7168.00M  used = 6247.94M  free = 920.06M  (encrypted)
- round-2 before: vm.swapusage: total = 7168.00M  used = 6150.75M  free = 1017.25M  (encrypted)
- round-2 after: vm.swapusage: total = 7168.00M  used = 6354.56M  free = 813.44M  (encrypted)
- After abort: vm.swapusage: total = 7168.00M  used = 6662.12M  free = 505.88M  (encrypted)

Effective SSD-cache limits at startup: 3.54 GiB, 2.99 GiB.

Build identity: `src-17aa01b274ec2db4791bdc212074156f02c28a51532ee90eaf29764eeca8a7e9`. Target revision: `b072e1d3b35a0a630cece372c2127528e0994386`; draft revision: `015e795645c74b1a0eeef3b570031fb62e769bc5`. Target artifact digest: `53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`.

Raw responses, native status, startup refusal evidence, launcher logs and reproduction runner: `build/validation/performance-538bd4df/`. Machine-readable summary: [bonsai-performance-538bd4df.json](bonsai-performance-538bd4df.json).
