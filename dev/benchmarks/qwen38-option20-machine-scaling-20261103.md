# Option 20 cross-machine throughput estimates (2026-11-03)

Historical estimates: superseded by the
[November 5 six-Mac prefill and generation update](qwen38-option20-mac-rebase-20261105.md).
The intermediate [November 4 log review](qwen38-option20-cache-estimates-20261104.md)
is also retained for history.
The larger-cache hit rates, linear store-cost scaling, launcher constraints,
and two-lane aggregate-throughput assumptions below must not be treated as
current measurements or validated predictions. This report is retained as the
original dated analysis.

Estimates for five machines, derived from measurements taken on this 16 GB
M5 MacBook Air against the live 131k option 20 server (build `src-6a06f0d6c0d0`,
git `3c693864`). Companion reports: [the live 131k benchmark](qwen38-option20-live-131k-20261102.md),
[the evening rerun](qwen38-option20-live-131k-evening-20261102.md), and
[the tuning plan](qwen38-option20-tuning-plan-20261102.md).

Confidence, stated up front:

- the default-flag column is high confidence. Two measured quantities (expert
  bytes per prefill token, expert bytes per decode token) reproduce both
  measured throughputs on this machine to within one percent, so the scaling
  arithmetic is anchored rather than guessed;
- the tuned column is medium to low confidence. It depends entirely on the
  traffic hit rate of a larger expert cache, which has never been measured on
  this profile;
- GPU core counts, GPU memory bandwidth, and SSD bandwidth for M5 Pro and M5
  Max are assumptions. I cannot verify Apple's spec sheets from this machine.
  Only RAM capacity is certain.

## 1. Measured basis on this machine

A controlled decode (110 emitted tokens, reasoning off, `verify_rows auto`)
with `/status` counters diffed before and after:

```text
TTFT 1.87 s, 12.98 tok/s
engine decode wall 8453 ms, engine decode gpu 8443 ms   (99.8% of wall charged to the GPU)
expert routed reads 24,607   physical loads 720   streamed 49.75 GB
per emitted token: 223.7 routed expert reads, 6.5 physical loads, 452 MB streamed
implied sustained read bandwidth during decode: 5.89 GB/s
```

A controlled cold prefill (936 prompt tokens, unique cache salt, 8 output
tokens):

```text
TTFT 6.48 s, 145.9 tok/s prompt processing
engine prefill wall 6420 ms, gpu 6410 ms
expert routed reads 14,014 in 48 physical loads, streamed 33.76 GB
per prompt token: 14.97 routed expert reads, 36.1 MB streamed
implied sustained read bandwidth during prefill: 5.26 GB/s
PLE row cache: prefill hit_rate 0.967, decode hit_rate 0.583
```

The storage device itself, read in 3 GiB sequential chunks out of the 43.8 GiB
Flash-Next blob:

```text
cold  offset 3 GiB   3.64 GB/s
cold  offset 12 GiB  5.51 GB/s
cold  offset 24 GiB  5.51 GB/s
warm  offset 3 GiB   6.10 GB/s
warm  offset 12 GiB  6.28 GB/s
```

Two facts follow. The engine demands 5.26 GB/s in prefill and 5.89 GB/s in
decode, and this Air's SSD supplies 3.6 to 6.3 GB/s, so **both phases run at
the storage ceiling**, not at a compute ceiling. And `ane_ffn.state` is `off`
with reason `the target's FFN layers are not all dense`, so the Neural Engine
cannot carry this model's experts on any M5 machine; extra ANE capacity in a
Pro or Max part does not apply to this workload.

## 2. The scaling law

With streamed bytes per token measured, throughput follows bandwidth directly:

```text
prompt processing tok/s = streamed read bandwidth / streamed MB per prompt token
decode tok/s            = streamed read bandwidth / streamed MB per emitted token

this machine: 5.26 GB/s / 36.1 MB = 145.7 tok/s   (measured 145.9)
              5.89 GB/s / 452 MB  = 13.03 tok/s   (measured 12.98)
```

