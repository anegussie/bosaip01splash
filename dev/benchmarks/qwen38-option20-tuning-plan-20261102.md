# Flash-Next option 20 tuning plan - 2026-11-02

This plan turns the measurements in [the 131k live report](qwen38-option20-live-131k-20261102.md) and the prefix-reuse probe into an ordered action list. The first group needs no server restart and is applied on the client side. The second group changes engine memory budgets, needs a restart, and is specified as single-variable experiments with acceptance criteria so that each result is attributable.

Raw evidence for every number quoted here is under `build/validation/option20-live-20261102/` (`status-final.json`, `reuse-probe.json`, `lane-probe.json`, `performance.json`, `requests/`).

## Decode is SSD-bandwidth-bound

Engine counters for one live instance (131,072 context, 1,024 chunks, `--verify-rows auto`, 10 GiB planner cap):

| Counter | Value |
|---|---:|
| Decode routed expert selections | 43,357,512 |
| Decode expert reads | 43,357,512 (`hit_rate` 0) |
| Decode expert bytes read | 84,512,761,135,104 |
| Decode batches (b1 / b2 / b3 / b4) | 37,564 / 0 / 0 / 0 |
| Expert store cap and floor | 2,089,468,688 each |
| Expert arena and staging | 1,323,827,200 plus 765,460,480 |
| Resident experts | 43 of 512 slots, 24,576 experts total |
| Prefill expert bytes read | 59,670,903,209,984 |

Dividing through: 43,357,512 routed selections over 1,803,216 loads is 24.0 experts per load and 48 loads per decode cycle, so one cycle pulls 1,154 expert tensors, 1.95 MB each, 2.25 GB per cycle. Measured decode cycle time is 448 to 630 ms, which is 3.6 to 5.0 GB/s of sustained SSD read. Every expert selection was read from storage; the arena never served a repeat.

The consequence is that decode tokens per second on this model is a function of expert residency, not of Metal compute. Any change that raises `streamed_experts.decode.hit_rate` converts directly into tokens per second, and any change that adds SSD work (a disk KV cache, more concurrent lanes competing for the same bandwidth) has to be measured rather than assumed.

Memory is a closed budget. The governor charged 8,736,474,012 of 10,737,418,240 bytes with `growth_allowed: false` and 621 denied reservations. Host available memory was 3,242,459,136 against a 1,717,986,918 reserve, leaving 308,330,496 bytes of real headroom. The fixed plan parts total about 7.98 GiB (target weights 5,665,555,216, draft 523,436,032, lane state 163,250,176, shared prefill 614,678,528, shared decode 183,840,928, pipeline reserve 268,435,456, runtime overhead reserve 536,870,912, PLE streamed table 67,108,844). Raising one budget means lowering another while host headroom stays this thin.

## Prefix reuse is worth two orders of magnitude

The reuse probe ran one 28,505-token prompt four times on the live instance, then a long generation on the same prompt:

| Row | Prompt tok | Cached tok | Prefilled tok | TTFT s | Decode tok/s |
|---|---:|---:|---:|---:|---:|
| cold | 28,505 | 0 | 28,505 | 185.47 | 11.47 |
| same salt, second call | 28,505 | 28,480 | 25 | 1.84 | 11.63 |
| same salt, third call | 28,505 | 28,480 | 25 | 1.80 | 12.16 |
| tail changed by 7 tokens | 28,512 | 28,480 | 32 | 1.96 | 12.30 |
| long generation, cold | 28,506 | 0 | 28,506 | 175.12 | 9.67 |

TTFT drops from 185.47 s to 1.80 s, a 103x improvement, when the prefix is already cached. Appending seven tokens to the prompt still reused 28,480 tokens, so only the changed tail is re-prefilled. The long generation held 99.88 percent draft acceptance over 1,895 output tokens (1,658 drafted, 1,656 accepted, 238 cycles) and 8.32 tokens per cycle in its late window, so drafting does not decay across a long output.

Client-side rules that follow:

- Keep the transcript append-only. A rewritten history invalidates the cached prefix; a grown one re-prefills only the tail.
- Do not vary `cache_salt` between turns of one session. The engine salts on the request value and defaults to zero when a client sends none (`server/backend.py:186`), and nothing in `/Users/mymac/startllamacpp.sh` or the local client configs sets one, so all clients currently share one salt namespace. Verified 2026-11-02.
- Treat a cold 28.5k prompt as a 185-second event and a cold 65k prompt as a 419-second event. Avoiding one such prefill is worth more than any decode tuning.
- Cap agent output budgets for lane fairness. A 16,384-token output at 9.7 tok/s holds the single lane for about 28 minutes, and the profile default output is 1,024 tokens.

