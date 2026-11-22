#include "ops/Inkling.hpp"

#include "metal/abi/Inkling.h"
#include "ops/BufferExtent.hpp"
#include "ops/Linear.hpp"

#include <algorithm>
#include <cmath>

namespace splash::ops {

uint64_t inklingAttentionScratchBytes(uint32_t rows, uint32_t end) noexcept {
  if (end <= SPLASH_INKLING_ATTENTION_TILE) return 0;
  const uint32_t tiles = 1 + (end - 1) / SPLASH_INKLING_ATTENTION_TILE;
  return uint64_t{rows} * SPLASH_INKLING_QUERY_HEADS * tiles * SPLASH_INKLING_ATTENTION_PARTIAL * sizeof(float);
}

void addInklingAttention(metal::CommandGraph &graph, const InklingAttentionBuffers &buffers,
                         uint32_t firstQuery, uint32_t rows, bool sliding, uint32_t slots, bool tileQueries) {
  constexpr uint32_t window = SPLASH_INKLING_WINDOW, queryHeads = SPLASH_INKLING_QUERY_HEADS;
  constexpr uint32_t relativeWidth = SPLASH_INKLING_RELATIVE_WIDTH;
  const uint64_t end = uint64_t{firstQuery} + rows;
  const uint64_t history = sliding ? std::min<uint64_t>(end, uint64_t{window} + rows - 1) : end;
  if (!rows || end > SPLASH_INKLING_CONTEXT || slots < history)
    throw std::invalid_argument("invalid Inkling attention range");
  constexpr uint64_t queryWidth = queryHeads * SPLASH_INKLING_HEAD_WIDTH;
  constexpr uint64_t kvWidth = SPLASH_INKLING_KV_HEADS * SPLASH_INKLING_HEAD_WIDTH;
  const uint64_t queryBytes = rows * queryWidth * sizeof(float);
  const uint64_t historyBytes = uint64_t{slots} * kvWidth * sizeof(uint16_t);
  requireBytes(buffers.query, queryBytes, "Inkling attention query");
  requireBytes(buffers.relativeQuery, uint64_t{rows} * queryHeads * relativeWidth * sizeof(float),
               "Inkling relative query");
  requireBytes(buffers.relativeTable, uint64_t{window} * relativeWidth * sizeof(float), "Inkling relative table");
  requireBytes(buffers.sinks, uint64_t{rows} * queryHeads * sizeof(float), "Inkling attention sinks");
  requireBytes(buffers.gate, queryBytes, "Inkling attention gate");
  requireBytes(buffers.keys, historyBytes, "Inkling attention keys");
  requireBytes(buffers.values, historyBytes, "Inkling attention values");
  requireBytes(buffers.output, rows * queryWidth * sizeof(uint16_t), "Inkling attention output");
  const bool tiled = tileQueries && rows >= SPLASH_INKLING_QUERY_TILE;
  const uint32_t queriesPerGroup = tiled ? SPLASH_INKLING_QUERY_TILE : 1;
  const uint32_t queryGroups = (rows + queriesPerGroup - 1) / queriesPerGroup;
  if (!sliding && end > SPLASH_INKLING_ATTENTION_TILE) {
    requireBytes(buffers.scratch, inklingAttentionScratchBytes(rows, uint32_t(end)), "Inkling attention partials");
    const uint32_t tiles = 1 + (uint32_t(end) - 1) / SPLASH_INKLING_ATTENTION_TILE;
    const InklingAttentionParams params{firstQuery, 0, slots, tiles, rows};
    graph.add(tiled ? "inkling_attention_split_tiled" : "inkling_attention_split",
              {buffers.query, buffers.relativeQuery, buffers.relativeTable, buffers.sinks,
               buffers.keys, buffers.values, buffers.scratch}, params,
              {queryHeads, queryGroups, tiles}, {32 * queriesPerGroup, 1, 1});
    graph.add("inkling_attention_merge", {buffers.scratch, buffers.gate, buffers.output}, params,
              {queryHeads, rows, 1}, {32, 1, 1});
    return;
  }
  graph.add(tiled ? "inkling_attention_tiled" : "inkling_relative_attention",
            {buffers.query, buffers.relativeQuery, buffers.relativeTable,
                                           buffers.sinks, buffers.gate, buffers.keys, buffers.values, buffers.output},
            InklingAttentionParams{firstQuery, sliding ? window : 0, slots, 0, rows},
            {queryHeads, queryGroups, 1}, {32 * queriesPerGroup, 1, 1});
}

void addInklingKeyValueStore(metal::CommandGraph &graph, const metal::MetalBuffer &keys,
                             const metal::MetalBuffer &values, metal::MetalBuffer historyKeys,
                             metal::MetalBuffer historyValues, uint32_t firstQuery, uint32_t rows, uint32_t slots) {
  constexpr uint32_t width = SPLASH_INKLING_KV_HEADS * SPLASH_INKLING_HEAD_WIDTH;
  if (!rows || slots < rows || uint64_t{firstQuery} + rows > SPLASH_INKLING_CONTEXT)
    throw std::invalid_argument("invalid Inkling KV history range");
  requireBytes(keys, uint64_t{rows} * width * sizeof(float), "Inkling attention keys");
  requireBytes(values, uint64_t{rows} * width * sizeof(float), "Inkling attention values");
  requireBytes(historyKeys, uint64_t{slots} * width * sizeof(uint16_t), "Inkling key history");
  requireBytes(historyValues, uint64_t{slots} * width * sizeof(uint16_t), "Inkling value history");
  graph.add("inkling_kv_store", {keys, values, std::move(historyKeys), std::move(historyValues)},
            InklingStoreParams{firstQuery, slots, width}, {width / SPLASH_INKLING_STORE_THREADS, rows, 1},
            {SPLASH_INKLING_STORE_THREADS, 1, 1});
}

void addInklingHeadClip(metal::CommandGraph &graph, metal::MetalBuffer values, const metal::MetalBuffer &weight,
                        uint32_t firstQuery, uint32_t rows, uint32_t heads, uint32_t width, float threshold,
                        bool scalePosition,
                        bool normalize, bool weighted) {
  if (!rows || !heads || !width || width > SPLASH_INKLING_HEAD_WIDTH || (!normalize && !(threshold > 0)))
    throw std::invalid_argument("invalid Inkling head clip dimensions");
  requireBytes(values, uint64_t{rows} * heads * width * sizeof(float), "Inkling clipped head");
  if (weighted) requireBytes(weight, uint64_t{heads} * width * sizeof(float), "Inkling clip weights");
  graph.add("inkling_head_clip", {std::move(values), weight},
            InklingClipParams{firstQuery, heads, width, threshold, scalePosition ? 1u : 0u,
                              normalize ? 1u : 0u, weighted ? 1u : 0u},
            {rows, heads, 1}, {SPLASH_INKLING_CLIP_THREADS, 1, 1});
}

void addInklingEmbedNorm(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weight,
                         metal::MetalBuffer output, uint32_t rows) {
  constexpr uint32_t width = SPLASH_INKLING_HIDDEN;
  if (!rows) throw std::invalid_argument("an Inkling embedding norm needs rows");
  requireBytes(input, uint64_t{rows} * width * sizeof(uint16_t), "Inkling embedding input");
  requireBytes(weight, width * sizeof(float), "Inkling embedding norm weight");
  requireBytes(output, uint64_t{rows} * width * sizeof(float), "Inkling embedding output");
  graph.add("inkling_embedding_norm", {input, weight, std::move(output)}, InklingNormParams{width}, {rows, 1, 1},
            {SPLASH_INKLING_MIX_THREADS, 1, 1});
}

void addInklingNorm(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weight,
                    metal::MetalBuffer output, uint32_t rows, uint32_t width) {
  if (!rows || !width) throw std::invalid_argument("an Inkling norm needs rows and a width");
  requireBytes(input, uint64_t{rows} * width * sizeof(float), "Inkling normalized input");
  requireBytes(weight, width * sizeof(float), "Inkling norm weights");
  requireBytes(output, uint64_t{rows} * width * sizeof(uint16_t), "Inkling normalized output");
  graph.add("inkling_norm_pack", {input, weight, std::move(output)}, InklingNormParams{width}, {rows, 1, 1},
            {SPLASH_INKLING_MIX_THREADS, 1, 1});
}

void addInklingAdd(metal::CommandGraph &graph, const metal::MetalBuffer &left, const metal::MetalBuffer &right,
                   metal::MetalBuffer output, uint32_t count) {
  if (!count) throw std::invalid_argument("an Inkling sum needs values");
  requireBytes(left, uint64_t{count} * sizeof(float), "Inkling sum input");
  requireBytes(right, uint64_t{count} * sizeof(float), "Inkling sum input");
  requireBytes(output, uint64_t{count} * sizeof(float), "Inkling sum output");
  graph.add("inkling_add", {left, right, std::move(output)}, count,
            {1 + (count - 1) / 256, 1, 1}, {256, 1, 1});
}

void addInklingRouteGather(metal::CommandGraph &graph, const metal::MetalBuffer &input,
                           const metal::MetalBuffer &order, metal::MetalBuffer gathered, uint32_t routes,
                           uint32_t width) {
  if (!routes || routes % SPLASH_INKLING_TOP_K || !width)
    throw std::invalid_argument("an Inkling route gather needs complete routes");
  requireBytes(input, uint64_t{routes / SPLASH_INKLING_TOP_K} * width * sizeof(uint16_t), "Inkling expert input");
  requireBytes(order, routes * sizeof(uint32_t), "Inkling route order");
  requireBytes(gathered, uint64_t{routes} * width * sizeof(uint16_t), "Inkling gathered expert input");
  graph.add("inkling_route_gather", {input, order, std::move(gathered)},
            InklingRouteParams{routes, width, SPLASH_INKLING_TOP_K},
            {(width + SPLASH_INKLING_STORE_THREADS - 1) / SPLASH_INKLING_STORE_THREADS, routes, 1},
            {SPLASH_INKLING_STORE_THREADS, 1, 1});
}

void addInklingRouteAccumulate(metal::CommandGraph &graph, const metal::MetalBuffer &expert,
                               const metal::MetalBuffer &inverseOrder, const metal::MetalBuffer &weights,
                               metal::MetalBuffer output, uint32_t routes, uint32_t width) {
  if (!routes || routes % SPLASH_INKLING_TOP_K || !width)
    throw std::invalid_argument("an Inkling route sum needs complete routes");
  requireBytes(expert, uint64_t{routes} * width * sizeof(float), "Inkling expert output");
  requireBytes(inverseOrder, routes * sizeof(uint32_t), "Inkling inverse route order");
  requireBytes(weights, routes * sizeof(float), "Inkling route weights");
  requireBytes(output, uint64_t{routes / SPLASH_INKLING_TOP_K} * width * sizeof(float), "Inkling expert sum");
  graph.add("inkling_route_accumulate", {expert, inverseOrder, weights, std::move(output)},
            InklingRouteParams{routes, width, SPLASH_INKLING_TOP_K},
            {(width + SPLASH_INKLING_STORE_THREADS - 1) / SPLASH_INKLING_STORE_THREADS, routes / SPLASH_INKLING_TOP_K, 1},
            {SPLASH_INKLING_STORE_THREADS, 1, 1});
}

void addInklingLogitCap(metal::CommandGraph &graph, metal::MetalBuffer logits, uint32_t count, float cap) {
  if (!count || cap <= 0) throw std::invalid_argument("an Inkling logit cap needs values");
  requireBytes(logits, uint64_t{count} * sizeof(float), "Inkling logits");
  graph.add("inkling_logit_cap", {std::move(logits)}, InklingCapParams{count, cap},
            {(count + 255) / 256, 1, 1}, {256, 1, 1});
}

void addInklingConvolution(metal::CommandGraph &graph, const metal::MetalBuffer &projection,
                           const metal::MetalBuffer &taps, const metal::MetalBuffer &history,
                           uint32_t rows, uint32_t channels, const metal::MetalBuffer &dynamicTaps, uint32_t heads) {
  if (!rows || !channels || (heads && channels % heads))
    throw std::invalid_argument("invalid Inkling convolution dimensions");
  requireBytes(projection, uint64_t{rows} * channels * sizeof(float), "Inkling convolution input");
  requireBytes(taps, uint64_t{channels} * 4 * sizeof(float), "Inkling convolution weights");
  requireBytes(history, uint64_t{channels} * 3 * sizeof(float), "Inkling convolution history");
  if (heads)
    requireBytes(dynamicTaps, uint64_t{rows} * heads * 4 * sizeof(float), "Inkling dynamic convolution weights");
  constexpr uint32_t threads = metal::CommandGraph::kDefaultThreads;
  graph.add("inkling_short_convolution", {projection, taps, history, heads ? dynamicTaps : taps},
            InklingConvolutionParams{rows, channels, heads ? channels / heads : 0},
            {1 + (channels - 1) / threads, 1, 1}, {threads, 1, 1});
}

void addInklingResidualMix(metal::CommandGraph &graph, std::span<const metal::MetalBuffer> states,
                           const metal::MetalBuffer &queries, const metal::MetalBuffer &output,
                           uint32_t rows, uint32_t queryCount) {
  constexpr uint64_t widthBytes = SPLASH_INKLING_HIDDEN * sizeof(float);
  if (!rows || states.empty() || states.size() > SPLASH_INKLING_MIX_STATES || !queryCount || queryCount > 3)
    throw std::invalid_argument("invalid Inkling residual mix dimensions");
  for (const auto &state : states) requireBytes(state, rows * widthBytes, "Inkling residual mix state");
  requireBytes(queries, queryCount * widthBytes, "Inkling residual mix queries");
  requireBytes(output, rows * widthBytes * queryCount, "Inkling residual mix output");
  std::vector<metal::MetalBuffer> bindings(states.begin(), states.end());
  bindings.resize(SPLASH_INKLING_MIX_STATES, states.back());
  bindings.insert(bindings.end(), {queries, output});
  graph.add("inkling_residual_mix", std::move(bindings), InklingMixParams{rows, uint32_t(states.size())},
            {rows, queryCount, 1}, {SPLASH_INKLING_MIX_THREADS, 1, 1});
}

void addInklingControl(metal::CommandGraph &graph, const InklingControlWeights &weights,
                       const InklingControlBuffers &buffers, uint32_t rows) {
  constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, rank = SPLASH_INKLING_GATE_RANK;
  if (!rows || weights.down.inputSize != 2 * hidden || weights.down.outputSize != rank ||
      weights.gain.inputSize != rank || weights.gain.outputSize != hidden ||
      weights.forget.inputSize != rank || weights.forget.outputSize != hidden)
    throw std::invalid_argument("invalid Inkling loop controller dimensions");
  for (const auto *weight : {&weights.down, &weights.gain, &weights.forget}) {
    if (!weight->isFloat() || weight->formatId != QuantizedSegment::kFloat32)
      throw std::invalid_argument("Inkling loop controller weights must be FP32 rows");
    requireBytes(weight->plane0, uint64_t{weight->inputSize} * weight->outputSize * sizeof(float),
                 "Inkling loop controller weights");
  }
  const uint64_t bytes = uint64_t{rows} * hidden * sizeof(float);
  requireBytes(buffers.current, bytes, "Inkling loop current residual");
  requireBytes(buffers.message, bytes, "Inkling loop message");
  requireBytes(buffers.output, bytes, "Inkling loop output");
  requireBytes(buffers.normalized, bytes, "Inkling loop normalized input");
  requireBytes(buffers.down, uint64_t{rows} * rank * sizeof(uint16_t), "Inkling loop down output");
  requireBytes(buffers.gain, bytes, "Inkling loop gain output");
  requireBytes(buffers.forget, bytes, "Inkling loop forget output");
  graph.add("inkling_control_input", {buffers.current, buffers.message, buffers.normalized},
            {rows, 2, 1}, {SPLASH_INKLING_MIX_THREADS, 1, 1});
  addGgufFloat(graph, buffers.normalized, weights.down, buffers.down, rows, rank, 0, FloatOutput::BFloat16,
               FloatTile::Simdgroup);
  const auto tile = rows == 1 ? FloatTile::Vector : FloatTile::Simdgroup;
  const FloatProjection gates[]{{&weights.gain, buffers.gain, hidden, 0, tile},
                                {&weights.forget, buffers.forget, hidden, 0, tile}};
  addGgufFloat(graph, buffers.down, gates, rows, FloatOutput::Float32);
  constexpr uint32_t threads = 128;
  graph.add("inkling_control_apply", {buffers.current, buffers.message, buffers.gain, buffers.forget, buffers.output},
            {hidden / threads, rows, 1}, {threads, 1, 1});
}

void addInklingRouting(metal::CommandGraph &graph, const metal::MetalBuffer &scores,
                       const metal::MetalBuffer &bias, const metal::MetalBuffer &indices,
                       const metal::MetalBuffer &weights, uint32_t rows) {
  if (!rows) throw std::invalid_argument("Inkling routing requires rows");
  constexpr uint64_t rowBytes = SPLASH_INKLING_EXPERTS * sizeof(float);
  requireBytes(scores, rows * rowBytes, "Inkling router scores");
  requireBytes(bias, rowBytes, "Inkling router bias");
  requireBytes(indices, uint64_t{rows} * SPLASH_INKLING_TOP_K * sizeof(uint32_t), "Inkling selected experts");
  requireBytes(weights, uint64_t{rows} * SPLASH_INKLING_TOP_K * sizeof(float), "Inkling routing weights");
  graph.add("inkling_expert_select", {scores, bias, indices, weights}, {rows, 1, 1}, {32, 1, 1});
}

void addInklingExpert(metal::CommandGraph &graph, const InklingExpertWeights &weights,
                      const InklingExpertBuffers &buffers, uint32_t rows) {
  constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, width = SPLASH_INKLING_EXPERT_WIDTH;
  if (!rows || weights.gateUp.inputSize != hidden || weights.gateUp.outputSize != 2 * width ||
      !std::isfinite(weights.gateUpScale) || !std::isfinite(weights.downScale) ||
      (!weights.nvfp4Down && weights.downScale != 1))
    throw std::invalid_argument("invalid Inkling expert weights or dimensions");
  constexpr uint64_t nvfp4RowBytes = width / 64 * 36;
  const uint64_t downBytes = weights.nvfp4Down ? nvfp4RowBytes : QuantizedSegment::rowBytes(GGUF_FMT_IQ4NL, width);
  requireBytes(weights.down, hidden * downBytes, "Inkling expert down weights");
  requireBytes(buffers.input, uint64_t{rows} * hidden * sizeof(uint16_t), "Inkling expert input");
  requireBytes(buffers.gateUp, uint64_t{rows} * 2 * width * sizeof(float), "Inkling expert gate-up scratch");
  requireBytes(buffers.activated, uint64_t{rows} * width * sizeof(uint16_t), "Inkling expert SiTU scratch");
  requireBytes(buffers.output, uint64_t{rows} * hidden * sizeof(float), "Inkling expert output");
  const auto tile = rows == 1 ? FloatTile::Vector : FloatTile::Simdgroup;
  addGgufFloat(graph, buffers.input, weights.gateUp, buffers.gateUp, rows, 2 * width, 0, FloatOutput::Float32, tile);
  constexpr uint32_t threads = 128;
  graph.add("inkling_expert_situ", {buffers.gateUp, buffers.activated}, InklingExpertParams{weights.gateUpScale},
            {width / threads, rows, 1}, {threads, 1, 1});
  if (weights.nvfp4Down) {
    graph.add("inkling_expert_nvfp4", {buffers.activated, weights.down, buffers.output},
              InklingExpertParams{weights.downScale}, {hidden / 4, rows, 1}, {128, 1, 1});
  } else {
    const auto down = QuantizedSegment::rows(GGUF_FMT_IQ4NL, hidden, width, weights.down);
    addGgufFloat(graph, buffers.activated, down, buffers.output, rows, hidden, 0, FloatOutput::Float32, tile);
  }
}

void addInklingExpertBatch(metal::CommandGraph &graph, const InklingExpertBuffers &buffers,
                           const metal::MetalBuffer &entries, const metal::MetalBuffer &tiles,
                           const std::shared_ptr<const std::vector<metal::MetalBuffer>> &weights,
                           uint32_t experts, uint32_t rowTiles, std::string_view gateFormat,
                           bool nvfp4Down, bool singleToken) {
  constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, width = SPLASH_INKLING_EXPERT_WIDTH;
  if (!experts || experts > SPLASH_INKLING_EXPERT_BATCH || !weights || weights->size() != 2 * experts ||
      rowTiles < experts || (singleToken && rowTiles != experts))
    throw std::invalid_argument("invalid Inkling expert batch");
  requireBytes(entries, uint64_t{experts} * sizeof(InklingExpertEntry), "Inkling expert entries");
  requireBytes(tiles, uint64_t{rowTiles} * sizeof(InklingExpertTile), "Inkling expert tiles");
  const auto project = [&](const metal::MetalBuffer &input, const metal::MetalBuffer &output,
                           uint32_t columns, std::string_view format, uint32_t gate) {
    if (singleToken) {
      graph.add("inkling_grouped_vector_" + std::string(format), {input, output, entries}, gate,
                {columns / 4, experts, 1}, {128, 1, 1});
    } else {
      graph.add("inkling_grouped_matrix_" + std::string(format), {input, output, entries, tiles}, gate,
                {columns / 8, rowTiles, 1}, {256, 1, 1});
    }
    graph.addresses(weights);
  };
  project(buffers.input, buffers.gateUp, 2 * width, gateFormat, 1);
  graph.add("inkling_grouped_situ", {buffers.gateUp, buffers.activated, entries, tiles},
            {width / 128, singleToken ? 1 : SPLASH_INKLING_EXPERT_TILE_ROWS, rowTiles}, {128, 1, 1});
  if (nvfp4Down && singleToken) {
    graph.add("inkling_grouped_nvfp4", {buffers.activated, buffers.output, entries},
              {hidden / 4, experts, 1}, {128, 1, 1});
    graph.addresses(weights);
  } else if (nvfp4Down) {
    graph.add("inkling_grouped_nvfp4_rows", {buffers.activated, buffers.output, entries, tiles},
              {hidden / 4, SPLASH_INKLING_EXPERT_TILE_ROWS / 4, rowTiles}, {128, 1, 1});
    graph.addresses(weights);
  } else {
    project(buffers.activated, buffers.output, hidden, "iq4nl", 0);
  }
}

} // namespace splash::ops
