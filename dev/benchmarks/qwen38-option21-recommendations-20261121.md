# Splash option 21 performance recommendations

Keep the **10.8 GiB Metal cap and 2,048-token prefill chunks** as the general
profile on the 16 GiB M5. The first changes to try are preserving prompt
prefixes and reducing thinking for routine edits. For engine work, start
with the streamed expert path.

## Measured baseline

The November 21 status check showed Qwen3.8 Flash-Next Q2_0 with the BF16
DFlash2 draft, INT8 KV, a 131,072-token context, and 2,048-token chunks. The
launcher log reports one active request and a 3 GiB persistent prefix cache.

The table uses the November 18 postmerge medians for the same profile.
Thinking was off, each response generated 512 tokens, and each context had
two valid trials per mode. Cold means zero prefix reuse with the model and
OS caches warm. Cached runs reused the prompt prefix. These synthetic
recall and counting trials establish the profile's latency and throughput
under the tested conditions. [Benchmark and raw evidence](option21-postmerge-20261118.md)

| Filled prompt | Cold prefill tok/s | Cold decode tok/s | Cold first token | Cached decode tok/s | Cached first token |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8,204 | 445.75 | 26.15 | 18.41 s | 26.62 | 0.58 s |
| 32,780 | 345.50 | 23.96 | 95.09 s | 26.09 | 0.57 s |
| 65,548 | 274.49 | 22.91 | 238.98 s | 24.17 | 0.57 s |
| 102,412 | 251.58 | 21.85 | 407.10 s | 25.16 | 0.56 s |

## Ranked recommendations

1. **Preserve prefixes and keep new input small.** Keep the system prompt
   and tool definitions stable within a session, read only the file ranges
   needed for the task, and compact long histories at task boundaries.
   At 102,412 prompt tokens, prefix reuse cut time to first token from
   407.10 s to 0.56 s. Track reused prompt tokens and first-token latency
   when changing the client workflow. [Postmerge benchmark](option21-postmerge-20261118.md)

2. **Test thinking off for mechanical edits and checks.** In the November
   21 Pi coding session, 56 requests with low thinking and at least 64
   generated tokens had a median decode rate of 12.81 tok/s and 4.13 tokens
   per draft cycle. The session used a different workload from the table.
   Compare `off` and `low` on the same edit and verification task, using
   successful completion and elapsed wall time as the decision criteria.
   Keep the larger output allowance for complete tool arguments. The local
   Pi-session telemetry is in
   `~/.local/state/llama-server/qwen3.8-flash-next-q2-0-dflash2-bf16-splash-20261120-162155.log.jsonl`.
   [Draft cycle measurements](qwen38-option21-arms-20261112.md)

3. **Try 1,024-token chunks as a separate cached-decode profile.** The older
   comparison measured 12.8–23.6% higher cached decode throughput and
   22.7–33.0% lower cold prefill throughput. At 100K with a 512-token output,
   1,024 chunks saved 4.06 s on the cached request and added 125.02 s to the
   cold request. Test this setting for long generations with reliable
   prefix hits. Keep 2,048 chunks as the general profile. [Chunk comparison](option21-chunk-context-20261113.md)

4. **Reclaim prefill workspace for expert residency.** Halving the chunk
   freed about 1 GiB of workspace, increased expert slots from 1,512 to
   2,176, and reduced expert reads per output token by 17.8% in one
   experiment. Decode throughput was inconclusive in that experiment.
   Profile buffer lifetimes and test whether the 2,048-token workspace can
   shrink while preserving its cold prefill advantage. For cold 64K–100K
   prompts, profile QSA indexer scoring and selection with retrieval
   quality held constant. Generic expert read-ahead is a lower priority
   because its matched trial measured changes within run-to-run variation.
   [Expert residency](qwen38-option21-arms-20261112.md) ·
   [Kernel timings](qwen38-option21-kernels-20261111.md) ·
   [Read-ahead trial](qwen38-option21-readahead-performance-20261112.md)

## Implementation and verification for recommendations 1 and 4

Pi's option 21 profile now sends later system messages in place, which the
running Splash chat template reports it supports. With the option 21
tokenizer, an in-place update preserved 6,436 of 6,436 prefix tokens in a
replay. Folding the update into the leading system message preserved 10.
Pi also defaults unspecified reads to 80 lines and leaves explicit ranges
intact. In the mock, the default read result dropped from 1,932 to 1,326
bytes, the explicit range was unchanged, and both requests used the same
initial prompt and tool definitions.

OpenCode's native request path already appends later guidance while
preserving earlier messages and tool definitions. A mock verified that
behavior and the existing 80-line default read. The updated checkpoint
hook selects option 21's `bounded-compaction` variant, which sends a
2,048-token output cap and disables thinking. Ordinary requests still use
their existing reasoning setting. Six unit tests and the isolated
OpenCode request checks passed.

The engine candidate reuses a prefill allocation between GDN, attention,
and MoE expert intermediate and output scratch. Routing and the tensors
carried across phases have independent storage. The Flash-Next
2,048-token planning test measured 642,187,264 bytes before and
340,852,736 bytes after for the target arena, a saving of 301,334,528 bytes
(287.375 MiB). Decode uses its own arena. The planning suite and two
focused Metal tests passed, including a GPU check of aliased phases and
independent buffers for each of two chunks.

The candidate was built separately at
`build/option21-shared-scratch/splash`. The live server continued to serve
the existing session. The allocation result is measured in the planning
test. Expert residency, real serving throughput, and a fresh long-context
QSA timing comparison remain to be measured in isolation.