Prefill and decode differ by 12.5x in bytes per token because a 1,024-token
prefill chunk amortizes each expert load across a thousand tokens, while decode
pays 6.5 physical expert loads per emitted token. That single ratio explains
why this profile measures 146 tok/s in prefill and 13 tok/s in decode.

## 3. Why nothing is resident: the weight-volume budget

The option 20 target downloads 75,839,998,528 bytes (70.6 GiB) of GGUF across
two shards, and the engine keeps only `target_weights_bytes`
5,665,555,216 (5.28 GiB) resident. The rest streams by design:

| volume | size | source |
|---|---|---|
| target GGUF, two shards | 70.6 GiB | `profile.json` `model_files_total_bytes` |
| per-layer token embedding table (`per_layer_token_embd.weight`) | 26.8 GiB | `/status` `streamed_table.table_bytes` 28,800,138,240 |
| expert tiles, implied | 43.8 GiB | 24,576 slots x 2.02 MB per routed read = 49.6 GB, matching 70.6 GiB minus the 26.8 GiB table within 6% |
| resident plan | 9.17 GiB minimum | `memory_plan.minimum_bytes` |

The cross-check matters: 24,576 expert slots at 2.02 MB per routed read is
49.6 GB, which is the model's non-table weight volume to within 6 percent. The
model's full routed-expert working set is therefore about 44 GiB of quantized
tiles, or about 93 GiB once the engine's arena and staging overhead
(3.89 MiB of store budget per slot, 1.93x the 2.02 MB tile) is included. No
Mac below 128 GB can hold it, which is exactly why this profile exists and why
"just load the model into RAM" is not an option here.

## 4. Why host-memory expert caching helps, with the arithmetic

### 4.1 What is actually being paid for

Each routed expert must be materialized before it can be used. The engine
measures this as `streamed_experts`: routed reads, physical loads, and
`read_bytes`. On this machine the store is stuck at its floor:

```text
cap_bytes      2,089,468,688  (1,992 MiB)  == floor_bytes
arena_bytes    1,323,827,200  (1,262 MiB)  resident GPU-side tiles
staging_bytes    765,460,480  (  730 MiB)  host-side staging
slots                  512    of 24,576 experts (2.1% of capacity)
resident                38    (0.15% actually resident)
shrinks 0, regrows 0, hits 0, misses 151,971
streamed_experts.decode.hit_rate 0.00
```

So every expert byte this machine uses comes off the SSD. The store is not
undersized because memory pressure took it away. `--expert-memory auto` never
raised it, and `memory_plan.native_budget` reserves 1,992,415,744 bytes as a
floor with `host_experts_can_move: false`: the floor is a hard reservation that
cannot be handed to the model. The SSD path is the configured budget, not an
accident.

### 4.2 Store size to cache coverage

One slot costs 1,992 MiB / 512 slots = **3.89 MiB** of store budget, which is
1.93x the 2.02 MB quantized tile it holds (the difference is the arena copy
plus the staging copy). Slots therefore scale as 1,024 / 3.89 = **263 slots per
GiB**:

| expert store | slots | coverage of 24,576 experts |
|---|---|---|
| 1.9 GiB (today, auto floor) | 512 | 2.1% |
| 2 GiB | 526 | 2.1% |
| 4 GiB | 1,053 | 4.3% |
| 8 GiB | 2,106 | 8.6% |
| 12 GiB | 3,159 | 12.9% |
| 16 GiB | 4,212 | 17.1% |
| 24 GiB | 6,317 | 25.7% |
| 32 GiB | 8,423 | 34.3% |
| full residency | 24,576 | 100%, needs 93.8 GiB of store budget |

