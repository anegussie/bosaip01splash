# Option 20 full matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 71.98 | 5.041 | 12.17 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.35 | 1.177 | 11.59 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 281.09 | 14.34 | 12.15 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.48 | 2.005 | 13.31 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 10.98 | 1.183 | 10.75 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.14 | 1.077 | 12.26 | 13 | 6.923 | 32 | 77/78 (98.7%) | 1 | True | True |
| code-3 | 48 | 11.95 | 1.339 | 10.96 | 13 | 5.154 | 32 | 54/57 (94.7%) | 1 | True | True |

coding decode mean 11.32 tok/s (range 10.75-12.26), tokens/cycle mean 6.544
4k cold prefill mean 281.09 tok/s
4k reuse TTFT mean 2.005 s
draft acceptance 535/560 (95.5%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.98 | 4.322 | 12.73 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 9.55 | 1.151 | 12.65 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 345.95 | 11.651 | 13.46 | 12 | 7.0 | 0 | 72/76 (94.7%) | 0 | True | True |
| 4k-reuse | 4031 | 15.73 | 1.97 | 12.3 | 14 | 6.786 | 4000 | 82/90 (91.1%) | 0 | True | True |
| code-3 | 48 | 11.94 | 1.339 | 11.1 | 12 | 6.083 | 32 | 61/72 (84.7%) | 1 | True | True |
| code-2 | 44 | 11.11 | 1.08 | 10.47 | 15 | 5.667 | 32 | 70/81 (86.4%) | 1 | True | True |
| code-1 | 45 | 11.68 | 1.113 | 10.67 | 19 | 7.158 | 32 | 117/118 (99.2%) | 1 | True | True |

coding decode mean 10.75 tok/s (range 10.47-11.10), tokens/cycle mean 6.303
4k cold prefill mean 345.95 tok/s
4k reuse TTFT mean 1.970 s
draft acceptance 555/597 (93.0%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 71.98 | 5.041 | 12.17 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 9.35 | 1.177 | 11.59 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 281.09 | 14.34 | 12.15 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.48 | 2.005 | 13.31 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 10.98 | 1.183 | 10.75 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.14 | 1.077 | 12.26 | 13 | 6.923 | 32 | 77/78 (98.7%) | 1 | True | True |
| code-3 | 48 | 11.95 | 1.339 | 10.96 | 13 | 5.154 | 32 | 54/57 (94.7%) | 1 | True | True |
| smoke-cold | 363 | 83.98 | 4.322 | 12.73 | 14 | 6.786 | 0 | 82/84 (97.6%) | 0 | True | True |
| smoke-reuse | 363 | 9.55 | 1.151 | 12.65 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 345.95 | 11.651 | 13.46 | 12 | 7.0 | 0 | 72/76 (94.7%) | 0 | True | True |
| 4k-reuse | 4031 | 15.73 | 1.97 | 12.3 | 14 | 6.786 | 4000 | 82/90 (91.1%) | 0 | True | True |
| code-3 | 48 | 11.94 | 1.339 | 11.1 | 12 | 6.083 | 32 | 61/72 (84.7%) | 1 | True | True |
| code-2 | 44 | 11.11 | 1.08 | 10.47 | 15 | 5.667 | 32 | 70/81 (86.4%) | 1 | True | True |
| code-1 | 45 | 11.68 | 1.113 | 10.67 | 19 | 7.158 | 32 | 117/118 (99.2%) | 1 | True | True |

coding decode mean 11.04 tok/s (range 10.47-12.26), tokens/cycle mean 6.423
4k cold prefill mean 313.52 tok/s
4k reuse TTFT mean 1.987 s
draft acceptance 1090/1157 (94.2%)
probes marked clean: 14/14
spill whole-page restores during probes: 6
disk KV read-back tokens during probes: 192
thermal states: fair
