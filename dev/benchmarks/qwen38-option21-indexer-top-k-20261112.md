# Option 21 with a 4096-token indexer

Qwen3.8-Flash-Next GSQ-RCO Q2_0 with the local BF16 DFlash2 draft on the 16 GiB
Apple M5. `runtime/model/Qwen4Exp.hpp` now sets `indexerTopBlocks` to 1024
blocks of 4 tokens, so a query row attends the 4096 tokens its indexer scores
highest instead of the 2048 it attended before. The family's GGUFs declare
`qwen4exp.attention.indexer.top_k`; the engine holds the file to the layout it
builds (`GgufImage.cpp requireMetadata`), so the metadata and the layout move
together.

## What the memory plan gives up

Live `/status` of a server started with `--max-context 131072`,
`--max-memory 11596411699`, `--max-cache-disk 3221225472`, `--ple-memory
67108864` and 2,048-token prefill chunks. Nothing exceeds the 16 GiB host, and
`deficit_bytes` is 0 either way.

| | top_k 2048 | top_k 4096 |
|---|---:|---:|
| Indexer hot block cache floor | 408,944,640 | 817,889,280 |
| Expert store cap | 3,380,609,808 | 2,941,043,472 |
| Expert slots resident | 2,104 | 1,786 |
| KV capacity pages | 3,840 | 4,864 |
| KV capacity | 1,627,914,240 | 2,062,024,704 |
| Resident context bound | 122,873 tokens | 155,641 tokens |
| Metal peak observed | 9,908,338,688 | 9,476,767,744 |
| Governor headroom | 832,679,831 | 2,207,707,031 |

The 390 MiB the wider indexer needs comes out of the expert arena, not out of
KV: KV capacity actually grows because the fixed runtime shrinks. The hot block
cache sits exactly at its floor (`hot_target_bytes == hot_floor_bytes`), so
nothing above the floor stays resident and the rest spills to the SSD cache.

## Serving results from the run log

`~/.local/state/llama-server/qwen3.8-flash-next-q2-0-dflash2-bf16-splash-20261112-165557.log`,
14 requests of a real OpenCode session, tool-calls included. PP is prompt
processing, TPS is decode.

| # | Input | Cached | Prefill | PP tok/s | TTFT | Decode | TPS | tok/cycle | Wall |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 63,491 | 62,112 | 1,379 / 6.07s | 227.1 | 6.2s | 215 / 15.64s | 13.7 | 3.4 | 21.9s |
| 2 | 63,834 | 63,456 | 378 / 4.04s | 93.7 | 4.0s | 213 / 16.76s | 12.7 | 3.3 | 20.8s |
| 3 | 64,880 | 63,808 | 1,072 / 6.02s | 178.2 | 6.0s | 96 / 7.76s | 12.4 | 3.2 | 13.8s |
| 4 | 65,912 | 64,864 | 1,048 / 5.42s | 193.4 | 5.4s | 350 / 27.64s | 12.7 | 3.1 | 33.1s |
| 5 | 67,854 | 65,888 | 1,966 / 7.48s | 262.9 | 7.5s | 268 / 21.37s | 12.5 | 3.0 | 28.9s |
| 6 | 68,928 | 67,840 | 1,088 / 5.90s | 184.4 | 5.9s | 349 / 26.89s | 13.0 | 3.4 | 32.8s |
| 7 | 71,003 | 68,896 | 2,107 / 9.88s | 213.2 | 9.9s | 865 / 83.24s | 10.4 | 2.6 | 93.1s |
| 8 | 71,965 | 70,976 | 989 / 7.76s | 127.5 | 7.8s | 266 / 19.74s | 13.5 | 4.7 | 27.5s |
| 9 | 73,193 | 71,936 | 1,257 / 8.91s | 141.0 | 8.9s | 836 / 86.37s | 9.7 | 2.8 | 95.3s |
| 10 | 74,155 | 73,184 | 971 / 8.10s | 119.9 | 8.1s | 157 / 14.66s | 10.7 | 4.2 | 22.8s |
| 11 | 75,312 | 74,144 | 1,168 / 7.81s | 149.6 | 7.8s | 509 / 48.23s | 10.6 | 2.8 | 56.0s |
| 12 | 76,346 | 75,296 | 1,050 / 6.94s | 151.2 | 6.9s | 752 / 59.08s | 12.7 | 3.5 | 66.0s |
| 13 | 77,166 | 76,320 | 846 / 6.11s | 138.4 | 6.1s | 729 / 55.07s | 13.2 | 5.1 | 61.2s |
| 14 | 78,381 | 77,152 | 1,229 / 8.80s | 139.7 | 8.8s | 154 / 13.05s | 11.8 | 3.5 | 21.9s |
| run | | | 12,795 tok | 179.5 | 7.0s | 4,831 tok | 12.2 | | 47.8s |

