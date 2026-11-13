# Option 21 arms: paying for the 1024-block indexer

Date: 2026-11-12. Machine: Apple M5, 16 GiB, one engine at a time.
Model: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` with the local BF16
DFlash2 draft, 131,072 context, 11,596,411,699 byte budget, persistent cache.

## The question

Widening the QSA indexer from 512 to 1024 blocks (`top_k` 2048 -> 4096) pins the
hot KV block cache at 780 MiB instead of 390 MiB. The kernel sweep showed the
wider indexer costs nothing in the attention kernels, so the whole price is
390 MiB taken from the expert store, which is where decode actually lives: a
decode cycle spends 265 ms, of which expert host steps are about 40%, while
attention across all 12 layers is about 6 ms.

The plan has one obvious place to find that money. The shared prefill arena is
sized by `--prefill-chunk-tokens`, and at 2,048 tokens it is 1,691,156,480 bytes
of the 9.35 GiB fixed runtime. Halving the chunk frees more than a GiB.

## Arms

| Arm | Change | Shared prefill bytes | Expert cap | Expert slots |
|---|---|---:|---:|---:|
| baseline | stock profile, chunk 2048 | 1,691,156,480 | 2,941,043,472 | 1,512 |
| chunk1024 | `SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS=1024` | 616,841,216 | 4,015,162,128 | 2,176 |
| context64k | `SPLASH_FLASH_NEXT_MAX_CONTEXT=65536` | not run yet | - | - |

The freed 1,074,315,264 bytes went entirely to the expert store: cap up 1,074 MiB,
residency up 664 slots, 44% more experts resident. Neither arm ever grew past its
floor (`chunks: 1`, `growth_allowed: false`), so residency is set by the plan, not
by the governor.

## Method

`dev/benchmarks/option21_arms.py` runs ABBA: baseline, candidate, candidate,
baseline, each round a real `startllamacpp.sh --direct 21` launch with its own
cold cache directory. Throughput comes from the timings each response carries
(`prompt_ms`, `predicted_ms`, `cycles`), which count engine work only, so a probe
queued behind another client's request is not miscounted. Expert work comes from
the engine's cumulative counters read over the whole round. `abba.py` decides the
verdict: a candidate must beat the baseline by more than the spread the run
measures in itself.

Probes: warmup (40 records), `cold_8k` (500 records, 96 output), `decode_512`
(a code-review prompt, 512 output), `cached_8k` (same 500 records again).

## Rounds

| Round | Arm | Chunk | Resident experts | Decode tok/s | ms/token | Tok/cycle | Cold prefill s | Cached prefill s | Expert ms/token | Expert reads/token | Hit rate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | baseline | 2048 | 1,512 | 11.0 | 90.97 | 3.00 | 52.82 | 1.92 | 34.24 | 261.2 | 32.7% |
| 2 | chunk1024 | 1024 | 2,176 | 11.8 | 85.00 | 3.39 | 52.17 | 1.93 | 28.92 | 215.6 | 47.0% |
| 3 | chunk1024 | 1024 | 2,176 | 12.7 | 78.96 | 3.35 | 71.74 | 1.86 | 30.06 | 209.2 | 44.1% |
| 4 | baseline | 2048 | 1,512 | 11.4 | 88.09 | 3.39 | 29.88 | 1.93 | 35.99 | 255.7 | 31.2% |

## Verdicts

| Metric | Baseline | Candidate | Change | Noise | Verdict |
|---|---:|---:|---:|---:|---|
| Expert host work per output token | 35.12 ms | 29.49 ms | -16.0% | 4.97% | PASS |
| Expert reads per output token | 258.5 | 212.4 | -17.8% | 3.02% | PASS |
| Decode ms per token | 89.53 | 81.98 | -8.4% | 7.36% | inconclusive |
| Cached prefill seconds | 1.927 | 1.897 | -1.6% | 3.75% | PASS |
| Cold prefill seconds | 41.35 | 61.95 | +49.8% | 55.5% | inconclusive |
| Total round seconds | 267.0 | 399.1 | +49.5% | 120.5% | inconclusive |

## What the numbers say

The mechanism is settled. Halving the prefill chunk buys a GiB, the store spends
it on residency, residency turns into a 44-47% expert hit rate instead of 31-33%,
and the streamed expert work per output token drops 16-18% with noise well below
the bound. That is the largest single lever found so far, and it attacks the part
of a decode cycle that is 40% of its wall time.

Decode throughput moves in the right direction (89.5 -> 82.0 ms/token, 11.2 ->
12.2 tok/s) but the run's own noise, 7.4%, is above the 5% limit the protocol
needs for a verdict. Two rounds per arm is not enough while something else is
using the machine: every round carried one or two requests from another client,
and the same cold 11,362-token prompt took 29.9 s in one baseline round and 71.7
s in a candidate round.

Prefill is the open question. Option 21 exists for prefill throughput, and the
kernel sweep says 2,048-token chunks beat 1,024-token chunks because a wider
chunk shares the expert dequantization across more rows. This run cannot tell how
much of that is lost; the cold-prefill spread is too large to conclude anything.

## Next

1. Re-run the decode pair with nothing else on the machine. The harness reports
   `foreign_requests` per round, so a round with any is a round to redo.
2. Measure prefill separately: same cold prompt, no decode probe, so the number
   is not mixed with queueing.
3. Try `context64k`, which buys the same money from the spill floor instead of
   the prefill arena.
4. Look for the GiB somewhere else. `lane_state_bytes` (163 MiB), `pipeline_reserve_bytes`
   (268 MiB) and `runtime_overhead_reserve_bytes` (537 MiB) are all fixed
   reservations; if any of them is oversized, the 2,048 chunk and the extra
   residency can both be kept.
