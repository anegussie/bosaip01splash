# Option 20 full matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 55.16 | 6.58 | 10.93 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.6 | 1.145 | 12.71 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 254.58 | 15.834 | 11.6 | 14 | 6.0 | 0 | 70/81 (86.4%) | 0 | True | True |
| 4k-reuse | 4031 | 15.33 | 2.025 | 13.39 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 11.27 | 1.153 | 10.89 | 15 | 7.4 | 32 | 96/98 (98.0%) | 1 | True | True |
| code-2 | 44 | 10.86 | 1.105 | 10.42 | 18 | 4.944 | 32 | 71/82 (86.6%) | 1 | True | True |
| code-3 | 48 | 11.8 | 1.355 | 11.75 | 11 | 5.909 | 32 | 54/54 (100.0%) | 1 | True | True |

coding decode mean 11.02 tok/s (range 10.42-11.75), tokens/cycle mean 6.084
4k cold prefill mean 254.58 tok/s
4k reuse TTFT mean 2.025 s
draft acceptance 507/540 (93.9%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 55.16 | 6.58 | 10.93 | 12 | 7.0 | 0 | 72/75 (96.0%) | 0 | True | True |
| smoke-reuse | 363 | 9.6 | 1.145 | 12.71 | 12 | 7.0 | 352 | 72/75 (96.0%) | 0 | True | True |
| 4k-cold | 4031 | 254.58 | 15.834 | 11.6 | 14 | 6.0 | 0 | 70/81 (86.4%) | 0 | True | True |
| 4k-reuse | 4031 | 15.33 | 2.025 | 13.39 | 12 | 7.0 | 4000 | 72/75 (96.0%) | 0 | True | True |
| code-1 | 45 | 11.27 | 1.153 | 10.89 | 15 | 7.4 | 32 | 96/98 (98.0%) | 1 | True | True |
| code-2 | 44 | 10.86 | 1.105 | 10.42 | 18 | 4.944 | 32 | 71/82 (86.6%) | 1 | True | True |
| code-3 | 48 | 11.8 | 1.355 | 11.75 | 11 | 5.909 | 32 | 54/54 (100.0%) | 1 | True | True |

coding decode mean 11.02 tok/s (range 10.42-11.75), tokens/cycle mean 6.084
4k cold prefill mean 254.58 tok/s
4k reuse TTFT mean 2.025 s
draft acceptance 507/540 (93.9%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair
