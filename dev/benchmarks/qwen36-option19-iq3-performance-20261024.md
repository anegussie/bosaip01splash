# Option 19 IQ3_XXS performance test, 2026-10-24

Live Qwen3.6-35B-A3B UD-IQ3_XXS on the Apple M5 with 16 GiB unified memory, through option 19 of the actual `/Users/mymac/startllamacpp.sh` launcher. Initial measurements reused an idle interactive launch; the clean restart used `--direct 19`. This characterizes the current profile; no matched baseline was measured.

Five of six executable coding checks passed. The failed varied-source merge_intervals response mutated input; its original response and failure are retained without retry.

| Filled prompt | Median prefill tok/s | Median decode tok/s | Median request s | PP spread | Decode spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3,986 | 1277.71 | 104.20 | 4.34 | 0.61% | 14.34% |
| 12,176 | 1108.52 | 94.02 | 12.38 | 3.78% | 8.33% |
| 20,366 | 999.07 | 96.50 | 21.77 | 5.50% | 4.98% |

Three uncached requests per context, each with zero reused prompt tokens and a distinct cache salt. The model process, expert cache and OS file cache were warm. These are not cold-machine or cold-SSD results. Spread is `(max - min) / mean`.

Recall/counting checks require ORCHID and the first ten numbers. Output is intentionally capped at 128 tokens, before the full count completes. Predictable counting throughput does not represent coding or prose throughput. The maximum configured context is 24,576; the table shows the actual filled prompts.

## Coding and prose

The varied-source merge_intervals response failed input preservation: it sorted a shallow outer copy, reused the input interval lists, then mutated an inner list while merging. This failure is retained and was not retried. The remaining independent utility checks continued.

| Workload | Filled prompt | Output tokens | Prefill tok/s | Decode tok/s | Request s | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| coding-merge_intervals | 4,015 | 118 | 1023.52 | 60.60 | 5.86 | True |
| coding-stable_unique | 4,016 | 41 | 1137.48 | 49.61 | 4.35 | True |
| coding-chunked | 4,020 | 65 | 1099.37 | 57.64 | 4.77 | True |
| varied-merge_intervals | 3,989 | 134 | 1174.25 | 57.87 | 5.70 | False |
| varied-stable_unique | 3,990 | 139 | 1245.17 | 61.91 | 5.44 | True |
| varied-chunked | 3,994 | 54 | 1243.52 | 51.83 | 4.24 | True |
| varied-prose-escaped | 3,981 | 256 | 1204.76 | 39.68 | 9.74 | True |

Coding checks execute merge_intervals, stable_unique and chunked on edge cases, including input preservation. Repeated-note and varied repository-source prompts are measured separately. Small utility tasks do not establish general coding quality. Prose checks cover topic and length, not factual quality; its output cap is 256 tokens.

## Prefix reuse

| Filled prompt | Reused tokens | First uncached s | Immediate replay s |
| --- | ---: | ---: | ---: |
| 3,986 | 3,968 | 4.50 | 1.70 |
| 12,176 | 12,160 | 12.05 | 1.78 |
| 20,366 | 20,352 | 21.48 | 1.76 |

Clean-restart replay reused 3,968/3,981 prompt tokens in 6.95s. Prefix reuse reduces prefill work; it does not prove faster generation.

## Configuration, conditions and validation

24K server / 22K client context, 2K output reserve, INT8 KV, BF16 state, 512-token chunks, one active request, reasoning off, DFlash2, automatic expert residency within an 8 GiB Metal budget, and a separate 2 GiB persistent prefix cache. Greedy sampling, seed 42; coding top-p 0.8 and top-k 20.

Checkout: `7f2c6a619e10790b20a89a72abb76737d353f4d7`. Engine build: `src-17aa01b274ec2db4791bdc212074156f02c28a51532ee90eaf29764eeca8a7e9`. Target SHA-256: `9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe`. Exact target and draft revisions are retained in the JSON assembly manifest.

Thermal states: ['fair', 'nominal']; memory pressure: ['warning']. System swap before: vm.swapusage: total = 3072.00M  used = 2247.06M  free = 824.94M  (encrypted); after: vm.swapusage: total = 3072.00M  used = 2239.06M  free = 832.94M  (encrypted). Swap-ins: 0.006 GiB; swap-outs: 0.000 GiB. These are system-wide observations.

Effective prefix-cache allowance: 2.00 GiB initially, 2.00 GiB after restart. Expert slots: 2959/10240.

Peak observed Metal allocation: 7.26 GiB. Minimum observed governor host headroom after reserves: 0.20 GiB. Governor headroom is not literal free RAM. Metal allocation is not total process RSS or total system memory use. Expert read-byte counters are retained per workload in the JSON; they describe model-file reads and do not establish physical SSD traffic.

Coding checks passed: 5/6. Tool-call/result and SSE smoke passed. Requests before restart: {'submitted': 26, 'completed': 26, 'cancelled': 0, 'failed': 0}; after restart: {'submitted': 1, 'completed': 1, 'cancelled': 0, 'failed': 0}. Metal remained healthy. Both launchers stopped and port 1235 is closed.

Model prefetch: 13.21 GB in 2734.02s, excluded from inference timings. Initial server startup: unmeasured (reused the existing idle IQ3 launcher). Restart readiness: 11.02s. Download, installation and readiness are excluded from request timings.

Raw requests, responses, before/after telemetry and launcher logs: `/Users/mymac/splash/splash/build/validation/option19-iq3-performance-20261024`. The global OpenCode configuration was not changed.
