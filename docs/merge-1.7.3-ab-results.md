# Splash 1.7.3 merge: prefill and decode A/B (2026-11-25)

Paired, interleaved runs (A,B,A,B,A,B) of the served option 21 stack: the same
model, same context (131,000), same chunk (2,048), same request (8,129 prompt
tokens, 128 output), one server at a time on port 1236.

| arm | engine | build id | PP tok/s | TTFT (s) | decode tok/s | expert reads (MiB/token) |
| --- | --- | --- | --- | --- | --- | --- |
| fork head `436e44b0` | `src-0ae0496c` | 340.8 / 303.7 / 293.2 | 23.9 / 26.8 / 27.7 | 25.86 / 25.50 / 25.24 | 226 / 228 / 230 |
| merged `bdd51e01` (1.7.3) | `src-3c914aeb` | 337.6 / 307.3 / 298.6 | 24.1 / 26.5 / 27.2 | 17.70 / 17.70 / 17.64 | 340 / 341 / 341 |

Means: prompt processing 315.9 (fork) vs 314.5 tok/s (merged), a 0.4% gap inside
the run-to-run spread. Decode: 25.5 vs 17.7 tok/s, a stable 31% loss. Expert
reads per decoded token go from 226 to 341 MiB, +50%.

## Verdict

The merge does not improve prompt processing. It is a tie on prefill and a clear
regression on decode for the served Q2_0 Flash-Next model, so it does not meet
the bar for the serving branch on its own.

## Where the decode loss comes from
## Where the decode loss comes from

The first hypothesis was staging: upstream `runtime/model/ExpertStore.cpp` now
stages the planes a file stores (codes, scales, biases, three page-padded planes
per projection) instead of native rows. That does not hold for this model.
`storedPlanes()` returns null for GGUF-sourced streamed experts, since it needs
`RowReader::Safetensors`, so the staging path is the same in both trees here. A
build that forced the native-row branch measured 17.22 and 17.46 tok/s against
17.38 and 17.71 for the plane path: no difference. The dead
`SPLASH_EXPERT_STAGE_NATIVE_ROWS` switch has been removed.

The cause is the memory plan. On the same host and the same 10.8 GiB Metal cap,
`--expert-memory auto` gives the routed experts a smaller store on the merged
engine than on the fork:

| arm | expert store | resident experts of 24,576 | hit rate | decode tok/s |
| --- | --- | --- | --- | --- |
| fork `436e44b0`, auto | 2,810 MiB | 1,790 (7%) | 0.645 | 24.30 |
| merged `bdd51e01`, auto | 2,125 MiB | 1,271 (5%) | 0.341 | 17.04 |
| merged `bdd51e01`, `--expert-memory 3072M` | 3,071 MiB | 1,988 (8%) | 0.520 | 25.07 |

Fewer resident experts means more of each decode route comes off SSD, which is
the +50% MiB/token the first run showed. Naming the store fixes it: the merged
engine at 3,072 MiB beats the fork on decode (25.07 against 24.30 tok/s) and on
time to first token (28,940 against 31,939 ms).

Both arms at 3,072 MiB are a tie, which confirms the gap is the store size and
not the engine: fork 2,821 PP tok/s, 16,880 ms TTFT, 25.70 decode tok/s, 0.552
hit; merged 2,892, 10,963 ms, 25.73, 0.546, six runs each.

## The ceiling for this model

3,136 MiB is the largest store that still lets the plan keep the 131,072-token
context resident (2,037 slots). 3,200 MiB caps context at 122,865 tokens and
3,584 MiB at 98,289. A paired run of 3,072 against 3,136 MiB is a wash (21.24
against 21.22 tok/s decode, 0.435 against 0.440 hit, two runs each), so the
launcher names 3,072 MiB: it is the round number below the ceiling and it leaves
room for the KV pool.

## Configuration

`startllamacpp.sh` option 21 now defaults `SPLASH_FLASH_NEXT_EXPERT_MEMORY` to
`3072M` when it is `auto`. An explicit value still wins. Options 19, 20 and 22
keep their own stores.

Evidence: `build/merge-ab/stack-ab-1795614647242532000/`,
`build/merge-ab/head-to-head-1795646259944863000/`,
`build/merge-ab/final-headtohead-1795661245697405000/`,
`build/merge-ab/ceiling-quick-1795680513285014000/`.
