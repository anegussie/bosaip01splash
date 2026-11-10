# Option 20 full matrix

cache state: longlived | thermal gate: none | build: src-81529c7c97580f531418c1c0ec9bf09bfd5997452ca96d8d0b8071fa40c86a6a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 80.42 | 4.514 | 11.76 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.77 | 1.125 | 11.06 | 13 | 6.462 | 352 | 71/81 (87.6%) | 0 | True | True |
| 4k-cold | 4031 | 243.17 | 16.576 | 12.3 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| 4k-reuse | 4031 | 15.63 | 1.984 | 11.78 | 13 | 6.462 | 4000 | 71/81 (87.6%) | 0 | True | True |
| code-1 | 45 | 18.9 | 2.381 | 10.59 | 18 | 7.556 | 0 | 118/121 (97.5%) | 0 | True | True |
| code-2 | 44 | 17.63 | 2.495 | 10.59 | 16 | 5.5 | 0 | 72/81 (88.9%) | 0 | True | True |
| code-3 | 48 | 18.55 | 2.587 | 11.16 | 14 | 5.571 | 0 | 64/68 (94.1%) | 0 | True | True |

coding decode mean 10.78 tok/s (range 10.59-11.16), tokens/cycle mean 6.209
4k cold prefill mean 243.17 tok/s
4k reuse TTFT mean 1.984 s
draft acceptance 550/591 (93.1%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 82.94 | 4.377 | 13.63 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 8.95 | 1.229 | 13.68 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 315.86 | 12.762 | 12.17 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.59 | 1.988 | 12.35 | 13 | 6.462 | 4000 | 71/78 (91.0%) | 0 | True | True |
| code-3 | 48 | 12.24 | 1.307 | 11.56 | 12 | 5.833 | 32 | 58/60 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.8 | 1.111 | 11.8 | 14 | 6.5 | 32 | 77/79 (97.5%) | 0 | True | True |
| code-1 | 45 | 11.37 | 1.143 | 10.6 | 16 | 6.688 | 32 | 91/93 (97.9%) | 0 | True | True |

coding decode mean 11.32 tok/s (range 10.60-11.80), tokens/cycle mean 6.340
4k cold prefill mean 315.86 tok/s
4k reuse TTFT mean 1.988 s
draft acceptance 512/540 (94.8%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 80.42 | 4.514 | 11.76 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.77 | 1.125 | 11.06 | 13 | 6.462 | 352 | 71/81 (87.6%) | 0 | True | True |
| 4k-cold | 4031 | 243.17 | 16.576 | 12.3 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| 4k-reuse | 4031 | 15.63 | 1.984 | 11.78 | 13 | 6.462 | 4000 | 71/81 (87.6%) | 0 | True | True |
| code-1 | 45 | 18.9 | 2.381 | 10.59 | 18 | 7.556 | 0 | 118/121 (97.5%) | 0 | True | True |
| code-2 | 44 | 17.63 | 2.495 | 10.59 | 16 | 5.5 | 0 | 72/81 (88.9%) | 0 | True | True |
| code-3 | 48 | 18.55 | 2.587 | 11.16 | 14 | 5.571 | 0 | 64/68 (94.1%) | 0 | True | True |
| smoke-cold | 363 | 82.94 | 4.377 | 13.63 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 8.95 | 1.229 | 13.68 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 315.86 | 12.762 | 12.17 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.59 | 1.988 | 12.35 | 13 | 6.462 | 4000 | 71/78 (91.0%) | 0 | True | True |
| code-3 | 48 | 12.24 | 1.307 | 11.56 | 12 | 5.833 | 32 | 58/60 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.8 | 1.111 | 11.8 | 14 | 6.5 | 32 | 77/79 (97.5%) | 0 | True | True |
| code-1 | 45 | 11.37 | 1.143 | 10.6 | 16 | 6.688 | 32 | 91/93 (97.9%) | 0 | True | True |

coding decode mean 11.05 tok/s (range 10.59-11.80), tokens/cycle mean 6.275
4k cold prefill mean 279.51 tok/s
4k reuse TTFT mean 1.986 s
draft acceptance 1062/1131 (93.9%)
probes marked clean: 14/14
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
