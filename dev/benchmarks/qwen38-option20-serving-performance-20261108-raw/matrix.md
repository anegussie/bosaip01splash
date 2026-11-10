## trial1
| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 85.94 | 4.496 | 12.69 | 13 | 7.385 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.15 | 2.257 | 12.5 | 13 | 7.385 | 352 | 83/84 (98.8%) |
| 4k-cold | 4066 | 394.13 | 10.329 | 12.05 | 14 | 6.857 | 0 | 82/85 (96.5%) |
| 4k-reuse | 4066 | 13.65 | 2.499 | 12.89 | 13 | 7.385 | 4032 | 82/82 (100.0%) |
| code-1 | 47 | 11.63 | 1.314 | 9.15 | 33 | 3.879 | 32 | 94/110 (85.5%) |
| code-2 | 40 | 9.09 | 0.902 | 8.68 | 38 | 3.368 | 32 | 90/109 (82.6%) |
| code-3 | 38 | 16.83 | 2.261 | 10.19 | 26 | 4.923 | 0 | 102/107 (95.3%) |

coding decode mean 9.34 tok/s (range 8.68-10.19)
4k cold prefill mean 394.13 tok/s
draft acceptance 616/660 (93.3%)
foreign active samples during probes: 0
thermal states after probes: fair, nominal

## trial2
| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 86.28 | 4.479 | 12.5 | 13 | 7.385 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.75 | 2.169 | 12.37 | 13 | 7.385 | 352 | 83/83 (100.0%) |
| 4k-cold | 4064 | 393.98 | 10.327 | 11.97 | 14 | 6.857 | 0 | 82/84 (97.6%) |
| 4k-reuse | 4064 | 13.69 | 2.344 | 11.55 | 15 | 6.4 | 4032 | 81/87 (93.1%) |
| code-3 | 38 | 16.5 | 2.308 | 9.41 | 27 | 4.741 | 0 | 100/116 (86.2%) |
| code-2 | 40 | 9.53 | 0.859 | 9.3 | 34 | 3.765 | 32 | 93/106 (87.7%) |
| code-1 | 47 | 12.54 | 1.219 | 9.17 | 32 | 4.0 | 32 | 95/111 (85.6%) |

coding decode mean 9.29 tok/s (range 9.17-9.41)
4k cold prefill mean 393.98 tok/s
draft acceptance 617/670 (92.1%)
foreign active samples during probes: 0
thermal states after probes: fair

## pooled
| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 85.94 | 4.496 | 12.69 | 13 | 7.385 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.15 | 2.257 | 12.5 | 13 | 7.385 | 352 | 83/84 (98.8%) |
| 4k-cold | 4066 | 394.13 | 10.329 | 12.05 | 14 | 6.857 | 0 | 82/85 (96.5%) |
| 4k-reuse | 4066 | 13.65 | 2.499 | 12.89 | 13 | 7.385 | 4032 | 82/82 (100.0%) |
| code-1 | 47 | 11.63 | 1.314 | 9.15 | 33 | 3.879 | 32 | 94/110 (85.5%) |
| code-2 | 40 | 9.09 | 0.902 | 8.68 | 38 | 3.368 | 32 | 90/109 (82.6%) |
| code-3 | 38 | 16.83 | 2.261 | 10.19 | 26 | 4.923 | 0 | 102/107 (95.3%) |
| smoke-cold | 386 | 86.28 | 4.479 | 12.5 | 13 | 7.385 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.75 | 2.169 | 12.37 | 13 | 7.385 | 352 | 83/83 (100.0%) |
| 4k-cold | 4064 | 393.98 | 10.327 | 11.97 | 14 | 6.857 | 0 | 82/84 (97.6%) |
| 4k-reuse | 4064 | 13.69 | 2.344 | 11.55 | 15 | 6.4 | 4032 | 81/87 (93.1%) |
| code-3 | 38 | 16.5 | 2.308 | 9.41 | 27 | 4.741 | 0 | 100/116 (86.2%) |
| code-2 | 40 | 9.53 | 0.859 | 9.3 | 34 | 3.765 | 32 | 93/106 (87.7%) |
| code-1 | 47 | 12.54 | 1.219 | 9.17 | 32 | 4.0 | 32 | 95/111 (85.6%) |

coding decode mean 9.32 tok/s (range 8.68-10.19)
4k cold prefill mean 394.06 tok/s
draft acceptance 1233/1330 (92.7%)
foreign active samples during probes: 0
thermal states after probes: fair, nominal
