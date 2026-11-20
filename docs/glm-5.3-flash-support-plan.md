# Native GLM-5.3-Flash support in Splash on Apple Silicon

## Objective and first decision

Serve option 24's existing GLM-5.3-Flash UD-IQ2_XXS checkpoint through Splash on the 16 GiB M5. The user-visible goal is a shorter wait for the first answer token in Pi and OpenCode. Measure output generation separately. The first engineering milestone is a text-only, single-request run that processes a fixed 32-token prompt, produces one correct greedy token, and reports peak memory. That small input is a correctness fixture. The initial performance comparison should use the better observed llama.cpp setting of 128 logical batch / 64 physical microbatch.

Develop the native route under an experimental model root and on a separate port. Keep the llama.cpp route available as the reference and fallback. Promote the native route to option 24 only after it passes correctness, memory, and real-client performance checks. Text, single-slot inference, and the installed quantization define the initial scope. Vision, native multi-token prediction (MTP), additional quants, and multi-slot scheduling can ship independently.

## Evidence and constraints

Planning baseline is Splash commit `07036397`, with the current working tree as inspected, and the local Unsloth llama.cpp reference at `722adcd`. The model revision is `a38483c8cd5df544f53d70fb281afe97369d5ab6`. The four existing GGUF shards total 101,844,951,904 bytes. A header-only inventory gives these **tensor payload** sizes, excluding file metadata and alignment.

| Tensor group | Bytes | Implementation consequence |
|---|---:|---|
| Main-model routed expert matrices | 92,541,026,304 | Map shard offsets, stage selected expert rows and cap their Metal allocations. |
| Other main-model weights, including shared experts | 6,506,409,208 | Calculate exact resident and transient costs for the selected representation. |
| Auxiliary block 45 | 2,787,995,776 | Classify separately as NextN/MTP. The text target executes blocks 0 through 44. |

The payload spans F32, Q8_0, Q6_K, Q5_K, Q4_K, Q3_K, Q2_K, IQ4_XS, IQ3_XXS, IQ2_S, and IQ2_XXS. A format appearing in the GGUF reader does not establish that an embedding, projection, or streamed expert kernel accepts it. Build the support matrix by tensor role. The existing native-format table and Metal decoding code are good starting points. [GGUF format table](../runtime/model/GgufFile.hpp) · [Metal quantization formats](../runtime/metal/kernels/common/quant_formats.h)

The target has width 4,096 and 45 layers. Its 34 KDA linear-attention layers alternate with 11 indexed sparse-attention layers according to the model's layer list. The first three feed-forward layers are dense. The remaining 42 select eight of 288 routed experts and add one shared expert. The residual path uses four hyper-connection streams and 20 Sinkhorn iterations. Read these parameters from the decoded model metadata and check them against the supported configuration. [Published model configuration](https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/config.json) · [Pinned llama.cpp forward pass](https://github.com/unslothai/llama.cpp/blob/722adcdff6341cd4befa07ca49486db17d8f6f39/src/models/glm5-next.cpp)

## Implementation sequence

### Checkpoint inspection implemented

The native `glm-flash-checkpoint` command opens the existing split GGUF in place. It validates the Flash architecture, text block schedule, router and attention parameters, and expected shapes and quant types for each text tensor. Its JSON includes absolute byte offsets within each shard and the contiguous byte stride of each routed expert. Tensor inspection uses the shared GGUF reader before Metal allocation. [Checkpoint reader](../runtime/model/Glm5FlashCheckpoint.cpp)

```sh
make -j 3 BUILD=build/glm5-checkpoint build/glm5-checkpoint/splash
build/glm5-checkpoint/splash glm-flash-checkpoint /path/to/UD-IQ2_XXS > glm-flash-manifest.json
```

On the installed revision, all four shards and 1,412 entries agreed with the pinned llama.cpp checkout's Python GGUF reader, including shapes, formats, offsets and byte lengths. Missing shards, an altered architecture identifier, and truncated tensor data were rejected. This validates the source layout.

