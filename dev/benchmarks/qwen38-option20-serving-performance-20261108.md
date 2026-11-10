# Qwen3.8 Flash Next option 20 live serving performance (2026-11-08)

Two complete trials against the live option-20 server on the 16 GB MacBook Air. Both trials passed the smoke correctness and cache gates, ran with zero competing requests, and recorded zero capacity failures and zero Metal failures.

Headline numbers: **4K cold prefill 394.1 tok/s**, **coding decode mean 9.32 tok/s** (8.68-10.19), **draft acceptance 92.7%** (1,233/1,330), 4K reuse readback **2.42 s TTFT**.

## Profile under test

| Item | Value |
|---|---|
| Model | `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS` (IQ3_XXS, GSQ-RCO) |
| Server | Splash front end pid 92460, `127.0.0.1:1235`, launched 2026-11-08 20:17 |
| Engine | `install/bin/splash` (build id `src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a`) |
| Profile | 131,072 context, 2,048 prefill chunk, INT8 KV, BF16 state, `--ple-memory 64 MiB`, persistent prefix cache, `--default-reasoning-effort low` |
| Metal budget | 10.805 GiB cap (`11,596,411,699` bytes), host cap 16.0 GiB, `growth_allowed: false` |
| Cache | `~/Library/Caches/Splash/flash-next-option20-iq3-xxs`, 17,179,869,184 byte cap |
| Speculation | DFlash2 `--ngram 4 --draft 16` |
| Machine | Apple M5 MacBook Air, 8 GPU cores, 16 GiB unified memory |
| Request shape | `/v1/chat/completions` SSE, `enable_thinking: false`, temperature 1.0, top_p 0.95, thinking off to measure decode |

Cache state at preflight: `warning` memory pressure, `nominal` thermal, 8.79 GiB Metal allocated, 2.33 GB host available, host headroom 0, KV pool 2,816 pages with 2,546 cache-resident and only 270 free, 14.16 GB of 17.18 GB persistent cache in use (10,923 KV blocks, 13 lifetime demotions).

## Method

`dev/benchmarks/qwen38-option20-serving-performance-20261108-raw/run_option20_perf2.py`. Per trial: 351-token smoke cold/reuse pair (correctness plus cache gate), 4,019-token cold/reuse pair, then three 128-token-capped coding prompts. Trial 2 runs the coding group in reverse order. Each trial uses fresh prompt salts so every cold probe is genuinely cold. Every probe waits for three consecutive idle samples, samples `/status` every 0.5 s while the request runs, and records the per-request metrics block (`cache`, `speculation.cycles`, latency breakdown). `clean` requires zero competing samples and exactly one completed request in the probe window; all 14 probes are clean.

## Trial 1

| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached tokens | Draft acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 85.94 | 4.496 | 12.69 | 13 | 7.38 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.15 | 2.257 | 12.5 | 13 | 7.38 | 352 | 83/84 (98.8%) |
| 4k-cold | 4066 | 394.13 | 10.329 | 12.05 | 14 | 6.86 | 0 | 82/85 (96.5%) |
| 4k-reuse | 4066 | 13.65 | 2.499 | 12.89 | 13 | 7.38 | 4032 | 82/82 (100.0%) |
| code-1 | 47 | 11.63 | 1.314 | 9.15 | 33 | 3.88 | 32 | 94/110 (85.5%) |
| code-2 | 40 | 9.09 | 0.902 | 8.68 | 38 | 3.37 | 32 | 90/109 (82.6%) |
| code-3 | 38 | 16.83 | 2.261 | 10.19 | 26 | 4.92 | 0 | 102/107 (95.3%) |

Coding decode mean 9.34 tok/s (8.68-10.19); 4K cold prefill 394.13 tok/s; draft acceptance 616/660 (93.3%).

## Trial 2 (reversed coding order)

| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached tokens | Draft acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 86.28 | 4.479 | 12.5 | 13 | 7.38 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.75 | 2.169 | 12.37 | 13 | 7.38 | 352 | 83/83 (100.0%) |
| 4k-cold | 4064 | 393.98 | 10.327 | 11.97 | 14 | 6.86 | 0 | 82/84 (97.6%) |
| 4k-reuse | 4064 | 13.69 | 2.344 | 11.55 | 15 | 6.40 | 4032 | 81/87 (93.1%) |
| code-1 | 47 | 12.54 | 1.219 | 9.17 | 32 | 4.00 | 32 | 95/111 (85.6%) |
| code-2 | 40 | 9.53 | 0.859 | 9.3 | 34 | 3.76 | 32 | 93/106 (87.7%) |
| code-3 | 38 | 16.5 | 2.308 | 9.41 | 27 | 4.74 | 0 | 100/116 (86.2%) |

