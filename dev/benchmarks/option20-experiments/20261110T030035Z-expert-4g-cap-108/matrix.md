# Option 20 full matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 84.12 | 4.315 | 12.03 | 12 | 7.0 | 0 | 72/73 (98.6%) | 0 | True | True |
| smoke-reuse | 363 | 10.6 | 1.037 | 12.35 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 259.98 | 15.505 | 12.54 | 14 | 6.786 | 0 | 82/85 (96.5%) | 0 | True | True |
| 4k-reuse | 4031 | 15.89 | 1.95 | 12.25 | 13 | 6.462 | 4000 | 71/78 (91.0%) | 0 | True | True |
| code-1 | 45 | 11.1 | 1.17 | 10.68 | 19 | 7.474 | 32 | 123/124 (99.2%) | 0 | True | True |
| code-2 | 44 | 10.64 | 1.128 | 11.26 | 17 | 5.706 | 32 | 80/85 (94.1%) | 0 | True | True |
| code-3 | 48 | 11.98 | 1.336 | 11.51 | 12 | 5.917 | 32 | 59/62 (95.2%) | 0 | True | True |

coding decode mean 11.15 tok/s (range 10.68-11.51), tokens/cycle mean 6.366
4k cold prefill mean 259.98 tok/s
4k reuse TTFT mean 1.950 s
draft acceptance 559/582 (96.0%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 96
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.18 | 4.363 | 13.68 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.91 | 1.109 | 12.86 | 13 | 6.462 | 352 | 71/77 (92.2%) | 0 | True | True |
| 4k-cold | 4031 | 340.79 | 11.828 | 12.65 | 12 | 7.0 | 0 | 72/78 (92.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.83 | 1.959 | 13.49 | 12 | 7.0 | 4000 | 72/74 (97.3%) | 0 | True | True |
| code-3 | 48 | 11.95 | 1.339 | 11.84 | 11 | 6.364 | 32 | 59/61 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.76 | 1.115 | 11.64 | 15 | 6.333 | 32 | 80/83 (96.4%) | 0 | True | True |
| code-1 | 45 | 11.04 | 1.177 | 10.87 | 18 | 7.611 | 32 | 119/119 (100.0%) | 0 | True | True |

coding decode mean 11.45 tok/s (range 10.87-11.84), tokens/cycle mean 6.769
4k cold prefill mean 340.79 tok/s
4k reuse TTFT mean 1.959 s
draft acceptance 545/567 (96.1%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 84.12 | 4.315 | 12.03 | 12 | 7.0 | 0 | 72/73 (98.6%) | 0 | True | True |
| smoke-reuse | 363 | 10.6 | 1.037 | 12.35 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 259.98 | 15.505 | 12.54 | 14 | 6.786 | 0 | 82/85 (96.5%) | 0 | True | True |
| 4k-reuse | 4031 | 15.89 | 1.95 | 12.25 | 13 | 6.462 | 4000 | 71/78 (91.0%) | 0 | True | True |
| code-1 | 45 | 11.1 | 1.17 | 10.68 | 19 | 7.474 | 32 | 123/124 (99.2%) | 0 | True | True |
| code-2 | 44 | 10.64 | 1.128 | 11.26 | 17 | 5.706 | 32 | 80/85 (94.1%) | 0 | True | True |
| code-3 | 48 | 11.98 | 1.336 | 11.51 | 12 | 5.917 | 32 | 59/62 (95.2%) | 0 | True | True |
| smoke-cold | 363 | 83.18 | 4.363 | 13.68 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.91 | 1.109 | 12.86 | 13 | 6.462 | 352 | 71/77 (92.2%) | 0 | True | True |
| 4k-cold | 4031 | 340.79 | 11.828 | 12.65 | 12 | 7.0 | 0 | 72/78 (92.3%) | 0 | True | True |
| 4k-reuse | 4031 | 15.83 | 1.959 | 13.49 | 12 | 7.0 | 4000 | 72/74 (97.3%) | 0 | True | True |
| code-3 | 48 | 11.95 | 1.339 | 11.84 | 11 | 6.364 | 32 | 59/61 (96.7%) | 0 | True | True |
| code-2 | 44 | 10.76 | 1.115 | 11.64 | 15 | 6.333 | 32 | 80/83 (96.4%) | 0 | True | True |
| code-1 | 45 | 11.04 | 1.177 | 10.87 | 18 | 7.611 | 32 | 119/119 (100.0%) | 0 | True | True |

coding decode mean 11.30 tok/s (range 10.68-11.84), tokens/cycle mean 6.567
4k cold prefill mean 300.38 tok/s
4k reuse TTFT mean 1.954 s
draft acceptance 1104/1149 (96.1%)
probes marked clean: 14/14
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 192
thermal states: fair