### 1. Establish the reference and inventory before changing dispatch

Capture the exact target revision, four shard identities, llama.cpp build and arguments, template, BOS/EOS handling, and generation settings. Use token IDs first so template differences cannot mask graph errors. Save a short ordinary prompt, a repeated-token case, and a case that crosses a chunk boundary. Record logits for selected positions, top candidate IDs and margins, and a short greedy continuation. Use the reference graph's named intermediates to capture one KDA block, the first sparse-attention/MoE block, and the final residual reduction. Run reference captures separately from Splash on this host.

The initial reference fixture now records 32 exact input IDs, greedy token 671, and the top five log probabilities from the pinned llama.cpp CPU build at 128/64 with zero prompt reuse. The margin between the top two candidates is 0.182 log-probability units. [Next-token reference fixture](../dev/tests/fixtures/glm-flash-next-token.json)

A separate instrumented CPU run now captures the replicated input streams, block 0 KDA and residual outputs, block 3 MLA latents and residual output, and final logits. On the same input IDs, its top two token IDs are 470 and 671, in the opposite order from the server fixture. The cause of that difference is unverified. Use the instrumented run for layer comparisons and retain the original serving fixture for the end-to-end comparison.

Produce a tensor manifest grouped by shard, layer, role, dimensions, quant type, byte range, and expert stride. Verify ranges against shard lengths, and distinguish auxiliary tensors explicitly. Reuse the cached snapshot through the installer's local-source conventions. Missing shards, inconsistent shard identity, unsupported role/format pairs, and truncated tensor ranges should produce actionable errors before Metal allocation.

**Exit evidence.** A reproducible reference fixture and inventory; every tensor has a consumer or a documented auxiliary role. These are also the inputs for the memory estimate.

### 2. Describe a GLM target and separate its lifecycle from the draft

Add a GLM target layout to the target variant. Update family detection, target-source validation, the GGUF loader, weight dispatch, and geometry planning. Follow the current split between model inspection and model loading. Derive recurrent/sparse layer types from the authoritative configuration. Validate the GGUF architecture `glm5-next`, expert counts, dimensions, layer schedule, and tensor names. Thread GLM through variant visitors that currently assume Qwen target geometry. [Target variant](../runtime/model/ModelDescriptor.hpp) · [Descriptor inspection](../runtime/model/ModelDescriptor.mm) · [Target factory](../runtime/model/ModelFactory.cpp) · [Installer families](../install/families.py)

There is a concrete dependency here. Family inspection can describe a source without its draft, but opening an assembled root currently requires a draft directory, and the factory loads draft weights. Introduce an explicit target-only mode for the experimental GLM path. Carry that choice through assembly, model validity, memory planning, and generation. Skip draft loading, draft context capture, and verification in that mode. Keep a missing draft an error for profiles explicitly requesting speculation. Exercise both paths with an existing supported family to catch changes in default behavior.

**Exit evidence.** An inspection command identifies all four shards as one GLM text target, reports the layer and format inventory and planned allocations, and can open a target-only experimental assembly. Existing family descriptors still load with their established defaults.

### 3. Implement the target forward pass in reference order

