# Option 20 verification-width comparison, November 6, 2026

Keep `verify-rows auto`. Fixed widths 2, 4 and 8 produced no coding throughput improvement in this experiment. The strongest fixed candidate, 8, was repeated against auto in A/B/B/A order: combined coding response time averaged 21.827 seconds for auto and 22.327 seconds for 8 (2.3% longer). Mean per-request decode throughput was 11.037 versus 10.713 tokens/s. These short probes do not establish a general regression or a winner across coding workloads.

M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. Exact model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2; target SHA-256 `261aef54bdfbeb8fb5bae01deeef4eb70f820fe19f410e4ed9de46c344969117`. Same installed binary and Metal libraries for all blocks, with hashes checked unchanged after execution. Runtime build ID `src-d3ea0ffe96934b78c61585e3965e6ccc76fea994a2f23b6c26b62f10b004d0cd`. No build or runtime source change was made for this experiment.

Every block used 131,072 served context, 2,048-token prefill chunks, 10.8G engine cap, automatic expert memory, 64M PLE row cache, INT8 KV, BF16 state, one active request, and a separate 16G persistent cache. The runner starts fresh HTTP servers sequentially on port 1245, waits for readiness and a 30-second idle period, then performs the cold/reuse gate. Each coding request follows a five-second pause. There was no pre-existing Splash server; every test server was stopped and waited for before the next block.

All requests used temperature zero, seed 42 and reasoning none. Each block first passed an exact ORCHID/count-to-30 smoke test, complete SSE, zero cached prompt tokens on cold input and nonzero prefix reuse on the repeat. Only then did timed coding requests run. The two tasks were merging sorted lists (59 prompt tokens, 96 output tokens) and bracket matching (56 prompt tokens, 84 output tokens). Both returned complete answers below their 256-token cap. Generated functions passed checks covering empty input, duplicates, empty list sides, nested brackets, mismatched and unmatched brackets, and ignored non-bracket characters. These are small functional probes, not an evaluation of complex code or long filled context.

All 16 coding responses passed and each task produced byte-identical output across all eight blocks. All 16 smoke responses passed exact output checks and all 32 requests finished SSE. Per-request completed counters increased by exactly one; failed counters, capacity failures and Metal failures did not increase. Cold coding requests had zero cached tokens.

| Block | Verify rows | Two coding responses, wall s | Mean decode tok/s | Expert source MB/output token | Output tokens/decode batch |
|---|---|---:|---:|---:|---:|
| screen-auto | auto | 21.918 | 11.051 | 564.47 | 6.429 |
| screen-2 | 2 | 29.811 | 7.442 | 796.86 | 1.978 |
| screen-4 | 4 | 24.467 | 9.512 | 644.94 | 3.913 |
| screen-8 | 8 | 22.399 | 10.718 | 585.80 | 6.923 |
| confirm-A1 | auto | 21.826 | 11.019 | 565.02 | 6.429 |
| confirm-B1 | 8 | 22.360 | 10.692 | 585.80 | 6.923 |
| confirm-B2 | 8 | 22.295 | 10.733 | 585.49 | 6.923 |
| confirm-A2 | auto | 21.827 | 11.055 | 564.28 | 6.429 |

The fixed-width candidate was selected by combined coding wall time from the screening blocks; screening rows are excluded from the confirmation means. Decode throughput is the arithmetic mean of the two per-request native decode rates. Combined wall time includes prefill and HTTP response completion. Expert source bytes are counter deltas divided by emitted tokens, in decimal MB: they measure bytes requested from expert sources, not physical SSD/NAND traffic, because OS caching is not flushed. Tokens per batch includes emitted output tokens and is a diagnostic, not a throughput measure. Width 8 emitted more tokens per batch but used more expert-source bytes per emitted token on this pair.

Memory pressure was normal at readiness and warning after all coding probes. Thermals ranged from nominal to fair. The first confirmation auto block and both width-8 blocks were fair after coding; the last auto block was nominal. Other desktop activity was uncontrolled. Swap snapshots were 714.38 MiB before the first block and 706.38 MiB after the last; these snapshots do not establish absence of swap activity. Low Power Mode was off in both battery and AC settings. A final power check showed AC attached at 80%; the runner overwrote its per-block battery-source field with the power-settings field, so continuous AC operation is not established by those records. Two confirmation blocks per setting, two short tasks, adaptive verification and thermal differences limit conclusions.

The Air launcher already uses auto, so no launcher default change was warranted. A different workload may favor a fixed width; this experiment supports retaining the current setting for these tasks.

[Summary JSON](qwen38-option20-verify-width-20261106.json) contains every coding result and binary identities. [Raw evidence](../../build/validation/option20-verify-20261106/) includes the runner, launch arguments, server logs, request payloads, complete parsed SSE events, before/after status, functional checks, host snapshots, initial worktree diff, and final artifact hashes. The cache directory contains experimental prefix-cache files and is separate from the launcher cache. No commit or push was performed.