Coverage of slots is not coverage of traffic. If routing were uniform, a cache
holding fraction c of slots would capture fraction c of routed bytes. Routing is
almost never uniform in a top-k MoE, so with skew the traffic hit h exceeds c.
**This is the unknown that decides whether a bigger machine is 1.4x or 3x this
one**, and it has not been measured here because the store has never been large
enough to measure (`hit_rate` 0.00 with 38 resident slots).

### 4.3 Throughput as a function of the traffic hit

With 452 MB streamed per emitted token and a storage bandwidth B:

```text
decode tok/s = B / (452 MB x (1 - h))
prefill tok/s = B / (36.1 MB x (1 - h))
```

| traffic hit h | decode MB per token | decode tok/s at 5.9 GB/s (Air SSD) | decode tok/s at 7.0 GB/s (Pro SSD) | prefill tok/s at 7.0 GB/s |
|---|---|---|---|---|
| 0.00 (today) | 452 | 13.1 | 15.5 | 194 |
| 0.10 | 407 | 14.5 | 17.2 | 215 |
| 0.25 | 339 | 17.4 | 20.6 | 258 |
| 0.45 | 249 | 23.7 | 28.1 | 352 |
| 0.65 | 158 | 37.3 | 44.3 | 555 |
| 0.85 | 68 | 86.8 | 102.9 | 1,310 |

Read the last two rows as ceilings, not promises: they assume the SSD stops
being the limit at all, which requires the cache to absorb the traffic rather
than merely shorten it.

### 4.4 Break-even: how many reuses pay for one cached tile

Cost of a use from storage: 2.02 MB / 5.89 GB/s = **0.343 ms** of SSD time.
Cost of a use from resident memory: 2.02 MB / 150 GB/s (Air GPU-side unified
bandwidth) = **13.5 microseconds**, and about 7 microseconds at 300 GB/s on a
Pro-class part.

```text
break-even reuses on this Air:  0.343 ms / 13.5 us  = 25 uses
break-even reuses on an M5 Pro: 0.343 ms /  6.7 us  = 51 uses
```

Equivalent framing at the token level: this machine spends 1 / 13.03 s = 76.7 ms
of SSD time per emitted token. A cache that captures fraction h of routed
traffic removes h x 76.7 ms per token, so decode tok/s = 1 / (76.7 ms x (1 - h)),
which reproduces the table above (h = 0.25 gives 17.4 tok/s).

Whether an expert clears break-even depends on how often the router picks it. A
hot tile routed once every 25 tokens is reused 25 times in about 50 seconds of
generation at 13 tok/s, which already pays for its own load on an Air and pays
for it half over on a Pro. A tile routed once every 500 tokens never pays.
Because decode routes 223.7 experts per token across the model's MoE layers,
there are 2,904 routed expert evaluations per second on this machine, so the
reuse opportunity is large in aggregate even when any single tile is rare.

### 4.5 What the cache does not fix

- it does not change compute demand: 223.7 expert evaluations per emitted token
  remain 223.7. That demand is tiny compared with the bandwidth demand (about
  31 GFLOP/s at 13 tok/s for a multi-TFLOP GPU), which is why the 99.8%
  `decode.gpu_ms` share is staging and dequant work, not matmul math;
- it does not fix cold-prompt TTFT as much as it fixes decode. Prefill already
  amortizes 36.1 MB per token instead of 452 MB, so the absolute win per token
  is 12.5x smaller. The large TTFT lever is `SPLASH_FLASH_NEXT_MAX_CACHE_DISK`
  (experiment E5), which today is 0 bytes: cold 65k prompts pay full prefill
  every time;
- it can thrash. A store sized for a long-tail routing distribution evicts as
  fast as it fills, and the eviction cost lands back on the SSD. The engine
  exposes `streamed_table.evictions` 2,683,358 and `state.evictions` 152 as
  evidence that eviction pressure is real on this profile, while experts show
  `shrinks 0` because the store never grew past its floor;