| Component | Native implementation and focused comparison |
|---|---|
| Input, residual streams, output | Load embeddings, replicate into four streams, implement attention and FFN pre/post hyper-connections, Sinkhorn normalization, final stream reduction, RMS norm, and output projection. Compare normalized mixing matrices, stream outputs and final logits. Match reference precision and epsilon before fusing operations. |
| KDA layers | Implement Q/K/V short convolutions and their histories, the bounded decay gate, beta, Q/K normalization, recurrent update and gated output projection. Preserve each layer's matrix state and token position across calls. Compare the output **and the next state** after individual tokens and a chunk. |
| Indexed sparse attention | Implement the query and latent projections, K-only latent cache, index projections, compressed key pooling, causal candidate selection including the tail, and attention over the selected positions. Preserve the distinction between positional treatment in the indexer and the NoPE MLA attention path. Compare selected indices, latent cache, and attention output below and above the 2,048-token index selection limit. |
| Feed-forward and routing | Implement the first three dense SiLU-gated FFNs. For MoE blocks, reproduce the reference's sigmoid router, bias for expert selection, normalization and scaling of mixture weights, and additive shared expert. The GGUF records a SwiGLU clamp of 10 for routed and shared experts. Match the clamp in the respective reference graphs. Compare selected IDs, associated weights, shared output and final sum. Specify tie handling in fixtures. |
| Execution and ownership | Reuse Metal matmul, norm, quant and scheduling primitives where shapes and math agree. Add small GLM-specific ops for missing semantics. Give each state buffer one owner and define its mutation point so a cancelled command cannot publish a partially advanced state. |

