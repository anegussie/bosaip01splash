# Option 19 chunk-size comparison at 80K — October 28, 2026

Selection: retain requested **512 tokens**. No alternative showed a repeatable overall advantage sufficient to change the profile. All four requested settings exposed identical effective streamed geometry: 2,048 rows per chunk, four allocated chunks, 8,192 maximum group rows and 1,065,893,888 shared prefill bytes.

The actual option-19 launcher was used with an isolated wrapper changing only `--prefill-chunk-tokens`. Eight launches ran in the order 512, 256, 1024, 2048, 2048, 1024, 256, 512. Each phase used cold and immediately cached coding requests at matched prompt lengths. Values are mean client request seconds from two trials per cell:

| Requested chunk | 4,013 cold / cached | 12,203 cold / cached | 32,689 cold / cached |
|---:|---:|---:|---:|
| 256 | 4.78 / 1.88 | 11.39 / 1.44 | 38.03 / 1.76 |
| **512** | **4.75 / 1.87** | **11.20 / 1.44** | **37.52 / 1.76** |
| 1,024 | 4.78 / 1.92 | 11.36 / 1.43 | 37.88 / 1.78 |
| 2,048 | 4.77 / 1.84 | 11.37 / 1.39 | 38.27 / 1.79 |

For 512, weighted native cold PP/TG was 1,258.7/42.6, 1,191.4/44.3, and 913.5/35.9 tokens/s at the respective depths. Cold prefixes had zero reuse; cached requests reused 4,000, 12,192, and 32,672 tokens. Cached PP measures the short uncached suffix and is not comparable to cold PP. The 12K cached cells for 256, 512 and 1024 had spreads of 6.12%, 5.51%, and 5.48%, and the 1024 4K cached cell had 8.78% spread; these are variable. With two samples per cell, small differences elsewhere are not conclusive. No streaming TTFT was measured. The workloads are bounded coding fixtures, not live agent tasks.

All 48 timed coding requests passed executable checks. The preliminary independent smoke passed readiness, cold/cache reuse, forced tool call and tool-result continuation; each of the eight measured launches also passed its four smoke checks. Each candidate used a unique prefix-cache salt and isolated benchmark cache. The comparison began each timed pair nominal. Every 32K 256, 1024 and 2048 cold pair ended fair; the two 512 cold pairs ended nominal and fair, respectively. Memory pressure was warning during test workload. Swap used varied from 2,421.25 MiB at the first phase start to 2,349.25 MiB at the last phase end; this is system-wide and does not attribute paging. Temperatures, swap, request/response records, raw statuses and individual timings are retained in the machine-readable record.

Runtime: Apple M5 / 16 GiB, Qwen3.6-35B-A3B UD-IQ3_XXS, target identity `c3c4fdbcbd03644cf8a1c71587da5aa35385a5aca07520a1d174b6d9bc5e0960`, build `src-7e2e9dc11f019304a5db05390e5a85e0a336ec7c1fb92fe58c337bc75b96d7dc`, 81,920 server context, INT8 KV, BF16 state, DFlash2 and automatic verification, 8 GiB Metal limit, 1,510 expert slots, one active request, 2 GiB isolated persistent cache, temperature 0, seed 42, reasoning off. Initial effective cache quota was 2 GiB. Cold means no prompt-prefix reuse, not cold model/OS cache. Different tasks were used at different depths; comparisons are within depth. Results do not establish behavior under concurrent load or at 57K+ filled context.

All isolated servers stopped. The normal service remained on its original instance, idle with released weights and unchanged request counts; no user request was cancelled. The existing launcher remains at 512. The [per-request measurements](qwen36-option19-chunk-80k-20261028.json) are tracked with this report. Full raw artifacts and runner remain locally in `build/validation/option19-chunk-80k-20261028/`.
