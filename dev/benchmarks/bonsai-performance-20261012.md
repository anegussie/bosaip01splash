# Bonsai performance, 2026-10-12

Commit: `e51378a29d45ee0f912c59a43c6307278bc3b159`. Three fresh-server rounds on Apple M5, 8 GPU cores, 16 GiB RAM.

Bonsai 27B PTQ1_0; DFlash2; Splash Metal; GPU-only prefill; INT8 KV; FP32 state; 24,576 declared context; 512-token prefill chunks; one active request; 8 GiB temporary SSD cache; greedy sampling, reasoning none.

| Measurement | Median | Range |
| --- | ---: | ---: |
| merge_intervals decode, tok/s | 32.83 | 27.88–34.55 |
| stable_unique decode, tok/s | 29.23 | 25.62–31.99 |
| chunked decode, tok/s | 33.67 | 29.13–36.86 |
| Cold request, seconds | 30.45 | 28.45–34.35 |
| Cold counting decode, tok/s | 35.40 | 31.62–38.04 |
| Cold prefill, tok/s | 176.24 | 156.08–188.56 |
| Cached request, seconds | 3.03 | 2.69–3.79 |
| Cached counting decode, tok/s | 34.67 | 27.49–39.41 |

Coding behavioral checks and recall results are recorded in [the summary](bonsai-performance-20261012.json). Actual context test prompt: 4,892 tokens. This measures the current build; it is not a controlled before/after comparison or a filled-24K benchmark. Raw replies, server logs and run metadata remain locally in `build/validation/performance-20261012/`; the committed summary retains status, thermal state and system swap.

All 9 coding behavioral checks and all 6 recall requests passed. Outputs were identical across rounds; all 15 requests completed with zero failures and healthy Metal. Draft acceptance: merge_intervals 71.43%, stable_unique 66.07%, chunked 78.57%.

Each cold context request had 0 cached tokens; every repeated context request reused 4,864 of 4,892 tokens. The chunked coding prompt reused 3,584 tokens; the other coding prompts were cold.

Thermal state: nominal in round one, fair in rounds two and three. Memory pressure: warning throughout. Observed timing spread was 18–35%; no speedup or regression conclusion is supported. System swap was already about 3.1 GiB; this is not attributable to Splash alone. Fixed planned runtime memory: 8,501.14 MiB.

Model sources:

- draft: `incoai/Qwen3.8-27B-DFlash2`, revision `015e795645c74b1a0eeef3b570031fb62e769bc5`.
- target: `prism-ml/Ternary-Bonsai-2-27B-gguf`, revision `b072e1d3b35a0a630cece372c2127528e0994386`.

Temporary benchmark servers were stopped.