The engine cache counters show reuse is working for agent traffic already: 151 hits against 79 cold misses (65.7 percent), 9,894,464 reused tokens. The weak point is retention, not lookup: `state.entries` was 1 with 163 state evictions and 61 checkpoint publication failures, and the disk cache is entirely off (`disk.capacity_bytes` 0). Long sessions lose their state and pay full prefill again.

## Reasoning effort changes decode speed about twofold

Same instance, same draft, three output styles:

| Output style | Acceptance | Tokens per cycle | Decode tok/s |
|---|---:|---:|---:|
| structured list, reasoning none | 100.0 percent | 7.86 | 10.06 |
| code, reasoning low | 87.6 percent | 3.94 | 8.89 |
| agent prose, reasoning medium | 72.3 percent | 2.39 | 6.33 |

Draft acceptance falls as reasoning effort rises, and cycle count per emitted token rises with it. Mechanical work should not inherit an interactive reasoning default. The option 20 launcher default is `SPLASH_FLASH_NEXT_REASONING_EFFORT=medium` (`startllamacpp.sh:49`).

## Applied 2026-11-02, no restart

Subagent runs against this engine were failing at the client timeout, so the agent harness limits were tightened in `~/.pi/agent/settings.json` under `pi-simple-agents.agentOverrides`. Two `context_compressor` jobs (S1005, S1006) each consumed the full 1,800,000 ms ceiling; S1006 reached only two assistant turns, the first ingesting 96,506 characters of documentation (about 23k tokens) in one tool batch, `docs/server.md` coming back truncated at line 734 of 980, and the second ending `stopReason: aborted` with no output.

| Agent | model | thinking | maxTurns | timeoutMs |
|---|---|---|---:|---:|
| context_compressor | inherit | minimal | 8 | 420000 |
| syntax_validation | inherit | minimal | 8 | 420000 |
| code_refactoring | inherit | low | 20 | 600000 |
| code_reviewer | inherit | low | 20 | 600000 |
| error_isolation | inherit | low | 15 | 600000 |

Rules adopted for delegation on this box, from the same evidence:

- Feed subagents excerpts, not whole documents. A 980-line `docs/server.md` read arrives truncated and costs 23k tokens of prefill at 150 to 180 tok/s.
- Keep a subagent context under roughly 30k tokens. A 100k-token child context costs about 11 minutes of prefill per turn on this lane.
- Prefer `thinking` minimal or low for mechanical agents; the reasoning ladder above is a measured 2x effect.
- Do not delegate while a timed benchmark is running on the same lane. The 17 contention-checked rows in the live report were measured inline for that reason.

## Restart-gated experiments

Each row changes one variable, boots with `--direct 20`, and is measured with the harness scripts kept at `build/validation/option20-live-20261102/` (`run_perf.py`, `run_long.py`, `run_extra.py`, `reuse_probe.py`). Record `streamed_experts` (`arena_bytes`, `resident`, `decode.hit_rate`), `streamed_table.decode.hit_rate`, `memory_governor` and the 939, 4,019, 28,589 and 65,451 token rows for every variant, plus the cold and cached 28,505-token reuse pair. Trials follow the contention rules used in the live report: engine idle at start, `queue_to_start_ms` under 100 ms, no foreign request of 1,024 or more output tokens during the trial window, exactly one completed request per trial.

| ID | Change | How | Acceptance |
|---|---|---|---|
| E1 | Serve 32,761 instead of 131,072 context | `SPLASH_FLASH_NEXT_MAX_CONTEXT=32761 /Users/mymac/startllamacpp.sh --direct 20` | 28,589-token prefill at 175 tok/s or better (179.65 was measured at this context on 2026-11-01, 161.02 at 131,072); larger `streamed_experts.arena_bytes` than 1,323,827,200 |
| E2 | Expert store floor 4 GiB | edit `--expert-memory auto` to `--expert-memory 4G` at `startllamacpp.sh:1663`, together with E1 | `streamed_experts.decode.hit_rate` above 0.10 and counting-probe decode above 13 tok/s |
| E3 | PLE row cache above 64 MiB | edit `--ple-memory 64M` at `startllamacpp.sh:1663` to 192M, then 512M (docs allow 512 MiB of the budget, `docs/server.md:92`) | `streamed_table.decode.hit_rate` above 0.80 (0.5668 today, 0.9789 in prefill) |
| E4 | Prefill chunk 2,048 | `SPLASH_BONSAI_PREFILL_CHUNK_TOKENS=2048` (launcher accepts 128 to 2,048 in multiples of 128, `startllamacpp.sh:1707`) | 28,589-token prefill above 181 tok/s at whatever context E1 chose, with planner minimum and pressure recorded |
| E5 | SSD prefix cache on | `SPLASH_FLASH_NEXT_MAX_CACHE_DISK=4G SPLASH_FLASH_NEXT_PERSISTENT_CACHE=1` | second cold session on a 28,505-token prompt under 10 s TTFT, and decode within 5 percent of the same-run baseline |
| E6 | `--verify-rows all` | run `build/splash serve-native` directly with the option 20 record and `--verify-rows all` | reproducibility check on greedy repeats, plus a decode tok/s delta against the `auto` baseline |
| E7 | Two active requests | run `build/splash serve-native` directly with `--max-active-requests 2` (the launcher requires 1, `startllamacpp.sh:1711`) | aggregate tokens per second across two concurrent requests well above 2x the single-request rate, since one 2.25 GB expert cycle would serve both lanes; costs about 163 MB of lane state each |

