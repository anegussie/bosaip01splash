# Option 21 Before & After Benchmark Comparison (2026-11-27)

Applies to **Option 21** (`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` + local BF16 `DFlash2` draft via Splash) running on **Apple M5 (8 GPU cores, 16 GiB unified memory, `10.8G` Metal cap, `2,048`-token prefill chunks)**.

References:
- Plan & baseline notes: [qwen38-option21-pp-tps-improvements-20261127.md](qwen38-option21-pp-tps-improvements-20261127.md)
- Launcher profile: [`startllamacpp.sh`](../../startllamacpp.sh)
- Probes: [`option21_arms.py`](option21_arms.py)

---

## 1. Memory Headroom & `ExpertStore` Capacity (`Qwen3.8-Flash-Next`)

| Metric | Before | After | Change | Source / Verification |
| :--- | :--- | :--- | :--- | :--- |
| Flash-Next prefill scratch (`Apple9`) | `1,128,873,984` B (`1,076.58 MiB`) | `982,073,344` B (`936.58 MiB`) | **`-140.00 MiB`** (`-146,800,640` B) | [`Qwen4Steps.cpp`](../../runtime/model/Qwen4Steps.cpp), `model-execution-plans` |
| Flash-Next prefill scratch (`Apple10`/`11`) | `1,123,041,280` B (`1,071.02 MiB`) | `976,240,640` B (`931.02 MiB`) | **`-140.00 MiB`** (`-146,800,640` B) | [`Qwen4Steps.cpp`](../../runtime/model/Qwen4Steps.cpp), `model-execution-plans` |
| Pipeline reserve (`kPipelineReserveBytes`) | `256 MiB` | `128 MiB` | **`-128 MiB`** | [`Model.hpp`](../../runtime/model/Model.hpp), `memory-audit` |
| Runtime overhead reserve (`kRuntimeOverheadReserveBytes`) | `512 MiB` | `192 MiB` | **`-320 MiB`** | [`Model.hpp`](../../runtime/model/Model.hpp), `memory-audit` |
| **Total reclaimed Metal headroom** | — | — | **`+588 MiB`** | — |
| Option 21 default `--expert-memory` (`SPLASH_FLASH_NEXT_Q2_EXPERT_MEMORY`) | `3072M` (`1,988 / 24,576` slots, `~8%`) | `3648M` (`2,425 / 24,576` slots, `~9.9%`) | **`+437` slots (`+22.0%`)** | [`startllamacpp.sh`](../../startllamacpp.sh), `/status` |
| Resident KV context @ `3072M` (`10.8G`, `2048` chunk) | `~131,072` (`3,136M` hard ceiling before) | `180,209` resident tokens | **`+49,137` tokens** | Live startup log & `/status` |
| Resident KV context @ `3648M` (`10.8G`, `2048` chunk) | `> 3,200M` dropped below `122,865` | `139,249` resident tokens (`131,072` served) | Keeps full **128K** resident (`3712M` trims to `131,057`) | Live startup log & `/status` |

---

## 2. Kernel Microbenchmarks (Apple M5, GPU Family 10, 8 Cores)

| Benchmark / Kernel | Before | After | Speedup / Notes | Implementation |
| :--- | :--- | :--- | :--- | :--- |
| **Dense `Q2_0` prefill** (`gguf-projection-benchmark`, `10240x2560`, `none`, `R2048`, median of 5 rounds) | `prefill128`: **`10.3135 ms`** | `prefill int8*`: **`5.6776 ms`** (`int8 codes`: `5.6230 ms`) | **`45.0%` faster** (`1.82x`) | [`gguf_prefill_int8_tile.h`](../../runtime/metal/kernels/common/gguf_prefill_int8_tile.h), [`gguf_prefill_int8.metal`](../../runtime/metal/kernels/prefill/gguf_prefill_int8.metal) |
| **MoE `Q2_0` prefill** (`gguf-moe-benchmark`, `flash-next` `2560x640`, 512 experts, top 10, `q20/q20/q20`, `R2048`, median of 5 rounds) | `staged`: **`32.3370 ms/layer`** | `int8`: **`22.3660 ms/layer`** | **`30.8%` faster** (`1.45x`) | [`moe_int8.metal`](../../runtime/metal/kernels/shared/moe_int8.metal), [`QuantFormat.h`](../../runtime/metal/abi/QuantFormat.h) |
| **QSA indexer scoring** (`attention-sweep`, `--shapes fn`, `32768` history, `R2048`, median of 3 graphs) | `block_indexer_score`: **`5.101125 ms`** (`fused_ms`: `108.065875 ms`) | `block_indexer_score`: **`4.623250 ms`** (`fused_ms`: `107.317833 ms`) | **`-9.4%`** on score pass (exact digest `4d86f18d5628c516`) | [`block_indexer.metal`](../../runtime/metal/kernels/shared/block_indexer.metal), [`BlockIndexer.h`](../../runtime/metal/abi/BlockIndexer.h), [`BlockIndexer.cpp`](../../runtime/ops/BlockIndexer.cpp) |
| **QSA indexer scoring** (`attention-sweep`, `--shapes fn`, `131072` history, `R2048`, median of 3 graphs) | `block_indexer_score`: **`19.846917 ms`** (`fused_ms`: `151.667833 ms`) | `block_indexer_score`: **`17.972875 ms`** (`fused_ms`: `149.166833 ms`) | **`-9.4%`** on score pass (exact digest `de71c4fbe4a139e0`) | Same (`BLOCK_INDEXER_SCORE_TILES = 8u`) |

