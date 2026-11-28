# Performance Optimizations — Last 30 Hours (2026-11-27)

- **Branch:** `option20-best-pp-20261106` (`2954b477`..`3779ad89`, **25 commits**, `2026-11-27 10:21` – `23:26 EST`)
- **Hardware:** Apple M5 (8-core GPU, GPU family 10, 16 GiB unified memory, macOS 27.2.1)
- **Target Profile (Option 21):** `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` + local `DFlash2` BF16 draft (`10.8G` Metal cap, `4384M` `--expert-memory` = 2,983–3,069 / 24,576 resident experts, `2048`-token prefill chunks, `int8` KV, `bf16` GDN state)

---

## 1. Current Performance Snapshot (`3779ad89`)

Measured via quiet-GPU `decode-profile` (`2048`-token prompt, `B1` speculative decode):

| Metric | Cool GPU (`3779ad89`) | Warm GPU (8-cycle run) | Notes |
|---|---:|---:|---|
| **PP (fused, incl. SSD streaming)** | **506.9 tok/s** (`4040.6 ms`) | **489.2 tok/s** (`4186.7 ms`) | Best cool run (`08a1a5a2`): **511.0 tok/s** (`4008.0 ms`) |
| **PP (GPU compute only)** | **635.1 tok/s** (`3224.6 ms`) | **558.9 tok/s** (`3664.1 ms`) | Up from `605.0 tok/s` (`3385.0 ms`) at `2a24f94a` (**+5.0%**) |
| **TPS (`B1` decode, wall)** | **31.05 tok/s** (`32.21 ms/tok`) | **20.56 tok/s** (`48.64 ms/tok`) | `2.75` vs `2.25` draft tok/cycle (`829` vs `940 MiB/cycle` SSD reads) |
| **Decode GPU compute / cycle** | **71.91 ms** | **71.78 ms** | `moe_expert_load`: `7.84–7.90 ms` (`62.7–63.2 GB/s` native in `repack`) |

---

## 2. Changes by Subsystem

### A. MoE INT8 Prefill, Fusion & Glue Kernels
- **`2954b477`** — Added `Q2_0` INT8 prefill support (`prefill_int8_accum<2>` in `gguf_prefill_int8_tile.h`, `gguf_prefill_int8_q20_*`, `moe_expert_int8_q20_*`).
- **`9f265b5f`** — Enabled streamed `Q2_0` INT8 MoE passes (`moeInt8RoutedExperts`) so streamed blocks run `MOE_TILES_LOADED` on INT8 even when shared experts use a different format.
- **`68cdcb62`** — Lowered `Q2_0` MoE INT8 prefill activation threshold from 6 to 2 routes/expert.
- **`786e5956`** — Specialized `prefill_int8_accum` for `<=16`-row tiles (`-7.6%` to `-28.8%` on small expert tiles).
- **`4b6e7802`** — Fused `moe_expert_int8_*_gate` and `up` into a single `moe_expert_int8_*_gate_up` dispatch.
- **`2637aea8`** — Multiple MoE glue & router optimizations:
  - Vectorized `moe_combine` (`bfloat4`, 64-thread TG, 4-way unrolled route loads; `-25.1%` prefill `1.397 -> 1.046 ms`, `-31%` to `-37%` decode).
  - Coalesced `moe_gather_int8` scale writes by simdgroup, cached `src_rows[32]` in TG memory, added tile-range filtering.
  - Filtered `moe_gather_rows` to `MOE_TILES_RESIDENT` on streamed INT8 prefill (~85% less work) and cached `src_rows[64]` in TG memory.
  - Added 2-part (`hi + mid`) neural-accelerator router GEMM (`gguf_float_na2_*`, `-18.3%` to `-19.3%` router time).
  - Hoisted clamped row pointers in `prefill_int8_accum<2>` and vectorized `<=16`-row tiles to `uint4` activation loads (`-6%` to `-9.4%` at 256–768 rows).
