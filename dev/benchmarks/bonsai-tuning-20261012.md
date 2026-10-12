# Bonsai state and prefill tuning, 2026-10-12

Selected option-14 default: **BF16 recurrent state, 512-token prefill chunks**. Coding decode is effectively unchanged, while backend buffers after the matched workload are 216 MiB smaller. This is a memory improvement; no end-to-end speedup is established.

## Workload

Apple M5, 8 GPU cores, 16 GiB RAM; runtime commit `60b0099151538075961d054fd1e1639f40d29db1` (runtime from `e51378a2`). Bonsai 27B PTQ1_0 target revision `b072e1d3b35a0a630cece372c2127528e0994386`, Qwen3.8-27B DFlash2 revision `015e795645c74b1a0eeef3b570031fb62e769bc5`; Splash Metal; INT8 KV; 24,576 declared context; one active request; GPU-only prefill; 8 GiB temporary SSD cache; greedy sampling; reasoning none.

Six fresh-server rounds: FP32/512, BF16/512, BF16/1024, BF16/1024, BF16/512, FP32/512. There was a 60-second cooldown between servers, then a wait of up to 180 seconds for nominal thermal state after readiness. Every measured round began nominal. Cooling did not eliminate timing variation.

Each round ran three Python coding tasks with 3,662–3,667 prompt tokens, then a cold and repeated 4,892-token recall/counting prompt with 96 output tokens. The chunked coding task reused 3,584 tokens; the other coding prompts and cold recall request reused zero tokens. Every recall repeat reused 4,864 tokens.

## Results

| Profile | Coding decode, tok/s | Cold prefill, tok/s | Cold request, s | Cached request, s | Fixed plan, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| fp32-512 | 33.63 | 179.34 | 29.87 | 3.06 | 8501.14 |
| bf16-512 | 33.53 | 174.34 | 30.74 | 3.04 | 8429.14 |
| bf16-1024 | 33.54 | 171.91 | 31.70 | 3.58 | 8537.60 |

Coding decode is the reciprocal of mean round milliseconds per token, each round using the geometric mean across the three coding tasks. Cold prefill is 4,892 tokens divided by mean prompt time. Request times are means of the two rounds per profile. These figures characterize observed runs, not proven speed changes.

The repository ABBA rule passes the aggregate coding-decode comparison: BF16/512 is 0.30% slower in time than FP32/512, with 4.70% within-build spread. The individual stable_unique comparison and the cold/cached end-to-end comparisons exceed the 5% noise limit and are inconclusive. BF16/1024 has effectively the same coding decode as BF16/512 (-0.03% in time), while cold prefill time is 1.41% longer with 0.69% spread. It increases planned prefill workspace by 108.47 MiB.

All 18 coding behavioral checks and 12 recall requests passed, with zero failed native requests and healthy Metal. Outputs repeat exactly within each profile. BF16 changed the chunked function text relative to FP32; both implementations pass all behavioral checks. DFlash acceptance stayed at 71.43% for merge_intervals and 66.07% for stable_unique; chunked rose from 78.57% to 80.36%.

BF16/512 reduces cached-state size from 152.62 to 80.62 MiB, lane-state allocation from 339.62 to 195.62 MiB, and state staging by 72 MiB. The fixed plan falls by 72 MiB because lane state is elastic. At the end of every matched round, backend buffer allocation is 8,511,040,640 bytes for BF16/512 versus 8,737,533,056 for FP32/512, a 216 MiB reduction. This is neither process RSS nor a zero-swap claim.

## Implementation

`/Users/mymac/startllamacpp.sh` option 14 defaults to `SPLASH_BONSAI_STATE_FORMAT=bf16` and retains 512-token chunks. The menu and startup log show the state format; invalid state values are rejected before OpenCode configuration mutation. `SPLASH_BONSAI_STATE_FORMAT=fp32` restores the former precision. The runtime/server defaults remain FP32 for other launches. The separate `watchllamacpp.sh` does not launch option 14; its in-launcher pressure monitor is unchanged.

The incremental launcher edit is [startllamacpp-option14-state.patch](startllamacpp-option14-state.patch). Raw replies, logs, status, and the local run script are retained in `build/validation/performance-tuning-20261012/`. The machine-readable comparison is [bonsai-tuning-20261012.json](bonsai-tuning-20261012.json).

## Validation

Eight staged launcher tests passed, covering state/chunk forwarding and invalid state overrides as well as existing context, cache, retry and cleanup behavior. Shell syntax checks pass for the launcher and watchdog. The installed launcher also passed all eight tests. Its actual API passed all three coding checks at 32.1–37.6 decode tok/s, followed by a 22,854-token prompt that correctly recalled AZURE from record 0, VIOLET from record 500, and ORCHID from the final record.

The long cold request used zero cached tokens and took 143.89 seconds. After a clean launcher restart, the same prompt reused 22,816 tokens and returned the same answer in 1.64 seconds. Server startup was separate: 13.47 seconds, 15.76 seconds. Both rounds reported BF16 state, 512-token chunks, 24,576 context, healthy Metal and zero failed requests. This demonstrates persistent-prefix reuse; it does not establish faster uncached computation or long-generation throughput. All temporary servers were stopped.
