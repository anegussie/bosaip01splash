#pragma once

#include "metal/CommandGraph.hpp"
#include "ops/Weights.hpp"

namespace splash::ops {

struct InklingAttentionBuffers {
  metal::MetalBuffer query;         // FP32 [row][query head][head width], clipped and position-scaled
  metal::MetalBuffer relativeQuery; // FP32 [row][query head][16], clipped and position-scaled
  metal::MetalBuffer relativeTable; // FP32 [distance][16]
  metal::MetalBuffer sinks;         // FP32 [row][query head]
  metal::MetalBuffer gate;          // FP32 [row][query head][head width]
  metal::MetalBuffer keys, values;  // BF16 [key slot][KV head][head width]
  metal::MetalBuffer output;        // BF16 [row][query head][head width]
  metal::MetalBuffer scratch;       // FP32 split-attention partials for long global history
};

// A causal slice of the visit's history, held in `slots` slots addressed by
// key position modulo them. An older key outside the learned distance table
// receives zero relative bias. The learned sink contributes only to the
// softmax denominator, and the output carries the gate.
void addInklingAttention(metal::CommandGraph &graph, const InklingAttentionBuffers &buffers,
                         uint32_t firstQuery, uint32_t rows, bool sliding, uint32_t slots, bool tileQueries = true);
[[nodiscard]] uint64_t inklingAttentionScratchBytes(uint32_t rows, uint32_t end) noexcept;

// Widen a chunk's K and V rows into the visit's BF16 history at their slots.
void addInklingKeyValueStore(metal::CommandGraph &graph, const metal::MetalBuffer &keys,
                             const metal::MetalBuffer &values, metal::MetalBuffer historyKeys,
                             metal::MetalBuffer historyValues, uint32_t firstQuery, uint32_t rows, uint32_t slots);

// Clip each head of a projection to `threshold`, or RMS normalize it, then
// scale by the depth factor full-attention layers use.
void addInklingHeadClip(metal::CommandGraph &graph, metal::MetalBuffer values, const metal::MetalBuffer &weight,
                        uint32_t firstQuery, uint32_t rows, uint32_t heads, uint32_t width, float threshold,
                        bool scalePosition,
                        bool normalize, bool weighted);

// RMS normalize an FP32 row by `weight` and write it as BF16 for a projection.
void addInklingNorm(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weight,
                    metal::MetalBuffer output, uint32_t rows, uint32_t width);
void addInklingEmbedNorm(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weight,
                         metal::MetalBuffer output, uint32_t rows);

void addInklingAdd(metal::CommandGraph &graph, const metal::MetalBuffer &left, const metal::MetalBuffer &right,
                   metal::MetalBuffer output, uint32_t count);

// `order` lists `routes` route ids, grouped by expert. Gather packs each
// route's input row. The inverse permutation maps each logical route back
// to its grouped output. Reduction overwrites the weighted per-row sum.
void addInklingRouteGather(metal::CommandGraph &graph, const metal::MetalBuffer &input,
                           const metal::MetalBuffer &order, metal::MetalBuffer gathered, uint32_t routes,
                           uint32_t width);
void addInklingRouteAccumulate(metal::CommandGraph &graph, const metal::MetalBuffer &expert,
                               const metal::MetalBuffer &inverseOrder, const metal::MetalBuffer &weights,
                               metal::MetalBuffer output, uint32_t routes, uint32_t width);

void addInklingLogitCap(metal::CommandGraph &graph, metal::MetalBuffer logits, uint32_t count, float cap);

// The static taps and the three history samples are oldest first. Dynamic
// taps, when present, are ordered by increasing lag within each head.
// Input projections are replaced in place and the raw history is advanced.
void addInklingConvolution(metal::CommandGraph &graph, const metal::MetalBuffer &projection,
                           const metal::MetalBuffer &taps, const metal::MetalBuffer &history,
                           uint32_t rows, uint32_t channels,
                           const metal::MetalBuffer &dynamicTaps = {}, uint32_t heads = 0);

// Mix normalized residual states with learned query vectors. The output
// stores a separate [row][hidden] matrix for each query.
void addInklingResidualMix(metal::CommandGraph &graph, std::span<const metal::MetalBuffer> states,
                           const metal::MetalBuffer &queries, const metal::MetalBuffer &output,
                           uint32_t rows, uint32_t queryCount);

struct InklingControlWeights {
  QuantizedSegment down, gain, forget;
};

struct InklingControlBuffers {
  metal::MetalBuffer current, message, output; // FP32 [row][hidden]
  metal::MetalBuffer normalized;             // BF16 [row][2 * hidden]
  metal::MetalBuffer down;                   // BF16 [row][rank]
  metal::MetalBuffer gain, forget;           // FP32 [row][hidden]
};

void addInklingControl(metal::CommandGraph &graph, const InklingControlWeights &weights,
                       const InklingControlBuffers &buffers, uint32_t rows);

// Select top-eight experts by biased sigmoid scores and return normalized
// weights from their unbiased scores. Both outputs are [row][eight].
void addInklingRouting(metal::CommandGraph &graph, const metal::MetalBuffer &scores,
                       const metal::MetalBuffer &bias, const metal::MetalBuffer &indices,
                       const metal::MetalBuffer &weights, uint32_t rows);

// One selected physical expert, for a gathered batch of input activations.
// Packed gate/up rows use ordinary GGUF projection kernels. The early blocks
// use native 64-element NVFP4 down blocks, which cover 1152 inputs exactly.
struct InklingExpertWeights {
  QuantizedSegment gateUp;
  metal::MetalBuffer down;
  bool nvfp4Down;
  float gateUpScale = 1.0f;
  float downScale = 1.0f;
};

struct InklingExpertBuffers {
  metal::MetalBuffer input;       // BF16 [row][hidden]
  metal::MetalBuffer gateUp;      // FP32 [row][2 * intermediate]
  metal::MetalBuffer activated;   // BF16 [row][intermediate]
  metal::MetalBuffer output;      // FP32 [row][hidden]
};

void addInklingExpert(metal::CommandGraph &graph, const InklingExpertWeights &weights,
                      const InklingExpertBuffers &buffers, uint32_t rows);

// Weights are supplied gate/up then down for each entry. Row tiles
// enumerate only populated 32-row tiles.
void addInklingExpertBatch(metal::CommandGraph &graph, const InklingExpertBuffers &buffers,
                           const metal::MetalBuffer &entries, const metal::MetalBuffer &tiles,
                           const std::shared_ptr<const std::vector<metal::MetalBuffer>> &weights,
                           uint32_t experts, uint32_t rowTiles, std::string_view gateFormat,
                           bool nvfp4Down, bool singleToken);

} // namespace splash::ops
