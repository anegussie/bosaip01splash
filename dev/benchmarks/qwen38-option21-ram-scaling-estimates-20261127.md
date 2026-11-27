# Option 21 RAM Scaling Estimates: +8 GiB (24 GiB) and +16 GiB (32 GiB) (2026-11-27)

Scaling analysis for **Option 21** (`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` + local BF16 `DFlash2` draft via Splash) assuming the **same Apple M5 8-core GPU and SSD**, anchored to our live 16 GiB M5 `/status` measurements in [qwen38-option21-before-after-results-20261127.md](qwen38-option21-before-after-results-20261127.md) and the M6 24 GiB profile in [`engine_memory_plan_test.cpp`](../tests/engine/engine_memory_plan_test.cpp).

---

## 1. Observed Baseline Anchor (16 GiB M5, 8 GPU Cores, `3648M` ExpertStore)

Measured live on commit `2954b477` (`10.8G` Metal cap, `2,048`-token prefill chunks, `131,072` served context, thinking disabled):

| Quantity | Measured Value | Notes |
| :--- | :--- | :--- |
| Metal hard budget | `10.80 GiB` (`11,596,411,699` B) | Current `10.8G` preset |
| `ExpertStore` resident experts | `2,425 / 24,576` (`9.9%`) in `3,648 MiB` | `~1.32 MiB` / slot (`3,261 MiB` arena / `2,474` slots; plus `450 MiB` staging) |
| Decode latency breakdown | `49.0–53.0 ms/tok` (`18.9–20.4 tok/s`) | `28.8–32.1 ms/tok` SSD expert work (~59–60%) + `~20–21 ms/tok` non-SSD GPU floor (~48–50 tok/s) |
| Decode expert cache hit rate | `49.4%–52.2%` | `159.7–174.9` expert SSD reads / output token |
| Prior hit-rate / TPS points (same M5) | `1,445` slots (`5.9%`): `~34%` -> `~17.2 tok/s`<br>`1,988` slots (`8.1%`): `44.5%–45.6%` -> `17.6–17.8 tok/s` | Direct scaling reference on this machine |
| Cold prefill (`11,363` tokens) | `369.5–400.9 tok/s` (`~400–450` warm ceiling) | ~99.9% GPU-compute bound on 8 GPU cores ([guide](qwen38-option21-pp-tps-improvements-20261127.md)) |

---

## 2. Estimated Scaling Summary (+8 GiB vs +16 GiB, Same 8-Core M5 GPU)

All 24 GiB and 32 GiB throughput figures below are **inferred estimates** derived from the measured `~1.32 MiB/slot` expert footprint, heavy-tailed router hit-rate scaling, and the measured `~20–21 ms/tok` non-SSD GPU compute floor.

| Config | Engine Metal Budget | `ExpertStore` Size & Slots | *Est.* Decode Hit Rate | *Est.* SSD Wait / Tok | *Est.* Decode TPS (Thinking Off) | *Est.* Decode TPS (Thinking On) | *Est.* Cold PP |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **16 GiB (Measured)** | `10.8 GiB` | `3.56 GiB` (`2,425`, `9.9%`) | `49.4%–52.2%` | `28.8–32.1 ms` | **`18.9–20.4 tok/s`** | `~10–13 tok/s` | `370–412 tok/s` |
| **24 GiB (+8 GiB)** | `~16.8 GiB` (`+6.0 GiB`) | `~9.6 GiB` (`~7,000`, `~28–29%`) | `~70%–82%` | `~11–17 ms` | **`~26–32 tok/s`** (**+35% to +55%**) | `~14–18 tok/s` | **`~400–450 tok/s`** (**~0% to +10%**) |
| **32 GiB (+16 GiB)** | `~24–25 GiB` (`+13–14 GiB`) | `~16.5–17.0 GiB` (`~12,200–12,600`, `~50%`) | `~84%–92%` | `~4–9 ms` | **`~33–41 tok/s`** (**+70% to +105%**) | `~17–22 tok/s` | **`~420–470 tok/s`** (**~+5% to +15%**) |

---

## 3. Key Takeaways

1. **+8 GiB (24 GiB total) — Decode jumps +35–55%, PP stays mostly flat:**
   - Using the 24 GiB `kM6` Metal working-set limit (`19,069,665,280` B minus `1 GiB` margin = `~16.8 GiB` budget in [`engine_memory_plan_test.cpp`](../tests/engine/engine_memory_plan_test.cpp)), `ExpertStore` nearly triples to `~7,000` experts (`~29%`).
   - Decode improves strongly because SSD streaming drops from ~60% of step time to roughly half as much, while cold PP remains compute-bound on the 8 M5 GPU cores (though 64K–128K prefills avoid macOS swap/pressure slowdowns).

2. **+16 GiB (32 GiB total) — Decode approaches ~2x (~33–41 tok/s), still ~50% streamed:**
   - Holds roughly **half** of all `24,576` routed experts (`~12,300` slots) plus `128K` resident KV and the full `~237 MiB` `PLE` row-cache share (`248,840,192` B).
   - Decode pushes close to the 8-core M5 GPU's `~48–50 tok/s` non-SSD ceiling, while full 100% expert residency for Q2_0 (~`34 GB` of experts) still requires **48–64 GiB** unified memory.

3. **What unlocks faster PP:**
   - Extra RAM alone yields only **~0%–15%** cold PP improvement on an 8-core M5 because `2,048`-token prefill already saturates GPU compute rather than SSD I/O. Substantially faster PP requires **more GPU cores and memory bandwidth** (e.g., M5 Pro / M5 Max).
