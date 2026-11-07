# Option 20: revised estimates for all six Macs, November 5, 2026

Historical planning scenarios: superseded by the [conservative cache, prefill and generation estimates](qwen38-option20-mac-conservative-20261105.md). The original analysis and measurements below are retained for traceability.

The latest saved chunk-size comparison replaces the older Air prefill anchor. **The 16 GB M5 Air measured 400.28 tok/s at 4,019 tokens and 241.00 tok/s at 28,589 tokens with 2,048-token chunks.** All other Mac figures below are conditional planning scenarios. They have not been measured on those devices. This revision supersedes the earlier option-20 hardware estimate tables; their original measurements and assumptions remain in the [complete estimate history](qwen38-option20-mac-estimates-20261105.md).

## Measured basis and current launcher

Exact artifact: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, matching DFlash2, M5 MacBook Air with 8 GPU cores and 16 GiB RAM, one request, 131,072 served context, INT8 KV and BF16 recurrent state. The entire 26.82 GiB n-gram table stays SSD-backed with an approximately 64 MiB RAM row cache. Persistent prefix-cache quota is 16 GiB. The engine cap is not total process RSS.

The same-binary A/B/B/A comparison used a **10 GiB cap** and changed prefill chunks only. Cold means zero conversation-prefix reuse; hardware/OS caches were not flushed. Each chunk size has two timed cold observations per prompt length. Prompts use repeated repository-note filler and a recall/counting check, rather than a representative novel codebase.

| Prompt tokens | 1,024 chunks, cold PP tok/s | 2,048 chunks, cold PP tok/s | Cold SSE TTFT with 2,048 chunks |
|---:|---:|---:|---:|
| 4,019 | 202.88 (201.43-204.33) | 400.28 (399.40-401.17) | 10.05 s mean |
| 28,589 | 170.155 (155.15-185.16) | 241.00 (234.57-247.43) | 118.76 s mean |

The corresponding prefill ratios are **1.9730 at 4K** and **1.4164 at 28.6K**. Only the latter is used for the approximately 30K planning table. The 4K ratio must not be applied across prompt lengths. The 28.6K observations reported fair thermal state, normal/warning memory pressure for 1,024 chunks and warning pressure for 2,048 chunks. Host headroom was approximately 0.96-1.16 GiB and 0.51-0.55 GiB respectively. These are small-sample, current-condition measurements.

The retained production decode settings, four read-ahead workers and 512 KiB pieces, measured **8.92 and 8.81 short-code tok/s** as the means of two separate baseline blocks. This does not establish a generation speedup. Predictable counting output at about 12 tok/s is a different workload. Source evidence: [I/O tuning report](qwen38-option20-io-tuning-20261105.md) and [raw measurement package](qwen38-option20-io-tuning-20261105.json).

The repository launcher now selects **10.8G and 2,048-token chunks** automatically for its 16 GiB/131K/automatic-expert/one-request/16G-persistent-cache preset. The cap parses as 11,596,411,699 bytes. Expert-store capacity remains 1.945969 GiB including staging. The 10.8G validation measured 398.60 cold PP tok/s at 4K and passed a resident-KV replay of a 130,733-token prefix. It did not repeat the cold 28.6K comparison or measure a cold near-131K prompt. Therefore 241.00 tok/s remains the measured **10G** anchor, not a new 10.8G benchmark. [Budget validation](qwen38-option20-budget108-20261105.md).

## Revised Mac planning scenarios

All rates are tok/s. Prefill concerns cold prompts around 30K; generation concerns short low-reasoning coding probes. The budgets and assumed expert allocations retain the previous deployment scenarios. They are not new per-device memory-plan results. The IQ3 Air row is measured; every Q2 row and every larger-Mac rate is an estimate.

| Mac | Quant | Requested engine cap | Assumed expert RAM, GiB | Previous cold PP | Revised cold PP | Short-code generation |
|---|---|---:|---:|---:|---:|---:|
| M5 Air 16 GB, 8-core GPU | IQ3_XXS | 10.8G current; measurements at 10G | 1.946, measured store | 183.27, earlier run | **241.00, measured at 28,589** | **8.81-8.92, measured block means** |
| M5 Air 16 GB, 8-core GPU | Q2_0 | 10.8G, hypothetical Q2 profile | 2-4 | 190-230 | **260-330**, full-transfer scenario | 10-13 |
| M5 Air 32 GB | IQ3_XXS | 24G | 12-16 | 180-250 | **250-360**, full-transfer scenario | 11-16 |
| M5 Air 32 GB | Q2_0 | 24G | 14-18 | 230-350 | **320-500**, full-transfer scenario | 14-22 |
| M6 mini 32 GB | IQ3_XXS | 24G | 12-16 | 180-250 | **250-360**, full-transfer scenario | 11-16 |
| M6 mini 32 GB | Q2_0 | 24G | 14-18 | 230-350 | **320-500**, full-transfer scenario | 14-22 |
| M5 Pro mini 48 GB, 16-core GPU | IQ3_XXS | 40G | 26-32 | 250-450 | **290-530**, partial-transfer scenario | 15-25 |
| M5 Pro mini 48 GB, 16-core GPU | Q2_0 | 40G | 28-32 | 350-650 | **410-770**, partial-transfer scenario | 22-40 |
| M5 Pro mini 64 GB, 16-core GPU | IQ3_XXS | 48G maximum | 38-41.55, conditional near/full residency | 600-900 | **600-900**, resident scenario retained | 35-60, conditional |
| M5 Pro mini 64 GB, 16-core GPU | Q2_0 | 48G maximum | Approximately 32-34, conditional full residency | 850-1,150 | **850-1,150**, resident scenario retained | 65-90, conditional |
| M5 Max Studio 128 GB, 40-core GPU | IQ3_XXS | 56G | 41.55, assumed resident weights | 1,200-1,800 | **1,200-1,800**, resident scenario retained | 70-110 |
| M5 Max Studio 128 GB, 40-core GPU | Q2_0 | 56G | Approximately 32-34, assumed resident weights | 1,600-2,300 | **1,600-2,300**, resident scenario retained | 100-150 |

**How the new estimates are calculated.** Let `r = 241.00 / 170.155 = 1.4163557`, from the matched chunk comparison, and use `new_PP = old_PP / ((1 - f) + f / r)`. Here `f` is an assumed fraction of previous prefill time that benefits from the Air chunk change. It is a sensitivity parameter, not an observed SSD-time fraction or a fitted device characteristic. Round estimated endpoints outward to multiples of 10 tok/s.

- **Full transfer, f = 1:** multiply the previous 16 GB Q2 and 32 GB ranges by 1.4164. This is an optimistic transfer assumption for continued expert streaming, not evidence of a 41.6% improvement on those configurations. With no transfer, their previous ranges remain valid alternatives.
- **Partial transfer, f = 0.5:** multiply the previous 48 GB ranges by 1.1723. This explicitly allows only half the previous time to benefit as more experts can remain in RAM. The half-time choice is a planning judgment; it has not been measured. The sensitivity spans no uplift at `f = 0` through 1.4164 at `f = 1`.
- **Resident scenario, f = 0:** retain the 64 GB near/full-resident and 128 GB resident ranges. There is no matching evidence that the Air's reduction in streamed prefill reads improves these configurations. Other chunk-size compute benefits remain unmeasured there.

The Air's earlier 183.27 figure came from a separate run. It is shown for table history, but **241 / 183.27 is not the controlled chunk-size ratio**. Q2 uses the exact alternative `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0`; option 20 still selects IQ3_XXS. Transferring the IQ3 chunk effect to Q2 is an additional unverified assumption. No generation estimate receives a chunk-derived multiplier, and no M6-specific uplift is assumed. These ranges are scenarios, not statistical confidence intervals or guaranteed performance floors.

## Larger-Mac configuration and residency conditions

The larger-Mac scenarios require **explicit 2,048-token prefill chunks, one active request and the requested larger memory cap**. Unmodified option 20 on hosts of 24 GB or more retains its 1,024-chunk/two-admitted-request/10G defaults. Running those defaults does not select the table's larger-cache or new chunk-transfer scenarios. For example, the 32 GB IQ3 scenario corresponds to:

```sh
SPLASH_FLASH_NEXT_MAX_MEMORY=24G \
SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=2048 \
SPLASH_FLASH_NEXT_MAX_ACTIVE_REQUESTS=1 \
  bash /Users/mymac/startllamacpp.sh --direct 20
```

Other table rows substitute their requested cap. This is an explanation of the assumed configuration; no launcher or runtime setting was changed for this estimate revision.

Requested ceilings can be clamped by Metal's recommended working set minus the larger of 1 GiB or 2%. Host pressure can also prevent expert-store growth. The launcher's printed three-quarters-of-RAM approximation is not a measured device limit. Expert RAM in streaming rows includes staging and bookkeeping; fully resident rows count resident expert weights without adding a second streaming cache. More capacity alone does not establish avoided expert-read traffic.

The IQ3 model's saved metadata sizing is **45.373 GiB of weights plus draft**, excluding the SSD n-gram table, including **41.555 GiB of routed experts**. Only 2.627 GiB remains under a 48G cap before KV, recurrent state, scratch and runtime reserves. The larger chunks consume more scratch, so the 64 GB IQ3 full-residency row remains conditional, especially at long context. Q2's approximate resident expert allocation has not had the equivalent sizing check. The 128 GB Studio assumes the earlier 40-core-GPU configuration; these hardware labels are retained assumptions, not a fresh product-availability audit.

For the 64 GB mini's IQ3 deployment, retain these distinct operating scenarios:

| Actual expert placement | Cold PP around 30K | Short-code generation |
|---|---:|---:|
| All or nearly all experts resident | 600-900 | 35-60 |
| Some recurring expert SSD reads, partial transfer | 350-650 | 20-35 |
| Substantial expert streaming, full transfer | 280-430 | 13-20 |

The cautious planning point remains approximately **500 prefill tok/s and 30 generation tok/s**, about 66 seconds for 32,768 prompt tokens before other request overhead. It is a judgment between operating scenarios, not a measured or fitted prediction. Neither more RAM nor the 10.8G Air cap justifies increasing generation without evidence.

## Long context and evidence boundary

A separate 10G/2,048-chunk request measured **321.84 cold PP tok/s, 406.358 s SSE TTFT and 11.90 predictable decode tok/s at 130,733 tokens**. Immediate and restarted persisted replays reused 130,720 tokens and passed recall/counting. This is one repeated-filler cold trial, with the 10G profile's SSD KV spill behavior; it is not a cold 10.8G resident-KV measurement or a general context-scaling curve. The later 10.8G near-131K request was a persisted replay and supplies functional residency evidence only. Cached suffix PP must not be substituted for full-prompt PP.

The native build remains `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`, binary SHA-256 `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691`. No rate above establishes filled-131,072 novel-codebase performance, sustained generation, or simultaneous-request throughput. Earlier publisher and other-runtime results remain separate anchors; no new external hardware or runtime results are introduced. DGX Spark is not a Mac and its separate CUDA estimates are unchanged.

This revision reads saved reports, JSON and launcher/planner source only. Arithmetic, links and preservation of the prior estimate document are checked locally. It runs no inference, benchmark, build, model download, server query or restart.
