# Option 20 prompt baseline and expert-streaming experiment, November 6, 2026

The current build reproduced approximately 400 PP on the original cold 4K workload. Profiling identified heavy physical storage traffic and reader threads in `pread`, rather than a CPU copying or scheduling hotspot. An isolated candidate doubled shared-arena decode read-ahead from four to eight workers. It passed the full expert-store suite but did not establish a serving throughput gain in A/B/B/A order. The original source was restored; the production binary and Metal libraries were unchanged.

## Matched setup and scope

M5 MacBook Air, eight GPU cores, 16 GiB unified memory. Model `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS` with matching DFlash2. Target SHA-256 `261aef54bdfbeb8fb5bae01deeef4eb70f820fe19f410e4ed9de46c344969117`. Same installed model layout for all runs. Baseline build ID `src-d3ea0ffe96934b78c61585e3965e6ccc76fea994a2f23b6c26b62f10b004d0cd`; candidate `src-507d3b59d1d7ff81adde754ad72693720d78b114a2a796257d8f4e760083ffe9`.

All runs used the real HTTP frontend on port 1245, 131,072 served context, 2,048-token prefill chunks, 10.8G cap, automatic expert memory, approximately 64 MiB PLE row cache, INT8 KV, BF16 state, one active request, `verify-rows auto`, and a dedicated 16G persistent-prefix-cache quota. The n-gram table stayed SSD-backed. Temperature zero, seed 42 and reasoning none. Every server was started fresh, waited 30 seconds after readiness, ran alone, and was stopped and waited for before the next server. Each coding request followed a five-second pause. No server was running before the experiment, and none was left running afterward. No inference overlapped a build or native test.

## Original long-prompt baseline

The preserved prompt generator uses the original repository-note filler, an initial AMBER code and final ORCHID code, followed by a count to 30. The tokenizer search reproduced exactly 4,019 and 28,589 prompt tokens. Each cold row used a unique cache salt and zero cached tokens; the first cold row at each size was immediately repeated with the same salt. All long responses returned the exact code and integers 1–30, completed SSE, and stayed under their 160-token cap. OS caches were not flushed.

| Actual prompt | Cold samples | Cold PP tok/s | Cold API decode tok/s | Cold SSE TTFT s | Reuse cached tokens | Reuse SSE TTFT s |
|---:|---:|---:|---:|---:|---:|---:|
| 4,019 | 2 | 403.71 (401.40–406.03) | 12.74 (12.73–12.75) | 9.96 (9.91–10.01) | 4,000 | 1.452 |
| 28,589 | 2 | 302.31 (264.60–340.02) | 12.19 (12.15–12.23) | 96.08 (84.11–108.05) | 28,576 | 1.101 |

These are current-condition characterizations, not a speedup claim against older binaries or profiles. The large spread at 28K is retained. The two 28K requests read about the same 296.5 GiB of expert-source data including decode, despite taking different times. The preceding 56–59-token coding prompts measuring roughly 21 PP did not establish a long-prompt regression. Reported API PP divides uncached prompt tokens by native start-to-first-token latency, which includes the costs of a small request; it is not a size-independent kernel rate.

## Storage diagnostic

A separate diagnostic server ran smoke and coding checks, then an LRU-code request while `/usr/bin/sample` captured the native process for eight seconds at a five-millisecond interval. This request and all diagnostic timings are excluded from the comparison. The LRU response was a diagnostic workload, not a separately validated code-quality result.

The sample's collapsed top-of-stack summary counted 31,031 thread-stack samples ending in `pread`, versus 16,237 in condition-variable waits and few samples in store bookkeeping. These counts include blocked threads and are not percentages of CPU execution time. They support an I/O-wait diagnosis; this was not a GPU kernel instruction profile.

The sources use `F_NOCACHE`. Per-request aggregate `iostat -Id` disk0 deltas closely matched expert-source reads: the baseline merge probe transferred about 60.97 GiB on disk0 against 60.88 GiB of expert-source bytes; bracket matching was 57.23 versus 57.14 GiB. The first cold 4K request was 88.30 versus 88.23 GiB. Disk counters are system-wide and include writes and unrelated desktop I/O, so these are corroborating observations, not exact process-attributed physical read totals.

On the initial merge/bracket probes, decode expert-source traffic was approximately 6.2–6.3 GB/s over native decode time. Host-load work accounted for roughly 5.2–5.7 seconds of 7.9–8.4 seconds of decode. Host and GPU/event timings overlap; these intervals cannot be summed into an independent wall-time budget or treated as fully recoverable time. No separate SSD maximum-throughput control was run, so the experiment does not establish a hardware ceiling.

