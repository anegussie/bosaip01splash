# Option 21 performance by context size

Q2_0 + BF16 DFlash2 on the 16 GiB Apple M5. Ranges cover two trials per context
with 96-token output budgets. Filled context includes chat-template tokens.
PP measures fresh-prompt processing; TPS measures decode. Cold means zero reused
prefix tokens, with the model and operating-system caches already warm.

| Filled context | PP tok/s | TPS | Cold first token | Cached TPS | Cached first token |
|---|---:|---:|---:|---:|---:|
| 363 | 111.8–112.0 | 25.3–27.1 | 3.24–3.25 s | 28.5–29.0 | 0.90–0.98 s |
| 4,031 | 464.4–469.3 | 27.4–28.0 | 8.59–8.68 s | 23.8–24.5 | 1.51–1.57 s |
| 8,204 | 436.0–445.1 | 25.9–27.6 | 18.43–18.82 s | 24.1–25.9 | 0.87–0.90 s |
| 16,396 | 310.7–392.8 | 24.3–27.2 | 41.74–52.77 s | 21.9–27.9 | 0.83–0.84 s |
| 65,548 | 276.3–345.2 | 22.8–23.6 | 189.88–237.26 s | 21.1–21.3 | 0.86–0.89 s |
| 102,412 | 264.9–306.8 | 22.1–23.9 | 333.78–386.58 s | 21.6–23.4 | 0.80–0.90 s |

All correctness and cache checks passed. Thermal state ranged from nominal to
fair; memory pressure reported warning. No new macOS swap-outs occurred during
the measured runs. These are current-condition measurements.

[Detailed report and raw evidence](qwen38-option21-performance-20261112.md).
