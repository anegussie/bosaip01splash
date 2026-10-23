# Option 18 performance characterization, 2026-10-23

Qwen3.6-35B-A3B UD-Q2_K_XL ran successfully through the live option-18 launcher on the 16 GiB Apple M5. Small executable coding tasks with varied repository-source context measured 59.1-69.2 decode tok/s. A 256-token prose sample measured 41.3 tok/s. These are workload-specific observations, with no matched baseline or speedup claim.

Profile: Splash Metal, 8 GPU cores, macOS 26.5.2; 8 GiB Metal budget, 24,576-token server context, 22,528-token OpenCode context, 2,048-token OpenCode output limit, INT8 KV, BF16 recurrent state, 512-token prefill chunks, one active request, text only, reasoning none. Qwen3.6 DFlash2 is active with automatic verification rows. Tests used greedy sampling and seed 42; coding also specified top_p 0.8 and top_k 20. Recall/counting output cap was 128 tokens, coding 384, and final prose 256; actual output lengths appear in the tables.

The process and expert cache were already warm. An uncached prompt below means zero reused prompt tokens, not a cold machine, process, SSD, or expert cache. Native weights were not rebuilt or restarted during measurement.

## Recall and counting

These prompts use repeated repository notes followed by final-code recall and capped counting. Counting is highly predictable and had roughly 97-100% draft acceptance. It is a separate workload from code or prose.

| Workload | Filled prompt | Cached | Output | Prefill tok/s | Decode tok/s | Request s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4K uncached, median of 3 | 3,986 | 0 | 128 | 1,280.91 | 119.28 | 4.18 |
| 4K repeated prefix | 3,986 | 3,968 | 128 | tail only | 112.03 | 1.50 |
| 12K uncached | 12,176 | 0 | 128 | 1,184.34 | 113.54 | 11.41 |
| 20K uncached | 20,366 | 0 | 128 | 1,032.93 | 106.86 | 20.93 |
| 20K repeated, no reuse | 20,366 | 0 | 128 | 1,035.73 | 107.74 | 20.84 |

The 12K and 20K rows are single samples. All final-code and counting checks passed. The longest filled prompt was 20,366 tokens; this is not a filled-24K benchmark.

## Varied source context

The following prompts contain approximately 3,900 tokens of actual excerpts from server/tokenization.py, server/constraints.py, and server/frontend.py. All prompts report zero reused tokens. Coding validates edge cases and input preservation with the existing executable checker; six of six coding requests passed across repeated-note and varied-source contexts.

| Workload | Filled prompt | Output | Prefill tok/s | Decode tok/s | Request s |
| --- | ---: | ---: | ---: | ---: | ---: |
| merge_intervals | 3,989 | 145 | 1,246.36 | 59.11 | 5.64 |
| stable_unique | 3,990 | 46 | 1,251.17 | 62.94 | 3.91 |
| chunked | 3,994 | 96 | 1,249.83 | 69.22 | 4.57 |
| Prose, escaped chat markers | 3,981 | 256 | 1,260.43 | 41.26 | 9.34 |

The prose sample reached its intentional 256-token cap (finish=length). These small utility tasks and a capped explanation do not establish general coding or prose quality.

## Cache, memory, and reliability

The 4K repeated request reused 3,968 of 3,986 prompt tokens, reducing request latency from 4.36 to 1.50 seconds. This saves prefill work; it does not establish a decode speedup. At 20K the repeated request reused zero tokens and took 20.84 seconds, essentially another full prefill.

The 20K run allocated a second KV extent, leaving only about 0.18 MiB of governor budget headroom. No reusable GDN state remained, and checkpoint publication failures were recorded. Effective disk prefix-cache allowance was zero despite a configured 2 GiB quota, because the volume was below the runtime's 10 GiB free-space reserve. These observations are consistent with insufficient checkpoint capacity under the current memory and disk limits. SSD expert streaming remained active throughout.

All **21 API requests completed**, with zero failed or cancelled requests, and Metal healthy at sampled boundaries. All recall/counting checks, six executable coding checks, a forced tool-call/result round trip, and SSE completion passed. Short streaming time to first content was 0.334 seconds. No competing inference requests were observed by the per-request counter checks.

Two initial prose outputs stopped mid-sentence immediately before quoting the literal chat-control marker in the raw source. They are retained as diagnostic samples and excluded from prose throughput conclusions. Marker emission is the likely cause, an inference supported by the escaped-marker prompt reaching its 256-token cap. The raw responses, the failed long-prose assertion, and both prompt variants are preserved.

Thermal state was nominal at every sampled boundary; system memory pressure was warning. System swap was 4,034.88 MiB before and 3,994.88 MiB after, with 0 new swapouts across the observation window. This is not a zero-swap system or attribution of existing swap to Splash. Maximum reported Metal allocation peak was 7.26 GiB, including process warmup; this is not total process RSS.

The three 4K uncached counting decode rates were 101.42, 121.62, and 119.28 tok/s: **17.70% spread**, computed as (max-min)/mean. This exceeds the 5% comparison threshold, so these results are characterization, with no stable improvement/regression claim. Longer-context and prose rows have one sample each.

## Identity and reproduction

Checkout: `b3a4348ff03b75b93cef103103cf76f988485396`. Active native build: `src-17aa01b274ec2db4791bdc212074156f02c28a51532ee90eaf29764eeca8a7e9`. The server was measured in place after startup and left online with the same production configuration.

Target: `unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL`, 12,290,628,576 bytes. Verified SHA-256: `96b9c0af5c77a4ecaabe3983175112b5ece763261c1ece12b2494b692a70dad7`. Target revision: `a483e9e6cbd595906af30beda3187c2663a1118c`. Draft: `incoai/Qwen3.6-35B-A3B-DFlash2` at `51ef7b6923ad6c14cb1bb41c37a9041446496ab6`.

Expert store: 3,428 slots for 10,240 experts, 3.34 GiB arenas plus 300 MiB staging.

Raw runner, requests, responses, per-request status snapshots, source excerpts, and run history: `/Users/mymac/splash/splash/build/validation/performance-option18-20261023`. Active launcher log: `/Users/mymac/.local/state/llama-server/qwen3.6-35b-a3b-q2-splash-20261023-134906.log`. Machine-readable summary: [qwen36-option18-performance-20261023.json](qwen36-option18-performance-20261023.json).
