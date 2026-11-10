# Option 20 full matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.52 | 4.346 | 13.4 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| smoke-reuse | 363 | 10.46 | 1.051 | 12.41 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 281.11 | 14.339 | 12.76 | 13 | 6.462 | 0 | 71/74 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 16.06 | 1.929 | 12.42 | 13 | 6.462 | 4000 | 71/76 (93.4%) | 0 | True | True |
| code-1 | 45 | 18.98 | 2.37 | 10.74 | 15 | 7.067 | 0 | 91/94 (96.8%) | 0 | True | True |
| code-2 | 44 | 17.7 | 2.486 | 11.15 | 17 | 5.588 | 0 | 78/82 (95.1%) | 0 | True | True |
| code-3 | 48 | 18.67 | 2.57 | 11.4 | 12 | 5.417 | 0 | 53/54 (98.2%) | 0 | True | True |

coding decode mean 11.10 tok/s (range 10.74-11.40), tokens/cycle mean 6.024
4k cold prefill mean 281.11 tok/s
4k reuse TTFT mean 1.929 s
draft acceptance 507/530 (95.7%)
probes marked clean: 7/7
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## trial2
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.96 | 4.323 | 12.93 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 10.79 | 1.019 | 12.9 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 354.85 | 11.359 | 12.62 | 13 | 6.462 | 0 | 71/77 (92.2%) | 0 | True | True |
| 4k-reuse | 4031 | 16.04 | 1.932 | 12.63 | 13 | 6.462 | 4000 | 71/77 (92.2%) | 0 | True | True |
| code-3 | 48 | 12.2 | 1.311 | 12.05 | 11 | 6.364 | 32 | 59/60 (98.3%) | 1 | True | True |
| code-2 | 44 | 10.83 | 1.108 | 11.14 | 19 | 5.684 | 32 | 89/96 (92.7%) | 1 | True | True |
| code-1 | 45 | 11.26 | 1.154 | 10.88 | 19 | 7.421 | 32 | 122/123 (99.2%) | 1 | True | True |

coding decode mean 11.36 tok/s (range 10.88-12.05), tokens/cycle mean 6.490
4k cold prefill mean 354.85 tok/s
4k reuse TTFT mean 1.932 s
draft acceptance 554/585 (94.7%)
probes marked clean: 7/7
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| smoke-cold | 363 | 83.52 | 4.346 | 13.4 | 12 | 7.0 | 0 | 72/74 (97.3%) | 0 | True | True |
| smoke-reuse | 363 | 10.46 | 1.051 | 12.41 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 281.11 | 14.339 | 12.76 | 13 | 6.462 | 0 | 71/74 (96.0%) | 0 | True | True |
| 4k-reuse | 4031 | 16.06 | 1.929 | 12.42 | 13 | 6.462 | 4000 | 71/76 (93.4%) | 0 | True | True |
| code-1 | 45 | 18.98 | 2.37 | 10.74 | 15 | 7.067 | 0 | 91/94 (96.8%) | 0 | True | True |
| code-2 | 44 | 17.7 | 2.486 | 11.15 | 17 | 5.588 | 0 | 78/82 (95.1%) | 0 | True | True |
| code-3 | 48 | 18.67 | 2.57 | 11.4 | 12 | 5.417 | 0 | 53/54 (98.2%) | 0 | True | True |
| smoke-cold | 363 | 83.96 | 4.323 | 12.93 | 13 | 6.462 | 0 | 71/76 (93.4%) | 0 | True | True |
| smoke-reuse | 363 | 10.79 | 1.019 | 12.9 | 13 | 6.462 | 352 | 71/76 (93.4%) | 0 | True | True |
| 4k-cold | 4031 | 354.85 | 11.359 | 12.62 | 13 | 6.462 | 0 | 71/77 (92.2%) | 0 | True | True |
| 4k-reuse | 4031 | 16.04 | 1.932 | 12.63 | 13 | 6.462 | 4000 | 71/77 (92.2%) | 0 | True | True |
| code-3 | 48 | 12.2 | 1.311 | 12.05 | 11 | 6.364 | 32 | 59/60 (98.3%) | 1 | True | True |
| code-2 | 44 | 10.83 | 1.108 | 11.14 | 19 | 5.684 | 32 | 89/96 (92.7%) | 1 | True | True |
| code-1 | 45 | 11.26 | 1.154 | 10.88 | 19 | 7.421 | 32 | 122/123 (99.2%) | 1 | True | True |

coding decode mean 11.23 tok/s (range 10.74-12.05), tokens/cycle mean 6.257
4k cold prefill mean 317.98 tok/s
4k reuse TTFT mean 1.930 s
draft acceptance 1061/1115 (95.2%)
probes marked clean: 14/14
spill whole-page restores during probes: 3
disk KV read-back tokens during probes: 96
thermal states: fair
