# Speculation log review, 2026-10-16

DFlash2 speculation is active and amortizes target verification across multiple emitted tokens. The logs suggest a workload-dependent benefit, but do not establish net latency improvement versus target-only decoding: no matched speculation-off baseline was found.

Reviewed option-14 log `bonsai-27b-splash-20261015-224839.log`, from October 15 at 22:48 through October 16 at 10:47 EDT. It contains 719 completed request records. The server stopped at 10:47:34 and port 1235 was unavailable at review time. No inference requests or configuration changes were made.

Runtime: Apple M5 with eight GPU cores; Bonsai 2 27B PTQ1_0, Splash Metal, `incoai/Qwen3.8-27B-DFlash2` draft revision `015e795645c74b1a0eeef3b570031fb62e769bc5`, target revision `b072e1d3b35a0a630cece372c2127528e0994386`, INT8 KV, BF16 state, 512-token prefill chunks, 24,576 configured context and one active request. Build `src-c988c87eac16f999a9e5b5df5f0823c8671a3ce7eb6bc32f79090735cd6a8737`. Mixed real tool/chat traffic, input median 13,013 and p95 20,859 tokens; sampling is not fully recorded. Persistent cache and nominal/fair thermal transitions are present. No current swap measurement is available after shutdown.

| Measurement | Result |
| --- | ---: |
| Accepted / proposed draft tokens at final snapshot | 117,807 / 264,033 = 44.62% |
| Per-request tokens per speculative cycle, p10 / median / p90 | 2.9 / 4.2 / 6.0 |
| Native batch decode at final snapshot | 16.63 tok/s over 156,218 tokens |
| Stream decode across all 719 log records | 16.54 tok/s |
| Stream decode over final 50 requests | 18.14 tok/s |
| Failed / cancelled / Metal failures at final snapshot | 0 / 0 / 0 |

The final compact status snapshot is at 10:38:56 and covers 714 completed requests. Five more completed afterward. Native batch and stream decode counters have different timing boundaries and should not be equated.

Among requests with at least 64 logged decode tokens:

| Tokens per speculative cycle | Requests | Aggregate stream decode |
| --- | ---: | ---: |
| Below 3 | 59 | 10.89 tok/s |
| 3 to below 5 | 342 | 15.14 tok/s |
| 5 or more | 135 | 23.73 tok/s |

Higher accepted output per cycle correlates with higher throughput. These groups differ in prompt content, context, cache and thermal conditions; this is not a controlled speedup measurement. The diagnostic computes tokens/cycle as `1 + accepted_draft_tokens / cycles`; 4.2 tokens/cycle does not mean 4.2 times faster, because drafting and wider target verification consume time.

At the final snapshot the memory governor denied 2,043 reservations, disabled growth and reported zero host headroom, while capacity failures remained zero. These conditions and thermal variation can affect observed speed. Prefix-cache reuse saves prefill work and does not establish a speculative decode gain.

Keep the current configuration pending a matched on/off comparison using representative tool requests, identical model/build/KV/state, filled context, sampling and cache state, with controlled thermal conditions. Compare complete request latency and decode cost while checking output quality. The logs alone support active, useful multi-token emission, not a quantified net speedup or proof that disabling it would be faster.

The committed [data summary](bonsai-speculation-review-20261016.json) includes aggregates, interval counters and all 719 parsed request records with source log line numbers. The source log snapshot and analysis script remain locally under `build/validation/speculation-review-20261016/`.