- **`2a24f94a`** — Upgraded `moe_expert_int8_gate_up` to a 64-col / 4-simdgroup (128-thread) tile with 4 KiB `park[32][64]`, fusing INT8 quantization directly into `expertIntermediate` (`codes` + `scales`), eliminating the separate `gguf_prefill_int8_quantize` dispatch and `28.8 MB/layer` BF16 round-trip (`-3.1%` to `-5.0%` MoE prefill).
- **`dd370025`** — Split `MoeTileCount` resident tiles into `MOE_TILES_RESIDENT_ROUTED` and `MOE_TILES_SHARED`, added indirect dispatch grids for `MOE_TILES_SHARED` and all `moe_expert_int8_*` passes, and routed resident `Q2_0` experts through `addInt8Experts` (quantizing input rows once and reusing `inputCodes`/`inputScales` in `addRouted`):
  - MoE compute + gather: `884.12 -> 802.17 ms` (**`-81.95 ms`**, **`-9.3%`**).
  - Prefill separate dispatches: `3331.12 -> 3265.07 ms` (**`-66.05 ms`**).

### B. Dense INT8 Prefill & Activation Quantization
- **`eccb529e`** — Added 128-row × 64-col double-buffered threadgroup-staged INT8 prefill kernels for `Q3_K` (`-12.8%`) and `IQ4_XS` (`-11.1%`).
- **`3779ad89`** — Vectorized `gguf_prefill_int8_quantize` and `moe_expert_int8_gate_up`'s fused epilogue with 32 coalesced `bfloat2` loads, a single `simd_shuffle_xor(p16, 8)` register transpose, and 16 coalesced `uint` code stores per 64-element group (bit-for-bit identical):
  - `gguf_prefill_int8_quantize`: `117.46 -> 109.08 ms` (**`-8.38 ms`**, **`-7.1%`**).
  - `moe_expert_int8_q20_gate_up`: `444.37 -> 440.44 ms` (**`-3.93 ms`**).
  - Prefill separate dispatches: `3264.01 -> 3224.61 ms` (**`-39.4 ms`**).

### C. Expert Streaming, Repack (`moe_expert_load`) & Adaptive Read-Ahead
- **`90c2505c`**, **`86641cc0`**, **`27bc1240`**, **`fced76b0`**, **`ff8321c3`**, **`786e5956`** — Sized `ExpertStore` staging by lanes (`-225 MiB`), switched to 2-chunk prefill groups, raised `kLongChunkRoutes` to 6, treated all prefill expert loads (`> cycleRows`) as ARC scans to protect hot decode experts, and tightened decode read-ahead cutoffs.
- **`128565cd`** — Added adaptive per-layer decode read-ahead precision gating in `ExpertStore`.
- **`2637aea8`** — Tuned `ExpertStore` adaptive decode read-ahead (`kDecodeAheadReaders = 8`, `256 KiB` pieces, `<0.35` EWMA skip with 1-in-16 probe, row-scaled weight floor `min(0.028, 0.11 / rows)`, `massShare <= 0.78`) and prefill read-ahead (`14` readers, `512 KiB` pieces): lifted live decode read-ahead precision from `70.3%` to `75.2%` and cut max host `work_ms` from `42.6 -> 13.85 ms`.
- **`2a24f94a`** — Set prefill `roundPlaces` to `3/4` of staging (`192/256` places) to keep `64` places free for inter-round read-ahead overlap.
- **`07d7b227`** — Added a threadgroup-staged `Q2_0` fast path in `moe_expert_load` (`32` rows × up to `16` blocks in `9.1 KiB` TG memory = 3 TGs/core, `73`-uint stride for zero bank conflicts, coalesced `uint4` loads including flat contiguous `uint4` for single-span `down`):
  - `gguf-moe-benchmark repack` (`flash-next Q2_0`): **`-10.2%` to `-18.5%`** (`62.7–63.3 GB/s` native / ~84% of M5 DRAM peak, bytewise exact).
  - Prefill `moe_expert_load`: `338.05 -> 293.03 ms` (**`-45.0 ms`**, **`-13.3%`**).
  - Decode `moe_expert_load`: `9.14 -> 7.84 ms` (**`-1.30 ms`**, **`-14.3%`**).

