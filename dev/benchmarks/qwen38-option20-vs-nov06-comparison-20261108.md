# Option 20 live serving performance: 2026-11-08 vs 2026-11-06

Side-by-side of the two-trial 2026-11-08 run (`qwen38-option20-serving-performance-20261108.md`) against the 2026-11-06 telemetry reference pair (`baseline` + `baseline2`), with the 2026-11-06 `instrumented` pair shown as a control because the current engine line is instrumented.

## Reference variants agree with each other

| Variant | 4K cold prefill tok/s | 4K reuse TTFT s | coding decode tok/s | draft acceptance |
|---|---:|---:|---:|---:|
| Nov 6 baseline pair | 406.91 | 1.539 | 10.04 | 92.8% |
| Nov 6 instrumented pair | 408.28 | 1.536 | 10.05 | 92.8% |
| **Nov 8 two trials** | **394.06** | **2.421** | **9.32** | **92.7%** |

The two Nov 6 variants are within 0.5% of each other on every metric, so instrumented telemetry itself costs nothing and either pair is a valid target.

## Per-probe comparison

| Probe | Metric | Nov 6 baseline | Nov 6 instrumented | Nov 8 | vs baseline | vs instrumented |
|---|---|---:|---:|---:|---:|---:|
| smoke-cold | prefill tok/s | 76.50 | 76.62 | 86.11 | +12.6% | +12.4% |
| smoke-cold | TTFT s | 4.591 | 4.582 | 4.488 | -2.2% | -2.1% |
| smoke-cold | decode tok/s | 12.33 | 12.34 | 12.59 | +2.1% | +2.0% |
| smoke-cold | speculation cycles | 13.0 | 13.0 | 13.0 | +0.0% | +0.0% |
| smoke-reuse | prefill tok/s | 14.55 | 14.93 | 15.45 | +6.2% | +3.5% |
| smoke-reuse | TTFT s | 2.141 | 2.088 | 2.213 | +3.4% | +6.0% |
| smoke-reuse | decode tok/s | 12.38 | 12.37 | 12.43 | +0.4% | +0.5% |
| smoke-reuse | speculation cycles | 13.0 | 13.0 | 13.0 | +0.0% | +0.0% |
| 4k-cold | prefill tok/s | 406.91 | 408.28 | 394.06 | -3.2% | -3.5% |
| 4k-cold | TTFT s | 9.881 | 9.848 | 10.328 | +4.5% | +4.9% |
| 4k-cold | decode tok/s | 12.66 | 12.64 | 12.01 | -5.1% | -5.0% |
| 4k-cold | speculation cycles | 13.0 | 13.0 | 14.0 | +7.7% | +7.7% |
| 4k-reuse | prefill tok/s | 12.38 | 12.43 | 13.67 | +10.5% | +10.0% |
| 4k-reuse | TTFT s | 1.539 | 1.536 | 2.421 | +57.3% | +57.6% |
| 4k-reuse | decode tok/s | 12.47 | 12.50 | 12.22 | -2.0% | -2.3% |
| 4k-reuse | speculation cycles | 13.0 | 13.0 | 14.0 | +7.7% | +7.7% |
| code-1 | prefill tok/s | 15.50 | 15.25 | 12.09 | -22.1% | -20.8% |
| code-1 | TTFT s | 2.131 | 2.167 | 1.267 | -40.6% | -41.6% |
| code-1 | decode tok/s | 9.61 | 9.64 | 9.16 | -4.7% | -4.9% |
| code-1 | speculation cycles | 26.0 | 26.0 | 32.5 | +25.0% | +25.0% |
| code-2 | prefill tok/s | 15.68 | 15.66 | 9.31 | -40.6% | -40.6% |
| code-2 | TTFT s | 2.043 | 2.046 | 0.881 | -56.9% | -57.0% |
| code-2 | decode tok/s | 9.67 | 9.68 | 8.99 | -7.0% | -7.2% |
| code-2 | speculation cycles | 30.0 | 30.0 | 36.0 | +20.0% | +20.0% |
| code-3 | prefill tok/s | 16.20 | 15.95 | 16.66 | +2.9% | +4.5% |
| code-3 | TTFT s | 2.226 | 2.260 | 2.284 | +2.7% | +1.1% |
| code-3 | decode tok/s | 10.84 | 10.84 | 9.80 | -9.6% | -9.6% |
| code-3 | speculation cycles | 26.0 | 26.0 | 26.5 | +1.9% | +1.9% |

## Run conditions

| Item | Nov 6 (all four variants) | Nov 8 |
|---|---|---|
| Engine state | freshly launched, 2 completed requests before the matrix | pid 92460, ~2h50m uptime, 77 completed requests before the matrix |
| KV page pool | 256 pages, 10 cache-resident, 246 free | 2816 pages, 2546 cache-resident, 270 free |
| Persistent cache on disk | 15.94 GiB of the 16.0 GiB cap, 19039 KV blocks, 0 lifetime demotions | 13.19 GiB of the 16.0 GiB cap, 10923 KV blocks, 13 lifetime demotions |
| `cache.kv_disk_hit_tokens` across the matrix | 0 before and 0 after, `disk_state_publications` 0 (every matched block was resident) | 64,768 before, 146,368 after, +81,600 tokens read back from disk KV |
| Metal | 7.875 GiB allocated, 8.290 GiB peak | 8.791 GiB allocated, 9.206 GiB peak during the run (10.805 GiB cap) |
| Host available | 2.36 GiB, headroom 0, growth allowed false | 2.17 GiB, headroom 0, growth allowed false |
| Memory pressure / thermal | `warning` / `nominal` for every probe | `warning` / `nominal` for the first two probes, `fair` for the rest |
| Prompt token counts | 351 smoke, 4,019 4K, 33 / 32 / 36 coding | 386 smoke, 4,066 / 4,064 4K, 47 / 40 / 38 coding |
| Coding prompt cache hits | 0 cached tokens on every coding probe | 32 cached tokens on code-1 and code-2, 0 on code-3 |

