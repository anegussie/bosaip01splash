# Option 21 prefill kernels: what a chunk actually costs (2026-11-11)

Kernel-level timings for the option 21 model (Qwen3.8-Flash-Next Q2_0, 48 layers,
12 attention layers every 4th layer, 24 query heads / 2 KV heads, head 256,
512 experts per layer, top 10, expert intermediate 640, hidden 2560), measured
on the M5 with the production kernels:

```
make -f Makefile build/engine-tests/attention-sweep build/engine-tests/gguf-moe-benchmark
build/engine-tests/attention-sweep build/splash.metallib --shapes fn --histories 8192,32768,131072 \
    --phases prefill --repeat 3 --qsa indexer
build/engine-tests/gguf-moe-benchmark build/splash.metallib flash-next 5
```

All figures are one layer of one 2,048-row prefill chunk, median of 3 fused graphs.

## Attention, per layer, per 2,048-row chunk

| Cached history | QSA sparse (what the model does) | of which the QSA indexer | dense (every key) |
|---|---|---|---|
| 8,192 | 54.5 ms | 3.7 ms | 122.5 ms |
| 16,384 | 66.3 ms | - | 228.5 ms |
| 32,768 | 76.4 ms | - | 454.1 ms |
| 65,536 | 88.8 ms | - | 876.8 ms |
| 131,072 | 111.5 ms | 34.1 ms | 1,718.0 ms |

Splitting the 131,072-token case: attention split 71.5 ms, indexer score 27.6,
indexer select 6.3, store 0.25, reduce 2.0. So at a full 128K window the QSA
indexer is 31% of the layer's attention time, and it grows linearly with the
window because "a row scores every block of the context".

FLOP efficiency: the sparse split runs at ~2.6 TFLOP/s, the dense loop at ~3.8,
the indexer at ~2.5. The MoE layer benchmark gives 36.2 ms per 2,048-row chunk
(~5.6 TFLOP/s). These are near the machine's practical ceiling; none of these
kernels is doing something obviously wasteful.

## Tile-shape experiments (both reverted)

| Change | 8,192 history, sparse | Verdict |
|---|---|---|
| tile rows 8 (production) | 54.5 ms | baseline |
| tile rows 4 | 57.8 ms | slower; more threadgroups and partial traffic outweigh the smaller block union |
| tile rows 16 | cannot compile | a block-list entry packs a block and one bit per tile row in 32 bits; 16 row bits leaves 16 bits for the block index, which the 1,048,576-token KV ceiling needs (`static_assert` in `runtime/metal/abi/PagedAttention.h`) |
| `SPLASH_SPARSE_SPLIT_BLOCKS` 48 -> 96 / 128 | 53.3 ms | no change; the output digest is identical |

Tile rows are already the best of the workable shapes: the parts rule
(`SPLASH_ATTENTION_TILE_PARTS`) gives a group of 12 two parts of 48 fused rows,
which is the 256-thread tile's 64-row limit at the fewest parts.

## What a chunk costs, all in

At a 128K-token cached history, one 2,048-token chunk:

- 12 attention layers: 12 x 111.5 ms = 1.34 s
- 48 MoE layers: 48 x 36 ms = 1.73 s
- 36 GDN layers' 2,560 x 16,512 input projections: ~1.5 s
- output projections, hyper-connections, draft prefill, stores: the rest

~5 s per chunk, which matches the measured 20-24 s TTFT for an 8,204-token
prompt (four chunks). Prefill is compute bound on the GPU, and the three big
terms are the experts, the GDN projections and the QSA attention.

## Consequences for prompt processing

1. Chunk size is already at the engine's ceiling (2,048 rows); the arena
   validation accepts only 128..2048 in multiples of 128.
2. Attention time is bounded by the QSA budget (512 blocks of 4 tokens per row),
   not by the context window: dense attention at 128K would be 15x the sparse
   cost. Nothing in the launcher changes it.
3. The indexer, not the attention loop, is the part that grows with a long
   conversation. Anything that reduces the window the indexer scores
   (a smaller served context, or a bounded indexer window in the engine) is
   where the remaining time is.
4. The Neural Engine FFN split does not apply here: it is for dense FFN models,
   and option 21's FFN is a streamed MoE (`ane_ffn=off` in `/status`).
