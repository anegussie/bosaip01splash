# Flash-Next option 20 live benchmark, 131,072 context - 2026-11-02 (evening rerun)

The running option 20 instance was benchmarked again without restarting it: 131,072 served context, 1,024-token prefill chunks, `--verify-rows auto`, 10 GiB planner cap, DFlash2 draft attached, `build src-6a06f0d6c0d0`, source tree `3c693864`. Eighteen timed rows covered prompt sizes from 25 to 65,367 tokens and five output styles. Same build, same instance as [the morning 131k report](qwen38-option20-live-131k-20261102.md), so the two runs compare directly.

Timed probe: bounded recall/counting prompt (initial code AMBER, filler lines, final code ORCHID, count to thirty), temperature zero, seed 42, reasoning none, 96 output tokens, unique cold cache salts, ten-second cooldowns, SSE first-token time. A row is clean only when the engine was already idle, nothing queued, native `queue_to_start_ms` stayed under 100 ms, no foreign request with a budget of 1,024 tokens or more was active during it (status polled every 4 s), and the idle wait stayed under 30 s. Contamination here is real: this repository's own coding agent runs on this engine (`PI_PROVIDER=splash-local`), so its requests appear as foreign rows and are excluded from group means.

## Prefill, TTFT and decode

| Row | Prompt tok | Cached tok | Prefill tok/s | TTFT s | Decode tok/s | Cycles | Tok/cycle | Drafted/accepted | Acceptance | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| smoke cold | 435 | 0 | 70.82 | 6.14 | 10.16 | 13 | 7.39 | 84/83 | 98.8% | no |
| smoke repeat | 435 | 0 | 76.29 | 5.70 | 11.22 | 13 | 7.39 | 83/83 | 100.0% | no |
| 939 trial 1 | 939 | 0 | 121.90 | 7.70 | 11.69 | 13 | 7.39 | 84/83 | 98.8% | yes |
| 939 trial 2 | 939 | 0 | 139.09 | 6.75 | 12.10 | 13 | 7.39 | 84/83 | 98.8% | yes |
| 939 trial 3 | 939 | 0 | 150.60 | 6.24 | 12.26 | 13 | 7.39 | 84/83 | 98.8% | yes |
| 4,019 trial 1 | 4,019 | 0 | 183.73 | 21.87 | 12.31 | 13 | 7.39 | 84/83 | 98.8% | yes |
| 4,019 trial 2 | 4,019 | 0 | 178.40 | 22.53 | 12.20 | 13 | 7.39 | 84/83 | 98.8% | no |
| 4,019 trial 3 | 4,019 | 0 | 140.93 | 28.52 | 11.46 | 13 | 7.39 | 84/83 | 98.8% | no |
| 28,589 trial 1 | 28,589 | 0 | 145.97 | 195.86 | 11.48 | 13 | 7.39 | 84/83 | 100.0% | no |
| 28,589 trial 2 | 28,589 | 0 | 148.66 | 192.32 | 11.60 | 13 | 7.39 | 84/83 | 100.0% | no |
| 28,589 trial 3 | 28,589 | 0 | 148.18 | 192.93 | 11.62 | 13 | 7.39 | 84/83 | 100.0% | yes |
| 28,589 sustain | 28,589 | 0 | 150.76 | 189.63 | 10.01 | 15 | 7.53 | 98/98 | 100.0% | yes |
| 65,451 single | 65,367 | 0 | 146.66 | 445.70 | 11.59 | 13 | 7.39 | 84/83 | 100.0% | yes |

Group means (clean rows only):

| Prompt tokens | Trials (clean) | Mean prefill tok/s | Spread | Mean TTFT s | Mean decode tok/s |
|---:|---:|---:|---|---:|---:|
| 939 | 3 (3) | 137.20 | 121.90 to 150.60 | 6.90 | 12.02 |
| 4,019 | 3 (1) | 183.73 | 140.93 to 183.73 | 21.87 | 12.31 |
| 28,589 | 4 (2) | 149.47 | 145.97 to 150.76 | 191.28 | 10.81 |
| 65,367 | 1 (1) | 146.66 | single trial | 445.70 | 11.59 |

## Against the morning run on the same instance and build

| Prompt tokens | Prefill tok/s (morning to evening) | TTFT s (morning to evening) | Decode tok/s (morning to evening) |
|---:|---|---|---|
| 939 | 145.40 to 137.20 (-5.6%) | 6.48 to 6.90 (+6.5%) | 11.31 to 12.02 (+6.3%) |
| 4,019 | 180.66 to 183.73 (+1.7%) | 22.25 to 21.87 (-1.7%) | 11.95 to 12.31 (+3.0%) |
| 28,589 | 161.02 to 149.47 (-7.2%) | 177.55 to 191.28 (+7.7%) | 11.85 to 11.16 (-5.8%) |
| 65,451 | 156.09 to 146.66 (-6.0%) | 419.31 to 445.70 (+6.3%) | 10.24 to 11.59 (+13.2%) |

