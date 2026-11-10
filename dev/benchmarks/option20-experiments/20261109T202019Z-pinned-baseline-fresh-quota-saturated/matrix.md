# Option 20 full matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 66.35 | 5.47 | 12.64 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.38 | 1.172 | 12.93 | 13 | 7.308 | 352 | 83/84 (98.8%) | 0 | True | True |
| 4k-cold | 4031 | 295.27 | 13.652 | 11.99 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.72 | 1.972 | 12.3 | 13 | 6.462 | 4000 | 71/79 (89.9%) | 0 | True | True |
| code-1 | 45 | 11.3 | 1.149 | 10.79 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.1 | 1.081 | 10.26 | 18 | 5.111 | 32 | 74/87 (85.1%) | 1 | True | True |
| code-3 | 48 | 12.24 | 1.307 | 11.47 | 11 | 5.909 | 32 | 54/56 (96.4%) | 1 | True | True |

coding decode mean 10.84 tok/s (range 10.26-11.47), tokens/cycle mean 6.192
4k cold prefill mean 295.27 tok/s
4k reuse TTFT mean 1.972 s
draft acceptance 543/580 (93.6%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.58 | 4.342 | 13.84 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.58 | 1.148 | 13.36 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 367.39 | 10.972 | 12.97 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.48 | 2.005 | 13.37 | 12 | 7.0 | 4000 | 72/76 (94.7%) | 0 | True | True |
| code-3 | 48 | 12.19 | 1.312 | 11.42 | 12 | 6.25 | 32 | 63/68 (92.7%) | 1 | True | True |
| code-2 | 44 | 11.29 | 1.063 | 11.25 | 18 | 5.778 | 32 | 86/93 (92.5%) | 1 | True | True |
| code-1 | 45 | 11.7 | 1.111 | 10.58 | 15 | 7.133 | 32 | 92/96 (95.8%) | 1 | True | True |

coding decode mean 11.08 tok/s (range 10.58-11.42), tokens/cycle mean 6.387
4k cold prefill mean 367.39 tok/s
4k reuse TTFT mean 2.005 s
draft acceptance 529/557 (95.0%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 66.35 | 5.47 | 12.64 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.38 | 1.172 | 12.93 | 13 | 7.308 | 352 | 83/84 (98.8%) | 0 | True | True |
| 4k-cold | 4031 | 295.27 | 13.652 | 11.99 | 13 | 6.462 | 0 | 71/80 (88.8%) | 0 | True | True |
| 4k-reuse | 4031 | 15.72 | 1.972 | 12.3 | 13 | 6.462 | 4000 | 71/79 (89.9%) | 0 | True | True |
| code-1 | 45 | 11.3 | 1.149 | 10.79 | 18 | 7.556 | 32 | 118/119 (99.2%) | 1 | True | True |
| code-2 | 44 | 11.1 | 1.081 | 10.26 | 18 | 5.111 | 32 | 74/87 (85.1%) | 1 | True | True |
| code-3 | 48 | 12.24 | 1.307 | 11.47 | 11 | 5.909 | 32 | 54/56 (96.4%) | 1 | True | True |
| smoke-cold | 363 | 83.58 | 4.342 | 13.84 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.58 | 1.148 | 13.36 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 367.39 | 10.972 | 12.97 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.48 | 2.005 | 13.37 | 12 | 7.0 | 4000 | 72/76 (94.7%) | 0 | True | True |
| code-3 | 48 | 12.19 | 1.312 | 11.42 | 12 | 6.25 | 32 | 63/68 (92.7%) | 1 | True | True |
| code-2 | 44 | 11.29 | 1.063 | 11.25 | 18 | 5.778 | 32 | 86/93 (92.5%) | 1 | True | True |
| code-1 | 45 | 11.7 | 1.111 | 10.58 | 15 | 7.133 | 32 | 92/96 (95.8%) | 1 | True | True |

coding decode mean 10.96 tok/s (range 10.26-11.47), tokens/cycle mean 6.290
4k cold prefill mean 331.33 tok/s
4k reuse TTFT mean 1.988 s
draft acceptance 1072/1137 (94.3%)
probes marked clean: 14/14
spill whole-page restores during probes: 6
disk KV read-back tokens during probes: 192
thermal states: fair