E1 is first because it is the only change that frees memory without taking it from the expert store, and it is also the direct test of the 10 percent long-prefill regression recorded in the live report. E7 is the most interesting row for agent-fleet throughput and the least safe on 16 GiB of unified memory.

Do not raise `SPLASH_FLASH_NEXT_MAX_MEMORY` to 11G while `host_headroom_bytes` is near zero. It is not a headroom source on this machine: 621 reservations were already denied at the 10 GiB cap, and peak Metal was 8.149 GiB against a 11.8 GiB device recommendation with 704.38 MiB of swap in use.

## Instance restarted at 12:58 on 2026-11-02

The measured instance (`94560cf93818e51935196bfb`, 76,300 s of uptime) was stopped deliberately at 12:58:11 (`Stopping · releasing engine resources` in `qwen3.8-flash-next-iq3-xxs-splash-20261101-151139.log`, together with terminated `startllamacpp.sh` and `monitorsplash.sh` watchdog sleeps) and relaunched with the same profile. The replacement is instance `bb9e88d3516b034f8fc66632`, pid 59456, 131,072 served context, 1,024 prefill chunks, `--ple-memory 64M`, `--expert-memory auto`, `--verify-rows auto`, 10 GiB cap, reasoning default medium, SSD cache off. Its counters restart at zero, so the live report's numbers describe the previous instance and remain valid for this configuration.

Three things the relaunch log answers directly:

- Weight restore is cheap. `Weights loaded in 2.41 s.` then `Weights loaded again in 2.02 s.` An idle release therefore costs about two seconds on the next request against the 5,665,555,216 bytes it frees. Keep `--idle-release 600s`.
- The expert store boots at its floor and gives nothing back: `512 slots for 24576 experts (2%) in 1262 MiB, a store of 1992 MiB in 1 chunks, all that --expert-memory auto leaves it beside the floors and the KV kept resident; it gives none back, its floor, 1992 MiB, 85% of its slots, being all of it`. E2 (a 4 GiB floor) is the only way to move this number, and it is confirmed to be the smallest part of the budget relative to its workload.
- Memory headroom is worse than it was. The new instance charged 9,170,584,476 bytes and reached 9,279,112,092 bytes within minutes, against `growth_allowed: false` and 30 denied reservations. Host available memory was 2,571,927,552 with `host_spare_bytes` 1,955,856,384 below the 2,147,483,648 reserve and `host_headroom_bytes` at 0. E1 (serve 32,761 instead of 131,072) is the recommended first run, and raising the cap is now excluded on evidence rather than on caution.

Baseline capture for the new instance is in `build/validation/option20-tuning-20261102/baseline-131k-20261102-1258/` (`status-live.json`, `key-metrics.json`).

## Measurement caveat: /status sections go null while a request is in flight

Polling `http://127.0.0.1:1235/status` during an active request returned `streamed_experts`, `cache` and `memory_governor` subfields as null, while the same fields came back populated seconds later with the engine idle. A null is not a zero, and a contention check that reads a null as absent work would pass silently. `build/validation/option20-live-20261102/perf_lib.py` now retries `status()` up to six times before accepting a partial snapshot, and `python3 -m py_compile` plus a live call confirm it returns populated `metrics`, `memory_actual`, `scheduler`, `requests` and `active_requests`.

## Not to change

- The DFlash2 draft. Acceptance is 100 percent on structured output and 99.88 percent across 1,895 emitted tokens, at 7.4 to 8.3 tokens per cycle. A draft-off A/B is still worth recording, but there is no evidence against it.
- INT8 KV pages and BF16 lane state.
- `--verify-rows auto` for interactive traffic; `all` is a reproducibility tool, not a speed tool on a 512-expert MoE target.
- `--idle-release` at 600 seconds. A restore costs 2.02 to 2.41 s of weight loading (measured on the 12:58 relaunch) and frees 5,665,555,216 bytes while idle, which is a good trade at 0 bytes of host headroom.

## Still unmeasured

Draft on against draft off, `--verify-rows all` against `auto`, and E1 through E7. All of them need a restart, which ends whatever session is using the instance, so they are scheduled as deliberate runs rather than folded into a live benchmark. The idle-release restore cost is no longer open: it is 2.02 to 2.41 s.
