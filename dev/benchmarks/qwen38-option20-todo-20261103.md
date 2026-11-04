# Option 20 performance TODO (2026-11-03)

Ranked action list for the served `qwen3.8-flash-next-iq3-xxs-splash` profile
(option 20) on the 16 GB MacBook Air (M5). Context stays at 131,072 tokens.

Sources: `qwen38-option20-live-131k-evening-20261102.md` (live reruns),
`qwen38-option20-machine-scaling-20261103.md` (measured bandwidth constants and
machine estimates), `qwen38-option20-tuning-plan-20261102.md` (32K sweeps).
All measurements follow `docs/validate.md`: 10 s cooldowns, unique cache salts,
bounded correctness probes (ORCHID, count-to-30), and contaminated rows dropped.

## Measured constants behind every estimate

| Quantity | Measured value |
|---|---|
| Expert bytes streamed per emitted token | 452 MB (223.7 routed evaluations x 2.02 MB tile) |
| Expert bytes streamed per prompt token | 36.1 MB |
| Decode storage demand | 5.89 GB/s (13.07 tok/s) |
| Prefill storage demand | 5.26 GB/s (149-161 tok/s) |
| This drive, measured | 3.64-5.51 GB/s cold, 6.10-6.28 GB/s warm |
| Expert store today | cap = floor = 1,992 MiB, 512 of 24,576 slots, 38 resident, `hit_rate` 0.00 |
| Store cost per slot | 3.89 MiB, so 263 slots per GiB of store budget |
| PLE row cache | 64 MiB (504,370 of 100.5 M rows), prefill `hit_rate` 0.968, decode 0.620 |
| Metal budget | configured limit 10 GiB, plan minimum 8.54 GiB, in use 7.44-8.35 GiB |

Both phases are at the drive's ceiling, not the GPU's: at 13 tok/s the GPU does
about 31 GFLOP/s of matmul while spending 99.8% of the wall staging and
dequantizing the stream.

## Done in the launcher (needs one restart to take effect)

1. **Disk prefix cache on by default**: `SPLASH_FLASH_NEXT_MAX_CACHE_DISK` is now
   `8G` with the existing persistent cache and its own directory
   (`~/Library/Caches/Splash/flash-next-option20-iq3-xxs`). It adds a disk tier
   for KV and state, which both shortens repeated prefill and frees RAM that the
   memory governor can spend on the expert store.
2. **Expert store knob**: `SPLASH_FLASH_NEXT_EXPERT_MEMORY` (default `auto`, or a
   size from `512M` to `8G`) reaches `--expert-memory` directly. `auto` has been
   measured to pin the store at its 1,992 MiB floor, which is why the store never
   grew past 512 slots.
3. **Prefill chunk knob**: `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS` (default 1024,
   128-2048 in 128 steps) so the chunk sweep no longer needs a script edit.
4. **Memory cap widened and made host-aware**: `SPLASH_FLASH_NEXT_MAX_MEMORY`
   accepts `8G` through `56G`, refuses a cap that would eat the 2-7 GiB cushion
   macOS keeps for itself, and prints the automatic ceiling when a cap is bigger
   than the engine would choose anyway. Default stays `10G`.
5. **Second active request for option 20**: `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS`
   accepts `1` or `2`. `2` is admitted when the machine can carry a second lane by
   the launcher's rule: 24 GB or more at 131,072 context, 16 GB or more at 65,536 or
   below. `SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1` admits it on a 16 GB Mac at any
   context the profile allows, prints what is at stake, and never lowers the 16 GB
   floor. Options 14, 16, 18 and 19 stay single-lane.
6. **Cache quota preflight and a bigger default**: the launcher refuses a quota larger
   than the free space on the volume that will hold the cache, and the option 20 default
   went from `8G` to `16G` after both were measured full on this Mac (8,547,762,176 of
   8,589,934,592, then 17,165,451,264 of 17,179,869,184 with 13.42 GiB taken back over
   12,553 KV blocks, against 67 GB free).
7. **Tests**: `dev/benchmarks/test_bonsai_launcher.py` covers the new defaults,
   the new knobs, the second-lane admission rule, the host memory ceiling, and
   the disk quota preflight.

## Pending, in order (each needs one authorized restart)