### D. Sparse Attention (QSA), Block Indexer, GDN Scan & HyperConnection
- **`2954b477`** & **`0f0e300b`** — Optimized `block_indexer_score` with `16x64` tiles and device-memory queries (`-40%`).
- **`8edbc43c`** — Optimized sparse QSA attention with 2-part tiles, block skipping, and INT8 queries.
- **`ff8321c3`** — Halved QSA prefill score batch (`-7 MiB` scratch).
- **`6e18c7af`** — Optimized `prefill_gdn_scan_*` with 2-row-per-thread interleaving and coalesced `bfloat4` output staging.
- **`08a1a5a2`** — Vectorized `hyper_connection_norm_{loaded,quarters}` (`float2`/`bfloat2`, `#pragma clang fp reassociate(off)` for bit-for-bit parity; `qwen4-kernels PASS`) and `hyper_connection_mix` (64 threads/TG, `bfloat4`):
  - `hyper_connection_norm_loaded`: `116.54 -> 109.44 ms` (**`-7.10 ms`**, **`-6.1%`**).
  - `hyper_connection_mix`: `76.58 -> 75.28 ms` (**`-1.30 ms`**, **`-1.7%`**).
  - Prefill fused total: `4051.11 -> 4008.00 ms` (**`-43.1 ms`**).

### E. Memory Arena Aliasing & Headroom (Expanded Resident Expert Budget)
- **`2954b477`**, **`9f265b5f`**, **`90c2505c`**, **`86641cc0`**, **`27bc1240`** — Freed **>600 MiB** of Metal scratch via phase aliasing in `TargetArena` (`-316 MiB`), `ExpertStore` lane-based staging (`-225 MiB`), `PrefillArena` `Context*` aliasing (`-28` to `-48 MiB`), `GdnOutput`/`AttentionOutput` aliasing, and INT8 MoE scratch aliasing with `groupedInput`.
- **`af4acc29`** / **`5fdfb4a6`** — Tested aliasing `expertOutput` with `groupedInput` (`-94.6 MiB`), then reverted cleanly in `5fdfb4a6` because streamed `MOE_TILES_RESIDENT` and `MOE_TILES_LOADED` overlap their lifetimes.

---

## 3. Chronological Commit Log (All 25 Commits)