## Isolated eight-worker candidate

Only `ExpertStore::Impl::startAhead` changed: shared-arena decode used eight read-ahead workers; other loads, prefill and the 32-thread demand-reader pool retained their settings. No additional reader threads or staging buffers were allocated. The hypothesis was that more useful expert data would finish before demand loads stalled the GPU.

The candidate built in `build/option20-stream-ahead8-20261106`; the original executable and libraries were preserved in `build/option20-stream-baseline-20261106`. Both Metal libraries were byte-identical across baseline and candidate. The full expert-store Metal suite exited zero with `expert_store_test: PASS`, including bitwise resident-weight comparisons, mixed layouts, chunk shrink/restore, read-ahead lifetimes, failed restores, and changed-source failures. The initial sandbox build failed on a protected compiler module-cache write; the same build succeeded with escalated cache access. Both logs are retained.

Each A/B/B/A block passed an exact 363-token cold/reuse ORCHID/count gate before three coding tasks and a 4K cold/reuse pair. Coding tasks were sorted-list merging, bracket matching, and interval merging with empty-input, duplicates, nesting, mismatches, touching/overlapping intervals and input-preservation checks. All returned complete functions below a 256-token output cap. Each task's text was byte-identical across all four blocks and passed its functional checks. These are small functional probes, not a broad coding benchmark or long-context coding evaluation.

| Block | Decode read-ahead workers | Coding API TPS mean | Coding native TPS mean | Three coding responses, total wall s | Expert-source MB/output token | Cold 4K PP |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 4 | 10.912 | 11.029 | 39.491 | 565.88 | 402.98 |
| B1 | 8 | 10.902 | 11.018 | 39.473 | 570.27 | 339.51 |
| B2 | 8 | 10.885 | 11.002 | 39.598 | 570.50 | 299.32 |
| A2 | 4 | 10.845 | 10.963 | 39.676 | 566.05 | 294.48 |

Across the two blocks per setting, baseline/candidate coding API TPS was 10.879/10.893, native TPS 10.996/11.010, and combined coding wall time 39.584/39.535 seconds. The approximately 0.1% throughput difference is inside observed variation and establishes no gain. Candidate source bytes per output token rose from 565.96 to 570.39 MB, about 0.8%.

Prefill source bytes and load counts were identical across the four 4K cold requests, but PP declined through A/B/B/A: 403, 340, 299, 294. The final original-binary result also fell, so these rows do not isolate a candidate prefill regression. Nominal/fair thermal-state changes, warning memory pressure during inference, and uncontrolled desktop activity limit interpretation. Initial readiness pressure was normal; inference snapshots were warning. All recorded battery and AC settings had Low Power Mode off; battery-source records are retained under full command names. Swap snapshots do not establish absence of swapping.

API TPS excludes the first output token and divides subsequent tokens by first-token-to-done latency. Native TPS uses `/status` decode-output and decode-wall counter deltas, so it includes a different boundary and is slightly higher. Coding TPS columns are arithmetic means across tasks; wall time is the sum of whole HTTP response times. Expert-source MB/token is weighted by output token count and uses decimal MB. It includes speculative and read-ahead work and is not an exact physical disk metric.

## Decision and artifacts

Retain four read-ahead workers and automatic verification. The original `ExpertStore.cpp` was restored by comparing exact candidate bytes before replacement, and a scoped git check confirmed it matches the pre-experiment source. SHA-256 checks confirmed `build/splash` and both production Metal libraries were unchanged. The candidate remains as an isolated build and patch; it was not installed. No commit or push was performed.

All six servers completed: 12 baseline requests, five diagnostic requests, and seven in each of the four comparison blocks (45 total). Every request completed SSE; per-request completion counts advanced by one, with no failed requests, capacity failures or Metal failures. All required smoke/cache gates and timed coding checks passed. The profiler completed successfully. All owned servers were stopped.

[Summary JSON](qwen38-option20-stream-profile-20261106.json) preserves measured rows and identities. [Raw evidence](../../build/validation/option20-stream-profile-20261106/) contains the archived runner and helpers, original and candidate source, rejected patch, exact commands, build/test logs, native sample, SSE events, request payloads, host/disk snapshots and before/after status. Reproduction should use a fresh `--label` to preserve existing evidence. Experimental prefix-cache files are separate from the launcher cache.