| # | Change | Command | Accept when |
|---|---|---|---|
| V1 | verify the new 8G prefix cache default at 131k | `bash startllamacpp.sh --direct 20` | **done 2026-11-03.** `dev/benchmarks/qwen38-option20-v1-20261103.md`: a repeated 28,589-token prompt starts in 1,204 ms instead of 192,000 ms once its KV has been demoted to disk (893 blocks, 442.5 MB restored), cold prefill and decode unchanged, governor charged fell 9.45 to 8.58 GiB and host spare rose 1.77 to 2.52 GiB |
| V2 | raise the expert store, funded by the disk tier | `SPLASH_FLASH_NEXT_MAX_MEMORY=11G SPLASH_FLASH_NEXT_EXPERT_MEMORY=3G bash startllamacpp.sh --direct 20` | **done 2026-11-03 as a null result** (`qwen38-option20-v2-20261103.md`). `2G` was accepted and became the store's floor: cap = floor = 2,089 MiB, 512 slots, `regrows 0`, `hit_rate` 0.00, decode 11.1-11.9 tok/s and 28k prefill 155 tok/s, identical to V1 |
| V3 | take memory back from the resident KV pool, and give the disk tier room | `SPLASH_FLASH_NEXT_MAX_MEMORY=11G SPLASH_FLASH_NEXT_EXPERT_MEMORY=4G SPLASH_FLASH_NEXT_MAX_CACHE_DISK=16G bash startllamacpp.sh --direct 20` | **done 2026-11-03, split result** (`qwen38-option20-v3-20261103.md`). The expert store did not move: cap = floor = 2,089 MiB, 512 slots, `regrows` 0, `hit_rate` 0.00, decode 11.5-11.7 tok/s, 28k cold 189.8 s at 150.7 tok/s. The 16 GiB quota did pay: startup restored 83 restore points over 5,314 KV blocks (7,076 MiB), the cache grew to 11.57 GiB, and 65,451-token cold prefill ran 436.4 s / 150.0 tok/s against 445.7 s / 146.7 at the 8 GiB quota |
| V3b | re-sweep prefill chunks at 131k | `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048 ...` | 2048 beats 1024 at 28,672 and 65,451 without raising peak bytes by more than ~1 GiB |
| V4 | two lanes at the full 131,072 context, which is the context this profile keeps | `SPLASH_FLASH_NEXT_MAX_MEMORY=11G SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1 bash startllamacpp.sh --direct 20` (`--expert-memory` stays `auto`) | **done 2026-11-04, the gate opened and the lane still did not run** (`qwen38-option20-v4-20261103.md`). Two requests were active in 327 of 371 samples with `waiting_concurrency` 0, yet max concurrent decoding and prefilling were both 1, `decode_batches_by_width` recorded b1 3,237 with b2/b3/b4 0, and a 20-token child queued 186.5 of its 188.5 s. The blocker is `host_headroom_bytes` 0: 1.83 GiB spare against the 2.15 GiB macOS reserve at an 11 GiB cap, so `growth_allowed` is false and every held request is refused (`denied_reservations` 2,052 to 4,608, log `Memory: growth paused; waiting=1; suspended=0; held=1`). Single-request speed matched V3 |
| V5 | two lanes funded by a smaller cap instead of more memory | `SPLASH_FLASH_NEXT_MAX_MEMORY=10G SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1 bash startllamacpp.sh --direct 20` | **done 2026-11-04, still serialized** (`qwen38-option20-v5-20261104.md`). `transport.max_active_requests` 2 and two active requests with `waiting_concurrency` 0, but max concurrent decoding and prefilling were 1, `decode_batches_by_width` stayed b1-only, and the child queued 180.4 of its 182.7 s. The rule is stricter than V4 assumed: growth resumes only at `host_headroom_bytes` >= `kHostWarningMarginBytes` 1 GiB (`MemoryGovernor.cpp:301`, `MemoryGovernor.hpp:85`), so the host needs 3.147 GiB spare (4.147 GiB to reopen after pressure) and measured 2.20-2.27 GiB idle, 2.95 GiB mid-prefill. Cold speed was the best of the series: 28,589-token prefill 171.8 s / 166.4 tok/s, decode 11.9 tok/s, repeat 1,126 ms |
| V5b | free host memory instead of lowering the cap - no restart | quit Chrome (1.42 GiB with its helpers) and LM Studio (0.39), then re-run `build/validation/option20-v5c-20261104/run_v5c.py` copied into `build/validation/option20-v5b-20261104/` | **done 2026-11-04, the lane works** (`qwen38-option20-v5b-20261104.md`). Same 9G process as V5c. `host_spare_bytes` 1.75-1.92 → 3.13-3.35 GiB, `host_headroom_bytes` 0.00-0.26 → 1.13-1.28 GiB, `growth_allowed` true for the first time on this Mac, swap 2,043 → 524 MiB. The child started 10 s into its parent's 182 s prefill and finished 13 s after submission (queue 11,050 ms against 186,500 / 180,264 / 165,268 ms in V4 / V5 / V5c), `max_concurrent_prefilling` 2, `decode_batches_by_width` recorded b2 21 for the first time, `lane-probe` overlap 1.079 and 1.16 (wall below summed). Cost measured on the contaminated row: two requests decoding at once each ran at 5.17 tok/s, about half the 11.4-11.9 tok/s a lone request gets |
| V5c | if V5b is not enough, take the last gigabyte from the cap | `SPLASH_FLASH_NEXT_MAX_MEMORY=9G SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1 bash startllamacpp.sh --direct 20` | **done 2026-11-04, faster and structurally worse** (`qwen38-option20-v5c-20261104.md`). Prefill hit the series best - 28,589 tokens in 156.24 s at 183.0 tok/s, decode 11.7 tok/s - but the lane still serialized (child queued 165.3 of 167.3 s, b2 0, overlap 0.997), `host_headroom_bytes` peaked at 0.52 GiB (below V5's 0.80, because the spill floors cost 669 MiB + 409 MiB hot cache + 145 MiB staging), and `kv_capacity_tokens` fell to 114,688 with resident 114,681, under the served 131,072 context |
| V5e | the configuration the recommendation now points at: 10G cap, two lanes, browser closed | `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2 SPLASH_FLASH_NEXT_SECOND_LANE_BELOW_GATE=1 bash startllamacpp.sh --direct 20` | `growth_allowed` true with `host_headroom_bytes` above 1.5 GiB **while a 100k-token conversation is resident**, child queued in under 20 s, resident KV 196,601 tokens stays above the served 131,072, and cold 28,589-token prefill within 10% of V5's 166.4 tok/s |
| V6 | expert quantization reduction | smaller quant of the same GSQ-RCO build | gated on correctness first (ORCHID, count-to-30, DFlash2 acceptance), then speed |

Verification for every row: `/status` before and after (`streamed_experts`
`cap_bytes`/`resident`/`hit_rate`, `memory_governor.denied_reservations`,
`memory_pressure`, `thermal_state`), then the `option20-live-20261102-evening`
script set with 10 s cooldowns and contaminated rows dropped. Salt rule: a fresh
`cache_salt` makes a row cold on purpose, because the salt is part of the cache
key. Hold the salt fixed when measuring reuse, change it when a cold row is
wanted. The 2026-11-02 claim that prefix reuse failed on a repeated prompt was
this salt, not the cache.

## What a larger memory cap can and cannot do on this 16 GB Mac

The cap is still not the binding constraint. Before V1 the governor showed a
10 GiB limit, 8.85 GiB charged, 1.89 GiB of cap headroom, and
`growth_allowed: false` because `host_spare_bytes` 1.90 GiB was below the
`host_spare_reserve_bytes` 2.15 GiB it keeps for macOS (7% of memory, clamped to
2-7 GiB). Every denied reservation came from that gate, not from the cap.

After V1 the disk tier changed that picture: charged fell to 8.58 GiB, cap
headroom rose to 2.16 GiB, host spare rose to 2.52 GiB and host headroom over the
reserve went from 0 to 0.37 GiB. The host gate is now open, yet the expert store
is still at its 2,089 MiB floor with 512 of 24,576 slots, 34 resident and
`hit_rate` 0.00, because `--expert-memory auto` sized the store at plan time and
`regrows` stays 0. Headroom is not spent on experts by itself.

- The engine clamps any cap to its automatic ceiling: the recommended working set
  (11.84 GiB here) minus a 1 GiB margin, i.e. about **10.84 GiB**. So `11G` is the
  largest useful value on this machine and `12G` or more buys nothing.
- Raising the cap alone therefore frees about 0.84 GiB of budget the governor
  will not spend while host spare stays under 2.15 GiB. Expect no measurable gain
  by itself.
- Raising the cap *with* the disk prefix cache is the sequence that paid, and V1
  and V3 confirmed both halves of it for the KV side: KV spills to disk, host
  spare rises above the reserve, and a 16 GiB quota holds what an 8 GiB one
  cannot (5,314 KV blocks, 7,076 MiB restored at startup).
- What V2 and V3 falsified is the other half. `/status` `memory_plan.budget`
  gives 3.46 GiB of `dynamic_budget_bytes` after `fixed_runtime_bytes` (7.38 GiB
  of weights, stores and reserves), and the resident KV pool claims 3.23 GiB of
  it (`kv_capacity_pages` 8,192, `kv_capacity_tokens` 262,144, and the startup
  line `resident 262137` shows the allowance is sized against the model's
  262,144-token window, not the 131,072 tokens this profile serves). An explicit
  `--expert-memory` is only a floor (`MemoryPlan.cpp:247`), and a floor above the
  leftover is rounded **down** to the whole slots and chunks the plan leaves, so
  it does not win that contest at all. `planSpill()` (`MemoryPlan.cpp:115-172`)
  binary-searches the longest context whose spill floors fit, the whole window
  fits on this Mac, and the experts keep their 2 GiB minimum and nothing more.
- Runtime growth cannot finish the job either. After the 65k row the governor
  held 2.51 GiB under its 11.64 GiB limit with `growth_allowed: false` and
  10,703 denied reservations, because `host_headroom_bytes` was 0 against the
  2.15 GiB it keeps for macOS. On 16 GB the room under the Metal cap and the room
  the operating system has are different budgets.
- Under `auto` the store can hold elastic chunks above its own floor and give them back down to
  it, but V2 and V3 showed the elasticity is decided at plan time and never at request time:
  `regrows` stayed 0 and `shrinks` stayed 0 through every row, so the shape to aim for is a plan
  that leaves the experts more at startup, not a store that grows while a request runs.
- The direction of that trade is already asserted by the engine's own plan tests.
  `dev/tests/engine/engine_memory_plan_test.cpp` (`testDenseExplicitContextKeepsMainsExperts`,
  `testDenseExplicitContextStreamsExperts`) shows a dense target loading every expert whole up to
  the context its KV allowance leaves, and streaming them from one token past that point: the
  context reservation and expert residency are the same budget seen from opposite ends. That is why
  V4 changes the served context rather than the expert flag.
- The gain is still bounded by reuse. Cached service costs 13.5 microseconds per
  expert on this GPU against 343 microseconds of SSD streaming, so a tile must be
  used about 25 times to pay for its slot. Decode is bandwidth-bound at 452 MB
  per token, so cutting expert streaming by 30% is worth roughly 30% of decode
  time, and that is the number the V3 rows measured: 452 MB per token at the 8 GiB
  quota, 510-546 MB per token at 11 GiB with the 4 GiB floor, and no change in tok/s.
- Watch the downside: extra residency on a 16 GB Mac means swap. The evening run
  was 6-7% slower in prefill than the morning run on the same instance, which is
  the cost of memory pressure. If `memory_pressure` reaches `red` or swap passes
  ~2 GiB, drop back to `10G` and `--expert-memory auto`.

## Out of reach, or reachable only on condition, on 16 GB at 131,072 tokens

- **A large expert store.** The routed experts need about 44 GiB as tiles and
  about 93 GiB as store slots. No Mac under 128 GB can hold them; 24-64 GB
  changes the fraction from 2% to 25-60%, which is where the big decode numbers
  in the scaling report come from. At 131,072 context on this Mac the store cannot
  even reach 3 GiB, because the resident KV allowance for the model's 262,144-token
  window takes the whole dynamic budget.
- **ANE.** `ane_ffn.state` is `off`: the target's FFN layers are not all dense,
  and the routed experts are exactly what the ANE would need.
- **Two lanes at the 131,072 context this profile serves are not a knob on 16 GB;
  they are a host-memory condition.** A second lane does not add 1.9 GiB of lane
  state: lane state is reserved for all four batch positions anyway
  (`ExecutionLimits::maximumBatchWidth` 4, `lane_state_bytes` 163,250,176 in
  `fixed_runtime_bytes`). Two things have to hold at once. `growth_allowed` needs
  `host_headroom_bytes` >= 1 GiB above the 2.147 GiB macOS reserve, so the host must
  keep about 3.15 GiB spare. And residency should cover the served context, which
  needs the cap high enough: resident KV is 262,137 tokens at 11G, 196,601 at 10G,
  114,681 at 9G (about 77,000 tokens per GiB). V4, V5 and V5c admitted the child and
  held it for the parent's whole run because headroom sat at 0.26, 0.80 and 0.52 GiB.
  V5b reached 1.13-1.28 GiB at the 9G cap with Chrome and LM Studio quit, and the
  child then ran alongside its parent. So the lane is available on 16 GB only with
  browser-class apps closed, and its honest cost is that two overlapping requests each
  decode at about half speed. 24 GB or more is still the answer when the machine has
  to carry a browser, an agent session and a delegated child at the same time.

## Machine watchlist

- On any 24 GB or larger Mac, the launcher now permits a larger cap; pair it with
  `SPLASH_FLASH_NEXT_EXPERT_MEMORY` of 3-6 GiB and re-measure. The scaling report
  projects 15-18 tok/s at 48-64 GB with those stores against 14-18 tok/s with the
  automatic store.
- The launch command for a fresh big-RAM profile is recorded in the scaling
  report's Section 6 and matches the knobs implemented above.