- the engine already hides part of the latency: of 29,888,708 routed decode
  reads, 10,779,985 (36.1%) were `prefetched` and 13,604,168 (45.5%) were
  `read_ahead`. A cache's value is proportional to the remaining, non-prefetchable
  tail;
- it competes with the other budgets. On this machine 1,992 MiB of expert floor
  plus 5,665,555,216 target weights plus 614,678,528 shared prefill plus
  183,840,928 shared decode plus 212,336,896 PLE budget is 8.2 GiB of hard
  floors against a 12,713,115,648 byte working set, which is exactly why the
  plan reports `headroom_status: tight` with 29,483,008 bytes spare.

## 5. Memory budget per machine

The engine plans against a working set of about 74% of RAM (measured here:
`recommended_max_working_set_bytes` 12,713,115,648 of 17,179,869,184 = 74.0%).
Fixed resident costs, all measured from `memory_plan`:

| item | bytes | GiB |
|---|---|---|
| target weights (resident portion) | 5,665,555,216 | 5.28 |
| draft weights (DFlash2) | 523,436,032 | 0.49 |
| lane state, per lane | 163,250,176 | 0.15 |
| shared prefill workspace | 614,678,528 | 0.57 |
| shared decode workspace | 183,840,928 | 0.17 |
| KV cache, INT8, 131,072 tokens | 1,736,708,864 (13,248 B/token) | 1.61 |
| KV cache, INT8, 262,144 tokens | 3,473,417,728 | 3.23 |
| PLE row cache (`--ple-memory`) | 67,108,864 today | 0.06 (0.50 if raised) |

Fixed resident sums to 8.8 GiB: 5.28 + 0.49 + 0.15 + 0.57 + 0.17 + 1.61 + 0.50.

| machine | working-set budget | fixed resident (131k, 1 lane, 512 MiB PLE) | room for the expert store | slots | coverage |
|---|---|---|---|---|---|
| M5 Air 16 GB | 11.8 GiB | 8.8 GiB | about 3 GiB | 790 | 3.2% |
| M5 Air 32 GB | 23.7 GiB | 8.8 GiB | about 15 GiB, but plan floor pressure remains | 3,900 | 15.9% |
| M5 Pro 48 GB | 35.5 GiB | 8.8 GiB | about 27 GiB | 7,100 | 28.9% |
| M5 Max 36 GB | 26.6 GiB | 8.8 GiB | about 18 GiB | 4,740 | 19.3% |
| Mac mini M5 Pro 64 GB | 47.4 GiB | 8.8 GiB | about 39 GiB | 10,260 | 41.7% |

Practical settings are one step below the arithmetic ceiling, because macOS,
Metal fragmentation, and the agent itself also live in the same unified memory:
24 GiB on a 64 GB machine, 12 to 16 GiB at 48 GB, 8 to 12 GiB at 36 GB, 4 to
6 GiB at 32 GB.

One launcher constraint applies before any of this: the option 20 profile accepts
only `SPLASH_FLASH_NEXT_MAX_MEMORY` in `8G|9G|10G|11G` (`startllamacpp.sh:1646`)
and caps `SPLASH_FLASH_NEXT_MAX_CONTEXT` at 131,072 (`startllamacpp.sh:1670`). A
64 GB machine gets nothing from its extra RAM until that whitelist is widened
and `--expert-memory` and `--ple-memory` are raised, which is a launcher edit
that must land together with the option 20 launcher tests.

## 6. Estimates at today's exact option 20 flags

10 GiB memory cap, `--expert-memory auto` (store stays at the 1,992 MiB floor,
512 slots, 38 resident), 64 MiB PLE cache, 1,024-token chunks, `--verify-rows
auto`, one active request, disk prefix cache off:

| machine | assumed SSD read bandwidth | PP, 939 to 4,019 tokens | PP, 28,589 to 65,367 tokens | decode, reasoning off | decode, reasoning low or medium | TTFT at 28,589 | TTFT at 65,367 |
|---|---|---|---|---|---|---|---|
| M5 Air 16 GB (measured) | 5.3 to 5.9 GB/s | 142 to 150 | 146 to 161 | 11.5 to 13.0 | 5.5 to 7.0 | 190 s | 420 to 446 s |
| M5 Air 32 GB | 5.3 to 6.0 GB/s | 145 to 155 | 155 to 170 | 11.5 to 13.0 | 5.5 to 7.0 | 170 to 185 s | 385 to 420 s |
| M5 Pro 48 GB (MacBook Pro) | 6.5 to 8 GB/s | 175 to 215 | 175 to 215 | 14 to 18 | 7 to 9 | 135 to 165 s | 305 to 375 s |
| M5 Max 36 GB | 7 to 8.5 GB/s | 185 to 235 | 185 to 230 | 15 to 19 | 7.5 to 9.5 | 125 to 155 s | 285 to 355 s |
| Mac mini M5 Pro 64 GB | 6.5 to 8 GB/s | 180 to 220 | 180 to 225 | 14 to 18 | 7 to 9 | 130 to 160 s | 295 to 365 s |

These are bandwidth arithmetic: 36.1 MB and 452 MB per token held constant,
bandwidth varied. The Mac mini row is the same silicon class as the MacBook Pro
row but with a sustained-cooling envelope instead of an edge-limited one, and
with `memory_pressure` gone entirely, so its prefill does not lose the 4 to 8
percent that this Air loses at 28.5k and 65k context.

## 7. Estimates with the profile tuned for the bigger machine

Settings assumed: `--expert-memory` at the per-machine practical value above,
`--ple-memory 512M`, `SPLASH_FLASH_NEXT_MAX_CACHE_DISK=8G`, `SPLASH_FLASH_NEXT_PREFILL_MAX_TOKENS=2048`,
`--max-active-requests 2`, 131,072 context. Traffic hit h is the unknown, so
each row shows the uniform-routing floor and the moderate-skew expectation.

| machine | expert store | slots (coverage) | decode tok/s at h = coverage (uniform) | decode tok/s at moderate skew | PP tok/s at moderate skew | aggregate decode with 2 lanes |
|---|---|---|---|---|---|---|
| M5 Air 16 GB | 2 to 3 GiB, at 32,761 context | 526 to 790 (2.1 to 3.2%) | 13 to 14 | 14 to 15 | 170 to 185 | 27 to 30 (32k context only) |
| M5 Air 32 GB | 4 to 6 GiB | 1,053 to 1,579 (4.3 to 6.4%) | 13 to 14 | 14 to 17 | 165 to 200 | 28 to 34 (only at 32k context) |
| M5 Max 36 GB | 8 to 12 GiB | 2,106 to 3,159 (8.6 to 12.9%) | 16 to 17 | 18 to 22 | 230 to 290 | 36 to 44 |
| M5 Pro 48 GB | 12 to 16 GiB | 3,159 to 4,212 (12.9 to 17.1%) | 17 to 18 | 20 to 25 | 250 to 320 | 40 to 50 |
| Mac mini M5 Pro 64 GB | 24 to 32 GiB | 6,317 to 8,423 (25.7 to 34.3%) | 20 to 23 | 24 to 34 | 280 to 380 | 48 to 68 |

For the Mac mini at 24 GiB and a 0.35 traffic hit, the arithmetic is explicit:
452 MB x 0.65 = 294 MB per token, 7.0 GB/s / 0.294 GB = 23.8 decode tok/s;
36.1 MB x 0.65 = 23.5 MB per prompt token, 7.0 GB/s / 0.0235 GB = 298 PP tok/s,
which puts a cold 28,589-token prompt at 96 seconds and a cold 65,367-token
prompt at 220 seconds. At 32 GiB and a 0.45 hit the same arithmetic gives 28.1
decode tok/s, 352 PP tok/s, 81 seconds to first token at 28.5k, and 186 seconds
at 65k. With the disk prefix cache on, warm agent turns skip most of that.

