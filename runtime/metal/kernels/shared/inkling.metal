#include "metal/abi/Inkling.h"
#include "metal/kernels/common/activation.h"
#include "metal/kernels/common/gguf_embedding_formats.h"

constant constexpr uint queryHeads = SPLASH_INKLING_QUERY_HEADS;
constant constexpr uint kvHeads = SPLASH_INKLING_KV_HEADS;
constant constexpr uint headWidth = SPLASH_INKLING_HEAD_WIDTH;
constant constexpr uint relativeWidth = SPLASH_INKLING_RELATIVE_WIDTH;
constant constexpr uint relativeExtent = SPLASH_INKLING_WINDOW;

struct InklingAttentionPartial {
  float maximum, normalizer;
  float4 values;
};

inline InklingAttentionPartial inkling_attention_slice(device const float *query, device const float *relativeQuery,
                                                       device const float *table, device const bfloat *keys,
                                                       device const bfloat *values, uint position, uint begin,
                                                       uint end, uint queryHead, uint kvHead, uint slots, uint lane,
                                                       float sink, bool includeSink) {
  const uint base = queryHead * headWidth + lane;
  const float4 q(query[base], query[base + 32], query[base + 64], query[base + 96]);
  const float relative = lane < relativeWidth ? relativeQuery[queryHead * relativeWidth + lane] : 0.0f;

  // Initialize online softmax with the learned sink and zero value.
  float maximum = includeSink ? sink : -INFINITY;
  float normalizer = includeSink ? 1.0f : 0.0f;
  float4 accumulator(0.0f);
  for (uint key = begin; key < end; ++key) {
    const ulong offset = (ulong(key % slots) * kvHeads + kvHead) * headWidth + lane;
    const float4 k(keys[offset], keys[offset + 32], keys[offset + 64], keys[offset + 96]);
    const uint distance = position - key;
    const float bias = distance < relativeExtent && lane < relativeWidth
                           ? relative * table[distance * relativeWidth + lane] : 0.0f;
    const float score = simd_sum(dot(q, k) * rsqrt(float(headWidth)) + bias);
    const float nextMax = max(maximum, score);
    const float oldScale = exp(maximum - nextMax);
    const float newScale = exp(score - nextMax);
    const float4 value(values[offset], values[offset + 32], values[offset + 64], values[offset + 96]);
    accumulator = accumulator * oldScale + value * newScale;
    normalizer = normalizer * oldScale + newScale;
    maximum = nextMax;
  }
  return {maximum, normalizer, accumulator};
}

inline void inkling_attention_output(device const float *gate, device bfloat *output, uint base, float4 result) {
  output[base] = bfloat(result.x * splash_sigmoid(gate[base]));
  output[base + 32] = bfloat(result.y * splash_sigmoid(gate[base + 32]));
  output[base + 64] = bfloat(result.z * splash_sigmoid(gate[base + 64]));
  output[base + 96] = bfloat(result.w * splash_sigmoid(gate[base + 96]));
}

constant constexpr uint attentionKeyBatch = 32;
constant constexpr uint attentionQueryBatch = SPLASH_INKLING_QUERY_TILE;

