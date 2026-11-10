# Option 20 full matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.09 | 4.368 | 11.49 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 9.56 | 1.15 | 11.78 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 177.84 | 22.665 | 13.13 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.77 | 1.966 | 12.19 | 13 | 6.462 | 4000 | 71/76 (93.4%) | 0 | True | True |
| code-1 | 45 | 11.5 | 1.13 | 10.39 | 16 | 6.938 | 32 | 95/101 (94.1%) | 0 | True | True |
| code-2 | 44 | 10.82 | 1.109 | 9.56 | 18 | 4.667 | 32 | 66/82 (80.5%) | 0 | True | True |
| code-3 | 48 | 12.04 | 1.328 | 11.67 | 12 | 5.917 | 32 | 59/60 (98.3%) | 0 | True | True |

coding decode mean 10.54 tok/s (range 9.56-11.67), tokens/cycle mean 5.841
4k cold prefill mean 177.84 tok/s
4k reuse TTFT mean 1.966 s
draft acceptance 516/553 (93.3%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 82.69 | 4.389 | 13.68 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 10.31 | 1.067 | 12.82 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 198.21 | 20.336 | 13.24 | 11 | 7.636 | 0 | 72/77 (93.5%) | 0 | True | True |
| 4k-reuse | 4031 | 15.37 | 2.02 | 13.4 | 12 | 7.0 | 4000 | 72/74 (97.3%) | 0 | True | True |
| code-3 | 48 | 12.01 | 1.332 | 11.48 | 12 | 5.917 | 32 | 59/61 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.58 | 1.134 | 11.01 | 17 | 5.647 | 32 | 79/85 (92.9%) | 0 | True | True |
| code-1 | 45 | 11.44 | 1.136 | 10.7 | 19 | 7.421 | 32 | 122/124 (98.4%) | 0 | True | True |

coding decode mean 11.06 tok/s (range 10.70-11.48), tokens/cycle mean 6.328
4k cold prefill mean 198.21 tok/s
4k reuse TTFT mean 2.020 s
draft acceptance 558/580 (96.2%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 32
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.09 | 4.368 | 11.49 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 9.56 | 1.15 | 11.78 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 177.84 | 22.665 | 13.13 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.77 | 1.966 | 12.19 | 13 | 6.462 | 4000 | 71/76 (93.4%) | 0 | True | True |
| code-1 | 45 | 11.5 | 1.13 | 10.39 | 16 | 6.938 | 32 | 95/101 (94.1%) | 0 | True | True |
| code-2 | 44 | 10.82 | 1.109 | 9.56 | 18 | 4.667 | 32 | 66/82 (80.5%) | 0 | True | True |
| code-3 | 48 | 12.04 | 1.328 | 11.67 | 12 | 5.917 | 32 | 59/60 (98.3%) | 0 | True | True |
| smoke-cold | 363 | 82.69 | 4.389 | 13.68 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 10.31 | 1.067 | 12.82 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 198.21 | 20.336 | 13.24 | 11 | 7.636 | 0 | 72/77 (93.5%) | 0 | True | True |
| 4k-reuse | 4031 | 15.37 | 2.02 | 13.4 | 12 | 7.0 | 4000 | 72/74 (97.3%) | 0 | True | True |
| code-3 | 48 | 12.01 | 1.332 | 11.48 | 12 | 5.917 | 32 | 59/61 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.58 | 1.134 | 11.01 | 17 | 5.647 | 32 | 79/85 (92.9%) | 0 | True | True |
| code-1 | 45 | 11.44 | 1.136 | 10.7 | 19 | 7.421 | 32 | 122/124 (98.4%) | 0 | True | True |

coding decode mean 10.80 tok/s (range 9.56-11.67), tokens/cycle mean 6.085
4k cold prefill mean 188.03 tok/s
4k reuse TTFT mean 1.993 s
draft acceptance 1074/1133 (94.8%)
probes marked clean: 14/14
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 128
thermal states: fair