The Mac mini has one option no laptop has: Thunderbolt 5 on a Pro-class mini can
carry an external NVMe volume at roughly 3 to 6 GB/s. That does not beat the
internal drive, so the right use is capacity rather than speed: put the GGUF
shards and the 8 GiB disk prefix cache on the external volume so the internal
drive serves only expert streaming.

## 8. What to measure to confirm or kill these numbers

The measurement is two minutes of counter diffing, not a benchmark:

1. start option 20 with `SPLASH_FLASH_NEXT_MAX_MEMORY` raised (widening the
   launcher whitelist first) and `--expert-memory 12G`;
2. snapshot `/status`, run one decode-only request (110 tokens, reasoning off),
   snapshot again, and diff `streamed_experts.decode.{routed, loads, read_bytes}`
   plus `model_timing.decode.{total_wall_ms, total_gpu_ms}`;
3. compute streamed MB per emitted token, physical MB per load, and implied GB/s
   exactly as in section 1, then read `streamed_experts.resident` and
   `streamed_experts.decode.hit_rate`.

Decision rule: if bytes per emitted token fall from 452 toward 250, the tuned
column is real and the machine is worth 2x. If they stay near 450, routing is
uniform, residency is decorative, and the only lever left is storage bandwidth,
at which point a 48 GB M5 Pro is about 1.35x this machine and a 64 GB Mac mini
is about the same, and the purchase is justified by context capacity and lane
count rather than by speed.

Measured on 2026-11-03, this machine already failed step 1 for a reason the
estimate did not anticipate (`qwen38-option20-v2-20261103.md`,
`qwen38-option20-v3-20261103.md`): at 16 GB and 131,072 context, `--expert-memory
2G` and `--expert-memory 4G` both produce the same 1,992 MiB, 512-slot store as
`auto`, because the plan first reserves the resident KV allowance for the model's
whole 262,144-token window and the flag only sets a floor that the plan rounds
back down to what is left. Bytes per emitted token went the wrong way, 452 to
510-546. The tuned columns of section 7 still stand for the larger machines,
where the KV window floors are satisfied many gigabytes early and a requested
floor lands inside the leftover instead of above it, but they now depend on a
measurement that has to be made on such a machine.

## 9. Side by side: prompt processing and decode throughput

Machines as columns, so the comparison is a single glance. Anchor is the measured
M5 Air 16 GB: PP 145.9 at 936 prompt tokens, 146 to 161 at 28.5k to 65k, TPS
12.98, 452 streamed MB per emitted token at 5.89 GB/s against an SSD that
supplies 3.64 to 6.28 GB/s.

### Today's exact option 20 flags

10 GiB cap, `--expert-memory auto` (store pinned at the 1,992 MiB floor), 64 MiB
PLE cache, 1,024-token chunks, `--verify-rows auto`, one active request, disk
prefix cache off.

| metric | M5 Air 16 GB (measured) | M5 Air 32 GB | M5 Pro 48 GB (MacBook Pro) | M5 Max 36 GB | Mac mini M5 Pro 64 GB |
|---|---|---|---|---|---|
| assumed SSD read bandwidth | 5.3 to 5.9 GB/s | 5.3 to 6.0 | 6.5 to 8.0 | 7.0 to 8.5 | 6.5 to 8.0 |
| **PP**, 939 to 4,019 token prompt | **142 to 150** | **145 to 155** | **175 to 215** | **185 to 235** | **180 to 220** |
| **PP**, 28,589 to 65,367 token prompt | **146 to 161** | **155 to 170** | **175 to 215** | **185 to 230** | **180 to 225** |
| **TPS**, reasoning off | **11.5 to 13.0** | **11.5 to 13.0** | **14 to 18** | **15 to 19** | **14 to 18** |
| **TPS**, reasoning low (launcher default) | **5.5 to 7.0** | **5.5 to 7.0** | **7 to 9** | **7.5 to 9.5** | **7 to 9** |
| TTFT at 28,589 prompt tokens | 190 s | 170 to 185 s | 135 to 165 s | 125 to 155 s | 130 to 160 s |
| TTFT at 65,367 prompt tokens | 420 to 446 s | 385 to 420 s | 305 to 375 s | 285 to 355 s | 295 to 365 s |
| PP multiplier vs this Air | 1.00x | 1.06x | 1.27x | 1.35x | 1.32x |
| TPS multiplier vs this Air | 1.00x | 1.00x | 1.31x | 1.39x | 1.31x |