| # | Hash | Time (EST) | Summary |
|---:|---|---|---|
| 1 | `2954b477` | 10:21 | Optimize Option 21 memory headroom, QSA indexer scoring, and `Q2_0` INT8 prefill |
| 2 | `9ac9caa0` | 10:32 | Document Option 21 +8 GiB and +16 GiB RAM scaling estimates |
| 3 | `9f265b5f` | 10:52 | Enable streamed `Q2_0` INT8 MoE passes and alias INT8 MoE scratch in `TargetArena` |
| 4 | `06b5276a` | 10:54 | Add Option 21 optimization session summary (2026-11-27) |
| 5 | `68cdcb62` | 11:19 | Lower `Q2_0` MoE int8 prefill activation threshold to 2 routes/expert |
| 6 | `90c2505c` | 11:36 | Alias `TargetArena` phases (`-316 MiB`), size `ExpertStore` staging by lanes (`-225 MiB`), trim decode read-ahead tail |
| 7 | `86641cc0` | 11:55 | Use 2-chunk prefill groups, alias `GdnOutput`/`AttentionOutput`, tune `ExpertStore` staging/read-ahead |
| 8 | `27bc1240` | 12:08 | Alias `PrefillArena` `Context*` with `TargetArena` phase scratch (`-28` to `-48 MiB`), raise `kLongChunkRoutes` to 6 |
| 9 | `fced76b0` | 12:20 | Treat all prefill expert loads (`> cycleRows`) as ARC scans in `ExpertStore` |
| 10 | `af4acc29` | 12:36 | Alias MoE `expertOutput` with `groupedInput` in `TargetArena` (`-94.6 MiB`) |
| 11 | `eccb529e` | 13:02 | Add 128-row threadgroup-staged INT8 prefill kernels for `Q3_K` (`-12.8%`) and `IQ4_XS` (`-11.1%`) |
| 12 | `5fdfb4a6` | 13:07 | Revert `expertOutput`/`groupedInput` aliasing (streamed resident/loaded overlap) |
| 13 | `8edbc43c` | 14:40 | Optimize sparse QSA attention with 2-part tiles, block skipping, and INT8 queries |
| 14 | `0f0e300b` | 15:04 | Optimize `block_indexer_score` with 16x64 tile and device-memory queries (`-40%`) |
| 15 | `ff8321c3` | 15:13 | Halve QSA prefill score batch (`-7 MiB`) and tighten decode read-ahead cutoff to 0.78 |
| 16 | `6e18c7af` | 15:59 | Optimize GDN prefill scan with 2-row-per-thread interleaving and coalesced output staging |
| 17 | `786e5956` | 16:50 | Optimize INT8 MoE prefill for `<=16`-row tiles (`-7.6%` to `-28.8%`) and tighten `ExpertStore` read-ahead |
| 18 | `4b6e7802` | 17:15 | Fuse INT8 MoE prefill gate and up passes into one dispatch (`moe_expert_int8_*_gate_up`) |
| 19 | `128565cd` | 17:29 | Add adaptive per-layer decode read-ahead precision gating in `ExpertStore` |
| 20 | `2637aea8` | 21:25 | Optimize MoE prefill glue/router/int8 kernels and `ExpertStore` read-ahead/staging |
| 21 | `2a24f94a` | 22:08 | Fuse INT8 quantization into `moe_expert_int8_gate_up` and use 3/4-staging prefill rounds |
| 22 | `07d7b227` | 22:18 | Stage `Q2_0` `moe_expert_load` through threadgroup memory with coalesced `uint4` loads |
| 23 | `dd370025` | 22:45 | Run resident `Q2_0` experts on INT8 prefill path with indirect grids |
| 24 | `08a1a5a2` | 23:07 | Vectorize `hyper_connection_norm` (`float2`/`bfloat2`) and `hyper_connection_mix` (`bfloat4`) |
| 25 | `3779ad89` | 23:26 | Vectorize INT8 activation quantization with `bfloat2` loads and coalesced `uint` code stores |

---

## 4. Evaluated & Reverted Experiments (Do Not Repeat)

| Experiment | Outcome | Reason |
|---|---|---|
| `Q4_K` INT8 prefill (`gguf_prefill_int8_q4k_a`) | `13.57–21.11 ms` vs `9.78 ms` BF16 `prefill128` | Per-32-group `-dmin * mn` offset requires extra `sum_qa` reduction + 2nd FMA per element, hitting register/occupancy cliff |
| Padded stage stride (`KS + 4`) in `gguf_staged_tile.h` | `-1.5%` on dense `m16`, hung `moe_gguf` `m64` | Broke `moe_gguf.metal` `kStagedSimdgroupStage` `park` aliasing |
| 16-row/TG grid flip in `gguf_prefill_int8_quantize` | `+71.8 ms` (`117.5 -> 189.3 ms`) | Destroyed row-sequential DRAM locality on `input` and `codes` |
| 64-thread `float4` `hyper_connection_combine` | `+1.77 ms` (`131.6 -> 133.3 ms`) | Already at ~85% DRAM peak at 256 threads/TG |
| `MOE_COLUMN_ROWS = 4u` | `+20%` to `+27%` decode regression | Register pressure in `column_dot` |
| `uint4` activation loads on `>16`-row `prefill_int8_accum<2>` | `+5%` at 2048 rows | 16 live registers alongside `cf[2][16]` |
| `half4` `select` `Q2_0` dequant in `gguf_staged.h` | `+11%` to `+22%` slower | Slower than magic-mantissa `| 0x64006400u` on M5 |
| Unfused `gate`+`up` hybrid cutoff at 2048 rows | `19.85 ms` vs `19.27 ms` fused | Fused `moe_expert_int8_q20_gate_up` wins at every row count (`64–2048`) |
| Full-staging (`roundPlaces = places.count`) prefill | Dropped prefill read-ahead coverage `59% -> 40–46%` | Left 0 free places for inter-round overlap; replaced with `3/4` staging (`2a24f94a`) |

