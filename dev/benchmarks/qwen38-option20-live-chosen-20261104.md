# Option 20 live chosen-configuration performance - 2026-11-04

Measured through the existing live HTTP server. No build or restart was performed.

Server build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Checkout HEAD: `05d272aae89301687994e487bd14a52835104be9`. These identities describe different things; this is a live-service characterization, not validation of a newly built engine.

M5 MacBook Air, 16 GB unified memory; GSQ-RCO IQ3_XXS Flash-Next with DFlash2, INT8 KV/BF16 state; 131,072 served context, 10 GiB Metal cap, 1,024-token chunks, 16 GiB persistent prefix-cache quota, expert memory auto, two active-request lanes, verify-rows auto.

Fresh unique salts make cold-prefix rows cold by construction. The OS file cache is not flushed. Reuse rows hold the prompt and salt fixed. Cooldowns are 10 seconds. Temperature 0, seed 42, reasoning none for ORCHID rows; 160 output tokens permit the full count to 30. The earlier 96-token harness checked only 1-10 and truncated this response, so decode output lengths differ from those old rows. SSE TTFT measures first nonempty content; prefill/decode rates and speculation are native per-request values.

Clean rows exclude observed foreign active requests, submitted/completed request counter mismatches, idle waits >=30 s, and native queues >=100 ms. Only clean rows enter means. No timed subagent delegation was performed. The explicit concurrency probes follow the serial matrix.

| Actual prompt tokens | Clean cold trials | Cold prefill tok/s (mean; range) | Cold SSE TTFT mean, s | Reuse SSE TTFT mean, s | Cold decode tok/s mean |
|---:|---:|---:|---:|---:|---:|
| 4,019 | 3 | 203.93; 203.67-204.24 | 19.713 | 1.535 | 12.58 |
| 28,589 | 3 | 168.69; 164.48-174.28 | 169.601 | 1.148 | 11.84 |
| 65,367 | 1 | 149.40; 149.40-149.40 | 437.618 | 2.110 | 11.18 |

The 65k group has one cold/reused pair and does not establish variability. Longer filled-131k inference was not tested.

Correctness and SSE: `{"clean": 22, "contaminated": 0, "correctness_passed": 16, "correctness_probes": 16, "sse_complete": 22, "total": 22}`. Contaminated rows: `[]`.

## Output styles

| Style | Clean | Decode tok/s | Draft acceptance | Tokens/cycle | Reasoning tokens | Finish reason |
|---|---:|---:|---:|---:|---:|---|
| style-primes | True | 12.37 | 1.0 | 7.714 | 0 | stop |
| style-arithmetic | True | 9.35 | 1.0 | 3.75 | 0 | stop |
| style-code-low | True | 8.76 | 0.8861 | 3.672 | 128 | length |
| style-prose-none | True | 6.87 | 0.7015 | 2.205 | 0 | stop |
| style-agent-medium | True | 7.11 | 0.7353 | 2.648 | 256 | length |
| style-agent-medium-check | True | 7.73 | 0.7488 | 2.703 | 256 | length |

Style rows characterize output shape and reasoning cost; they are not a semantic-quality benchmark. Length-limited rows are explicitly shown above. The medium-reasoning response spent its entire 256-token budget on reasoning, so visible-answer SSE TTFT is null. The initial harness wrongly required a visible first token for that case and stopped after preserving the row. The check was narrowed to permit only a completed reasoning-only length cap for style rows; the fresh style-agent-medium-check passed before resuming the remaining probes. No completed long-prompt rows were repeated. Original error/results and source are retained in the local raw-artifact directory as matrix-at-style-budget-stop.json and run_perf-initial.py.

## Concurrency

`lane-probe`: `{"clean": true, "correct": true, "growth_allowed_after": true, "growth_allowed_before": true, "overlap_ratio": 0.998, "request_counter_deltas": {"cancelled": 0, "completed": 3, "failed": 0, "submitted": 3}, "submitted": 3, "summed_wall_seconds": 6.057, "total_wall_seconds": 6.067}`.

`parent-child`: `{"b2_batches": 0, "child_predicted_ms": 500.943, "child_prompt_ms": 1638.223, "child_prompt_tokens": 20, "child_queue_ms": 165324.6, "child_wall_seconds": 167.464, "clean": true, "correct": true, "growth_allowed_after": true, "growth_allowed_before": true, "max_active_requests": 2, "max_concurrent_decoding": 1, "max_concurrent_prefilling": 1, "max_waiting": 1, "parent_prompt_tokens": 28589, "parent_wall_seconds": 168.639, "request_counter_deltas": {"cancelled": 0, "completed": 2, "failed": 0, "submitted": 2}}`.

The chosen 10G/two-lane configuration admitted both requests but did not overlap their execution in this probe: the child queued 165.3 s, maximum concurrent prefilling/decoding were each 1, and b2 batches were zero. Idle growth_allowed snapshots were true before and after, while in-flight snapshots showed headroom below 1 GiB and growth_allowed false. Idle eligibility therefore did not guarantee prompt child execution after this long-context workload.

Parent-child queue is the prior V5b harness estimate: child wall minus native prompt/decode time. Parent wall includes executor completion; raw requests/responses and samples are retained. Each probe checks its expected request-counter delta for foreign traffic. These deliberate overlaps are separate from single-request means.

## Conditions and limits

Observed thermal states: ['fair', 'nominal']; memory pressure: ['normal', 'warning']. Host headroom ranged 0.42-1.52 GiB; growth_allowed values: [False, True].

Swap before: `vm.swapusage: total = 2048.00M  used = 436.25M  free = 1611.75M  (encrypted)`. Swap after: `vm.swapusage: total = 2048.00M  used = 436.25M  free = 1611.75M  (encrypted)`.

Unit correction: observed host spare reserve bytes are [2147483648]. The live reserve is 2,147,483,648 bytes, exactly 2.00 GiB (about 2.15 decimal GB). With the 1 GiB growth margin, normal growth needs 3.00 GiB spare, or 4.00 GiB after pressure with the 2 GiB recovery margin. Earlier notes calling the reserve 2.15 GiB and the threshold 3.15 GiB mixed decimal and binary units. The direct host_headroom_bytes and growth_allowed observations remain valid.

Engine failure counters start/end: Metal 0/0; capacity 0/0. Final expert slots 512, cap 2089468688 bytes, decode hit rate 0.

This run measures current conditions. Prior V5/V5b rows have different thermal/memory histories and some different output budgets; there is no matched ABBA experiment establishing a configuration speedup. Immediate prefix reuse does not prove a cold-disk restore or persistent-cache survival across restart. Native make test-performance-real was not run because it requires another engine load and stopping the live server.

## Evidence

Published measurements: [qwen38-option20-live-chosen-20261104.json](qwen38-option20-live-chosen-20261104.json). The JSON retains every measured row with output, usage, native timings, per-request speculation and counter deltas; concurrency samples; machine/build metadata; initial/final status; prompt hashes and generation; and original raw-artifact SHA-256 values.

Full local raw evidence remains in `build/validation/option20-live-20261104-chosen/` (gitignored), including exact payloads, per-row status snapshots, progress snapshots, concurrency responses, logs, original harness failure and focused recovery, and harness sources. The published JSON is a data package, not a full copy of that local directory.
