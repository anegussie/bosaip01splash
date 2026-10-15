# Live Splash log and performance review, 2026-10-15

Reviewed 2026-10-15 at 15:22 EDT. Snapshot of the option-14 server on port
1235, engine `c8e0c8b8bc8cd9a328b5460d`, started at 13:59:46. The saved log
contains all 385 completed requests through request 385 at 15:16:46.

The runtime is healthy. Two responses hit the output ceiling. The main
observed performance constraints are low draft acceptance on this traffic,
memory pressure with SSD-backed cache reuse, and cold-prefill latency.
The logs do not isolate the precise contribution of each to decode time.

## Fixed runtime and workload

Apple M5, 8 GPU cores, 16 GiB; Bonsai 2 27B PTQ1_0 target with the original
Qwen3.8-27B DFlash2 draft, speculation enabled. Splash Metal, INT8 KV, BF16
state, 512-token prefill chunks, one active request, 24,576 configured context.
Actual input lengths: median 10,741, p95 20,460, maximum 22,275 tokens.
The engine uses optimized build
`src-c988c87eac16f999a9e5b5df5f0823c8671a3ce7eb6bc32f79090735cd6a8737`,
the source content published in commit `2446f378`.

This is real tool/chat traffic, not the earlier greedy utility benchmark.
The log records one initial thinking-enabled request and subsequent requests
with reasoning none; it does not record all sampling parameters.

## Measurements

| Metric | Observed |
| --- | ---: |
| Completed / failed / cancelled | 385 / 0 / 0 |
| Transport restarts / Metal failures / capacity failures | 0 / 0 / 0 |
| Native aggregate prefill | 116.98 tok/s over 213,791 processed tokens |
| Native aggregate decode | 14.53 tok/s over 35,504 output tokens |
| Per-request logged decode, median / p95 | 18.8 / 25.4 tok/s |
| Draft acceptance | 26,188 / 62,531 = 41.88% |
| TTFT median / p95 / maximum | 1.57 / 20.35 / 114.8 s |
| Logged native request time, median / p95 / maximum | 5.04 / 40.91 / 132.08 s |
| Native queue time, median / p95 | 0.024 / 0.247 s |
| HTTP preparation / tokenization, mean | 5.0 / 2.6 ms |
| Input tokens covered by cached prefixes | 95.26% |
| Requests with some cached prefix / zero cached prefix | 369 / 16 |
| SSD reads / writes in this engine session | 61.05 / 36.14 GiB |
| SSD cache used / effective limit | 6.905 / 6.975 GiB, 99.0% utilized |
| Current / peak Metal device allocation | 7.80 / 8.44 GiB |
| System-wide swap used | 4,189.44 MiB at the resource snapshot |

Native aggregate rates divide native token counters by their accumulated
stage times. The per-request distribution comes from rounded log entries;
these are different aggregates. Prefill rate applies to processed tokens,
not the complete context including reused prefixes. Allocations are not RSS,
and system swap is not attributed solely to Splash.

## Findings

1. **Two responses hit the output ceiling.** Request 210 at 14:29:17
   (log line 446; [saved evidence](bonsai-live-review-20261015.json)) and request 350 at 15:06:14
   (log line 734; [saved evidence](bonsai-live-review-20261015.json)) each generated 1,024 tokens and ended
   `finish=length`. Their request times were 122.44 and 94.09 seconds.
   These are possible truncated answers/tool arguments; the logs alone do
   not establish downstream validity. Completed-request counters do not
   establish semantic correctness. Inspect client continuation handling and
   use a larger per-request output budget where the task needs it.

2. **Real-workload draft acceptance is substantially below the benchmark.**
   The previous 77.3% rate was measured on short coding utilities. Current
   traffic is 41.88%. In the 14:10-14:20 interval acceptance was 63.25% with
   19.92 native decode tok/s; in 14:20-14:30 it was 30.78% with 10.88 tok/s.
   This is correlation across different requests, not a controlled speed
   comparison. It supports profiling verification and draft efficiency on
   representative tool traffic before extrapolating the utility results.

3. **Memory pressure prevents RAM cache residency.** Both status snapshots
   report warning memory pressure, cache growth disabled and zero host
   headroom under the governor's policy. There are 1,133 denied reservation
   attempts, but zero request capacity failures. The state cache has zero
   resident snapshot bytes, 369 disk hits, zero promotions and 369 skipped
   promotions. All state offloads and KV restores report zero failures.
   `Cache::promoteState` treats RAM promotion as optional, so requests can
   complete while future reuse still requires disk reads. The SSD traffic is
   consistent with these counters; its exact latency contribution requires
   profiling. Reduce competing RAM use and measure whether cache promotion
   resumes before changing memory policy or cache configuration.

4. **Cold prefill explains the largest TTFT outlier.** Request 385
   (log line 806; [saved evidence](bonsai-live-review-20261015.json)) had 13,825 input tokens, zero cached
   tokens, 114.84 seconds of prefill and 132.08 seconds total. Frontend and
   native queue times were both zero. Its tool-schema fingerprint first
   appears on this request, consistent with a changed prefix, but the log
   cannot distinguish all causes of the cache miss. Most requests benefit
   from caching; this outlier is not evidence that caching generally fails.

5. **Queueing and frontend processing are minor in this session.** Only one
   request had frontend queueing, 9.132 seconds near startup. Median native
   queue time is 24 ms and p95 is 247 ms. At the final snapshot the server is
   ready, idle, Metal-healthy, with no waiting, suspended or recovering work.
   The active workload ran in fair thermal state from 14:06:14 until
   15:17:57, then returned to nominal. Thermal state alone does not establish
   the size of a throttling effect.

## Interpretation and next work

The earlier 2-3% projection improvement remains a local kernel measurement.
These live requests have different lengths, tool schemas and acceptance,
and there is no matched old-build run of this traffic. Their 14.53 tok/s
aggregate does not establish a regression from the optimization.

Prioritize the two truncated responses, RAM/cache residency under the
existing governor, and draft/verification profiling on this real workload.
Keep prompt and tool prefixes stable when possible to avoid expensive cold
prefill. Validate any performance change with the same requests and cache
conditions before selecting a winner.

The committed [data summary](bonsai-live-review-20261015.json) preserves aggregates, interval
metrics, resource counters, the final status snapshot and log excerpts for
the two output-limit responses and the longest TTFT. Full raw snapshots,
`server.log` and parsed per-request records remain locally under
`build/validation/log-review-20261015/`. The review submitted no model requests
and changed no runtime settings or inference source files.
