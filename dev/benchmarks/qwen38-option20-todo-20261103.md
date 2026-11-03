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
   accepts `1` or `2`. `2` is admitted only when the machine can carry a second
   lane: 24 GB or more at 131,072 context, 16 GB or more at 65,536 or below.
   Options 14, 16, 18 and 19 stay single-lane.
6. **Cache quota preflight**: the launcher now refuses a quota larger than the
   free space on the volume that will hold the cache.
7. **Tests**: `dev/benchmarks/test_bonsai_launcher.py` covers the new defaults,
   the new knobs, the second-lane admission rule, the host memory ceiling, and
   the disk quota preflight.

## Pending, in order (each needs one authorized restart)

| # | Change | Command | Accept when |
|---|---|---|---|
| V1 | verify the new 8G prefix cache default at 131k | `bash startllamacpp.sh --direct 20` | prefill TTFT drops, `cache.kv_disk_hit_tokens` grows, `memory_pressure` stays at or below `warning`, expert `cap_bytes` no smaller than 1,992 MiB |
| V2 | raise the expert store, funded by the disk tier | `SPLASH_FLASH_NEXT_MAX_MEMORY=11G SPLASH_FLASH_NEXT_EXPERT_MEMORY=3G bash startllamacpp.sh --direct 20` | `streamed_experts.cap_bytes` rises near 3 GiB, `resident` climbs well past 38, decode tok/s rises, swap stays under ~2 GiB |
| V3 | re-sweep prefill chunks at 131k | `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048 ...` | 2048 beats 1024 at 28,672 and 65,451 without raising peak bytes by more than ~1 GiB |
| V4 | two lanes where the machine allows it | `SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=2` on a 24 GB or larger Mac | subagent children run while the parent works; wall time per delegated task drops |
| V5 | expert quantization reduction | smaller quant of the same GSQ-RCO build | gated on correctness first (ORCHID, count-to-30, DFlash2 acceptance), then speed |

Verification for every row: `/status` before and after (`streamed_experts`
`cap_bytes`/`resident`/`hit_rate`, `memory_governor.denied_reservations`,
`memory_pressure`, `thermal_state`), then the `option20-live-20261102-evening`
script set with 10 s cooldowns, unique salts, and contaminated rows dropped.

## What a larger memory cap can and cannot do on this 16 GB Mac

The cap is not the binding constraint today. `/status` shows the governor with a
10 GiB limit, 8.85 GiB charged, 1.89 GiB of cap headroom, and
`growth_allowed: false` because `host_spare_bytes` 1.90 GiB is below the
`host_spare_reserve_bytes` 2.15 GiB it keeps for macOS (7% of memory, clamped to
2-7 GiB). All 574 denied reservations come from that gate, not from the cap.

- The engine clamps any cap to its automatic ceiling: the recommended working set
  (11.84 GiB here) minus a 1 GiB margin, i.e. about **10.84 GiB**. So `11G` is the
  largest useful value on this machine and `12G` or more buys nothing.
- Raising the cap alone therefore frees about 0.84 GiB of budget the governor
  will not spend while host spare stays under 2.15 GiB. Expect no measurable gain
  by itself.
- Raising the cap *with* the 8G disk prefix cache (V1 then V2) is the sequence
  that can pay: the disk tier gives KV and state somewhere to live, host spare
  rises, and the expert store can move from 512 slots (2.1% of 24,576) toward
  roughly 1,500 slots. Every 263 slots is one GiB of store.
- The gain is still bounded by reuse. Cached service costs 13.5 microseconds per
  expert on this GPU against 343 microseconds of SSD streaming, so a tile must be
  used about 25 times to pay for its slot. Decode is bandwidth-bound at 452 MB
  per token, so cutting expert streaming by 30% is worth roughly 30% of decode
  time, and that is the number to watch after V2.
- Watch the downside: extra residency on a 16 GB Mac means swap. The evening run
  was 6-7% slower in prefill than the morning run on the same instance, which is
  the cost of memory pressure. If `memory_pressure` reaches `red` or swap passes
  ~2 GiB, drop back to `10G` and `--expert-memory auto`.

## Out of reach on 16 GB at 131,072 tokens

- **Two lanes.** A second lane adds about 1.9 GiB of lane state and KV
  reservation. That is why the launcher requires 24 GB for `2` active requests at
  this context. It is the fix for the delegation stall (a child request waits
  393 seconds behind a parent turn), and it needs a bigger machine or a smaller
  context.
- **A large expert store.** The routed experts need about 44 GiB as tiles and
  about 93 GiB as store slots. No Mac under 128 GB can hold them; 24-64 GB
  changes the fraction from 2% to 25-60%, which is where the big decode numbers
  in the scaling report come from.
- **ANE.** `ane_ffn.state` is `off`: the target's FFN layers are not all dense,
  and the routed experts are exactly what the ANE would need.

## Machine watchlist

- On any 24 GB or larger Mac, the launcher now permits a larger cap; pair it with
  `SPLASH_FLASH_NEXT_EXPERT_MEMORY` of 3-6 GiB and re-measure. The scaling report
  projects 15-18 tok/s at 48-64 GB with those stores against 14-18 tok/s with the
  automatic store.
- The launch command for a fresh big-RAM profile is recorded in the scaling
  report's Section 6 and matches the knobs implemented above.
