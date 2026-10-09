# Bonsai performance and correctness test, 2026-10-09

All ten real-model requests passed: six coding requests and four cold/cached context requests. No runtime source changes or upstream merge were made. This is the current local Bonsai build, not an upstream Bonsai comparison.

## Runtime contract

Apple M5, eight GPU cores, 16 GiB unified memory. `prism-ml/Ternary-Bonsai-2-27B-gguf:PTQ1_0`, existing DFlash draft, INT8 KV, 24,576 server context, 512-token prefill chunks, one active request, persistent 8 GiB disk-cache quota, temperature zero and reasoning none. Coding requests used seed 42, top_p 0.8, top_k 20 and a 384-token output limit; context requests used a 96-token output limit. All requests used the already-running endpoint on port 1235, which was left running.

Live build ID: `src-5a54ebc57301fb80a33e2d009aab28419fbdff023c223b4ac4acdea9ed9bb590`.

## Coding correctness and decode

Each task ran twice against about 3,660 prompt tokens of synthetic repository notes. The generated functions passed behavioral checks for expected values, empty inputs and input mutation; merge_intervals covers nested/touching intervals, stable_unique covers unhashable objects, and chunked covers invalid sizes. Both responses to each task matched exactly.

| Task | Decode tok/s, median | Draft acceptance | Output tokens per run | Checks |
| --- | ---: | ---: | ---: | --- |
| merge_intervals | 33.89 | 71.43% | 109 | 2/2 passed |
| stable_unique | 30.42 | 66.07% | 46 | 2/2 passed |
| chunked | 36.03 | 78.57% | 53 | 2/2 passed |

The first merge_intervals and stable_unique requests were cold (0 cached prompt tokens), processing prompts at 199.60 and 189.20 tok/s. Their repeats reused 3,648 tokens. The first chunked request reused 3,584 tokens from the shared repository context, so its initial prefill is not a cold sample. All six requests were isolated; total request time includes prefill/cache restoration and decode. These short utility functions differ from the earlier 256-token code-review response, which measured about 21.11 decode tok/s and 37.96% acceptance; the task and acceptance differences prevent treating the higher utility rates as a runtime speedup.

## Longer prompts

Unique labels at the beginning of each prompt prevented cold-prefix reuse, verified from the response. Both depths recalled ORCHID; cold and cached responses matched exactly. Draft acceptance was 91.21% for the repetitive counting output.

| Prompt tokens | Cold prefill tok/s | Cold decode tok/s | Cold total s | Cached total s | Reused tokens |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8,143 | 184.22 | 37.28 | 46.704 | 2.935 | 8,128 |
| 16,423 | 132.75 | 28.49 | 126.997 | 3.831 | 16,416 |

Cold prompt-processing time was 44.202 s at 8,143 tokens and 123.715 s at 16,423 tokens. Cached decode rates were 37.17 and 28.37 tok/s respectively: cache reuse primarily removed prefill work, rather than speeding decode. These are one cold and one cached sample per depth; depth and test order are confounded with thermal/host state, so the lower 16K rates cannot be attributed to context length alone.

## Health and memory

All ten requests completed, none failed or were cancelled, and Metal remained healthy. The generated utility functions passed all checks, and all five pairs of responses repeated exactly. Request snapshots confirm one submitted/completed request per measurement.

Memory pressure remained warning. During the context phase, system swap changed from `vm.swapusage: total = 4096.00M  used = 3227.81M  free = 868.19M  (encrypted)` to `vm.swapusage: total = 4096.00M  used = 3473.88M  free = 622.12M  (encrypted)`: +246.07 MiB system-wide. This does not attribute paging to Splash. Metal current allocation rose from 8.005 to 8.513 GiB; these are device allocations, not process RSS. No zero-swap claim is made.

## Limits and artifacts

No controlled thermal cooldown or other-app workload control was applied. Upstream `c35f3ea` cannot directly run the local PTQ1_0 model; a matched current/upstream Bonsai comparison still requires explicit PTQ1_0 compatibility work and resolving the draft-restoration buffer-size mismatch. Current source, configuration and service were left unchanged.

Raw responses, complete native status snapshots and summary: `build/validation/bonsai-performance-20261009/`. Coding harness: `dev/benchmarks/bonsai_coding.py`; context runner is copied beside the raw results.
