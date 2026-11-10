| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cached tokens |
|---|---:|---:|---:|---:|---:|
| smoke-cold | 385 | 87.04 | 4.426 | 12.54 | 0 |
| smoke-reuse | 385 | 15.23 | 2.178 | 12.42 | 352 |
| 4k-cold | 4067 | 312.15 | 13.04 | 11.55 | 0 |
| 4k-reuse | 4067 | 13.99 | 2.511 | 11.19 | 4032 |
| code-1 | 47 | 18.94 | 2.487 | 9.17 | 0 |
| code-2 | 40 | 16.92 | 2.368 | 9.66 | 0 |
| code-3 | 38 | 17.06 | 2.231 | 10.07 | 0 |

coding decode mean: 9.63 tok/s (range 9.17-10.07)
draft acceptance over all probes: 615/672 (91.5%)
