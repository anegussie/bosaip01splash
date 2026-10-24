# Option 19 performance test, 2026-10-24

Live Qwen3.6-35B-A3B UD-Q4_K_M on the Apple M5 with 16 GiB unified memory, through the actual `/Users/mymac/startllamacpp.sh --direct 19` launcher. This characterizes the current profile; no matched baseline was measured.

| Filled prompt | Median prefill tok/s | Median decode tok/s | Median request s | PP spread | Decode spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3,986 | 1161.39 | 32.94 | 7.26 | 2.28% | 1.30% |
| 12,176 | 996.65 | 31.17 | 16.36 | 11.92% | 2.35% |
| 20,366 | 878.77 | 30.07 | 27.41 | 3.28% | 1.26% |

Three uncached requests per context, each with zero reused prompt tokens and a distinct cache salt. The model process, expert cache and OS file cache were warm. These are not cold-machine or cold-SSD results. Spread is `(max - min) / mean`.

Recall/counting checks require ORCHID and the first ten numbers. Output is intentionally capped at 128 tokens, before the full count completes. Predictable counting throughput does not represent coding or prose throughput. The maximum configured context is 24,576; the table shows the actual filled prompts.

## Coding and prose

| Workload | Filled prompt | Output tokens | Prefill tok/s | Decode tok/s | Request s | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| coding-merge_intervals | 4,015 | 143 | 797.89 | 21.41 | 11.67 | True |
| coding-stable_unique | 4,016 | 41 | 785.51 | 22.87 | 6.87 | True |
| coding-chunked | 4,020 | 66 | 724.63 | 22.42 | 8.45 | True |
| varied-merge_intervals | 3,989 | 165 | 889.98 | 21.42 | 12.15 | True |
| varied-stable_unique | 3,990 | 36 | 780.15 | 21.96 | 6.71 | True |
| varied-chunked | 3,994 | 58 | 773.07 | 23.19 | 7.63 | True |
| varied-prose-escaped | 3,981 | 256 | 790.89 | 16.84 | 20.19 | True |

Coding checks execute merge_intervals, stable_unique and chunked on edge cases, including input preservation. Repeated-note and varied repository-source prompts are measured separately. Small utility tasks do not establish general coding quality. Prose checks cover topic and length, not factual quality; its output cap is 256 tokens.

## Prefix reuse

| Filled prompt | Reused tokens | First uncached s | Immediate replay s |
| --- | ---: | ---: | ---: |
| 3,986 | 3,968 | 7.23 | 4.62 |
| 12,176 | 12,160 | 16.36 | 4.80 |
| 20,366 | 20,352 | 27.10 | 4.80 |

Clean-restart replay reused 3,968/3,981 prompt tokens in 16.49s. Prefix reuse reduces prefill work; it does not prove faster generation.

## Configuration, conditions and validation

24K server / 22K client context, 2K output reserve, INT8 KV, BF16 state, 512-token chunks, one active request, reasoning off, DFlash2, automatic expert residency within an 8 GiB Metal budget, and a separate 2 GiB persistent prefix cache. Greedy sampling, seed 42; coding top-p 0.8 and top-k 20.

Checkout: `920faad11ac1d2c3e7ae00c5f3b75f7558ba0108`. Engine build: `src-17aa01b274ec2db4791bdc212074156f02c28a51532ee90eaf29764eeca8a7e9`. Target SHA-256: `ac0e2c1189e055faa36eff361580e79c5bd6f8e76bffb4ce547f167d53e31a61`. Exact target and draft revisions are retained in the JSON assembly manifest.

Thermal states: ['fair', 'nominal']; memory pressure: ['warning']. System swap before: vm.swapusage: total = 1024.00M  used = 52.25M  free = 971.75M  (encrypted); after: vm.swapusage: total = 2048.00M  used = 1192.94M  free = 855.06M  (encrypted). Swap-ins: 0.039 GiB; swap-outs: 1.145 GiB. These are system-wide observations.

Effective prefix-cache allowance: 2.00 GiB initially, 2.00 GiB after restart. Expert slots: 1325/10240.

Peak observed Metal allocation: 7.25 GiB. Minimum observed governor host headroom after reserves: 0.00 GiB. Governor headroom is not literal free RAM. Metal allocation is not total process RSS or total system memory use. Expert read-byte counters are retained per workload in the JSON; they describe model-file reads and do not establish physical SSD traffic.

Tool-call/result and SSE smoke passed. Requests before restart: {'submitted': 26, 'completed': 26, 'cancelled': 0, 'failed': 0}; after restart: {'submitted': 1, 'completed': 1, 'cancelled': 0, 'failed': 0}. Metal remained healthy. Both launchers stopped and port 1235 is closed.

First readiness (includes download/installation): 3829.23s. Restart readiness: 11.02s. Neither is included in request timings.

Raw requests, responses, before/after telemetry and launcher logs: `/Users/mymac/splash/splash/build/validation/option19-performance-20261024`. The global OpenCode configuration was not changed.
