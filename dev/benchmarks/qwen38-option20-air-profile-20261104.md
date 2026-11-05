# Option 20: 16 GB Air request admission and cache validation - November 4, 2026

The launcher now defaults to **one active request below 24 GB unified memory**, including the 16 GB M5 Air. Hosts with 24 GB or more keep two by default, and an explicit `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2` retains the supported opt-in behavior on 16 GB. The menu and direct-launch paths use the same host default. This is request-admission tuning, not a new model kernel or a demonstrated isolated-throughput speedup.

## Installed profile

`/Users/mymac/startllamacpp.sh` matches the repository launcher byte for byte and the live option-20 service on port 1235 reports one active-request slot. The existing idle server was stopped cleanly and restarted through that installed launcher. The engine binary SHA-256 is unchanged across deployment.

- Model: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, with its existing DFlash2 draft.
- Context: 131,072 server / 129,024 OpenCode tokens. The validated default is preserved.
- Engine ceiling: 10 GiB; automatic expert memory; 1,024-token prefill chunks.
- INT8 KV, BF16 state, low default reasoning; `verify-rows auto`.
- N-gram table remains SSD-backed, with a 64 MiB row-cache reservation.
- Prefix cache: 16 GiB disk quota, persistent, using the existing option-20 cache directory.

The optional smaller-context experiment is still available through `SPLASH_FLASH_NEXT_MAX_CONTEXT=65536`, which synchronizes the OpenCode context to 63,488 tokens. No throughput gain or equivalent coding capacity is claimed for that smaller window. The change does not enlarge the PLE cache, select a larger prefill chunk, raise the engine ceiling, or force a larger expert floor.

## Validation

The focused launcher regression first reproduced the old 16 GB default of two active requests. After the change, **33/33 launcher tests passed**, including 16 GB defaults, menu/direct agreement, explicit overrides, larger-host behavior, cache wiring, argument rejection before config mutation, and shutdown handling. Shell syntax, Ruff checks/format, and Git whitespace checks passed.

The existing option-20 HTTP harness checked ORCHID/count-to-30 correctness, complete streaming, native DFlash2 acceptance, request counters, cache modes and failure counters. Temperature was zero, seed 42, reasoning none, output budget 160 tokens, and cooldowns ten seconds. The six clean requests below used the same engine binary and model, sequentially; no concurrent performance workload was run.

| Request | Prompt tokens | Cached tokens | Newly prefilled tokens | Correctness / SSE / DFlash2 |
|---|---:|---:|---:|---|
| baseline cold | 435 | 0 | 435 | pass |
| baseline immediate repeat | 435 | 416 | 19 | pass |
| persistent seed | 4019 | 0 | 4019 | pass |
| candidate next turn after restart | 4165 | 4000 | 165 | pass |
| candidate cold | 435 | 0 | 435 | pass |
| candidate immediate repeat | 435 | 416 | 19 | pass |

The candidate's first next-turn request restored **4,000 KV tokens from disk and one recurrent state** after the clean restart. The candidate's fresh prompt had zero cached tokens; its immediate repeat reused **416 of 435 prompt tokens**, leaving 19 to prefill. This verifies a disk-cache restart round trip and immediate prefix reuse, rather than inferring persistence from a configuration flag.

The initial baseline request restored weights after idle release and therefore had 2,826 ms of queue-to-start time. Its output was correct, but it was excluded by the harness's cleanliness rule; raw evidence remains in `baseline-idle-restore/`. The replacement baseline passed after weights were resident. This is a focused functional validation, not an ABBA performance comparison or a general coding-quality evaluation. No filled-131K inference or multi-client speedup is established, and no single-request generation speedup is claimed.

## Identity, conditions and artifacts

Build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Measured device: Apple M5, 8 GPU cores, 16 GiB unified memory. Installed launcher SHA-256: `f5ae8056bc0d39a2cc748a1217f502d7300e9f94b1747ed21957f52933cc525d`.

Final thermal state: nominal; memory pressure: warning. Candidate swap snapshots are recorded in the raw results. Metal failures: 0; capacity failures: 0. These snapshots do not establish absence of swap activity or sustained thermals.

Raw evidence is in `build/validation/option20-air-single-20261104/`: baseline and candidate payloads/results/status, persistent-cache seed and next turn, deployment record and logs, the excluded idle-restore baseline, the copied existing HTTP harness and focused check script. The previous installed launcher is saved there for rollback. The live service remains on http://127.0.0.1:1235.

[Current launcher profile](qwen38-option20.md#current-16-gb-air-defaults-2026-11-04-follow-up).