*(Note: Option 21's live model uses mixed `shexp` formats across layers and streams routed experts, so dense `Q2_0` non-expert tensors run `gguf_prefill_int8_q20_*` while streamed MoE remains on the staged path per [`RuntimeArenas.hpp`](../../runtime/model/RuntimeArenas.hpp) / [`KernelSelection.cpp`](../../runtime/ops/KernelSelection.cpp) and `checkMoeInt8Passes`.)*

---

## 3. Live Option 21 End-to-End Comparison (`3072M` vs `3648M` on Rebuilt `build/splash`)

Measured on port `11235` with `SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G`, `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048`, `SPLASH_BONSAI_PERSISTENT_CACHE=0`, and local BF16 DFlash2 using the [`option21_arms.py`](option21_arms.py) workload (`records=500`, `decode_512`, `cached_8k`, thinking disabled):
- **Run 1 (`task-448`)**: measured decode and cached probes cleanly; `3648M` `cold_8k` hit prefix cache (`1.759 s`).
- **Run 2 (`task-478`)**: salted `cold_8k` (`cached_tokens = 0`, `11,363` input tokens) followed by `decode_512` and `cached_8k` (`cached_tokens = 11,328`).

| Metric | `3072M` (`1,988` slots) | `3648M` (`2,425` slots) | Change (`3648M` vs `3072M`) |
| :--- | :--- | :--- | :--- |
| **Served max context** | `131,072` | `131,072` | Preserved (`128K`) |
| **Decode throughput (Run 1 / Run 2)** | `17.82` / `17.58 tok/s` | **`20.43`** / **`18.88 tok/s`** | **`+14.7%`** / **`+7.4%`** |
| **Decode ms/token (Run 1 / Run 2)** | `56.12` / `56.88 ms/tok` | **`48.95`** / **`52.95 ms/tok`** | **`-12.8%`** / **`-6.9%`** |
| **Tokens per draft cycle (Run 1 / Run 2)** | `4.51` / `4.22` | **`4.54`** / **`4.43`** | `+0.7%` / `+5.0%` |
| **Draft acceptance rate (Run 1 / Run 2)** | `0.893` / `0.895` | **`0.928`** / **`0.896`** | `+3.5 pp` / `+0.1 pp` |
| **Expert cache hit rate (Run 1 / Run 2)** | `0.445` / `0.456` | **`0.522`** / **`0.494`** | **`+7.7 pp`** / **`+3.8 pp`** |
| **Expert reads / output token (Run 1 / Run 2)** | `191.7` / `190.4` | **`159.7`** / **`174.9`** | **`-16.7%`** / **`-8.1%`** |
| **Expert host-step work / token (Run 1 / Run 2)** | `34.43` / `33.87 ms` | **`28.84`** / **`32.05 ms`** | **`-16.2%`** / **`-5.4%`** |
| **Cached `11,328`-token prefill (Run 1 / Run 2)** | `1.772 s` / `1.646 s` | **`1.712 s`** / **`1.557 s`** | **`-3.4%`** / **`-5.4%`** |
| **Cold `11,363`-token prefill (Run 2, single-shot)** | `28.344 s` (`400.9 tok/s`) | `30.751 s` (`369.5 tok/s`) | Single-shot variance (total round time: `72.40 s` vs `72.92 s`) |

---

## 4. Follow-Up: Streamed `Q2_0` INT8 MoE (`MOE_TILES_LOADED`) + Aliased Scratch

Enabled `moe_expert_int8_q20` for streamed `Q2_0` routed expert tiles (`MOE_TILES_LOADED`, without requiring mixed-format `shexp` slices to match) via `ops::moeInt8RoutedExperts` ([`KernelSelection.cpp`](../../runtime/ops/KernelSelection.cpp), [`MoE.cpp`](../../runtime/ops/MoE.cpp), [`QwenTarget.hpp`](../../runtime/model/QwenTarget.hpp), [`RuntimeArenas.hpp`](../../runtime/model/RuntimeArenas.hpp)) and aliased `{inputCodes, inputScales, groupedCodes, groupedScales}` (`67.5 MiB`) inside `groupedInput` (`110.2 MiB`) in `TargetArena` (`0` extra prefill arena bytes).

| Metric (`3648M`, `10.8G`, `2048` chunk) | Before Streamed INT8 MoE (`task-478`) | After Streamed INT8 MoE (`task-604` / `task-621` aliased) | Change |
| :--- | :--- | :--- | :--- |
| **Served / resident context** | `131,072` / `139,249` | **`131,072` / `139,249`** (aliased; `131,057` unaliased) | `0` bytes extra scratch (`1,531,297,792` B) |
| **Cold `11.4K`-token prefill (`cached=0`)** | `30.751 s` (`369.5 tok/s`; `3072M`: `28.344 s` / `400.9 tok/s`) | **`26.057–26.992 s`** (**`421.2–436.2 tok/s`**) | **`+5.1%` to `+18.1%` faster cold PP** |
| **Cached `11.4K`-token prefill** | `1.557 s` | **`0.300–0.352 s`** | **`4.4x–5.2x` faster** |
| **Decode throughput** | `18.88 tok/s` (`52.95 ms/tok`) | **`18.50–18.97 tok/s`** (`52.71–54.06 ms/tok`) | Preserved (`50.3%–51.8%` expert hit rate) |
| **Total probe round time** | `72.40 s` (`3072M`: `72.92 s`) | **`67.25–67.33 s`** | **`-5.1 to -5.6 s` (`-7.0%` to `-7.7%`)** |
| **Live answer checks** | All `true` | All `true` (`cold_final_code`, `cached_final_code`, `decode_returns_code`) | Verified |
