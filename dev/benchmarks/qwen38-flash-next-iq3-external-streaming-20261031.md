# Flash-Next IQ3_XXS external-drive assessment - 2026-10-31

On this Apple M5 with 8 GPU cores and 16 GiB unified memory, the external drive has enough capacity for the model. Its sampled read performance suggests that Flash-Next expert streaming would be impractical for interactive coding. RAM fit remains unverified: only model headers and drive reads were checked, not model startup or inference.

## Model sizing and compatibility

Model: `unsloth/Qwen3.8-Flash-Next-GGUF:UD-IQ3_XXS`, revision `766911a6b7369840a91dbcd95f9f997acaab6cd6`. All three shards are required; the first is metadata only. Combined download size is 81,961,823,936 bytes (81.96 GB / 76.33 GiB).

Headers read through the installer's range reader passed `install.gguf.require_loadable`. Their stored tensor spans divide as follows; spans include alignment padding and do not establish native memory allocation:

| Target component | Stored bytes | GiB |
|---|---:|---:|
| Remaining target weights | 4,522,949,120 | 4.21 |
| PLE n-gram table | 28,800,138,240 | 26.82 |
| Routed experts | 48,627,712,000 | 45.29 |

Splash supports SSD-backed expert and PLE streaming. The remaining target weights are before the draft, KV, expert and PLE caches, workspace, and driver overhead. Successful format screening does not prove that these runtime floors fit 16 GiB, or the 8 GiB engine cap used for the current Qwen3.6 benchmark.

Sources: [pinned quant files](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/766911a6b7369840a91dbcd95f9f997acaab6cd6/UD-IQ3_XXS), [PLE and expert streaming](../../docs/server.md#ple-table-streaming).

## Measured external-drive sample

`/Volumes/Untitled`: 500.09 GB ExFAT volume, 458.18 GB free when inspected. JMicron USB-to-ATA/ATAPI bridge behind a hub, negotiated at 5 Gb/s. macOS did not identify whether the underlying media is solid state; the observed sample is HDD-like.

The test opened an existing 718,998,097-byte file read-only and set `F_NOCACHE`. It read two 128 MiB sequential regions in 4 MiB blocks, then 128 randomly positioned 512 KiB blocks through four workers. Random seed was 42, with offsets aligned to 16 KiB. No file was created or modified on the external drive. The tested filename and contents are not included in the record.

| Read pattern | Measured rate | Additional observation |
|---|---:|---|
| Sequential region 1 | 78.78 MB/s | 128 MiB in 1.704s |
| Sequential region 2 | 85.63 MB/s | 128 MiB in 1.567s |
| Random 512 KiB, four workers | 35.89 MB/s | 64 MiB in 1.870s; median read latency 58.63ms |

These are small samples from one existing file. They do not establish sustained model-sized performance, whole-device speed, media type, or the latency of the PLE table's much smaller row reads.

## Performance estimates, not model benchmarks

Assuming text-only serving, one request, and successful startup with expert and PLE streaming:

| Metric | Low-confidence estimate |
|---|---:|
| Cold prompt processing | 3-12 tok/s |
| Generation | 0.03-0.2 tok/s |
| Time per generated token | About 5-35 seconds |
| Cold 32K prompt | About 45 minutes-3 hours |

The estimate reflects I/O demand, not a measured scaling factor. A large prefill group that reads most of the roughly 49 GB of experts takes about ten minutes of sequential reads at 80 MB/s before PLE and compute costs. Splash can group up to 8,192 prompt rows to share those reads. For generation, selecting 10 of 512 routed experts across the model corresponds to roughly 0.95 GB of expert weights per base token before cache reuse; actual traffic depends on routing, read-ahead, speculative verification, and accepted draft tokens. A small RAM cache and this drive's sampled random-read rate can therefore produce seconds to tens of seconds per output token. PLE row reads can add latency.

These ranges are extrapolations and may be missed in either direction. Cached prefixes reduce prompt work but do not eliminate generation's expert reads. The earlier internal-SSD planning estimate of 100-400 prompt tok/s and 5-15 generation tok/s does not apply to this external volume. A different external SSD requires its own assessment.

Exact sizing, drive sample, method parameters, estimates, and validation limits are preserved in [the companion JSON](qwen38-flash-next-iq3-external-streaming-20261031.json). The model was not installed, loaded, or benchmarked, and the existing server was not restarted for this assessment.