Start with per-operation fixtures and a small resident slice for routing parity. Connect the streamed weight path in step 4 before trying a full 45-layer run on this machine. On a numerical mismatch, compare at the first divergent layer and operation. Establish tolerances per tensor using the same quantized reference and measured backend variance, and freeze them before tuning. Require matching greedy IDs on fixed, well-separated reference logits. Inspect logit margins for near ties and retain those cases in the error report. [Reference KDA, sparse attention and hyper-connections](https://github.com/unslothai/llama.cpp/blob/722adcdff6341cd4befa07ca49486db17d8f6f39/src/models/glm5-next.cpp)

**Implemented GLM hyper-connections.** The Metal operators take the checkpoint's Q8_0 projection, FP32 scales and biases, and four FP32 residual streams. They compute flattened RMS normalization, pre and post gates, the 20-iteration Sinkhorn matrix, the weighted branch input and the in-place residual update. Each operation uses Flash's 4,096-wide streams. The focused test compares the coefficients and activations against a double-precision CPU oracle for single-token and 32-token batches. Wiring the operators into GLM attention and FFN execution and comparing real layer outputs with llama.cpp remain separate steps. [Operator interface](../runtime/ops/HyperConnection.hpp) · [Metal kernels](../runtime/metal/kernels/shared/hyper_connection.metal) · [Oracle test](../dev/tests/engine/glm_flash_hyper_test.mm)

**Implemented the GLM KDA state update.** The Metal operator consumes projected Q, K, V and gate inputs, updates the three causal convolution histories and the per-key-channel recurrent matrix, then applies the gated output norm. A CPU oracle checks the output and both states at the full GLM dimensions for a 32-token chunk and for the same prompt split into 1, 7 and 24 tokens. Target integration still needs to bind the checkpoint projections, allocate the state as part of the runtime, and implement state rollback. [KDA operator](../runtime/ops/GlmFlashKda.hpp) · [KDA oracle test](../dev/tests/engine/glm_flash_kda_test.mm)

**Implemented the GLM MoE routing variant.** Splash ranks experts by sigmoid logits plus the checkpoint's selection bias, then uses the selected experts' unbiased scores with the reference normalization floor and 2.5 scale. One shared expert has weight one. The stream planner carries the bias to its prediction pass, and the grouped expert kernels apply the GLM clamp before SwiGLU. The focused GPU checks cover high-numbered experts, ties, the normalization floor, and clamped activations for routed and shared Q8_0 experts in one-row and 32-row cases. Full layer parity with the checkpoint weights remains an integration check. [MoE operator](../runtime/ops/MoE.cpp) · [Routing oracle test](../dev/tests/engine/glm_flash_moe_test.mm)

**Implemented indexed sparse attention for contiguous sequences up to 8,192 tokens.** The Metal path caches normalized index keys and gates, uses the position bias to compress each complete four-token pool, and ranks visible pools using weighted, rectified query-key scores. Up to 512 pools and the incomplete causal tail feed latent attention. The test crosses the selection threshold, exercises a tie, and checks the cache and output against a CPU oracle. The block loader binds the model's rank-reduced Q/KV projections and per-head Q8_0 projections, and connects attention to the streamed MoE. On block 3, the 32-token residual update has 2.15% relative RMS error against the instrumented llama.cpp output and 0.0099% against the same Splash input split into 1/7/24 tokens. [Sparse attention operator](../runtime/ops/GlmFlashSparseAttention.hpp) · [Oracle test](../dev/tests/engine/glm_flash_dsa_test.mm) · [Integrated block](../runtime/model/GlmFlashSparseLayer.cpp)

**Integrated the first dense blocks.** The dense-block loader binds the GGUF hyper-connections, KDA projections, and clamped FFN. On block 0, the 32-token residual update has 2.23% relative RMS error against the instrumented llama.cpp reference. Splash's output is bitwise identical for the same inputs in one chunk and in 1/7/24-token chunks. The projection path uses BF16 activations and FP32 accumulators. This result covers one full block with real weights. [Dense block](../runtime/model/GlmFlashRecurrentLayer.cpp) · [Real-weight comparison](../dev/tests/engine/glm_flash_dense_test.mm)

### 4. Stream experts and prove the first milestone on 16 GiB

Bind gate/up/down expert slices to the existing expert store using their actual source offsets and quant block alignment. Reuse one cached copy per layer/expert and the existing completion and eviction rules. Verify selected expert outputs against direct reads of the same slices. Begin with demand reads. Measure distinct experts per layer per chunk, cache hits, bytes read, and time waiting for I/O before adding read-ahead. A larger prefill chunk may amortize an expert load across multiple tokens, while increasing the number of distinct experts and required staging space. [Expert store](../runtime/model/ExpertStore.hpp) · [GGUF preparation](../runtime/model/GgufPreparation.cpp)

**Real checkpoint streaming verified.** The planner binds all 42 MoE blocks' routed sources from the four installed shards. The store's calculated minimum is 5,360,493,200 bytes, including its arena and staging. In a single-token block 3 smoke, Splash loaded 8 experts and read 60,686,336 source bytes. The next identical run reused the weights and produced bitwise-identical output. This memory number is for the store alone. [Expert source adapter](../runtime/model/GlmFlashExperts.cpp) · [Real-weight smoke](../dev/tests/engine/glm_flash_experts_test.mm)

Use a component budget: resident target weights after repacking + recurrent and index state + latent cache + activation/work buffers + Metal staging + expert cache + any optional draft. Include peak allocations during load and leave headroom for macOS and the client. For scale, one FP32 KDA matrix state per recurrent layer at 64 heads × 128 × 128 × 34 layers totals **136 MiB per sequence** before convolution histories, snapshots, and alignment. If eight experts miss in every MoE layer, their average raw weight payload is roughly **2.57 GB per decoded token** (92.54 GB × 8 / 288), assuming equal-size experts within each layer. This is a traffic scenario, not measured disk throughput. It explains why a correctness pass alone cannot predict speed.

**Exit evidence.** Run the 32-token fixture through all layers and generate one token on the Mac. Save token IDs, reference comparison, allocated bytes by component, peak footprint, SSD reads, expert-cache counters, system swap delta and thermal state. If admission fails or paging dominates, identify the largest allocation or I/O source before increasing context or enabling speculation.

**First full forward pass verified.** The offline Metal runner opens the exact checkpoint, embeds the 32 fixture IDs, runs all 45 text layers, and projects the last row to 154,880 logits. Splash picked **671**, matching the earlier llama.cpp server's greedy token. The instrumented C API trace ranked token 470 first and 671 second. Splash's three highest candidates were 671, 470, and 10610. Peak process footprint was 6,083,120,056 bytes, and the system swapout counter did not increase. The expert store reported 39,286,112,256 bytes read from the source files. These may include OS cache hits. The runner releases each finished layer after its forward pass and used Metal shader validation. Its 14.90-second layer-and-head wall time is an offline observation. A persistent serving process needs its own admission and performance checks. [Offline forward runner](../dev/tests/engine/glm_flash_forward_test.mm)

```sh
make -j 3 BUILD=build/glm5-checkpoint build/glm5-checkpoint/engine-tests/glm-flash-forward
jq -r '.prompt_token_ids[]' dev/tests/fixtures/glm-flash-next-token.json |
  xargs build/glm5-checkpoint/engine-tests/glm-flash-forward \
  build/glm5-checkpoint/splash.metallib "$GLM_FLASH_SHARDS" /tmp/glm-flash-logits.f32
```

### 5. Make state, the API, and client behavior correct

Start with a single slot and a cold state per request. A GLM snapshot must restore recurrent matrices, convolution histories, latent cache, pooled index keys, partially filled pools, and logical positions consistently. Version the layout and include target revision, cache format, and execution mode in cache identity. Enable prefix reuse and persistence only after replay agrees with full recomputation. Validate cancellation at a chunk boundary, a divergent suffix, process restart, and eviction. Check lengths around 4-token pool boundaries, 31/32/33 and 127/128/129, then beyond 2,048 tokens. [State cache](../runtime/engine/StateCache.cpp) · [KV cache](../runtime/engine/KvCache.cpp)

The native GLM worker serves one request through Splash's HTTP server. It retains each layer's recurrent and attention state across prefill chunks and single-token decode steps, then resets that state when the request ends. The worker loads transient layer weights from the local shards, with the expert arena, embedding, and output projection held in memory. Prefix reuse and persistence remain future work. [Sequence state](../runtime/model/GlmFlashSequence.cpp) · [Native worker](../runtime/engine/GlmFlashNative.mm)

Use the same GLM tokenizer and chat template as the baseline, including stop IDs, reasoning settings, streamed reasoning/content fields, and tool-call formatting. Verify plain text first, then a Pi or OpenCode tool call and tool-result round trip. Serve the candidate on a separate loopback port with the same model alias. Target the existing client contract of 8,192 context and 2,048 max output, subject to measured admission. Advertise only capabilities exercised by this implementation.

**Initial serving smoke with 32-token chunks.** The 32-token reference prompt selected token 671, matching the llama.cpp server. Option 24 completed a 64-token prompt across two chunks, generated two tokens, and returned `4` in a constrained chat request. A request following a client disconnect completed with zero worker restarts. The API alias `glm-5.3-flash-ud-iq2-xxs` serves 8,192 context tokens and up to 2,048 output tokens per request. A real Pi or OpenCode tool-call transcript and cached replay remain validation milestones.

### 6. Measure performance and decide whether to promote

1. Build and identify the candidate before loading it. Keep the reference binary and production caches separate. Run one inference workload at a time. Reuse the repository's native CPU, Metal, real-HTTP and performance entry points where applicable. Add GLM fixtures to the existing suites. [Validation guide](validate.md) · [Development targets](../dev/Makefile)
2. Start with one short request on each engine. Verify the exact model, tokenized input, output correctness, cache state, context and effective chunk sizes. A failed smoke check blocks longer trials.
3. Compare target-only execution at 128/64 on llama.cpp and the closest supported Splash prefill geometry. Record logical chunk and physical dispatch separately. Test 32, 64 and 128 on Splash with the same prompt tokens, expert memory budget and decoding settings. Existing llama.cpp timings favor 128/64 but do not establish a Splash optimum.
4. Use short and representative Pi prompts, including the roughly 4K-token workload that exposed the delay. Begin with a small output cap to measure time to first token; use a longer fixed decode segment to measure steady output rate. Alternate engine order and repeat viable configurations. Distinguish cold model/OS pages, warm weights with a fresh prefix, and cached-prefix replay.
5. Save raw observations and one table with prompt tokens, cached tokens, prefill tokens/s, first streamed token and first visible answer latency, decode tokens/s, output correctness, expert hit rate/bytes read, peak memory, swap delta and thermals. Review repetitions and variability before claiming a gain.

**Launcher status.** Local option 24 defaults to the experimental Splash worker with 2,048-token prefill chunks. `GLM53_FLASH_ENGINE=llama.cpp` selects the reference profile. The initial 64-token serving smoke used 32-token chunks and measured 12.9 seconds to the first token and about 0.46 decode tokens per second. A matched performance sweep remains pending.

The 128-token build matched the 32-token build's greedy two-token completion for the same 129-token prompt. The 128-token run crossed a chunk boundary and took 14.8 seconds to the first token at 8.70 prefill tokens per second. The system swap-out counter stayed flat during the run. The KDA and MoE oracles also passed with 128 rows under Metal shader validation.

On the 16 GB M5, a 513-token uncached prompt crossed the new 512-token boundary and produced the same greedy two-token completion as the 128-token build. In one run per build, prefill took 49.81 seconds with 128-token chunks (10.30 tok/s) and 19.64 seconds with 512-token chunks (26.12 tok/s). Each request had one timed decode step.

On the same M5, a 1,025-token uncached prompt produced the same two-token greedy completion with 512- and 1,024-token chunks. One request per build measured 29.47 and 37.84 prefill tokens/s, respectively, with first-token latencies of 34.78 and 27.09 seconds.

#### M5 Pro Mac mini with 64 GB

These planning estimates use a single 3,820-token Pi prompt, zero cached prompt tokens, the UD-IQ2_XXS checkpoint and 128-token prefill chunks. Only the M5 row was measured. Its prefill took 450.69 seconds, and 145 decode steps took 334.98 seconds. A second request on that machine processed 3,776 tokens in 444.98 seconds and completed 33 decode steps in 75.83 seconds.

| Host and weight-cache configuration | Routed expert arena | Prefill tok/s | Decode tok/s | Approximate time to first token |
|---|---:|---:|---:|---:|
| M5, 16 GB, measured | 2.64 GiB | 8.48 | 0.43 | 7 min 31 s |
| M5 Pro, 64 GB, existing worker | 2.64 GiB | 11 | 0.56 | 5 min 47 s |
| M5 Pro, fixed layer weights resident, 25% of routed read bytes served from RAM | 32 GiB | 14 | 1.2 | 4 min 33 s |
| M5 Pro, fixed layer weights resident, 50% of routed read bytes served from RAM | 32 GiB | 17 | 1.4 | 3 min 45 s |

The existing GLM worker requests the minimum expert-store allocation on either host. The larger-cache scenarios require changes to retain prepared fixed weights and keep routed experts across layer formats. The checkpoint has 5.39 GiB of fixed block weights on disk and 86.19 GiB of routed weights. Decode selects eight of each layer's 288 experts, corresponding to 2.39 GiB of routed weights per step before reuse. Prepared weights, staging, context state and macOS also need memory.

The projections assume a 1.3× hardware speedup with unchanged code. For the warm-cache scenarios, they assume loading and preparation account for 65% of prefill time and 70% of decode time. Fixed weights account for an estimated 7% of those costs in prefill and 69% in decode. The model eliminates the fixed share and applies the indicated reuse fraction to the remaining routed share. Times to first token use the rounded prompt rates. Actual cache residency, hit rates and throughput on the 64 GB mini remain unmeasured.

### 7. Add Flash-specific DFlash2 after target parity

Use `incoai/GLM-5.3-Flash-DFlash2` with option 24. At assembly time check the base-model family, feature width, ordered tap IDs, vocabulary and mask token ID against the supported pair. Report a model-pair mismatch if given `incoai/GLM-5.3-DFlash2`: that draft needs width 6,144 and requests layers through 75; the Flash target has width 4,096 and 45 layers. Pin both revisions in the fixture manifest and include the draft identity in speculative cache keys. [Flash draft config](https://huggingface.co/incoai/GLM-5.3-Flash-DFlash2/blob/main/config.json) · [Full-model draft config](https://huggingface.co/incoai/GLM-5.3-DFlash2/blob/main/config.json)

**Capture the inputs the draft was trained on.** SGLang's GLM implementation collects the completed outputs of zero-based layers 5, 14, 24, 33 and 42. Its loop takes the samples just before layers 6, 15, 25, 34 and 43. At each tap it combines the hidden and residual contributions, then takes the arithmetic mean across the four hyper-connection streams. This produces one 4,096-element vector per token per tap. In Splash, sample the equivalent completed block output; if the residual has already been incorporated, averaging the four streams is sufficient. Keep the five vectors in the draft's declared order. A fixture with distinct values per layer and stream should detect an off-by-one layer, swapped taps, a wrong reduction axis or a double-added residual. [Pinned reference implementation](https://github.com/sgl-project/sglang/blob/2d4b6acea720f5eb5a2b2c269f1cc9dcbc8b10c0/python/sglang/srt/models/glm5_next.py) · [Upstream capture tests](https://github.com/sgl-project/sglang/blob/2d4b6acea720f5eb5a2b2c269f1cc9dcbc8b10c0/test/registered/unit/models/test_glm5_next_dflash_capture.py)

| Deliverable | Implementation and evidence for review |
|---|---|
| Standalone draft parity | Feed identical captured vectors and token IDs to the Flash reference and Splash. The draft's 32 query heads, eight KV heads, head width 128, selector rank 256 and 16 candidates per position match existing Metal constants. Exercise those kernels before adding new ones. Compare the feature projection, draft logits, candidate IDs and final selected path. Record numeric tolerances and near ties. [Draft attention](../runtime/metal/abi/DraftAttention.h) · [Selector geometry](../runtime/metal/abi/ExecutionGeometry.h) · [Draft implementation](../runtime/model/DFlashDraft.cpp) |
| Verification and rollback | The block size of eight gives seven proposed tokens per verification step. Exercise full acceptance, rejection at the first and middle proposals, and EOS inside the block. After each case, compare the next target logits with a target-only replay of the committed prefix. Include recurrent matrices, convolution histories, latent and pooled index state, positions and draft feature history in the check. Verify greedy continuations and sampled behavior separately. |
| Memory on the 16 GiB host | Measure the draft weights in their loaded representation, context buffers, rollback snapshots and expert-cache capacity. At BF16 the five raw tap vectors alone cost 40 KiB per token, or 320 MiB if retained for all 8,192 tokens. These are storage calculations. Inspect the existing incremental draft context path and measure actual peak residency, including any overlap between raw and projected features. |
| Paired serving trial | On the same Splash build compare target-only and Flash draft on/off at identical prompt length, cache state, sampling settings and total memory allowance. Use a short coding prompt and the representative Pi prompt. Record prefill tokens/s, time to first visible answer, accepted tokens per verification, output tokens/s, total wall time, expert SSD traffic, peak memory and swap delta. Repeat viable trials in alternating order. |

**Decision.** Keep target-only as the baseline through the first native release. Offer speculation as opt-in when it preserves correctness, fits on this Mac, and repeatedly reduces wall time on a representative generation workload. A decode gain alongside unchanged prompt latency is a legitimate decode result; report the two measurements separately. Use the local paired results to decide the default. Inco's published full-model GPU benchmarks cannot establish a Flash speedup on this hardware. [Flash checkpoint evaluation status](https://huggingface.co/incoai/GLM-5.3-Flash-DFlash2#evaluation)

## Suggested review boundaries

Land inventory and reference fixtures first, followed by descriptor/target-only lifecycle, GLM operator and state parity, streamed full-model execution, server/client support, and finally optional draft support. Each change should carry its smallest reproducer and the output demonstrating its exit condition. The first performance decision comes after the streamed target-only milestone; loader registration or a successful HTTP health check alone cannot answer whether Splash improves option 24.