Runs are weighted by tokens (PP is prefill tokens over prefill seconds, TPS is
output tokens over decode seconds), so a run of long generations is not the
same thing as a run of short ones.

## Option 21 runs on this machine today

| Run start | Indexer hot floor | Requests | Max context | PP tok/s | TPS | Mean TTFT | Wall/request |
|---|---:|---:|---:|---:|---:|---:|---:|
| 00:16 | 390 MiB (2048) | 36 | 34,742 | 195.3 | 11.2 | 6.9s | 43.7s |
| 10:24 | 390 MiB (2048) | 27 | 62,588 | 218.5 | 11.7 | 10.7s | 48.1s |
| 10:54 | 390 MiB (2048) | 76 | 110,588 | 192.5 | 10.4 | 16.2s | 80.0s |
| 12:37 | 390 MiB (2048) | 78 | 111,739 | 175.1 | 10.1 | 11.6s | 77.7s |
| 14:23 | 780 MiB (4096) | 48 | 110,974 | 193.4 | 9.7 | 24.3s | 90.7s |
| 16:55 | 780 MiB (4096) | 14 | 78,381 | 179.5 | 12.2 | 7.0s | 47.8s |

Decode is not measurably sensitive to the wider indexer here: 11.2-11.7 tok/s
at 2048 and 9.7-12.2 tok/s at 4096, with the spread explained by context depth
and output length rather than by `top_k`. The cost shows up as residency, and
it is worst in the 14:23 run, which ran out to 110,974 tokens with 24.3s mean
TTFT while the 4096 run at 78,381 tokens needed 7.0s.

## Reading

4096 is affordable on a 16 GiB Mac, but only by handing 390 MiB of the expert
arena to the indexer: 2,104 resident expert slots become 1,786, and routed
experts stream from their files more often. On these agentic sessions that
trade-off did not pay back. Before adopting 4096 as the option 21 default, run
the context matrix of `qwen38-option21-context-results-20261112.md` against the
same binary at 512 and 1024 blocks, and check long prefills specifically, where
the doubled select and sparse-attention work is most likely to show.

## Reproducing the metadata

The upstream GGUFs still state 2048. Locally, `dev/tools/gguf_metadata.py` sets
one scalar key of a GGUF header in place, keeping the tensor data where the
header says it is:

```sh
python3 dev/tools/gguf_metadata.py \
  ~/.cache/huggingface/hub/models--ISTA-DASLab--Qwen3.8-Flash-Next-GSQ-RCO-GGUF/snapshots/ed59f92082b1e93c0e96d60a8b11aab089b52f09/Q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf \
  qwen4exp.attention.indexer.top_k 4096
```

A Hub blob is content-addressed, so editing it in place makes
`python3 -m install.models --model ...:Q2_0 verify --full` report a content
hash mismatch: the file no longer matches the digest the Hub publishes for it.
Quick verify, the one the launcher and the server use, still passes. The right
home for this change is the upstream file, not a local patch.
