# Conservative option-20 planning estimates - November 5, 2026

Source: the conservative section of `/Users/mymac/MacPerfEstimates.md`, SHA-256 `0d5bfa598f41626757a170a2a4a161072c67fd3be3d7d4d82457cb40aa78485e`.

This report supersedes the earlier planning scenarios retained in the [complete estimate history](qwen38-option20-mac-estimates-20261105.md). It uses more conservative expert-store targets and throughput assumptions. Only the 16 GB Air IQ3_XXS row is measured, and those saved measurements used the 1.946 GiB expert store at a 10G cap. Every other figure is a low-confidence estimate, not a validated safe allocation, a guaranteed rate or a benchmark result.

PP is cold prefill around 30K prompt tokens; TPS is short-code generation, in tokens per second. Expert RAM is in GiB. Assumptions: one active request, 2,048-token prefill chunks, matching DFlash2, INT8 KV, BF16 recurrent state, the whole n-gram table SSD-backed with an approximately 64 MiB RAM row cache, and a separate 16 GiB persistent SSD prefix cache. Neither n-gram file size nor prefix-cache disk quota is included in expert RAM.

| Mac | IQ3_XXS expert RAM (GiB) | IQ3_XXS PP | IQ3_XXS TPS | Q2_0 expert RAM (GiB) | Q2_0 PP | Q2_0 TPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| M5 Air 16 GB, 8-core GPU | 1.946, measured | 241, measured | 8.81-8.92, measured block means | 2-3 | 240-300 | 10-12 |
| M5 Air 32 GB | 12 | 250-270 | 9-12 | 14 | 250-350 | 11-17 |
| M6 mini 32 GB | 12 | 250-270 | 9-12 | 14 | 250-350 | 11-17 |
| M5 Pro mini 48 GB, 16-core GPU | 24 | 330-430 | 13-20 | 24 | 330-540 | 16-28 |
| M5 Pro mini 64 GB, 16-core GPU | 32 | 340-450 | 15-23 | 28 | 360-580 | 20-34 |
| M5 Max Studio 128 GB, 40-core GPU | 41.55, resident | 900-1,350 | 50-85 | ~32-34, resident | 1,200-1,750 | 75-115 |

## Conservative memory choices

- Keep the 16 GB Air IQ3 expert store at its measured 1.946 GiB. The speculative 3 GiB IQ3 / 4 GiB Q2 targets are not adopted. The 2-3 GiB Q2 target still needs exact-model sizing.
- Use 12 GiB IQ3 / 14 GiB Q2 on both 32 GB machines. Exclude a 24 GiB expert store. These targets leave more room than the earlier 16/18 GiB proposal, but actual Metal budgets and model-specific footprints still need checking.
- Use 24 GiB for either quant on the 48 GB mini. The earlier 32 GiB IQ3 target was an unverified upper scenario; neither 32 nor 38 GiB is used here. Do not assume fully resident Q2 on this host.
- Use 32 GiB IQ3 / 28 GiB Q2 on the 64 GB mini and model both as streaming, rather than assuming full residency. Additional capacity or a confirmed resident plan may improve performance beyond these conservative scenarios.
- A 48 GiB expert store is not needed for either quant: all IQ3 expert weights total about 41.55 GiB, while Q2 is estimated at 32-34 GiB. A 48G total engine cap is a different quantity and still requires the actual Metal budget to permit it; this conservative 64 GB scenario uses a 40G engine ceiling.
- Only the 128 GB Studio retains the earlier fully resident expert scenario. Its requested 56G budget leaves substantially more room around the saved 45.373 GiB IQ3 weights-plus-draft sizing. Q2's approximately 32-34 GiB resident-expert sizing remains approximate.
- Working engine-cap scenarios are 10.8G for the Air 16 GB, 24G for the 32 GB hosts, 32G for the 48 GB mini, 40G for the 64 GB mini, and 56G for the Studio. These are proposed total engine ceilings, not measured allocations on the other devices or settings applied by this update. Metal can clamp them and host pressure can block growth.
- For context only, the saved IQ3 Air minimum excluding its expert store was about 6.684 GiB. Adding the proposed IQ3 stores gives approximately 18.684, 30.684 and 38.684 GiB for the 32/48/64 GB host scenarios before additional resident-KV growth and device-specific differences. This is rough budget arithmetic, not a planner run or a proof of safe startup.

Expert RAM counts the whole streaming store, including staging/bookkeeping. Studio resident rows count expert weights without adding another store. `--expert-memory SIZE` sets a floor, not an exact cache cap; automatic planning can select a different final allocation. Long contexts may spill more KV to SSD. Device-specific sizing and serving validation are required before changing a real deployment.

## Conservative calculation

For the streamed 32/48/64 GB scenarios, use `rate = baseline_rate / ((1-p)/g + p*(1-h))`. This recalculates from the small-store baseline rather than applying another multiplier to the older larger-cache estimates.

- IQ3 baseline: 241.00 PP at 28,589 tokens and 8.8675 short-code TPS, the equal-weight average of the two saved production-setting baseline block means. They are separate workloads. The measured Air table entry keeps those block means visible rather than presenting the modeled average as a new measurement.
- Q2 planning baseline: 240-300 PP and 10-12 TPS. These are conservative small-store judgments, not local Q2 measurements. They reduce the earlier 260-330 PP / 10-13 TPS proxy; no exact Q2 performance baseline has been validated here.
- Assumed expert-read-sensitive time fractions `p`: 0.35 for PP and 0.75 for generation, reduced from the optimistic scenario's 0.50 and 0.85. Neither fraction has been profiled.
- Assumed avoided expert reads `h`: IQ3 15-30%, Q2 20-35% for the 32 GB rows; IQ3 40-60%, Q2 45-65% for the 48 GB row; IQ3 50-70%, Q2 60-75% for the 64 GB row. Cache capacity does not establish these traffic reductions; they are explicit scenario assumptions.
- Assumed speed factor for the non-expert-I/O portion `g`: 1 for both 32 GB rows, and 1.25-1.5 for the 16-core-GPU minis. No M6 uplift is assumed. These compute factors have not been benchmarked on those devices.
- Round streaming PP outward to tens and TPS outward to whole tokens/s. These are scenario bands, not statistical confidence intervals or guaranteed bounds.
- For the Studio, retain the prior resident scenarios with a 25% planning discount for uncertainty, then round PP outward to 50 and TPS outward to 5: IQ3 900-1,350 PP / 50-85 TPS; Q2 1,200-1,750 PP / 75-115 TPS. The discount is a budgeting judgment, not a measured regression or a fitted correction.

Poor expert reuse, Metal clamping, thermal/memory pressure, draft acceptance or SSD performance can put actual throughput outside the table, including below its lower endpoints. This update does not establish filled-131K novel-codebase performance, sustained generation, coding quality or simultaneous-request throughput. In particular, the previous 48 GB Q2 65-90 TPS resident scenario is not used in this conservative table.

Evidence: [I/O tuning report](qwen38-option20-io-tuning-20261105.md), [raw measurements](qwen38-option20-io-tuning-20261105.json), [10.8G validation](qwen38-option20-budget108-20261105.md), and [previous scenarios](qwen38-option20-mac-rebase-20261105.md).

No runtime configuration, inference, benchmark, model download, build or server restart was performed for this revision. Earlier tables and their source measurements remain in the complete estimate history.