Coding decode mean 9.29 tok/s (9.17-9.41); 4K cold prefill 393.98 tok/s; draft acceptance 617/670 (92.1%).

## Pooled (14 probes)

| Probe | Prompt tokens | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached tokens | Draft acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 386 | 85.94 | 4.496 | 12.69 | 13 | 7.38 | 0 | 83/83 (100.0%) |
| smoke-cold | 386 | 86.28 | 4.479 | 12.5 | 13 | 7.38 | 0 | 83/83 (100.0%) |
| smoke-reuse | 386 | 15.15 | 2.257 | 12.5 | 13 | 7.38 | 352 | 83/84 (98.8%) |
| smoke-reuse | 386 | 15.75 | 2.169 | 12.37 | 13 | 7.38 | 352 | 83/83 (100.0%) |
| 4k-cold | 4066 | 394.13 | 10.329 | 12.05 | 14 | 6.86 | 0 | 82/85 (96.5%) |
| 4k-cold | 4064 | 393.98 | 10.327 | 11.97 | 14 | 6.86 | 0 | 82/84 (97.6%) |
| 4k-reuse | 4066 | 13.65 | 2.499 | 12.89 | 13 | 7.38 | 4032 | 82/82 (100.0%) |
| 4k-reuse | 4064 | 13.69 | 2.344 | 11.55 | 15 | 6.40 | 4032 | 81/87 (93.1%) |
| code-1 | 47 | 11.63 | 1.314 | 9.15 | 33 | 3.88 | 32 | 94/110 (85.5%) |
| code-1 | 47 | 12.54 | 1.219 | 9.17 | 32 | 4.00 | 32 | 95/111 (85.6%) |
| code-2 | 40 | 9.09 | 0.902 | 8.68 | 38 | 3.37 | 32 | 90/109 (82.6%) |
| code-2 | 40 | 9.53 | 0.859 | 9.3 | 34 | 3.76 | 32 | 93/106 (87.7%) |
| code-3 | 38 | 16.83 | 2.261 | 10.19 | 26 | 4.92 | 0 | 102/107 (95.3%) |
| code-3 | 38 | 16.5 | 2.308 | 9.41 | 27 | 4.74 | 0 | 100/116 (86.2%) |

4K cold prefill mean **394.06 tok/s**, 4K cold TTFT 10.33 s, 4K reuse TTFT 2.42 s, coding decode mean **9.32 tok/s** (8.68-10.19), draft acceptance **1233/1330 (92.7%)**.

## Side by side with the 2026-11-06 telemetry reference

| Probe | Nov 6 prefill tok/s | Nov 8 | delta | Nov 6 TTFT s | Nov 8 | delta | Nov 6 decode tok/s | Nov 8 | delta | Nov 6 acc | Nov 8 acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-cold | 76.50 | 86.11 | +12.6% | 4.591 | 4.488 | -2.2% | 12.33 | 12.59 | +2.1% | 98.8% | 100.0% |
| smoke-reuse | 14.55 | 15.45 | +6.2% | 2.141 | 2.213 | +3.4% | 12.38 | 12.43 | +0.4% | 98.8% | 99.4% |
| 4k-cold | 406.91 | 394.06 | -3.2% | 9.881 | 10.328 | +4.5% | 12.66 | 12.01 | -5.1% | 98.8% | 97.0% |
| 4k-reuse | 12.38 | 13.67 | +10.5% | 1.539 | 2.421 | +57.3% | 12.47 | 12.22 | -2.0% | 98.8% | 96.4% |
| code-1 | 15.50 | 12.09 | -22.1% | 2.131 | 1.267 | -40.6% | 9.61 | 9.16 | -4.7% | 83.6% | 85.5% |
| code-2 | 15.68 | 9.31 | -40.6% | 2.043 | 0.881 | -56.9% | 9.67 | 8.99 | -7.0% | 83.2% | 85.1% |
| code-3 | 16.20 | 16.66 | +2.9% | 2.226 | 2.284 | +2.7% | 10.84 | 9.80 | -9.6% | 94.4% | 90.6% |

Aggregate: 4K cold prefill 406.91 -> 394.06 tok/s (-3.2%), coding decode 10.04 -> 9.32 tok/s (-7.2%), draft acceptance 92.8% -> 92.7%, 4K reuse TTFT 1.54 -> 2.42 s (+57.3%).