---

## 5. Detailed Performance Test Results (`3779ad89`)

### A. Commit-by-Commit Quiet-GPU Progression (Qwen3.8-Flash-Next Q2_0, `2048`-Token Prefill)

| Commit | Change | Prefill Fused (ms) | Fused PP (tok/s) | Prefill GPU-Only (ms) | GPU-Only PP (tok/s) | Key Kernel Delta |
|---|---|---:|---:|---:|---:|---|
| `2a24f94a` | Fused `moe_expert_int8_gate_up` + `3/4` staging | `4126.70` | `496.3` | `3385.03` | `605.0` | Baseline for quiet-GPU `decode-profile` series |
| `07d7b227` | `Q2_0` TG-staged `uint4` `moe_expert_load` | `4070.66` | `503.1` | `3331.12` | `614.8` | `moe_expert_load`: `338.05 -> 293.03 ms` (`-13.3%`), decode `9.14 -> 7.84 ms` (`-14.3%`) |
| `dd370025` | Resident `Q2_0` INT8 MoE + indirect grids | `4051.11` | `505.5` | `3265.07` | `627.2` | MoE compute + gather: `884.12 -> 802.17 ms` (`-81.95 ms`, `-9.3%`) |
| `08a1a5a2` | Vectorized `hyper_connection_{norm,mix}` | **`4008.00`** | **`511.0`** | `3264.01` | `627.4` | `norm_loaded`: `116.54 -> 109.44 ms` (`-6.1%`), `mix`: `76.58 -> 75.28 ms` (`-1.7%`) |
| `3779ad89` | Vectorized `gguf_prefill_int8_quantize` + `moe_int8` epilogue | `4040.60` | `506.9` | **`3224.61`** | **`635.1`** | `int8_quantize`: `117.46 -> 109.08 ms` (`-7.1%`), `gate_up`: `444.37 -> 440.44 ms` |

### B. Full `decode-profile` Kernel Breakdown (`3779ad89`, Cool GPU)

Command:
```bash
./build/engine-tests/decode-profile build/splash.metallib \
  /Users/mymac/splash/splash/install/models/.selections/be19a0828c0f96ac1e4ea064e868e18642917d41b5063d625fb3899718685cab \
  --prompt-tokens 2048 --cycles 4 --widths 1 --kv-format int8 --state-format bf16 \
  --expert-memory 4384M --ple-memory 64M
```

#### Prefill (`2048` rows — `4040.60 ms` fused / `506.9 tok/s`, `3224.61 ms` separate / `635.1 tok/s`)
| Kernel | Calls | GPU ms | Share |
|---|---:|---:|---:|
| `moe_expert_int8_q20_gate_up` | 96 | 440.441 | 13.7% |
| `gguf_prefill_int8_q3k_a` | 46 | 315.883 | 9.8% |
| `moe_expert_load` | 144 | 291.621 | 9.0% |
| `prefill_gdn_scan_bf16_state` | 36 | 242.154 | 7.5% |
| `moe_expert_int8_q20_down` | 96 | 222.961 | 6.9% |
| `gguf_prefill_int8_iq4xs_a` | 36 | 201.823 | 6.3% |
| `gguf_prefill_int8_q80_a` | 194 | 200.715 | 6.2% |
| `gguf_prefill_q4k_a` | 26 | 144.829 | 4.5% |
| `hyper_connection_combine` | 96 | 131.868 | 4.1% |
| `gguf_prefill_int8_quantize` | 295 | 109.077 | 3.4% |
| `hyper_connection_norm_loaded` | 97 | 108.361 | 3.4% |
| `attention_q8q_sparse_kv2_g12` | 12 | 85.225 | 2.6% |
| `gguf_prefill_iq4xs_a` | 8 | 76.165 | 2.4% |
| `hyper_connection_mix` | 97 | 74.729 | 2.3% |
| `gguf_prefill_q3k_a` | 9 | 60.815 | 1.9% |
| `moe_combine` | 48 | 53.103 | 1.6% |
| `gguf_float_na_bf16_f32` | 60 | 52.523 | 1.6% |
| `moe_expert_gguf_m32_gate_up_mixed` | 34 | 47.029 | 1.5% |
| `gguf_prefill_q5k_a` | 11 | 43.810 | 1.4% |
| `gguf_prefill_q6k_a` | 10 | 37.517 | 1.2% |
| `moe_gather_int8` | 96 | 32.229 | 1.0% |
| `attention_sparse_reduce_kv2_g12` | 12 | 28.888 | 0.9% |