// Each SIMD group evaluates one query, keeping the original key order and
// masks. The whole threadgroup cooperatively loads K/V once for its queries.
inline InklingAttentionPartial inkling_attention_tiled_slice(
    device const float *query, device const float *relativeQuery, device const float *table,
    device const float *sinks, device const bfloat *keys, device const bfloat *values,
    constant InklingAttentionParams &params, uint3 group, uint sg, uint lane,
    threadgroup bfloat *keyBatch, threadgroup bfloat *valueBatch) {
  const uint first = group.y * attentionQueryBatch;
  const uint last = min(first + attentionQueryBatch, params.rows) - 1;
  const uint row = min(first + sg, last);
  const uint position = params.firstQuery + row;
  const uint head = row * queryHeads + group.x;
  const uint kvHead = group.x / (queryHeads / kvHeads);
  const uint qbase = head * headWidth + lane;
  const float4 q(query[qbase], query[qbase + 32], query[qbase + 64], query[qbase + 96]);
  const float relative = lane < relativeWidth ? relativeQuery[head * relativeWidth + lane] : 0.0f;
  const uint start = params.tiles ? group.z * SPLASH_INKLING_ATTENTION_TILE : 0;
  const uint firstPos = params.firstQuery + first;
  const uint firstKey = params.window && firstPos >= params.window ? firstPos - params.window + 1 : start;
  const uint end = params.tiles ? min(params.firstQuery + last + 1, start + SPLASH_INKLING_ATTENTION_TILE)
                                : params.firstQuery + last + 1;
  const uint ownFirstKey = params.window && position >= params.window ? position - params.window + 1 : start;
  const bool includeSink = group.z == 0;
  float maximum = includeSink ? sinks[head] : -INFINITY;
  float normalizer = includeSink ? 1.0f : 0.0f;
  float4 accumulator(0.0f);
  for (uint block = firstKey; block < end; block += attentionKeyBatch) {
    const uint count = min(attentionKeyBatch, end - block);
    for (uint i = sg; i < count; i += attentionQueryBatch) {
      const ulong offset = (ulong((block + i) % params.slots) * kvHeads + kvHead) * headWidth + lane;
      const uint local = i * headWidth + lane;
      keyBatch[local] = keys[offset];
      keyBatch[local + 32] = keys[offset + 32];
      keyBatch[local + 64] = keys[offset + 64];
      keyBatch[local + 96] = keys[offset + 96];
      valueBatch[local] = values[offset];
      valueBatch[local + 32] = values[offset + 32];
      valueBatch[local + 64] = values[offset + 64];
      valueBatch[local + 96] = values[offset + 96];
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    const uint from = max(block, ownFirstKey), to = min(block + count, position + 1);
    for (uint key = from; key < to; ++key) {
      const uint local = (key - block) * headWidth + lane;
      const float4 k(keyBatch[local], keyBatch[local + 32], keyBatch[local + 64], keyBatch[local + 96]);
      const uint distance = position - key;
      const float bias = distance < relativeExtent && lane < relativeWidth
                             ? relative * table[distance * relativeWidth + lane] : 0.0f;
      const float score = simd_sum(dot(q, k) * rsqrt(float(headWidth)) + bias);
      const float nextMax = max(maximum, score);
      const float oldScale = exp(maximum - nextMax), newScale = exp(score - nextMax);
      const float4 v(valueBatch[local], valueBatch[local + 32], valueBatch[local + 64], valueBatch[local + 96]);
      accumulator = accumulator * oldScale + v * newScale;
      normalizer = normalizer * oldScale + newScale;
      maximum = nextMax;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
  return {maximum, normalizer, accumulator};
}

inline void inkling_store_attention_partial(device float *out, InklingAttentionPartial partial, uint lane) {
  if (!lane) {
    out[0] = partial.maximum;
    out[1] = partial.normalizer;
  }
  out[2 + lane] = partial.values.x;
  out[34 + lane] = partial.values.y;
  out[66 + lane] = partial.values.z;
  out[98 + lane] = partial.values.w;
}

kernel void inkling_relative_attention(device const float *query [[buffer(0)]],
                                       device const float *relativeQuery [[buffer(1)]],
                                       device const float *table [[buffer(2)]],
                                       device const float *sinks [[buffer(3)]],
                                       device const float *gate [[buffer(4)]],
                                       device const bfloat *keys [[buffer(5)]],
                                       device const bfloat *values [[buffer(6)]],
                                       device bfloat *output [[buffer(7)]],
                                       constant InklingAttentionParams &params [[buffer(8)]],
                                       uint2 group [[threadgroup_position_in_grid]],
                                       uint lane [[thread_index_in_simdgroup]]) {
  const uint position = params.firstQuery + group.y;
  const uint begin = params.window && position >= params.window ? position - params.window + 1 : 0;
  const uint queryHead = group.y * queryHeads + group.x;
  const uint kvHead = group.x / (queryHeads / kvHeads);
  const auto partial = inkling_attention_slice(query, relativeQuery, table, keys, values, position, begin,
                                              position + 1, queryHead, kvHead, params.slots, lane,
                                              sinks[queryHead], true);
  inkling_attention_output(gate, output, queryHead * headWidth + lane, partial.values / partial.normalizer);
}

kernel void inkling_attention_split(device const float *query [[buffer(0)]],
                                    device const float *relativeQuery [[buffer(1)]],
                                    device const float *table [[buffer(2)]],
                                    device const float *sinks [[buffer(3)]],
                                    device const bfloat *keys [[buffer(4)]],
                                    device const bfloat *values [[buffer(5)]],
                                    device float *scratch [[buffer(6)]],
                                    constant InklingAttentionParams &params [[buffer(7)]],
                                    uint3 group [[threadgroup_position_in_grid]],
                                    uint lane [[thread_index_in_simdgroup]]) {
  const uint position = params.firstQuery + group.y;
  const uint queryHead = group.y * queryHeads + group.x;
  const uint kvHead = group.x / (queryHeads / kvHeads);
  const uint begin = group.z * SPLASH_INKLING_ATTENTION_TILE;
  const uint end = min(position + 1, begin + SPLASH_INKLING_ATTENTION_TILE);
  const auto partial = inkling_attention_slice(query, relativeQuery, table, keys, values, position, begin, end,
                                              queryHead, kvHead, params.slots, lane, sinks[queryHead], group.z == 0);
  device float *out = scratch + (ulong(queryHead) * params.tiles + group.z) * SPLASH_INKLING_ATTENTION_PARTIAL;
  inkling_store_attention_partial(out, partial, lane);
}

kernel void inkling_attention_tiled(device const float *query [[buffer(0)]],
                                   device const float *relativeQuery [[buffer(1)]],
                                   device const float *table [[buffer(2)]],
                                   device const float *sinks [[buffer(3)]],
                                   device const float *gate [[buffer(4)]],
                                   device const bfloat *keys [[buffer(5)]],
                                   device const bfloat *values [[buffer(6)]],
                                   device bfloat *output [[buffer(7)]],
                                   constant InklingAttentionParams &params [[buffer(8)]],
                                   uint3 group [[threadgroup_position_in_grid]],
                                   uint lane [[thread_index_in_simdgroup]],
                                   uint sg [[simdgroup_index_in_threadgroup]]) {
  threadgroup bfloat keyBatch[attentionKeyBatch * headWidth], valueBatch[attentionKeyBatch * headWidth];
  const auto partial = inkling_attention_tiled_slice(query, relativeQuery, table, sinks, keys, values,
                                                     params, group, sg, lane, keyBatch, valueBatch);
  const uint row = group.y * attentionQueryBatch + sg;
  if (row >= params.rows) return;
  const uint head = row * queryHeads + group.x;
  inkling_attention_output(gate, output, head * headWidth + lane, partial.values / partial.normalizer);
}

kernel void inkling_attention_split_tiled(device const float *query [[buffer(0)]],
                                         device const float *relativeQuery [[buffer(1)]],
                                         device const float *table [[buffer(2)]],
                                         device const float *sinks [[buffer(3)]],
                                         device const bfloat *keys [[buffer(4)]],
                                         device const bfloat *values [[buffer(5)]],
                                         device float *scratch [[buffer(6)]],
                                         constant InklingAttentionParams &params [[buffer(7)]],
                                         uint3 group [[threadgroup_position_in_grid]],
                                         uint lane [[thread_index_in_simdgroup]],
                                         uint sg [[simdgroup_index_in_threadgroup]]) {
  threadgroup bfloat keyBatch[attentionKeyBatch * headWidth], valueBatch[attentionKeyBatch * headWidth];
  const auto partial = inkling_attention_tiled_slice(query, relativeQuery, table, sinks, keys, values,
                                                     params, group, sg, lane, keyBatch, valueBatch);
  const uint row = group.y * attentionQueryBatch + sg;
  if (row >= params.rows) return;
  const uint head = row * queryHeads + group.x;
  device float *out = scratch + (ulong(head) * params.tiles + group.z) * SPLASH_INKLING_ATTENTION_PARTIAL;
  inkling_store_attention_partial(out, partial, lane);
}

kernel void inkling_attention_merge(device const float *scratch [[buffer(0)]],
                                    device const float *gate [[buffer(1)]],
                                    device bfloat *output [[buffer(2)]],
                                    constant InklingAttentionParams &params [[buffer(3)]],
                                    uint2 group [[threadgroup_position_in_grid]],
                                    uint lane [[thread_index_in_simdgroup]]) {
  const uint queryHead = group.y * queryHeads + group.x;
  device const float *tiles = scratch + ulong(queryHead) * params.tiles * SPLASH_INKLING_ATTENTION_PARTIAL;
  float maximum = -INFINITY;
  for (uint i = 0; i < params.tiles; ++i) maximum = max(maximum, tiles[i * SPLASH_INKLING_ATTENTION_PARTIAL]);
  float normalizer = 0.0f;
  float4 sum(0.0f);
  for (uint i = 0; i < params.tiles; ++i) {
    device const float *tile = tiles + i * SPLASH_INKLING_ATTENTION_PARTIAL;
    const float scale = exp(tile[0] - maximum);
    normalizer += scale * tile[1];
    sum += scale * float4(tile[2 + lane], tile[34 + lane], tile[66 + lane], tile[98 + lane]);
  }
  inkling_attention_output(gate, output, queryHead * headWidth + lane, sum / normalizer);
}

// Every KV row of a chunk, rounded from FP32 to the BF16 history of its visit.
kernel void inkling_kv_store(device const float *keys [[buffer(0)]],
                             device const float *values [[buffer(1)]],
                             device bfloat *historyKeys [[buffer(2)]],
                             device bfloat *historyValues [[buffer(3)]],
                             constant InklingStoreParams &params [[buffer(4)]],
                             uint2 group [[threadgroup_position_in_grid]],
                             uint tid [[thread_index_in_threadgroup]]) {
  const uint row = group.y;
  const uint column = group.x * SPLASH_INKLING_STORE_THREADS + tid;
  if (column >= params.width) return;
  const ulong source = ulong(row) * params.width + column;
  const ulong target = ulong((params.firstQuery + row) % params.slots) * params.width + column;
  historyKeys[target] = bfloat(keys[source]);
  historyValues[target] = bfloat(values[source]);
}

// One threadgroup per query row and head: clip or normalize one head width.
kernel void inkling_head_clip(device float *values [[buffer(0)]],
                              device const float *weight [[buffer(1)]],
                              constant InklingClipParams &params [[buffer(2)]],
                              uint2 group [[threadgroup_position_in_grid]],
                              uint tid [[thread_index_in_threadgroup]],
                              uint lane [[thread_index_in_simdgroup]],
                              uint simd [[simdgroup_index_in_threadgroup]]) {
  threadgroup float scaled[SPLASH_INKLING_HEAD_WIDTH];
  threadgroup float partials[SPLASH_INKLING_CLIP_THREADS / 32];
  const ulong row = ulong(group.x) * params.heads * params.width + ulong(group.y) * params.width;
  float sum = 0.0f;
  for (uint column = tid; column < params.width; column += SPLASH_INKLING_CLIP_THREADS) {
    const float value = values[row + column] * (params.weighted ? weight[group.y * params.width + column] : 1.0f);
    scaled[column] = value;
    sum += value * value;
  }
  sum = simd_sum(sum);
  if (!lane) partials[simd] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  sum = 0.0f;
  for (uint i = 0; i < SPLASH_INKLING_CLIP_THREADS / 32; ++i) sum += partials[i];
  const float depth = float(params.firstQuery + group.x + 1) / 8192.0f;
  const float tau = params.scalePosition ? 1.0f + 0.1f * log(max(1.0f, depth)) : 1.0f;
  const float scale = params.normalize ? tau * rsqrt(sum / float(params.width) + 1e-6f)
                                       : tau * min(1.0f, params.threshold / (sqrt(sum) + 1e-6f));
  for (uint column = tid; column < params.width; column += SPLASH_INKLING_CLIP_THREADS)
    values[row + column] = scaled[column] * scale;
}

template <class Input, class Output>
inline void inkling_norm(device const Input *input, device const float *weight, device Output *output,
                         constant InklingNormParams &params, uint row, uint tid, uint lane, uint simd,
                         threadgroup float *partials) {
  const ulong base = ulong(row) * params.width;
  float sum = 0.0f;
  for (uint column = tid; column < params.width; column += SPLASH_INKLING_MIX_THREADS) {
    const float value = float(input[base + column]);
    sum += value * value;
  }
  sum = simd_sum(sum);
  if (!lane) partials[simd] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  sum = 0.0f;
  for (uint i = 0; i < SPLASH_INKLING_MIX_THREADS / 32; ++i) sum += partials[i];
  const float scale = rsqrt(sum / float(params.width) + 1e-6f);
  for (uint column = tid; column < params.width; column += SPLASH_INKLING_MIX_THREADS)
    output[base + column] = Output(float(input[base + column]) * scale * weight[column]);
}

kernel void inkling_norm_pack(device const float *input [[buffer(0)]],
                              device const float *weight [[buffer(1)]],
                              device bfloat *output [[buffer(2)]],
                              constant InklingNormParams &params [[buffer(3)]],
                              uint row [[threadgroup_position_in_grid]],
                              uint tid [[thread_index_in_threadgroup]],
                              uint lane [[thread_index_in_simdgroup]],
                              uint simd [[simdgroup_index_in_threadgroup]]) {
  threadgroup float partials[SPLASH_INKLING_MIX_THREADS / 32];
  inkling_norm(input, weight, output, params, row, tid, lane, simd, partials);
}

kernel void inkling_embedding_norm(device const bfloat *input [[buffer(0)]],
                                   device const float *weight [[buffer(1)]],
                                   device float *output [[buffer(2)]],
                                   constant InklingNormParams &params [[buffer(3)]],
                                   uint row [[threadgroup_position_in_grid]],
                                   uint tid [[thread_index_in_threadgroup]],
                                   uint lane [[thread_index_in_simdgroup]],
                                   uint simd [[simdgroup_index_in_threadgroup]]) {
  threadgroup float partials[SPLASH_INKLING_MIX_THREADS / 32];
  inkling_norm(input, weight, output, params, row, tid, lane, simd, partials);
}

kernel void inkling_add(device const float *left [[buffer(0)]],
                        device const float *right [[buffer(1)]],
                        device float *output [[buffer(2)]],
                        constant uint &count [[buffer(3)]],
                        uint index [[thread_position_in_grid]]) {
  if (index < count) output[index] = left[index] + right[index];
}

// Copy each route's input row, so one dispatch runs the experts of a batch.
kernel void inkling_route_gather(device const bfloat *input [[buffer(0)]],
                                 device const uint *order [[buffer(1)]],
                                 device bfloat *output [[buffer(2)]],
                                 constant InklingRouteParams &params [[buffer(3)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint tid [[thread_index_in_threadgroup]]) {
  const uint route = order[group.y];
  const ulong column = ulong(group.x) * SPLASH_INKLING_STORE_THREADS + tid;
  if (column >= params.width) return;
  output[ulong(group.y) * params.width + column] = input[ulong(route / params.topK) * params.width + column];
}

// Sum a token's original route order by gathering from expert-grouped rows.
kernel void inkling_route_accumulate(device const float *expert [[buffer(0)]],
                                     device const uint *inverseOrder [[buffer(1)]],
                                     device const float *weights [[buffer(2)]],
                                     device float *output [[buffer(3)]],
                                     constant InklingRouteParams &params [[buffer(4)]],
                                     uint2 group [[threadgroup_position_in_grid]],
                                     uint tid [[thread_index_in_threadgroup]]) {
  const ulong column = ulong(group.x) * SPLASH_INKLING_STORE_THREADS + tid;
  if (column >= params.width) return;
  float sum = 0.0f;
  const uint first = group.y * params.topK;
  for (uint route = first; route < first + params.topK; ++route)
    sum += weights[route] * expert[ulong(inverseOrder[route]) * params.width + column];
  output[ulong(group.y) * params.width + column] = sum;
}

kernel void inkling_logit_cap(device float *logits [[buffer(0)]],
                              constant InklingCapParams &params [[buffer(1)]],
                              uint index [[thread_position_in_grid]]) {
  if (index < params.count) logits[index] = params.cap * tanh(logits[index] / params.cap);
}

kernel void inkling_short_convolution(device float *projection [[buffer(0)]],
                                      device const float4 *taps [[buffer(1)]],
                                      device float *history [[buffer(2)]],
                                      device const float4 *dynamic [[buffer(3)]],
                                      constant InklingConvolutionParams &params [[buffer(4)]],
                                      uint channel [[thread_position_in_grid]]) {
  if (channel >= params.channels) return;
  const uint base = 3 * channel;
  float3 past(history[base], history[base + 1], history[base + 2]);
  const float4 weights = taps[channel];
  const bool hasDynamic = params.channelsPerHead != 0;
  const float scale = rsqrt(hasDynamic ? 9.0f : 5.0f);
  for (uint row = 0; row < params.rows; ++row) {
    const ulong index = ulong(row) * params.channels + channel;
    const float input = projection[index];
    const float4 window(past, input);
    float sum = input + dot(window, weights);
    if (hasDynamic) {
      const uint heads = params.channels / params.channelsPerHead;
      sum += dot(window.wzyx, dynamic[ulong(row) * heads + channel / params.channelsPerHead]);
    }
    projection[index] = sum * scale;
    past = float3(past.yz, input);
  }
  history[base] = past.x;
  history[base + 1] = past.y;
  history[base + 2] = past.z;
}

constant constexpr uint hidden = SPLASH_INKLING_HIDDEN;
constant constexpr uint mixThreads = SPLASH_INKLING_MIX_THREADS;

kernel void inkling_residual_mix(device const float *state0 [[buffer(0)]],
                                 device const float *state1 [[buffer(1)]],
                                 device const float *state2 [[buffer(2)]],
                                 device const float *state3 [[buffer(3)]],
                                 device const float *state4 [[buffer(4)]],
                                 device const float *queries [[buffer(5)]],
                                 device float *output [[buffer(6)]],
                                 constant InklingMixParams &params [[buffer(7)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint tid [[thread_index_in_threadgroup]],
                                 uint lane [[thread_index_in_simdgroup]],
                                 uint simd [[simdgroup_index_in_threadgroup]]) {
  device const float *states[] = {state0, state1, state2, state3, state4};
  threadgroup float2 partials[mixThreads / 32];
  const ulong row = ulong(group.x) * hidden;
  const uint query = group.y * hidden;
  float inverseRms[SPLASH_INKLING_MIX_STATES];
  float scores[SPLASH_INKLING_MIX_STATES];
  float maximum = -INFINITY;
  for (uint i = 0; i < params.states; ++i) {
    float2 sums(0.0f);
    for (uint col = tid; col < hidden; col += mixThreads) {
      const float value = states[i][row + col];
      sums += value * float2(value, queries[query + col]);
    }
    sums = simd_sum(sums);
    if (!lane) partials[simd] = sums;
    threadgroup_barrier(mem_flags::mem_threadgroup);
    sums = float2(0.0f);
    for (uint j = 0; j < mixThreads / 32; ++j) sums += partials[j];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    inverseRms[i] = rsqrt(sums.x / float(hidden) + 1e-6f);
    scores[i] = sums.y * inverseRms[i] * rsqrt(float(hidden));
    maximum = max(maximum, scores[i]);
  }
  float mass = 0.0f;
  for (uint i = 0; i < params.states; ++i) {
    scores[i] = exp(scores[i] - maximum);
    mass += scores[i];
    inverseRms[i] *= scores[i];
  }
  const ulong target = (ulong(group.y) * params.rows + group.x) * hidden;
  for (uint col = tid; col < hidden; col += mixThreads) {
    float sum = 0.0f;
    for (uint i = 0; i < params.states; ++i) sum += states[i][row + col] * inverseRms[i];
    output[target + col] = sum / mass;
  }
}

kernel void inkling_control_input(device const float *current [[buffer(0)]],
                                  device const float *message [[buffer(1)]],
                                  device bfloat *output [[buffer(2)]],
                                  uint2 group [[threadgroup_position_in_grid]],
                                  uint tid [[thread_index_in_threadgroup]],
                                  uint lane [[thread_index_in_simdgroup]],
                                  uint simd [[simdgroup_index_in_threadgroup]]) {
  const ulong source = ulong(group.x) * hidden;
  const ulong target = (ulong(group.x) * 2 + group.y) * hidden;
  device const float *input = group.y ? message : current;
  threadgroup float partials[mixThreads / 32];
  float sum = 0.0f;
  for (uint col = tid; col < hidden; col += mixThreads) {
    const float value = input[source + col];
    sum += value * value;
  }
  sum = simd_sum(sum);
  if (!lane) partials[simd] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  sum = 0.0f;
  for (uint i = 0; i < mixThreads / 32; ++i) sum += partials[i];
  const float inverseRms = rsqrt(sum / float(hidden) + 1e-6f);
  for (uint col = tid; col < hidden; col += mixThreads)
    output[target + col] = bfloat(input[source + col] * inverseRms);
}

kernel void inkling_control_apply(device const float *current [[buffer(0)]],
                                  device const float *message [[buffer(1)]],
                                  device const float *gain [[buffer(2)]],
                                  device const float *forget [[buffer(3)]],
                                  device float *output [[buffer(4)]],
                                  uint2 position [[thread_position_in_grid]]) {
  const ulong index = ulong(position.y) * hidden + position.x;
  output[index] = (1.0f - tanh(forget[index])) * current[index] + tanh(gain[index]) * message[index];
}

constant constexpr uint expertCount = SPLASH_INKLING_EXPERTS;
constant constexpr uint topK = SPLASH_INKLING_TOP_K;
constant constexpr uint expertWidth = SPLASH_INKLING_EXPERT_WIDTH;

kernel void inkling_expert_select(device const float *scores [[buffer(0)]],
                                  device const float *bias [[buffer(1)]],
                                  device uint *indices [[buffer(2)]],
                                  device float *weights [[buffer(3)]],
                                  uint row [[threadgroup_position_in_grid]],
                                  uint lane [[thread_index_in_simdgroup]]) {
  device const float *rowScores = scores + ulong(row) * expertCount;
  float biased[expertCount / 32];
  for (uint i = 0; i < expertCount / 32; ++i) {
    const uint expert = lane + 32 * i;
    biased[i] = splash_sigmoid(rowScores[expert]) + bias[expert];
  }
  float selected[topK], total = 0.0f;
  for (uint rank = 0; rank < topK; ++rank) {
    uint slot = 0;
    for (uint i = 1; i < expertCount / 32; ++i)
      if (biased[i] > biased[slot]) slot = i;
    const float best = simd_max(biased[slot]);
    const uint candidate = biased[slot] == best ? lane + 32 * slot : 0xffffffffu;
    const uint winner = simd_min(candidate);
    if (candidate == winner) biased[slot] = -INFINITY;
    if (!lane) indices[ulong(row) * topK + rank] = winner;
    selected[rank] = splash_sigmoid(rowScores[winner]);
    total += selected[rank];
  }
  if (lane < topK) weights[ulong(row) * topK + lane] = 8.0f * selected[lane] / max(total, 0x1p-14f);
}

inline bfloat inkling_situ(float gate, float up, float scale) {
#pragma clang fp reassociate(off)
  gate *= scale;
  up *= scale;
  const float sigmoid = 1.0f / (1.0f + precise::exp(-gate));
  return bfloat(100.0f * precise::tanh(gate * 0.25f) * sigmoid * precise::tanh(up * 0.04f));
}

kernel void inkling_expert_situ(device const float *gateUp [[buffer(0)]],
                                device bfloat *activation [[buffer(1)]],
                                constant InklingExpertParams &params [[buffer(2)]],
                                uint2 position [[thread_position_in_grid]]) {
  const ulong row = ulong(position.y) * expertWidth;
  activation[row + position.x] = inkling_situ(gateUp[2 * row + position.x],
                                            gateUp[2 * row + expertWidth + position.x], params.scale);
}

kernel void inkling_grouped_situ(device const float *gateUp [[buffer(0)]],
                                 device bfloat *activation [[buffer(1)]],
                                 device const InklingExpertEntry *experts [[buffer(2)]],
                                 device const InklingExpertTile *tiles [[buffer(3)]],
                                 uint3 position [[thread_position_in_grid]]) {
  const auto tile = tiles[position.z];
  const auto expert = experts[tile.expert];
  const uint localRow = tile.tile * SPLASH_INKLING_EXPERT_TILE_ROWS + position.y;
  if (localRow >= expert.rows) return;
  const ulong row = ulong(expert.firstRow + localRow) * expertWidth;
  activation[row + position.x] = inkling_situ(gateUp[2 * row + position.x],
                                            gateUp[2 * row + expertWidth + position.x], expert.gateScale);
}

// One SIMD group per output row of the original GGUF type-40 layout.
// Four 16-value groups share a 36-byte block, with lanes j and j+8
// in the low and high nibble of byte j in each group.
inline float inkling_nvfp4_dot(device const bfloat *activations, device const uchar *packed, uint out, uint lane) {
  using Format = GgufEmbedInklingNVFP4;
  constexpr uint blockWidth = Format::Weights, blockBytes = Format::Bytes;
  device const uchar *row = packed + ulong(out) * (expertWidth / blockWidth) * blockBytes;
  float sum = 0.0f;
  for (uint i = lane; i < expertWidth; i += 32) {
    device const uchar *block = row + i / blockWidth * blockBytes;
    sum += float(activations[i]) * Format::decode(block, i);
  }
  return simd_sum(sum);
}

kernel void inkling_expert_nvfp4(device const bfloat *input [[buffer(0)]],
                                 device const uchar *packed [[buffer(1)]],
                                 device float *output [[buffer(2)]],
                                 constant InklingExpertParams &params [[buffer(3)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint lane [[thread_index_in_simdgroup]],
                                 uint simd [[simdgroup_index_in_threadgroup]]) {
  const uint out = group.x * 4 + simd;
  const float sum = inkling_nvfp4_dot(input + ulong(group.y) * expertWidth, packed, out, lane);
  if (!lane) output[ulong(group.y) * hidden + out] = params.scale * sum;
}

kernel void inkling_grouped_nvfp4(device const bfloat *input [[buffer(0)]],
                                  device float *output [[buffer(1)]],
                                  device const InklingExpertEntry *experts [[buffer(2)]],
                                  constant ulong *addresses [[buffer(3)]],
                                  uint2 group [[threadgroup_position_in_grid]],
                                  uint lane [[thread_index_in_simdgroup]],
                                  uint simd [[simdgroup_index_in_threadgroup]]) {
  const auto expert = experts[group.y];
  const uint out = group.x * 4 + simd;
  const ulong row = expert.firstRow;
  device const uchar *packed = reinterpret_cast<device const uchar *>(addresses[2 * group.y + 1]);
  const float sum = inkling_nvfp4_dot(input + row * expertWidth, packed, out, lane);
  if (!lane) output[row * hidden + out] = expert.downScale * sum;
}

template <bool FullTile>
inline float4 inkling_activations4(device const bfloat *input, uint live, uint i) {
  return float4(float(input[i]), FullTile || live > 1 ? float(input[expertWidth + i]) : 0.0f,
                FullTile || live > 2 ? float(input[2 * expertWidth + i]) : 0.0f,
                FullTile || live > 3 ? float(input[3 * expertWidth + i]) : 0.0f);
}

template <bool FullTile>
inline float4 inkling_nvfp4_rows_dot(device const bfloat *activation, device const uchar *weights,
                                      uint live, uint lane) {
  using Format = GgufEmbedInklingNVFP4;
  static_assert(Format::Weights == 64 && expertWidth % Format::Weights == 0);
  float4 sum(0.0f);
  for (uint first = lane; first < expertWidth; first += Format::Weights) {
    // Process both halves of the same packed block without recomputing its
    // address. Keep the reduction order identical to the single-row kernel.
    sum += inkling_activations4<FullTile>(activation, live, first) * Format::decode(weights, lane);
    sum += inkling_activations4<FullTile>(activation, live, first + 32) * Format::decode(weights, lane + 32);
    weights += Format::Bytes;
  }
  return float4(simd_sum(sum.x), simd_sum(sum.y), simd_sum(sum.z), simd_sum(sum.w));
}

// Four routed rows reuse each decoded NVFP4 weight. Each row keeps the
// same K traversal and SIMD reduction as the single-row projection.
kernel void inkling_grouped_nvfp4_rows(device const bfloat *input [[buffer(0)]],
                                       device float *output [[buffer(1)]],
                                       device const InklingExpertEntry *experts [[buffer(2)]],
                                       device const InklingExpertTile *tiles [[buffer(3)]],
                                       constant ulong *addresses [[buffer(4)]],
                                       uint3 group [[threadgroup_position_in_grid]],
                                       uint lane [[thread_index_in_simdgroup]],
                                       uint simd [[simdgroup_index_in_threadgroup]]) {
  using Format = GgufEmbedInklingNVFP4;
  const auto tile = tiles[group.z];
  const auto expert = experts[tile.expert];
  const uint local = tile.tile * SPLASH_INKLING_EXPERT_TILE_ROWS + group.y * 4;
  if (local >= expert.rows) return;
  const uint live = min(4u, expert.rows - local);
  const uint out = group.x * 4 + simd;
  const ulong first = expert.firstRow + local;
  device const bfloat *activation = input + first * expertWidth;
  device const uchar *packed = reinterpret_cast<device const uchar *>(addresses[2 * tile.expert + 1]);
  device const uchar *weights = packed + ulong(out) * (expertWidth / Format::Weights) * Format::Bytes;
  const float4 result = live == 4 ? inkling_nvfp4_rows_dot<true>(activation, weights, live, lane)
                                  : inkling_nvfp4_rows_dot<false>(activation, weights, live, lane);
  if (!lane)
    for (uint row = 0; row < live; ++row)
      output[(first + row) * hidden + out] = expert.downScale * result[row];
}
