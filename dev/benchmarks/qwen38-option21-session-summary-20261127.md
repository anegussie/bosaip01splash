# Option 21 Optimization Session Summary (2026-11-27)

Consolidated record of the host, launcher, and engine optimizations completed for **Option 21** (`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` + local BF16 `DFlash2` draft via Splash) on **Apple M5 (8 GPU cores, 16 GiB unified memory, `10.8G` Metal cap, `2,048`-token prefill chunks)**.

Companion reports:
- Optimization plan & Section 5 notes: [qwen38-option21-pp-tps-improvements-20261127.md](qwen38-option21-pp-tps-improvements-20261127.md)
- Detailed before/after benchmarks: [qwen38-option21-before-after-results-20261127.md](qwen38-option21-before-after-results-20261127.md)
- +8 GiB / +16 GiB RAM scaling estimates: [qwen38-option21-ram-scaling-estimates-20261127.md](qwen38-option21-ram-scaling-estimates-20261127.md)

---

## 1. Host & Launcher Changes
- **Status log cleanup:** Truncated `~/.local/state/llama-server/splash-status.jsonl` (`8.92 GB -> 0 B`), increasing free space on `/` from `9.7 GiB` to **`18 GiB`** so the `10 GiB` disk reserve no longer clamps persistent prefix caching.
- **Launcher `ExpertStore` default:** Raised `SPLASH_FLASH_NEXT_Q2_EXPERT_MEMORY` from `3072M` (`1,988` slots) to **`3648M`** (`2,425` of `24,576` experts, `+437` slots / `+22.0%`) in both [`startllamacpp.sh`](../../startllamacpp.sh) and `/Users/mymac/startllamacpp.sh`, keeping `139,249` resident tokens (`131,072` served context).

---

## 2. Engine & Kernel Optimizations
- **Reclaimed `588 MiB` Metal headroom (commit `2954b477`):**
  - Aliased lifetime-disjoint `Ple` and `MixerQsa` prefill scratch in [`Qwen4Steps.cpp`](../../runtime/model/Qwen4Steps.cpp) (`-140.00 MiB` on Flash-Next).
  - Reduced `kPipelineReserveBytes` (`256 -> 128 MiB`) and `kRuntimeOverheadReserveBytes` (`512 -> 192 MiB`) in [`Model.hpp`](../../runtime/model/Model.hpp) (`-448 MiB`).
- **QSA indexer scoring (`block_indexer_score`, commit `2954b477`):**
  - Swept `BLOCK_INDEXER_SCORE_TILES = 8u` key tiles per threadgroup in [`BlockIndexer.h`](../../runtime/metal/abi/BlockIndexer.h), [`block_indexer.metal`](../../runtime/metal/kernels/shared/block_indexer.metal), and [`BlockIndexer.cpp`](../../runtime/ops/BlockIndexer.cpp) (`-9.4%` at `32K` and `131K` with exact `output_digest` match).
- **`Q2_0` INT8 prefill & MoE kernels (commits `2954b477`, `9f265b5f`):**
  - Implemented `BITS == 2` (`Q2_0`) in [`QuantFormat.h`](../../runtime/metal/abi/QuantFormat.h), [`gguf_prefill_int8_tile.h`](../../runtime/metal/kernels/common/gguf_prefill_int8_tile.h), [`gguf_prefill_int8.metal`](../../runtime/metal/kernels/prefill/gguf_prefill_int8.metal), and [`moe_int8.metal`](../../runtime/metal/kernels/shared/moe_int8.metal) (`-45.0%` dense `R2048` `10.31 -> 5.68 ms`; `-30.8%` MoE `R2048` `32.34 -> 22.37 ms/layer`).
  - Enabled `moe_expert_int8_q20` for streamed `Q2_0` routed expert tiles (`MOE_TILES_LOADED`, no shared slices) via `ops::moeInt8RoutedExperts` in [`KernelSelection.hpp`](../../runtime/ops/KernelSelection.hpp), [`KernelSelection.cpp`](../../runtime/ops/KernelSelection.cpp), [`QwenTarget.hpp`](../../runtime/model/QwenTarget.hpp), [`QwenTarget.cpp`](../../runtime/model/QwenTarget.cpp), [`RuntimeArenas.hpp`](../../runtime/model/RuntimeArenas.hpp), and [`MoE.cpp`](../../runtime/ops/MoE.cpp).
  - Aliased `{inputCodes, inputScales, groupedCodes, groupedScales}` (`67.5 MiB`) inside `groupedInput` (`110.2 MiB`) in `TargetArena` ([`RuntimeArenas.hpp`](../../runtime/model/RuntimeArenas.hpp)), keeping `shared_prefill_bytes` at `1,531,297,792` B (`0` extra arena bytes).
- **Intentionally skipped after verification:**
  - `kv_spill` floor (`1,552 MiB`): Live `/status` confirmed `hot_kv` shares `dynamic_budget` lazily (`hot_kv.current_bytes == 0` when not spilling), so it does not consume resident KV capacity when `3648M` is pinned.
  - `indexerTopBlocks` (`1024 -> 512`): Left unchanged because [`qwen38-option21-indexer-top-k-20261112.md`](qwen38-option21-indexer-top-k-20261112.md) notes `GgufImage.cpp` requires local GGUF header metadata (`4096`) to match `Qwen4Exp.hpp`.

---

## 3. Verified Live Option 21 Results (`10.8G`, `2,048`-Token Chunks, Thinking Off)

| Metric | Prior (`3072M` / `3648M` Staged MoE) | Final (`3648M` + Streamed `Q2_0` INT8 MoE + Aliased Scratch) |
| :--- | :--- | :--- |
| **Served / resident context** | `131,072` / `139,249` (`3648M`) | **`131,072` / `139,249`** (`0` B extra scratch) |
| **Resident expert slots** | `1,988` (`3072M`) | **`2,425 / 24,576`** (`+22.0%`) |
| **Cold `11.4K`-token prefill (`cached=0`)** | `28.34–30.75 s` (`369.5–400.9 tok/s`) | **`26.06–26.99 s`** (**`421.2–436.2 tok/s`**, **`+5%` to `+18%`**) |
| **Cached `11.4K`-token prefill** | `1.56–1.77 s` | **`0.300–0.352 s`** |
| **Decode throughput** | `17.58–17.82 tok/s` (`3072M`) | **`18.50–18.97 tok/s`** (`50.3%–51.8%` expert hit rate) |
| **Total probe round time** | `72.40–72.92 s` | **`67.25–67.33 s`** (**`-5.1 to -5.6 s`**) |
| **Live answer checks** | Passed | **`cold_final_code`, `cached_final_code`, `decode_returns_code` all `true`** |

- **Tests passed:** `model-execution-plans`, `execution-plans`, `kernel-selection --library build/splash.metallib dev/tests/engine/kernel_selection_golden.txt`, `engine-memory-plan`, `memory-audit`, `qwen4-kernels`, `gguf-moe-e512`, and all 13 `test_option21*` tests in [`test_bonsai_launcher.py`](test_bonsai_launcher.py).