Long prefill moved the wrong way by 6 to 7 percent while decode is unchanged within trial noise. The machine was tighter during this run than in the morning: `memory_pressure` `warning` at both ends, `thermal_state` `fair`, the governor charged 8,302,363,548 of 10,737,418,240 bytes with `growth_allowed` false and 168 denied reservations, host available 3,732,013,056 against a 1,717,986,918 reserve (29,509,713 bytes spare), Metal peak 7.60 GiB, swap 1,020 to 1,357 MiB in use across the run. A cold 28.6k prompt is a 190 to 196 second event on this instance and a 65k prompt a 446 second event.

## Prefix reuse did not repeat

The morning run's repeat smoke reused 416 of 435 prompt tokens and cut TTFT from 5.20 s to 1.46 s. This evening the same cold-then-repeat pair reused nothing: `cached_prompt_tokens` 0 on both rows, TTFT 6.14 s then 5.70 s. The engine's retention is the weak point, not its lookup: at snapshot `cache` recorded 45 hits against 36 cold misses (55.6%), 1,593,824 reused tokens, `lost_state_misses` 2, `disk_state_publications` 0; `state.entries` 1 with 151 publications, 84 evictions, `checkpoint_entries` 0, 13 checkpoint evictions; and the disk prefix cache is entirely off (`disk.limit_bytes` 0 for this instance). With one state slot and no disk tier, a prefix published by an earlier request is gone before the next one looks for it.

## Draft acceptance by output style

| Workload | Prompt tok | Out tok | Reasoning tok | Decode tok/s | Cycles | Tok/cycle | Drafted/accepted | Acceptance |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| First fifteen primes, comma separated | 25 | 55 | 0 | 12.21 | 7 | 7.71 | 49/47 | 95.9% |
| Four arithmetic results, one per line | 52 | 16 | 0 | 8.92 | 4 | 3.75 | 12/11 | 91.7% |
| Python function with docstring and doctests, reasoning low | 61 | 256 | 139 | 7.68 | 73 | 3.51 | 228/183 | 80.3% |
| Short explanatory paragraph, reasoning none | 26 | 95 | 0 | 5.72 | 44 | 2.09 | 73/48 | 65.8% |
| Three-paragraph explanation plus risk list, reasoning medium | 39 | 256 | 256 | 6.66 | 100 | 2.56 | 221/156 | 70.6% |

Same shape as the morning run and as [the tuning plan](qwen38-option20-tuning-plan-20261102.md): structured output drafts at 7.7 tokens per cycle, agent prose with reasoning on at 2.1 to 2.6, and reasoning effort roughly halves emitted decode speed. Four of these five rows carried a foreign sample, so they compare workload shapes rather than absolute rates; `style-prose-no-reasoning` is the clean one.

## Decode is still SSD-bandwidth-bound

Over the run window the engine recorded 83,088 decode expert loads, 4,470 GB of decode expert read bytes, `streamed_experts.decode.hit_rate` 0.0 and 38 of 512 expert slots resident. Every routed expert selection still came from storage.

## Single lane

Three concurrent 20-token requests with 24-token budgets: total wall 6.193 s against 6.180 s of summed walls, so they ran strictly one after another. Native `prompt_ms` was 1,494 / 1,484 / 1,671 ms and `cache_n` 0 for all three, so short requests pay a fixed 1.5 second floor in front of any work.

## Not measured

- Native `make test-performance-real` for this model (decode widths B1-B4, the 14,096-token partial prefix, three samples) was not run: it starts a second engine load and the live instance already holds 10 GiB of the 16 GiB machine.
- Chunk re-sweep at 131,072 served context (1,024 against 2,048), the open follow-up from the morning report. It needs one server restart per setting.
- Filled-131,072 context inference, and any run with the disk prefix cache enabled (`SPLASH_FLASH_NEXT_MAX_CACHE_DISK` above 0), which is where the retention finding above would be tested.

Raw evidence: `build/validation/option20-live-20261102-evening/` (`performance.json`, `results.json`, per-row JSON, `status-start.json`, `status-final.json`, `lane-probe.json`, `run.log`, `run_live.py`, `run_rest.py`). Machine-readable results: [qwen38-option20-live-131k-evening-20261102.json](qwen38-option20-live-131k-evening-20261102.json).