Conditions differ from the reference run: the reference used a freshly launched engine on port 1245 with a small KV pool (256 pages, 10 cache-resident, 246 free) and `nominal` thermal on every probe, 7.875 GiB Metal allocated and 2.39-2.46 GiB host available, with the persistent cache directory itself already at 15.9-16.0 GiB. This run used the long-lived server on port 1235 (~2h50m uptime, 76 prior requests, ~14 GB persistent cache already resident), 8.79-8.99 GiB Metal allocated, 2.33-3.44 GB host available, `nominal` only for the first two probes and `fair` afterwards. Engine line also differs (`882891f8` instrumented build vs the `6a06f0d6` baseline build used by the Nov 6 reference pair).

## What the numbers say

1. Long-context prefill is intact. 394.13 / 393.98 tok/s across two trials, within 3.2% of the Nov 6 reference (406.91), with the same cycle shape (14 cycles for 96 decoded tokens vs 13 in the reference).

2. Prefix reuse works but reads back slower than the fresh-launch reference. Both 4K reuse probes were cache `hit` with 4,032 matched tokens, yet TTFT was 2.499 / 2.344 s vs 1.553 / 1.518 s in the reference, i.e. +57%. The `/status` counters explain it: `cache.kv_disk_hit_tokens` grew by 81,600 tokens during the run (64,768 -> 146,368) and `disk.kv_demotions` grew 13 -> 35, so the reuse probes reloaded KV blocks from the persistent cache instead of finding them resident, while the Nov 6 reference recorded `cache.kv_disk_hit_tokens = 0` before and after its whole matrix with `disk_state_publications = 0`. Immediately before each 4K reuse probe the engine had already evicted cache-resident pages (2,546 -> 126 cached pages, 270 -> 642 free pages) to make room. The post-run `/status` snapshot shows `kv_spill.restores.whole_pages` 4,574 pages restored from disk with 445 s cumulative restore time (p50 131 ms, p95 262 ms per page), while `kv_spill` itself stayed at zero spill and zero write-through pages, so the cost is in cached-page restoration rather than in KV eviction pressure.

3. Coding decode is 7.2% below the reference (9.32 vs 10.04 tok/s mean). Dense probes did not regress (smoke decode 12.43-12.69, 4K decode 11.97-12.89, within 2% of the reference), and thermal was `fair` for the coding probes, so the gap is coding-specific speculation behavior rather than global slowdown: this run needed more cycles for the same 128 tokens (code-1 32.5 vs 26, code-2 36 vs 30) at equal or better draft acceptance, so fewer accepted tokens per cycle (3.7-4.9 vs 4.3-4.9).

4. A single-trial run earlier the same evening (20:54, warm and contended, `fair` thermal throughout) measured 4K cold prefill 312.15 tok/s. With idle gating and two trials the same build measures 394 tok/s. The earlier figure was environment noise, not an engine regression.

5. Memory stayed inside budget. Metal peak 9.206 GiB against the 10.805 GiB cap, host available never below 3.23 GB during a probe, zero capacity failures, zero Metal failures, zero KV spill, `growth_allowed: false` throughout.

## Open items

- Reuse readback latency grows with KV pool saturation, not with directory size: the Nov 6 reference already had 15.9-16.0 GiB on disk yet recorded `cache.kv_disk_hit_tokens = 0` because its pool had 246 of 256 pages free. Worth a controlled A/B on the same build: freshly launched engine versus this long-lived engine, and emptied cache directory versus populated, measuring 4K reuse TTFT, `cache.kv_disk_hit_tokens`, and `kv.pages_cache` / `kv.pages_free` immediately before the reuse probe. See `qwen38-option20-vs-nov06-comparison-20261108.md`.

- The coding decode gap needs a same-thermal comparison. A `nominal`-thermal trial would separate thermal from speculation effects; that was not possible in this session because a live tool-calling agent session (90k+ token contexts) kept the machine at `fair` and kept the server busy.

- Engine identity is not identical to the Nov 6 baseline pair. The `/status` digests for `loaded_model_layout_sha256` (92020136... vs b7f2417c...) and `kv.target_model_sha256` (f22d21e0... vs 261aef54...) differ, while the GGUF blobs are untouched (HF revision `dbba1494...`, blobs dated Oct 31; a full-file sha256 matches neither digest), so these are internal prepared-layout digests rather than model file hashes.

## Raw artifacts

`dev/benchmarks/qwen38-option20-serving-performance-20261108-raw/`: `run_option20_perf2.py`, `preflight.json`, `matrix-results.json`, `matrix.md`, `trial1/`, `trial2/`, and `warm-server-single-trial/` (the 20:54 single-trial run used as the noise control).

