# Splash performance: 48-hour telemetry summary

Window: October 26, 2026, 09:17:45 to October 28, 2026, 09:17:45, America/Toronto (UTC-04:00). Source: `/Users/mymac/.local/state/llama-server/splash-performance.jsonl`. The calculation includes 558 complete, non-overlapping summary intervals contained within the window; their combined coverage is 46 hours 36 minutes 28 seconds. Gaps and intervals crossing the window boundaries are excluded.

Model: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS`. The context values below are configured limits, not measured filled context.

| Configured context | Build fingerprint prefix | PP tokens/s | Generation tokens/s | Completed requests |
|---:|---|---:|---:|---:|
| 24,576 | `src-a850c11` | 532.5 | 30.0 | 2,623 |
| 24,576 | `src-7e2e9dc` | 550.9 | 30.4 | 625 |
| 40,960 | `src-7e2e9dc` | 495.8 | 27.3 | 83 |
| 61,440 | `src-7e2e9dc` | 433.1 | 24.1 | 250 |
| 71,680 | `src-7e2e9dc` | 454.6 | 23.7 | 163 |
| 81,920 | `src-7e2e9dc` | 389.4 | 23.3 | 1,419 |
| **Overall** | **Both** | **488.6** | **26.8** | **5,163** |

Overall totals: 11,106,204 prefill tokens in 22,730,976.3661 ms; 1,106,082 output tokens in 41,299,784.9467 ms; 63,031,200 cached tokens; zero failed and 45 cancelled requests. Each rate is total stage tokens divided by total native stage elapsed time, not an average of interval rates. Idle time is excluded.

The full build fingerprints are `src-a850c11b2298b331e36c2c52e159c0d9c700e8e84d09a77dca2daa5adb18e327` and `src-7e2e9dc11f019304a5db05390e5a85e0a336ec7c1fb92fe58c337bc75b96d7dc`. Workloads, context usage, memory pressure, and thermal state varied, so these figures describe observed traffic rather than a controlled comparison.
