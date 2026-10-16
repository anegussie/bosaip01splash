# Option 16 performance, 2026-10-15

Measured the real `/Users/mymac/startllamacpp.sh --direct 16` launcher in three fresh sessions, followed by a clean restart, tool-call/result round trip, SSE/FIFO queue check, and longer recall prompts. This characterizes the current build; there is no matched baseline or speedup claim.

Apple M5, 8 GPU cores, 16 GiB unified memory. Ternary Bonsai 2 27B Uncensored Heretic PTQ1_0; Splash Metal with active `incoai/Qwen3.8-27B-DFlash2` speculation. INT8 KV, BF16 recurrent state, 512-token prefill chunks, configured context 24,576, one active request. Greedy, seed 42, reasoning none. Coding output cap 384 tokens, recall cap 96. Filled prompt lengths and actual output lengths are recorded in the JSON.

Checkout `2753e6afbb86f72bb0927726ca64ad216c750900`. Native build `src-c988c87eac16f999a9e5b5df5f0823c8671a3ce7eb6bc32f79090735cd6a8737`.

Target artifact: `/Users/mymac/.cache/huggingface/hub/models--prism-ml--Ternary-Bonsai-2-27B-gguf/snapshots/b072e1d3b35a0a630cece372c2127528e0994386/Ternary-Bonsai-2-27B-Uncensored-Heretic-PTQ1_0.gguf` (5,946,648,928 bytes), SHA-256 `a18c3e17da397838305522b3ee877f9d2cbf4facd04ba01a394b22f3f3a477be`.

Resolved selection: `/Users/mymac/splash/splash/install/models/.selections/95c14e2a5970ea9fe1423a3943ddb179ec3e1112c079e6d79c8ee4d952335e99`. Draft revision `015e795645c74b1a0eeef3b570031fb62e769bc5`; safetensors digest `67fc76d68dc5a9415511a4f394ef744d67510cd20e93b37cc2cc7d28e4bab65c`. The complete model assembly is retained in the summary JSON.

## Three-session results

Values are medians of three identical workloads on fresh server processes. Coding requests share their repository-note prefix within each session; reuse is reported by the cached-token column. The separate recall cold requests each report zero cached tokens.

| Workload | Prompt tokens | Cached tokens | Prefill tok/s | Decode tok/s | Request seconds | Draft acceptance | Decode spread |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| coding-merge_intervals | 3,662 | 0 | 192.66 | 41.17 | 22.156 | 88.1% | 4.91% |
| coding-stable_unique | 3,663 | 0 | 188.43 | 30.50 | 20.759 | 67.3% | 10.63% |
| coding-chunked | 3,667 | 3,584 | 126.39 | 30.71 | 2.217 | 69.6% | 12.67% |
| context-220-cold | 4,892 | 0 | 182.13 | 42.13 | 29.120 | 100.0% | 11.48% |
| context-220-cached | 4,892 | 4,864 | 118.74 | 40.74 | 2.595 | 100.0% | 14.05% |

Prefill and decode rates are the server response timing fields. Draft acceptance comes from per-request metric deltas. Decode spread is (maximum - minimum) / mean across the three sessions. Cache reuse saves prefill work; cached prefill rates reflect only the uncached tail and should not be compared with cold prefill rates.

## Restart and longer prompts

| Workload | Prompt tokens | Cached tokens | Prefill tok/s | Decode tok/s | Request seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| restart-context-220-first | 4,892 | 4,864 | 112.49 | 47.21 | 2.401 |
| restart-context-220-cached | 4,892 | 4,864 | 126.62 | 47.05 | 2.329 |
| context-560-cold | 12,712 | 0 | 176.75 | 36.56 | 74.538 |
| context-560-cached | 12,712 | 12,704 | 41.29 | 38.00 | 2.739 |
| context-920-first (partially cached) | 20,992 | 8,192 | 149.91 | 31.76 | 88.425 |
| context-920-cached | 20,992 | 20,960 | 105.05 | 31.42 | 3.359 |

Longer prompts have one first/repeated pair per depth and are single-sample observations. The 12,712-token first request was fully cold; the 20,992-token first request reused 8,192 tokens and prefills only its remaining 12,800 tokens. Its prefill rate is not a full cold 21K measurement. Recall validation requires the final code ORCHID; the capped counting continuation is not a complete long-form correctness evaluation.

## Correctness and runtime health

All 25/25 requests completed: 9/9 executable Python coding checks, 12/12 final-code recall checks, the two-request forced tool round trip, and two requests for streaming/queueing. Zero failed or cancelled requests; Metal healthy at every sampled boundary. DFlash2 drafted tokens in every phase.

Clean restart restored 4,864 tokens with identical output. SSE reached its first content token in 0.196 s; a queued second request was observed (peak frontend waiting 1).

The synthetic coding checks exercise empty inputs, endpoint/nested interval merges, unhashable stable deduplication, invalid chunk sizes, and input preservation. They do not establish general coding quality.

The harness stopped after the final successful request because it expected zero cache reuse at the last depth. The preserved raw run contains that assertion. Final verification confirms the completed-request log, all saved outputs and health assertions, and classifies that first long request as partially cached. The final live status sample was captured during request 10, with nine requests completed at that instant; request 10 completion is confirmed by the response and launcher log. The runner now permits earlier-prefix reuse at this depth.

## Measurement conditions

Thermal states at phase boundaries: nominal, nominal, nominal, nominal, nominal, fair, nominal, fair. Per-request thermal transitions and spreads are retained in the JSON. Memory pressure was recorded for every measured request. Treat thermal variation or spread above 5% as unsuitable for a comparative performance claim.

System-wide swap: 5630.50 MiB before, 5710.00 MiB after; highest phase-boundary sample 5710.00 MiB. Swap ownership is not attributed to Splash and no zero-swap claim is made. Actual memory snapshots are retained in the JSON.

Maximum reported Metal allocation peak: 8.44 GiB. This is the backend's allocation accounting, not total process RSS or system memory use.

Requested persistent cache quota was 8 GiB; effective quotas at phase starts were 3.43 GiB, 3.26 GiB, 3.09 GiB, 3.09 GiB.

All test servers stopped. Removed only this run's three scratch caches (3.11 GiB allocated). The production launcher configuration was not edited. Used isolated OpenCode configuration, logs and caches on port 1236; the normal API port 1235 was unused and monitored for competing work.

Raw responses, status snapshots, exact runner and logs: `/Users/mymac/splash/splash/build/validation/performance-option16-20261015`. Machine-readable summary: [bonsai-option16-performance-20261015.json](bonsai-option16-performance-20261015.json).
