# Option 21 PP and TPS Optimization Guide (2026-11-27)

Applies to option 21 in `/Users/mymac/startllamacpp.sh` (`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` + local BF16 `DFlash2` draft via Splash) running on an **Apple M5 (8 GPU cores, 16 GiB unified memory)**.

## Current Baseline Configuration

In `/Users/mymac/startllamacpp.sh`, option 21 currently runs:

- **Metal cap & prefill chunk**: `SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G`, `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048` (falls back to `10G` / `1024` if bootstrap warmup hits the 5 s Metal event timeout)
- **Expert store**: `SPLASH_FLASH_NEXT_Q2_EXPERT_MEMORY=3072M` (overrides `auto`, yielding ~1,988 of 24,576 routed experts resident / ~52% hit rate at ~25.1 tok/s vs `auto`'s 17.0 tok/s in `docs/merge-1.7.3-ab-results.md`)
- **Context & caches**: `131072` server context, `16384` max output tokens, `int8` KV, `bf16` state, `64M` PLE row cache, `3G` persistent prefix cache (`--persistent-cache`), `1` active request
- **Reasoning**: `SPLASH_FLASH_NEXT_Q2_REASONING_EFFORT=medium`, `SPLASH_FLASH_NEXT_Q2_THINKING_TOKEN_BUDGET=1500` (`low` for worker subagents)

## Where Time Goes

- **Prompt processing (PP)** is **~99.9% GPU-compute bound**: ~5 s per 2,048-token chunk at 128K history (~1.73 s MoE, ~1.5 s GDN projections, ~1.34 s QSA attention). Attention per row is bounded by `indexerTopBlocks = 1024` (4,096 tokens), while the **QSA indexer** scans every block of history (growing from 3.7 ms/layer at 8K to 34.1 ms/layer at 131K, ~31% of attention time).
- **Decode (TPS)** is dominated by **routed expert SSD streaming** (~40% of a ~265 ms decode cycle, since only ~8% of experts stay resident in `3072M`) and **DFlash2 acceptance rate** (~3–4 tokens/cycle when thinking is active vs ~7 tokens/cycle with thinking off).

---

## 1. Immediate Launcher & Workflow Improvements (No Code Changes)

### Improve PP & TTFT

1. **Maximize prefix-cache reuse (40x–700x faster TTFT than cold prefill)**
   - In `dev/benchmarks/option21-postmerge-20261118.md`, reusing the prefix at 102,412 prompt tokens cut TTFT from **407.10 s** (251.58 tok/s cold PP) to **0.56 s**.
   - Keep system prompts and tool schemas stable within a session, read targeted line ranges instead of whole files, and compact long histories at task boundaries.
   - If your disk has free space beyond the 10 GiB volume reserve, increase the persistent cache quota above `3G` so older prefixes are not evicted across sessions:
     ```bash
     SPLASH_FLASH_NEXT_Q2_MAX_CACHE_DISK=8G /Users/mymac/startllamacpp.sh
     ```

2. **Bound `MAX_CONTEXT` when 128K is unnecessary**
   - Setting `SPLASH_FLASH_NEXT_Q2_MAX_CONTEXT=65536` does not speed up a cold 8K prompt directly, but it caps the QSA indexer's linear history scan on long sessions and reduces KV spill / macOS swap pressure.

### Improve Decode TPS

1. **Lower or disable reasoning for routine edits (~2x effective decode TPS)**
   - Thinking tokens average ~3–4 tokens per DFlash2 draft cycle (~10–13 tok/s in real sessions) compared to ~7 tokens/cycle with thinking disabled (**22–26.6 tok/s**).
   - Override reasoning effort for faster turns:
     ```bash
     SPLASH_FLASH_NEXT_Q2_REASONING_EFFORT=low /Users/mymac/startllamacpp.sh
     ```
   - Or send `reasoning_effort: "none"` per request for mechanical edits and verification steps.

2. **Use `1024`-token prefill chunks for cached-prefix, decode-heavy workloads (+13–24% cached TPS)**
   - Halving `--prefill-chunk-tokens` from `2048` to `1024` frees ~1 GiB of prefill workspace that can go to `ExpertStore`, boosting cached decode TPS by **12.8–23.6%** while slowing cold PP by **22.7–33.0%** (`dev/benchmarks/option21-chunk-context-20261113.md`).
   - Note: in `splash_flash_next_host_defaults` (`/Users/mymac/startllamacpp.sh`), overriding `SPLASH_FLASH_NEXT_EXPERT_MEMORY` explicitly from the environment disables the automatic `2048`-chunk override unless `SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G` and `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048` are also set.
   - Explicit cached-decode launch profile:
     ```bash
     SPLASH_FLASH_NEXT_MAX_MEMORY=10.8G \
     SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=1024 \
     SPLASH_FLASH_NEXT_EXPERT_MEMORY=3840M \
     /Users/mymac/startllamacpp.sh
     ```
   - With `2048`-token chunks and 128K resident context, `3136M` is the hard ceiling (`3072M` is already the default and ties `3136M` within noise in `docs/merge-1.7.3-ab-results.md`).

3. **Keep host RAM free & thermals cool**
   - Identical runs range **252–412+ tok/s PP** depending on thermal state (`fair` vs `nominal`) and host memory pressure (`dev/benchmarks/qwen38-option21-pp-ceiling-20261111.md`). Closing memory-heavy apps keeps `host_spare_bytes` above ~2 GiB and avoids macOS swap during 64K–100K prefills.

---

## 2. Knobs Already Tested That Do Not Help

- **Raising `--max-memory` above `10.8G`**: Clamped by `EngineMemoryPolicy::hardBudgetBytes` (~11.6 GiB) or rejected by the launcher's 2 GiB macOS reserve check.
- **Raising `--prefill-chunk-tokens` above `2048`**: Hard-capped at `SPLASH_PREFILL_TOKEN_BUDGET = 2048` (`runtime/metal/abi/ExecutionGeometry.h`); expert deduplication is already saturated at 2,048 rows (all 512 experts touched per layer), and larger single host steps trip the 5 s Metal GPU timeout.
- **Reducing decode expert read-ahead budget**: Paired A/B tests in `build/decode-read-ahead/run-1795474492367191000/results.json` (100% vs 50%) measured ~24.0–24.4 vs ~24.0 tok/s (no gain).
- **Disabling DFlash2 draft**: Unsupported for option 21, and DFlash2 provides a ~95% acceptance rate that drives decode throughput.

---

## 3. Engine / Code-Level Opportunities

1. **Reclaim more memory for `ExpertStore` without dropping `2048` chunks (TPS)**
   - Commit `5039edf5` (`runtime/model/RuntimeArenas.cpp`) saved ~287 MiB by aliasing prefill scratch across GDN, attention, and MoE.
   - Shrinking remaining fixed reservations (`lane_state_bytes` ~163 MiB, `pipeline_reserve_bytes` ~268 MiB, `runtime_overhead_reserve_bytes` ~537 MiB, or the `1,170 MiB` hot KV block cache floor) would raise resident expert slots above 1,988/24,576 while keeping 2,048-token PP speed.

2. **Bound or optimize the QSA indexer scan (Long-context PP)**
   - Bounding the indexer window or optimizing its score/select kernels directly targets the 34.1 ms/layer cost at 128K history (`dev/benchmarks/qwen38-option21-kernels-20261111.md`).

3. **Faster 2-bit / `Q2_0` MoE & projection kernels (PP & TPS)**
   - Splash's `gguf_prefill_int8_*` / `moe_expert_int8_*` paths currently support `AF4G64`, `AF5G64`, and (`prefill` only) `Q8_0`, while `gguf_decode_int8_*` supports rotated `PQ2_0` (`runtime/metal/abi/QuantFormat.h`).
   - Note that the experimental prepacked INT2 `Q2_0` path in `build/int2-prepacked/benchmark-int2.log` was ~5x slower at the kernel level (48.1–53.3 ms vs 9.5 ms for staged BF16 `prefill128`) and regressed end-to-end PP (346–382 vs 412 tok/s). Any replacement kernel must beat the `prefill128` BF16 path or use a `PQ2_0`-compatible rotated 128-element layout.

---

## 5. Implemented & Measured (2026-11-27)

1. **Reclaimed `588 MiB` for `ExpertStore` without shrinking 2,048-token prefill chunks:**
   - Aliased lifetime-disjoint `Ple` and `MixerQsa` prefill scratch in [`runtime/model/Qwen4Steps.cpp`](../../runtime/model/Qwen4Steps.cpp) (`-146,800,640` bytes / `140.00 MiB` on `Qwen3.8-Flash-Next` verified by `model-execution-plans`).
   - Reduced `kPipelineReserveBytes` (`256 -> 128 MiB`) and `kRuntimeOverheadReserveBytes` (`512 -> 192 MiB`) in [`runtime/model/Model.hpp`](../../runtime/model/Model.hpp) (`-448 MiB`, verified by `memory-audit` and `engine-memory-plan`).
   - Raised the Option 21 `ExpertStore` default `SPLASH_FLASH_NEXT_Q2_EXPERT_MEMORY` in [`startllamacpp.sh`](../../startllamacpp.sh) from `3072M` (`1,988` slots) to `3648M` (`2,425` of `24,576` experts, `+437` slots / `+22.0%`), keeping `139,249` tokens resident (`131,072`-token served context intact; `3712M` trims resident context to `131,057` tokens).
   - Live Option 21 comparison (`10.8G`, `2,048`-token chunks, local BF16 DFlash2):
     - `3072M` (`1,988` slots): decode `17.58–17.82 tok/s`, expert hit rate `0.445–0.456`, `190.4–191.7` expert reads/tok.
     - `3648M` (`2,425` slots): decode `18.88–20.43 tok/s` (`+7.4%` to `+14.7%`), expert hit rate `0.494–0.522`, `159.7–174.9` expert reads/tok.

2. **QSA Indexer Scoring (`block_indexer_score`):**
   - Swept `BLOCK_INDEXER_SCORE_TILES = 8u` consecutive `kScoreBlocks` key tiles per threadgroup in [`runtime/metal/kernels/shared/block_indexer.metal`](../../runtime/metal/kernels/shared/block_indexer.metal), [`runtime/metal/abi/BlockIndexer.h`](../../runtime/metal/abi/BlockIndexer.h), and [`runtime/ops/BlockIndexer.cpp`](../../runtime/ops/BlockIndexer.cpp).
   - `attention-sweep --shapes fn --histories 32768,131072 --phases prefill --repeat 3 --qsa indexer` on Apple M5:
     - `32768`: `block_indexer_score` `5.101 -> 4.623 ms` (`-9.4%`), `fused_ms` `108.066 -> 107.318 ms`, exact digest `4d86f18d5628c516`.
     - `131072`: `block_indexer_score` `19.847 -> 17.973 ms` (`-9.4%`), `fused_ms` `151.668 -> 149.167 ms`, exact digest `de71c4fbe4a139e0`.

3. **`Q2_0` Apple10 Hardware `matmul2d` INT8 Prefill & MoE Kernels:**
   - Added `GGUF_FMT_Q20` support to `quant_prefill_int8_format` / `quant_moe_int8_format` ([`QuantFormat.h`](../../runtime/metal/abi/QuantFormat.h)), `prefill_int8_tile<2, Ep>` ([`gguf_prefill_int8_tile.h`](../../runtime/metal/kernels/common/gguf_prefill_int8_tile.h)), `gguf_prefill_int8_q20_{a,r,g}` ([`gguf_prefill_int8.metal`](../../runtime/metal/kernels/prefill/gguf_prefill_int8.metal)), and `moe_expert_int8_q20_{gate,up,down}{,_s2}` ([`moe_int8.metal`](../../runtime/metal/kernels/shared/moe_int8.metal)).
   - Microbenchmarks on Apple M5 (8 cores, GPU family 10):
     - Dense `q20` `10240x2560`, `R2048`: `prefill128` `10.3135 ms` vs `prefill int8*` `5.6776 ms` (**`45.0%` faster**; `int8 codes` `5.6230 ms`).
     - MoE `flash-next` (`2560x640`, 512 experts, top 10, `q20/q20/q20`, `R2048`): `staged` `32.3370 ms` vs `int8` `22.3660 ms` (**`30.8%` faster**).
   - Accuracy & selection verified across `gguf-moe-e512`, `gguf-projection` (`int8 prefill` & `int8 prefill edges`), and `kernel-selection` (updated [`dev/tests/engine/kernel_selection_golden.txt`](../../dev/tests/engine/kernel_selection_golden.txt)). *(Note: Option 21's streamed MoE path with mixed `shexp` formats still routes through staged MoE in [`RuntimeArenas.hpp`](../../runtime/model/RuntimeArenas.hpp) / [`KernelSelection.cpp`](../../runtime/ops/KernelSelection.cpp) per `checkMoeInt8Passes`; resident `Q2_0` dense tensors in Option 21 now use `gguf_prefill_int8_q20_*` automatically.)*