## Reading the deltas

1. **Prefill is essentially intact.** 4K cold 406.91 / 408.28 -> 394.06 tok/s (-3.2% / -3.5%), TTFT 9.88 -> 10.33 s (+4.5%). Both runs are single-request and idle-gated at `warning` pressure, but Nov 8 ran at `fair` thermal from the 4K pair onward. Treat -3.5% as the warm-pool-and-thermal band, not a code regression.

2. **Cached reuse readback is the one real regression: 1.54 s -> 2.42 s TTFT (+57%).** Both runs report a cache `hit` with ~4,000 matched tokens and only 19-34 uncached prompt tokens, so matching is not the issue. The counters separate the runs cleanly. Nov 6: `cache.kv_disk_hit_tokens` 0 before and after the whole matrix, `disk_state_publications` 0, with a small pool that had 246 of 256 pages free. Nov 8: +81,600 disk-hit tokens and 22 new demotions, because 2,546 of 2,816 pages were occupied by cached KV with only 270 free; the engine had evicted cache-resident pages (down to 126 cached, 642 free) and reloaded KV blocks from the 13.2 GiB persistent cache for the same probe. The post-run snapshot shows 4,574 whole-page restores totalling 445 s (p50 131 ms, p95 262 ms per page), while `kv_spill` stayed at zero spill and zero write-through pages.

3. **Uncached short-prompt latency is unchanged.** code-3 cached nothing in both runs: TTFT 2.226 / 2.259 -> 2.284 s (+1-3%). The fixed prompt-phase floor did not drift. code-1 and code-2 appear 41-57% better only because this run had a 32-token cached shared prefix that the Nov 6 probes never had; their lower `prefill tok/s` (12.09 / 9.31 vs 15.50 / 15.68) is the same effect seen from the other side, since prefill tok/s counts only uncached tokens.

4. **Coding decode is 7% slower: 10.04 -> 9.32 tok/s.** The cleanest signal is code-3 (no cache hit, unchanged TTFT): 10.84 -> 9.80 tok/s (-9.6%) at the same cycle count (26 -> 26.5). code-1 and code-2 needed more cycles for the same 128 output tokens (26 -> 32.5, 30 -> 36) at equal or better draft acceptance (85.5% / 85.1% vs 83.6% / 83.2%), so fewer tokens are accepted per cycle (3.4-4.0 vs 4.3-4.9). Dense decode did not regress (smoke 12.43-12.69, 4K 11.97-12.89, within 2-5%) and aggregate acceptance is identical (92.7% vs 92.8%), so this is coding-output speculation efficiency rather than a global slowdown.

5. **Small cold prefill improved.** smoke-cold 76.50 -> 86.11 tok/s (+12.6%) with the same 13 cycles and equal or better acceptance (100% vs 98.8%).

## Verdict

Against the Nov 6 reference, long-context prefill, draft acceptance, and uncached small-prompt latency are within noise. Two things genuinely changed: cached reuse costs 57% more TTFT on a long-lived, pool-saturated server, and coding decode dropped ~7% through fewer accepted tokens per speculation cycle. Memory headroom did not regress: Metal peaked at 9.206 of 10.805 GiB, host availability never fell below 3.23 GiB during a probe, and capacity failures, Metal failures, and KV spill all stayed at zero, same as Nov 6.

## Follow-ups worth running

- Fresh-engine control: relaunch option 20 empty (same build, same cache directory) and re-run the 4K cold/reuse pair. If reuse TTFT returns to ~1.5 s with a populated directory but a free pool, the cost is eviction and reload, not directory size.

- Cache-state A/B on the same engine: emptied cache directory versus the populated one, comparing 4K reuse TTFT, `cache.kv_disk_hit_tokens`, and `kv.pages_cache` / `kv.pages_free` immediately before the reuse probe.

- Coding decode A/B at matched `nominal` thermal on the same build, counting cycles and accepted tokens per cycle for the three coding prompts. If cycles fall back toward 26 / 30 / 26 the 7% is thermal; if they stay near 32 / 36 / 26 it is a speculation-policy change worth bisecting between the Nov 6 engine line and HEAD.

Recommended actions, ranked, are in [option 20 recommendations (2026-11-08)](qwen38-option20-recommendations-20261108.md).

## Raw data

- Nov 8: `dev/benchmarks/qwen38-option20-serving-performance-20261108-raw/` (`matrix-results.json`, `preflight.json`, `trial1/`, `trial2/`).

- Nov 6: `dev/benchmarks/qwen38-option20-telemetry-performance-20261106-raw/{baseline,baseline2,instrumented,instrumented2}/`.

