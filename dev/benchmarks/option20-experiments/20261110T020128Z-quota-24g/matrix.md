# Option 20 full matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 81.79 | 4.438 | 11.7 | 12 | 7.0 | 0 | 72/79 (91.1%) | 0 | True | True |
| smoke-reuse | 363 | 8.73 | 1.26 | 11.1 | 13 | 6.462 | 352 | 71/88 (80.7%) | 0 | True | True |
| 4k-cold | 4031 | 260.72 | 15.461 | 12.63 | 12 | 7.0 | 0 | 72/79 (91.1%) | 0 | True | True |
| 4k-reuse | 4031 | 15.01 | 2.068 | 12.41 | 14 | 6.786 | 4000 | 82/86 (95.3%) | 0 | True | True |
| code-1 | 45 | 10.88 | 1.194 | 10.74 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.18 | 1.073 | 11.02 | 18 | 5.444 | 32 | 80/84 (95.2%) | 1 | True | True |
| code-3 | 48 | 12.08 | 1.324 | 11.0 | 12 | 5.833 | 32 | 58/65 (89.2%) | 1 | True | True |

coding decode mean 10.92 tok/s (range 10.74-11.02), tokens/cycle mean 6.278
4k cold prefill mean 260.72 tok/s
4k reuse TTFT mean 2.068 s
draft acceptance 553/600 (92.2%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.28 | 4.359 | 12.68 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.16 | 1.201 | 12.62 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 324.17 | 12.438 | 12.78 | 14 | 6.786 | 0 | 82/83 (98.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.09 | 2.057 | 13.55 | 11 | 7.636 | 4000 | 72/73 (98.6%) | 0 | True | True |
| code-3 | 48 | 11.86 | 1.348 | 11.61 | 11 | 6.364 | 32 | 59/65 (90.8%) | 1 | True | True |
| code-2 | 44 | 11.56 | 1.037 | 11.58 | 14 | 6.429 | 32 | 76/80 (95.0%) | 1 | True | True |
| code-1 | 45 | 11.41 | 1.14 | 10.92 | 15 | 7.467 | 32 | 97/98 (99.0%) | 1 | True | True |

coding decode mean 11.37 tok/s (range 10.92-11.61), tokens/cycle mean 6.753
4k cold prefill mean 324.17 tok/s
4k reuse TTFT mean 2.057 s
draft acceptance 539/559 (96.4%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 81.79 | 4.438 | 11.7 | 12 | 7.0 | 0 | 72/79 (91.1%) | 0 | True | True |
| smoke-reuse | 363 | 8.73 | 1.26 | 11.1 | 13 | 6.462 | 352 | 71/88 (80.7%) | 0 | True | True |
| 4k-cold | 4031 | 260.72 | 15.461 | 12.63 | 12 | 7.0 | 0 | 72/79 (91.1%) | 0 | True | True |
| 4k-reuse | 4031 | 15.01 | 2.068 | 12.41 | 14 | 6.786 | 4000 | 82/86 (95.3%) | 0 | True | True |
| code-1 | 45 | 10.88 | 1.194 | 10.74 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.18 | 1.073 | 11.02 | 18 | 5.444 | 32 | 80/84 (95.2%) | 1 | True | True |
| code-3 | 48 | 12.08 | 1.324 | 11.0 | 12 | 5.833 | 32 | 58/65 (89.2%) | 1 | True | True |
| smoke-cold | 363 | 83.28 | 4.359 | 12.68 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.16 | 1.201 | 12.62 | 14 | 6.786 | 352 | 82/84 (97.6%) | 0 | True | True |
| 4k-cold | 4031 | 324.17 | 12.438 | 12.78 | 14 | 6.786 | 0 | 82/83 (98.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.09 | 2.057 | 13.55 | 11 | 7.636 | 4000 | 72/73 (98.6%) | 0 | True | True |
| code-3 | 48 | 11.86 | 1.348 | 11.61 | 11 | 6.364 | 32 | 59/65 (90.8%) | 1 | True | True |
| code-2 | 44 | 11.56 | 1.037 | 11.58 | 14 | 6.429 | 32 | 76/80 (95.0%) | 1 | True | True |
| code-1 | 45 | 11.41 | 1.14 | 10.92 | 15 | 7.467 | 32 | 97/98 (99.0%) | 1 | True | True |

coding decode mean 11.14 tok/s (range 10.74-11.61), tokens/cycle mean 6.516
4k cold prefill mean 292.45 tok/s
4k reuse TTFT mean 2.062 s
draft acceptance 1092/1159 (94.2%)
probes marked clean: 14/14
spill whole-page restores during probes: 6
disk KV read-back tokens during probes: 192
thermal states: fair