Each column is bandwidth divided by the same two measured constants, 36.1 MB per
prompt token and 452 MB per emitted token. RAM moves nothing here because
`--expert-memory auto` never spends spare RAM on the expert store.

### With the expert store sized to the machine

`--expert-memory` raised to the practical value for that RAM, `--ple-memory 512M`,
`SPLASH_FLASH_NEXT_MAX_CACHE_DISK=8G`, 2,048-token chunks,
`--max-active-requests 2`, 131,072 context.

| metric | M5 Air 16 GB (measured) | M5 Air 32 GB | M5 Max 36 GB | M5 Pro 48 GB | Mac mini M5 Pro 64 GB |
|---|---|---|---|---|---|
| expert store | 2 to 3 GiB | 4 to 6 GiB | 8 to 12 GiB | 12 to 16 GiB | 24 to 32 GiB |
| slots, coverage of 24,576 | 526 to 790, 2.1 to 3.2% | 1,053 to 1,579, 4.3 to 6.4% | 2,106 to 3,159, 8.6 to 12.9% | 3,159 to 4,212, 12.9 to 17.1% | 6,317 to 8,423, 25.7 to 34.3% |
| **TPS**, uniform routing floor | **13 to 14** | **13 to 14** | **16 to 17** | **17 to 18** | **20 to 23** |
| **TPS**, moderate routing skew | **14 to 15** | **14 to 17** | **18 to 22** | **20 to 25** | **24 to 34** |
| **PP**, moderate routing skew | **170 to 185** | **165 to 200** | **230 to 290** | **250 to 320** | **280 to 380** |
| **TPS**, aggregate across 2 lanes | 27 to 30, 32k context only | 28 to 34, 32k context only | 36 to 44 | 40 to 50 | 48 to 68 |
| TTFT at 28,589 prompt tokens | 155 to 168 s | 145 to 175 s | 100 to 125 s | 90 to 115 s | 75 to 102 s |
| TTFT at 65,367 prompt tokens | 355 to 385 s | 325 to 395 s | 225 to 285 s | 205 to 260 s | 172 to 235 s |
| PP multiplier vs this Air | 1.16x | 1.19x | 1.69x | 1.86x | 2.15x |
| TPS multiplier vs this Air | 1.18x | 1.27x | 1.63x | 1.84x | 2.37x |

The first column is this machine, and its tuned configuration is constrained in a
way the others are not. Its working set is 11.8 GiB against 8.8 GiB of fixed
resident cost, so a 2 to 3 GiB expert store only fits by giving context back:
the realistic tuned 16 GB profile is 32,761 served context with `--expert-memory
3G`, which is also experiment E1 and the only 16 GB configuration that measured
faster prefill (179.65 tok/s at 28,589 tokens on 2026-11-01, against 149.47 to
161.02 at 131,072). Two lanes on 16 GB are likewise a 32k-context option, not a
131k option, because the second lane's INT8 KV reservation does not fit beside a
larger store.

The distance between the two tables is the routing-skew assumption alone. If the
top-k router is effectively uniform, the tuned columns collapse onto the default
columns and a 64 GB Mac mini is worth about 1.3x rather than 2.4x. Section 8 is
the two-minute measurement that decides which world the purchase lives in.