#### Decode (`B1` speculative verify — `31.05 tok/s` cool 4-cycle / `20.56 tok/s` warm 8-cycle, `71.78–71.91 ms` GPU compute/cycle)
| Kernel | Calls | GPU ms | Share |
|---|---:|---:|---:|
| `gguf_decode_fused_m16` | 48 | 10.712 | 14.9% |
| `moe_expert_gguf_m8_gate_up_mixed` | 68 | 10.404 | 14.5% |
| `moe_expert_load` | 48 | 7.896 | 11.0% |
| `moe_expert_gguf_m8_down` | 96 | 7.036 | 9.8% |
| `gguf_decode_q5k_m8_a_f32` *(lm_head)* | 3 | 5.662 | 7.9% |
| `moe_expert_gguf_m8_gate_up` | 28 | 3.994 | 5.6% |
| `gguf_decode_sg_q80_l1_a` | 97 | 3.547 | 4.9% |
| `gguf_decode_q80_m8_a` | 97 | 3.195 | 4.5% |
| `gguf_float_bf16_f32` | 107 | 2.653 | 3.7% |
| `gguf_decode_iq4xs_m8_a` | 17 | 1.844 | 2.6% |
| `verify_gdn_fused_p16512_f32_bf16_state` | 36 | 1.694 | 2.4% |
| `gguf_decode_q4k_m8_a` | 15 | 1.482 | 2.1% |

### C. Microbenchmark Results (`3779ad89`)

#### `gguf-moe-benchmark repack` (`flash-next q20/q20/q20`, `1.38 MB/expert`, 15 rounds, bytewise exact)
| Jobs | Baseline (`2a24f94a`) | Optimized (`3779ad89`) | Native Bandwidth | Speedup |
|---:|---:|---:|---:|---:|
| 1 | `0.0323 ms` (`42.7 GB/s`) | `0.0283–0.0328 ms` | `42.2–48.8 GB/s` | up to `-12.4%` |
| 2 | `0.0562 ms` (`49.2 GB/s`) | `0.0458–0.0556 ms` | `49.8–60.4 GB/s` | up to `-18.5%` |
| 4 | `0.0986 ms` (`56.1 GB/s`) | `0.0882 ms` | **`62.7 GB/s`** | **`-10.5%`** |
| 8 | `0.1945 ms` (`56.9 GB/s`) | `0.1749 ms` | **`63.2 GB/s`** | **`-10.1%`** |
| 32 | `0.8044 ms` (`55.0 GB/s`) | `0.7059 ms` | **`62.7 GB/s`** (~84% M5 DRAM peak) | **`-12.2%`** |

#### `gguf-projection-benchmark` (`10240 x 2560`, `2048`-row prefill)
| Format | BF16 `prefill128` | INT8 `prefill int8*` | INT8 `codes` only | Speedup |
|---|---:|---:|---:|---:|
| `q3k` | `10.45 ms` | **`9.28 ms`** | `9.09 ms` | **`-11.2%`** |
| `iq4xs` | `10.72 ms` | **`9.64 ms`** | `9.46 ms` | **`-10.0%`** |
| `q80` | `11.31 ms` | **`9.64 ms`** | `9.51 ms` | **`-14.8%`** |
| `q4k` | **`9.78 ms`** | *(reverted — BF16 faster)* | — | — |
