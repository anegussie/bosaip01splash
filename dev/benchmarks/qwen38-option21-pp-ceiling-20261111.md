# Option 21 prompt processing: where the ceiling is (2026-11-11)

Same host as the chunk test: 16 GiB M5, option 21 (`Q2_0` target + BF16 DFlash2
draft), 128K context, `--prefill-chunk-tokens 2048`, persistent cache 16G, PLE 64M.

## One thing to know before reading the numbers

Identical configs measured minutes apart ranged **252 to 412 tok/s** at 8,204 prompt
tokens. Thermal state was `fair` in almost every run. Any conclusion below needs
several trials; single runs are not trustworthy.

## What was tried, and what it did

| Lever | Config | 8,192-token cold prefill | Verdict |
|---|---|---|---|
| Chunk (already shipped) | 1024 -> 2048 | 282 -> 337-412 tok/s | the one real win |
| Bigger cap | 10.8G -> 12G | 336.9 -> 331.8 | no change; the engine clamps 12G to 11.64G |
| Bigger expert store | `--expert-memory 4G`, `6G` | boot refused: "hard budget cannot fit one lane's state and the KV runway" | not possible on 16 GiB |
| Smaller expert store | `--expert-memory 1126M` (1,482 slots vs 1,784) | 340.1 vs 336.9 | no change either way |
| Draft on/off | not possible | - | the launcher has no draft-off knob for option 21 (`SPLASH_MTP` is unused here; `--draft-model` takes a path, and `serve-native` defaults to the family's DFlash2 draft). Runs labelled "off" were the same config |
| Context | 131072 vs 32768 | 318.1/385.1 vs 371.2/388.4 | no difference once warm |
| Chunk below full row | 1536 | 220 | worse: 1,536 rows is not a full row group |

## Where prefill time actually goes

From `/status` after an 8,204-token prefill:

- **GPU busy 99.9% of wall time** (`model_timing.prefill`: gpu 352,905 ms vs wall 353,170 ms).
  Prefill is not stalled on the host; the GPU is the limit.
- **Expert streaming**: 138,736 reads of routed experts, 1.9 MB each, hit rate 8-12%.
  Sustained SSD read rate ~1.8 GB/s, measured ceiling on this drive ~5-6.7 GB/s.
  The SSD has headroom, which is why shrinking the expert store changed nothing.
- **Expert residency**: 1,784 of 24,576 experts resident (7%). Only ~2 GB of RAM is
  available for the store, so residency cannot rise meaningfully on a 16 GiB host.
- **KV**: no disk read-back and no spill pages in any probe; KV is not the problem.
- **Prefix reuse**: 40x faster than cold prefill (0.6-0.8 s TTFT vs 24 s). Keeping
  prompts stable is worth more than any tuning knob.

## What would move PP, in order of likelihood

1. **Engine kernels, not flags.** PP is GPU-bound. The prefill attention tile is a
   compile-time constant (`SPLASH_PREFILL_ATTENTION_TILE_ROWS 8` in
   `runtime/metal/abi/ExecutionGeometry.h`); wider tiles or a fused dequant path
   are where the remaining throughput is.
2. **Chunks above 2,048 need a split host step.** `RuntimeGeometry::from` accepts
   multiples of 128 in `[128, 2048]`; 4,096 rows per host step ran 6.157 s without
   a host step and tripped the 5 s Metal window (`kMaskWaitLimitMilliseconds`,
   `runtime/engine/Engine.cpp:19`). A 4,096-row chunk issued as two host-visible
   steps is the path to a larger group.
3. **Read-ahead waste in the expert store.** 15% of read-ahead bytes are never
   used (968 GB read ahead, 754 GB used). Tightening the ahead plan would cut SSD
   traffic, though with SSD headroom the gain may be small.
4. **Host free RAM.** The store gives back a 421 MiB chunk whenever the governor
   sees less than 2 GiB spare (`host_spare_bytes` ~1.8 GiB here). Closing other
   apps lets it keep both chunks; measured effect on PP was negligible, so treat
   this as stability, not speed.

## What to run, given the measurements

- Keep 2,048-token chunks, 10.8G cap and 128K context. Nothing tested beat it.
- Do not chase a 4,096-row chunk. The 1,024 -> 2,048 gain came from expert
  de-duplication (a 1,024-row chunk touches about 450 of the 512 experts, a
  2,048-row chunk touches all 512). Past 2,048 the dedup is saturated and
  attention and MoE cost scale linearly with rows, so the upside is small while
  the 5 s Metal window risk is real.
- Shrink the prompt. Attention per row is capped at 512 blocks of 4 tokens, but
  the QSA indexer scores a row against every block of the history: 3.7 ms per
  layer at 8K history, 34.1 ms per layer at 128K. That scan is the only part of
  attention that grows with the conversation, and trimming the prompt cuts it
  directly.
- Serve a smaller context when a session does not need 128K. It does not speed
  up a cold 8K prompt (the history is 8K either way), but it bounds the indexer
  scan and the KV footprint.
- Keep the draft. There is no supported way to run option 21 without it, and the
  decode it gives (17 tok/s, 95.8% acceptance) is worth more than the prefill it
  costs.
