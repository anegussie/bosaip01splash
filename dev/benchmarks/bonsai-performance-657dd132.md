# Performance on 657dd132

Apple M5, 8 GPU cores, 16 GiB memory. Three fresh sessions through actual launcher option 14, followed by a clean restart using the third session cache. This is current-build characterization without a matched before/after baseline.

Bonsai 2 27B PTQ1_0 with the original DFlash2 draft, Splash Metal, INT8 KV, BF16 state, 512-token prefill chunks, 24,576-token context limit, one active request, greedy sampling and reasoning none. Coding prompts fill 3,662-3,667 tokens; the recall/counting prompt fills 4,892 tokens. The test does not establish performance at a filled 24K context.

| Workload | Median | Range |
| --- | ---: | ---: |
| chunked decode, tok/s | 35.22 | 34.83-38.40 |
| merge_intervals decode, tok/s | 34.18 | 33.74-35.03 |
| stable_unique decode, tok/s | 31.18 | 29.22-32.59 |
| Cold prefill, tok/s | 186.04 | 181.50-196.26 |
| Cold counting decode, tok/s | 39.52 | 37.80-41.73 |
| Cached counting decode, tok/s | 38.52 | 38.45-41.56 |
| Cold request, seconds | 28.70 | 27.21-29.47 |
| Cached request, seconds | 2.73 | 2.54-2.75 |

| Round | Workload | Input | Cached | PP tok/s | TG tok/s | Seconds | Thermal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | cold | 4892 | 0 | 196.26 | 41.73 | 27.21 | nominal |
| 1 | cached | 4892 | 4864 | 121.79 | 41.56 | 2.54 | nominal |
| 2 | cold | 4892 | 0 | 186.04 | 39.52 | 28.70 | nominal |
| 2 | cached | 4892 | 4864 | 117.82 | 38.52 | 2.73 | nominal |
| 3 | cold | 4892 | 0 | 181.50 | 37.80 | 29.47 | fair |
| 3 | cached | 4892 | 4864 | 111.49 | 38.45 | 2.75 | fair |

Correctness: 9/9 executable coding checks and 8/8 context-recall checks, with identical replies across repeats. A forced add(17,25) call returned correct arguments and the tool-result continuation returned 42. SSE completed normally, and a second concurrent request queued and completed successfully.

Clean-restart cache reuse: 4,864 prompt tokens restored. Peak frontend waiting requests: 1; observed frontend queue: 4.054 seconds. All 21 generated workload requests passed, with healthy Metal and zero failed requests.

Cached prefill rates measure only the uncached suffix. Cache reuse saves prefill; it does not establish faster decode.

The first restart-check attempt used a symlink cache root, which the loader correctly rejected and replaced with a temporary cache. Its two generated requests were excluded from performance statistics. The corrected persistence check reused the actual saved directory and passed. The initial attempt and its error remain in the raw artifacts.

Thermal states: fair, nominal. Memory pressure: warning. Cached counting decode spread: 7.88% (range divided by mean across the three rounds). These measurements do not establish a speedup or regression versus earlier builds. Thermal transitions and spread above 5% prevent a controlled speed conclusion.

Requested SSD cache: 8 GiB; effective limits at round start:

- round-1: 6.69 GiB effective, 8.00 GiB requested.
- round-2: 6.52 GiB effective, 8.00 GiB requested.
- round-3: 6.34 GiB effective, 8.00 GiB requested.

System swap snapshots, not attributed solely to Splash:

- round-1 before: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)
- round-1 after: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)
- round-2 before: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)
- round-2 after: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)
- round-3 before: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)
- round-3 after: vm.swapusage: total = 5120.00M  used = 3594.06M  free = 1525.94M  (encrypted)

Build identity: `src-b8e108596c65114fc2adc3b8f48a52d36f7269d32bd701a095f0bdeacb55afee`.
Target GGUF artifact digest: `53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`.
DFlash2 revision: `015e795645c74b1a0eeef3b570031fb62e769bc5`.

Temporary benchmark servers stopped. The original server on port 1235 stayed online, and its request counters were unchanged. Client configuration and caches were isolated; the original launcher and global OpenCode configuration were not edited.

Raw status snapshots, replies, logs and the reproducible runner are in `build/validation/performance-657dd132/`. Machine-readable summary: [bonsai-performance-657dd132.json](bonsai-performance-657dd132.json).
