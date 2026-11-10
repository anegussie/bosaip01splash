# Option 20 full matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 82.4 | 4.405 | 11.75 | 12 | 7.0 | 0 | 72/77 (93.5%) | 0 | True | True |
| smoke-reuse | 363 | 10.83 | 1.015 | 11.35 | 13 | 6.462 | 352 | 71/79 (89.9%) | 0 | True | True |
| 4k-cold | 4031 | 258.47 | 15.595 | 12.25 | 13 | 6.462 | 0 | 71/77 (92.2%) | 0 | True | True |
| 4k-reuse | 4031 | 15.79 | 1.963 | 12.85 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 11.21 | 1.16 | 10.66 | 19 | 7.474 | 32 | 123/124 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.45 | 1.048 | 11.22 | 17 | 5.588 | 32 | 78/79 (98.7%) | 1 | True | True |
| code-3 | 48 | 12.1 | 1.322 | 11.3 | 18 | 6.056 | 32 | 90/91 (98.9%) | 1 | True | True |

coding decode mean 11.06 tok/s (range 10.66-11.30), tokens/cycle mean 6.373
4k cold prefill mean 258.47 tok/s
4k reuse TTFT mean 1.963 s
draft acceptance 577/602 (95.8%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.34 | 4.355 | 12.7 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 10.8 | 1.018 | 12.61 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 318.95 | 12.638 | 13.39 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 15.96 | 1.941 | 12.29 | 13 | 6.462 | 4000 | 71/82 (86.6%) | 0 | True | True |
| code-3 | 48 | 12.07 | 1.325 | 11.46 | 11 | 6.364 | 32 | 59/68 (86.8%) | 1 | True | True |
| code-2 | 44 | 10.63 | 1.128 | 11.87 | 14 | 6.429 | 32 | 76/76 (100.0%) | 1 | True | True |
| code-1 | 45 | 11.01 | 1.18 | 10.39 | 19 | 7.421 | 32 | 122/129 (94.6%) | 1 | True | True |

coding decode mean 11.24 tok/s (range 10.39-11.87), tokens/cycle mean 6.738
4k cold prefill mean 318.95 tok/s
4k reuse TTFT mean 1.941 s
draft acceptance 564/598 (94.3%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 82.4 | 4.405 | 11.75 | 12 | 7.0 | 0 | 72/77 (93.5%) | 0 | True | True |
| smoke-reuse | 363 | 10.83 | 1.015 | 11.35 | 13 | 6.462 | 352 | 71/79 (89.9%) | 0 | True | True |
| 4k-cold | 4031 | 258.47 | 15.595 | 12.25 | 13 | 6.462 | 0 | 71/77 (92.2%) | 0 | True | True |
| 4k-reuse | 4031 | 15.79 | 1.963 | 12.85 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 11.21 | 1.16 | 10.66 | 19 | 7.474 | 32 | 123/124 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.45 | 1.048 | 11.22 | 17 | 5.588 | 32 | 78/79 (98.7%) | 1 | True | True |
| code-3 | 48 | 12.1 | 1.322 | 11.3 | 18 | 6.056 | 32 | 90/91 (98.9%) | 1 | True | True |
| smoke-cold | 363 | 83.34 | 4.355 | 12.7 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 10.8 | 1.018 | 12.61 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 318.95 | 12.638 | 13.39 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 15.96 | 1.941 | 12.29 | 13 | 6.462 | 4000 | 71/82 (86.6%) | 0 | True | True |
| code-3 | 48 | 12.07 | 1.325 | 11.46 | 11 | 6.364 | 32 | 59/68 (86.8%) | 1 | True | True |
| code-2 | 44 | 10.63 | 1.128 | 11.87 | 14 | 6.429 | 32 | 76/76 (100.0%) | 1 | True | True |
| code-1 | 45 | 11.01 | 1.18 | 10.39 | 19 | 7.421 | 32 | 122/129 (94.6%) | 1 | True | True |

coding decode mean 11.15 tok/s (range 10.39-11.87), tokens/cycle mean 6.555
4k cold prefill mean 288.71 tok/s
4k reuse TTFT mean 1.952 s
draft acceptance 1141/1200 (95.1%)
probes marked clean: 14/14
spill whole-page restores during probes: 6
disk KV read-back tokens during probes: 192
thermal states: fair
