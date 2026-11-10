# Option 20 full matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 75.49 | 4.808 | 11.65 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 10.8 | 1.018 | 11.72 | 13 | 7.308 | 352 | 83/87 (95.4%) | 0 | True | True |
| 4k-cold | 4031 | 256.17 | 15.735 | 12.06 | 13 | 6.462 | 0 | 71/79 (89.9%) | 0 | True | True |
| 4k-reuse | 4031 | 15.88 | 1.952 | 12.25 | 13 | 6.462 | 4000 | 71/77 (92.2%) | 0 | True | True |
| code-1 | 45 | 18.88 | 2.383 | 10.76 | 15 | 7.4 | 0 | 96/99 (97.0%) | 0 | True | True |
| code-2 | 44 | 17.64 | 2.493 | 11.18 | 18 | 5.444 | 0 | 80/82 (97.6%) | 0 | True | True |
| code-3 | 48 | 18.54 | 2.589 | 11.67 | 12 | 5.917 | 0 | 59/60 (98.3%) | 0 | True | True |

coding decode mean 11.20 tok/s (range 10.76-11.67), tokens/cycle mean 6.254
4k cold prefill mean 256.17 tok/s
4k reuse TTFT mean 1.952 s
draft acceptance 532/559 (95.2%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 82.59 | 4.395 | 12.8 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.83 | 1.118 | 12.24 | 13 | 6.462 | 352 | 71/81 (87.6%) | 0 | True | True |
| 4k-cold | 4031 | 312.01 | 12.919 | 13.04 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 15.17 | 2.045 | 12.52 | 14 | 6.786 | 4000 | 82/85 (96.5%) | 0 | True | True |
| code-3 | 48 | 12.14 | 1.318 | 11.83 | 11 | 6.364 | 32 | 59/61 (96.7%) | 1 | True | True |
| code-2 | 44 | 11.74 | 1.022 | 10.92 | 20 | 6.0 | 32 | 100/111 (90.1%) | 1 | True | True |
| code-1 | 45 | 10.81 | 1.202 | 10.81 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |

coding decode mean 11.19 tok/s (range 10.81-11.83), tokens/cycle mean 6.640
4k cold prefill mean 312.01 tok/s
4k reuse TTFT mean 2.045 s
draft acceptance 573/608 (94.2%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 75.49 | 4.808 | 11.65 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 10.8 | 1.018 | 11.72 | 13 | 7.308 | 352 | 83/87 (95.4%) | 0 | True | True |
| 4k-cold | 4031 | 256.17 | 15.735 | 12.06 | 13 | 6.462 | 0 | 71/79 (89.9%) | 0 | True | True |
| 4k-reuse | 4031 | 15.88 | 1.952 | 12.25 | 13 | 6.462 | 4000 | 71/77 (92.2%) | 0 | True | True |
| code-1 | 45 | 18.88 | 2.383 | 10.76 | 15 | 7.4 | 0 | 96/99 (97.0%) | 0 | True | True |
| code-2 | 44 | 17.64 | 2.493 | 11.18 | 18 | 5.444 | 0 | 80/82 (97.6%) | 0 | True | True |
| code-3 | 48 | 18.54 | 2.589 | 11.67 | 12 | 5.917 | 0 | 59/60 (98.3%) | 0 | True | True |
| smoke-cold | 363 | 82.59 | 4.395 | 12.8 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.83 | 1.118 | 12.24 | 13 | 6.462 | 352 | 71/81 (87.6%) | 0 | True | True |
| 4k-cold | 4031 | 312.01 | 12.919 | 13.04 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 15.17 | 2.045 | 12.52 | 14 | 6.786 | 4000 | 82/85 (96.5%) | 0 | True | True |
| code-3 | 48 | 12.14 | 1.318 | 11.83 | 11 | 6.364 | 32 | 59/61 (96.7%) | 1 | True | True |
| code-2 | 44 | 11.74 | 1.022 | 10.92 | 20 | 6.0 | 32 | 100/111 (90.1%) | 1 | True | True |
| code-1 | 45 | 10.81 | 1.202 | 10.81 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |

coding decode mean 11.20 tok/s (range 10.76-11.83), tokens/cycle mean 6.447
4k cold prefill mean 284.09 tok/s
4k reuse TTFT mean 1.998 s
draft acceptance 1105/1167 (94.7%)
probes marked clean: 14/14
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair
