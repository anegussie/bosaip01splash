#pragma clang fp reassociate(off)
#include "metal/abi/HyperConnection.h"
#include "metal/abi/KernelABI.h"
#include "metal/kernels/common/activation.h"
#include "metal/kernels/common/gguf_sgmatrix.h"
#include "metal/kernels/common/hyper_streams.h"
#include "metal/kernels/common/rms_inverse.h"

#include <metal_stdlib>

using namespace metal;

// Hyper-connections (metal/abi/HyperConnection.h, Qwen3.8-Flash-Next's:
// model/Qwen4Exp.hpp). The residual streams are fp32 [rows][streams][hidden];
// the projections between these kernels read and write bf16 rows.

// Writes the lane's two values of span `span` of row `row` into the row's
// 8-row tile of the Table16 table the register-tile projection reading the
// rows takes (gguf_sg::Table16, as decode_linear_gguf_prepare writes it).
inline void hyper_table16_write(device bfloat *table, device float *sums, uint width, uint span, uint row,
                                uint lane, bfloat a, bfloat b) {
  gguf_sg::Table16::write(table + ulong(row / gguf_sg::kRows) * width * gguf_sg::kRows,
                          sums + ulong(row / gguf_sg::kRows) * gguf_sg::Table16::sums_per_tile(width), width,
                          span, row % gguf_sg::kRows, lane, a, b);
}

// The first mix step of a row: each stream's RMS norm times the mix's norm
// weights (the GGUF stores 1 + w) into bf16 rows of streams * hidden, and,
// when it injects, the injection weights 2 sigmoid(inject(normalized) /
// streams) of the block's output into each stream. Its kernels are compiled
// for Flash-Next's shape, kStreams streams of kNormHidden values. Each takes
// every load of a pass before the pass's arithmetic: at decode's few rows, a
// threadgroup per row that waits on each load in turn runs latency-bound.
// The two sum alike, so a row's output and weights are bit for bit the same
// whichever of them runs it. They write no table: a register-tile down
// projection prepares its own (decode_linear_gguf_prepare, a simdgroup per
// span and row over the whole GPU). A threadgroup per row writing its row's
// table stores two bytes at a time into a lane's eight-row tiles from one
// core, which costs 1.5 to 5.2 us per mix more than the plain norm and that
// preparation.
constant constexpr uint kNormHidden = HYPER_CONNECTION_NORM_HIDDEN;
constant constexpr uint kNormValues = kNormHidden / kRowThreads; // per thread and stream
constant constexpr uint kNormPairs = kNormValues / 2;
static_assert(kNormHidden % kRowThreads == 0 && kNormValues % 2 == 0,
              "a thread's values per stream are whole pairs");

// Prefill's rows, and a mix that injects nothing: a threadgroup of
// kRowThreads threads per row; each thread holds its values of every stream.
inline void hyper_norm_loaded_row(device const float *streams, device const float *norm,
                                  device const float *inject, device bfloat *normalized,
                                  device float *weights, constant HyperConnectionParams &p, uint row, uint tid,
                                  uint lane, uint sg, threadgroup float *scratch) {
  if (row >= p.rows) return;
  const uint hidden2 = kNormHidden / 2, width2 = kStreams * hidden2;
  device const float2 *x = reinterpret_cast<device const float2 *>(streams) + ulong(row) * width2;
  device const float2 *norm2 = reinterpret_cast<device const float2 *>(norm);
  device const float2 *inject2 = reinterpret_cast<device const float2 *>(inject);
  float2 xs[kStreams][kNormPairs];
  for (uint s = 0; s < kStreams; ++s)
    for (uint i = 0; i < kNormPairs; ++i) xs[s][i] = x[s * hidden2 + tid + i * kRowThreads];
  float sums[kStreams] = {0.0f, 0.0f, 0.0f, 0.0f};
  for (uint s = 0; s < kStreams; ++s)
    for (uint i = 0; i < kNormPairs; ++i) {
      sums[s] += xs[s][i].x * xs[s][i].x;
      sums[s] += xs[s][i].y * xs[s][i].y;
    }
  reduce_streams(sums, kStreams, scratch, lane, sg);
  float scale[kStreams];
  for (uint s = 0; s < kStreams; ++s) scale[s] = rsqrt(sums[s] / kNormHidden + kRmsEpsilon);
  float dots[kStreams] = {0.0f, 0.0f, 0.0f, 0.0f};
  device bfloat2 *out = reinterpret_cast<device bfloat2 *>(normalized) + ulong(row) * width2;
  for (uint s = 0; s < kStreams; ++s) {
    float2 ns[kNormPairs];
    for (uint i = 0; i < kNormPairs; ++i) ns[i] = norm2[s * hidden2 + tid + i * kRowThreads];
    for (uint i = 0; i < kNormPairs; ++i) {
      const uint c = s * hidden2 + tid + i * kRowThreads;
      const float2 v = xs[s][i] * scale[s] * ns[i];
      out[c] = bfloat2(v);
      if (p.inject)
        for (uint j = 0; j < kStreams; ++j) {
          const float2 w = inject2[ulong(j) * width2 + c];
          dots[j] += w.x * v.x;
          dots[j] += w.y * v.y;
        }
    }
  }
  if (!p.inject) return;
  reduce_streams(dots, kStreams, scratch, lane, sg);
  if (tid < kStreams) weights[row * kStreams + tid] = 2.0f * splash_sigmoid(dots[tid] / kStreams);
}

// Decode's rows of an injecting mix: a threadgroup of
// HYPER_CONNECTION_NORM_QUARTER_THREADS threads per row, whose quarter q stands for the
// loaded row's threadgroup in stream q's sum and in injection weight q's dot:
// each of its threads sums its values of stream q, then runs injection dot q
// over every stream's values in order, and writes stream q's normalized
// values.
inline void hyper_norm_quarter_row(device const float *streams, device const float *norm,
                                   device const float *inject, device bfloat *normalized,
                                   device float *weights, constant HyperConnectionParams &p, uint row,
                                   uint thread_id, uint lane, uint simdgroup, threadgroup float *scratch,
                                   threadgroup float *scales) {
  if (row >= p.rows) return;
  const uint q = thread_id / kRowThreads, tid = thread_id % kRowThreads;
  const uint hidden2 = kNormHidden / 2, width2 = kStreams * hidden2;
  device const float2 *x = reinterpret_cast<device const float2 *>(streams) + ulong(row) * width2;
  device const float2 *norm2 = reinterpret_cast<device const float2 *>(norm);
  float2 mine[kNormPairs];
  for (uint i = 0; i < kNormPairs; ++i) mine[i] = x[q * hidden2 + tid + i * kRowThreads];
  float sum = 0.0f;
  for (uint i = 0; i < kNormPairs; ++i) {
    sum += mine[i].x * mine[i].x;
    sum += mine[i].y * mine[i].y;
  }
  // The threadgroup's simdgroup `simdgroup` is quarter q's simdgroup
  // simdgroup % kSimdgroups.
  sum = simd_sum(sum);
  if (lane == 0) scratch[simdgroup] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (tid == 0) {
    float total = 0.0f;
    for (uint g = 0; g < kSimdgroups; ++g) total += scratch[q * kSimdgroups + g];
    scales[q] = rsqrt(total / kNormHidden + kRmsEpsilon);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  device bfloat2 *out = reinterpret_cast<device bfloat2 *>(normalized) + ulong(row) * width2;
  float dot = 0.0f;
  if (!p.inject) {
    for (uint i = 0; i < kNormPairs; ++i) {
      const uint c = q * hidden2 + tid + i * kRowThreads;
      out[c] = bfloat2(mine[i] * scales[q] * norm2[c]);
    }
  } else {
    device const float2 *w = reinterpret_cast<device const float2 *>(inject) + ulong(q) * width2;
    for (uint s = 0; s < kStreams; ++s) {
      const float scale = scales[s];
      float2 xv[kNormPairs], ns[kNormPairs], ws[kNormPairs];
      for (uint i = 0; i < kNormPairs; ++i) {
        const uint c = s * hidden2 + tid + i * kRowThreads;
        xv[i] = x[c];
        ns[i] = norm2[c];
        ws[i] = w[c];
      }
      for (uint i = 0; i < kNormPairs; ++i) {
        const uint c = s * hidden2 + tid + i * kRowThreads;
        const float2 v = xv[i] * scale * ns[i];
        if (s == q) out[c] = bfloat2(v);
        dot += ws[i].x * v.x;
        dot += ws[i].y * v.y;
      }
    }
  }
  if (!p.inject) return;
  dot = simd_sum(dot);
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (lane == 0) scratch[simdgroup] = dot;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (tid != 0) return;
  float total = 0.0f;
  for (uint g = 0; g < kSimdgroups; ++g) total += scratch[q * kSimdgroups + g];
  weights[row * kStreams + q] = 2.0f * splash_sigmoid(total / kStreams);
}

#define HYPER_NORM_ARGUMENTS                                                                                     \
  device const float *streams [[buffer(0)]], device const float *norm [[buffer(1)]],                            \
      device const float *inject [[buffer(2)]], device bfloat *normalized [[buffer(3)]],                        \
      device float *weights [[buffer(4)]]

kernel void hyper_connection_norm_loaded(HYPER_NORM_ARGUMENTS, constant HyperConnectionParams &p [[buffer(5)]],
                                         uint row [[threadgroup_position_in_grid]],
                                         uint tid [[thread_index_in_threadgroup]],
                                         uint lane [[thread_index_in_simdgroup]],
                                         uint sg [[simdgroup_index_in_threadgroup]]) {
  threadgroup float scratch[kSimdgroups * kStreams];
  hyper_norm_loaded_row(streams, norm, inject, normalized, weights, p, row, tid, lane, sg, scratch);
}

kernel void hyper_connection_norm_quarters(HYPER_NORM_ARGUMENTS, constant HyperConnectionParams &p [[buffer(5)]],
                                           uint row [[threadgroup_position_in_grid]],
                                           uint thread_id [[thread_index_in_threadgroup]],
                                           uint lane [[thread_index_in_simdgroup]],
                                           uint simdgroup [[simdgroup_index_in_threadgroup]]) {
  threadgroup float scratch[kStreams * kSimdgroups];
  threadgroup float scales[kStreams];
  hyper_norm_quarter_row(streams, norm, inject, normalized, weights, p, row, thread_id, lane, simdgroup, scratch,
                         scales);
}

#undef HYPER_NORM_ARGUMENTS

// silu(low / streams) of the mix's low-rank projection, in place.
kernel void hyper_connection_low(device bfloat *low [[buffer(0)]],
                                 constant HyperConnectionParams &p [[buffer(1)]],
                                 uint index [[thread_position_in_grid]]) {
  if (index >= p.rows * p.rank) return;
  low[index] = bfloat(splash_silu(float(low[index]) / p.streams));
}

// The same values into the up projection's table alone (a decode step's
// rows): a threadgroup per row, a simdgroup per 64-value span.
kernel void hyper_connection_low_table16(device const bfloat *low [[buffer(0)]],
                                         device bfloat *table [[buffer(1)]],
                                         device float *sums [[buffer(2)]],
                                         constant HyperConnectionParams &p [[buffer(3)]],
                                         uint row [[threadgroup_position_in_grid]],
                                         uint lane [[thread_index_in_simdgroup]],
                                         uint sg [[simdgroup_index_in_threadgroup]]) {
  if (row >= p.rows) return;
  device const bfloat *x = low + ulong(row) * p.rank;
  for (uint g = sg; g < p.rank / 64; g += kSimdgroups) {
    const uint k = g * 64 + 2 * lane;
    hyper_table16_write(table, sums, p.rank, g, row, lane, bfloat(splash_silu(float(x[k]) / p.streams)),
                        bfloat(splash_silu(float(x[k + 1]) / p.streams)));
  }
}

// The block's input: the mean over the streams of the normalized streams
// gated by sigmoid of the mix's up projection (64 threads/TG, 4 elements/thread).
kernel void hyper_connection_mix(device const bfloat *normalized [[buffer(0)]],
                                 device const bfloat *gate [[buffer(1)]],
                                 device bfloat *mixed [[buffer(2)]],
                                 constant HyperConnectionParams &p [[buffer(3)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint tid [[thread_index_in_threadgroup]]) {
  const uint row = group.x, d = group.y * kRowThreads + tid * 4u;
  if (row >= p.rows || d >= p.hidden) return;
  const ulong base = ulong(row) * p.streams * p.hidden + d;
  if (d + 4u <= p.hidden && (p.hidden & 3u) == 0u) {
    float4 sum = float4(0.0f);
    for (uint s = 0; s < p.streams; ++s) {
      const ulong off = base + ulong(s) * p.hidden;
      const float4 n = float4(*reinterpret_cast<device const bfloat4 *>(normalized + off));
      const float4 g = float4(*reinterpret_cast<device const bfloat4 *>(gate + off));
      sum += n * float4(splash_sigmoid(g.x), splash_sigmoid(g.y), splash_sigmoid(g.z), splash_sigmoid(g.w));
    }
    *reinterpret_cast<device bfloat4 *>(mixed + ulong(row) * p.hidden + d) = bfloat4(sum / float(p.streams));
    return;
  }
  for (uint i = 0; i < 4u && d + i < p.hidden; ++i) {
    float sum = 0.0f;
    for (uint s = 0; s < p.streams; ++s)
      sum += float(normalized[base + i + ulong(s) * p.hidden]) *
             splash_sigmoid(float(gate[base + i + ulong(s) * p.hidden]));
    mixed[ulong(row) * p.hidden + d + i] = bfloat(sum / p.streams);
  }
}

// The mix with the next projection's table (a decode step's rows, hidden a
// multiple of the threadgroup): the threadgroup's 256 values are four
// 64-value spans, which its first four simdgroups write.
kernel void hyper_connection_mix_table16(device const bfloat *normalized [[buffer(0)]],
                                         device const bfloat *gate [[buffer(1)]],
                                         device bfloat *mixed [[buffer(2)]],
                                         device bfloat *table [[buffer(3)]],
                                         device float *sums [[buffer(4)]],
                                         constant HyperConnectionParams &p [[buffer(5)]],
                                         uint2 group [[threadgroup_position_in_grid]],
                                         uint tid [[thread_index_in_threadgroup]],
                                         uint lane [[thread_index_in_simdgroup]],
                                         uint sg [[simdgroup_index_in_threadgroup]]) {
  threadgroup bfloat values[kRowThreads];
  const uint row = group.x, d = group.y * kRowThreads + tid;
  if (row >= p.rows) return;
  const ulong base = ulong(row) * p.streams * p.hidden + d;
  float sum = 0.0f;
  for (uint s = 0; s < p.streams; ++s)
    sum += float(normalized[base + s * p.hidden]) * splash_sigmoid(float(gate[base + s * p.hidden]));
  const bfloat value = bfloat(sum / p.streams);
  mixed[ulong(row) * p.hidden + d] = value;
  values[tid] = value;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (sg >= kRowThreads / 64) return;
  const uint k = sg * 64 + 2 * lane;
  hyper_table16_write(table, sums, p.hidden, group.y * (kRowThreads / 64) + sg, row, lane, values[k],
                      values[k + 1]);
}

// Every stream plus the block's output scaled by the stream's injection weight.
kernel void hyper_connection_combine(device float *streams [[buffer(0)]],
                                     device const bfloat *branch [[buffer(1)]],
                                     device const float *weights [[buffer(2)]],
                                     constant HyperConnectionParams &p [[buffer(3)]],
                                     uint2 group [[threadgroup_position_in_grid]],
                                     uint tid [[thread_index_in_threadgroup]]) {
  const uint row = group.x, d = group.y * kRowThreads + tid;
  if (row >= p.rows || d >= p.hidden) return;
  const float b = float(branch[ulong(row) * p.hidden + d]);
  device float *x = streams + ulong(row) * p.streams * p.hidden + d;
  for (uint s = 0; s < p.streams; ++s) x[s * p.hidden] += b * weights[row * p.streams + s];
}

// The streams' start: every stream a copy of the token's embedding.
kernel void hyper_connection_init(device const bfloat *embedding [[buffer(0)]],
                                  device float *streams [[buffer(1)]],
                                  constant HyperConnectionParams &p [[buffer(2)]],
                                  uint2 group [[threadgroup_position_in_grid]],
                                  uint tid [[thread_index_in_threadgroup]]) {
  const uint row = group.x, d = group.y * kRowThreads + tid;
  if (row >= p.rows || d >= p.hidden) return;
  const float e = float(embedding[ulong(row) * p.hidden + d]);
  device float *x = streams + ulong(row) * p.streams * p.hidden + d;
  for (uint s = 0; s < p.streams; ++s) x[s * p.hidden] = e;
}

// The mean of each row's streams (bf16), at column p.column of row p.row + r
// of a destination of p.stride values: Qwen3.8-Flash-Next's capture of a
// layer's output, which its DFlash2 draft reads (DFlashDraftLayout's
// target_hidden_reduction).
kernel void hyper_connection_stream_mean(device const float *streams [[buffer(0)]],
                                         device bfloat *destination [[buffer(1)]],
                                         constant HyperStreamMeanParams &p [[buffer(2)]],
                                         uint2 group [[threadgroup_position_in_grid]],
                                         uint tid [[thread_index_in_threadgroup]]) {
  const uint row = group.x, d = group.y * kRowThreads + tid;
  if (row >= p.rows || d >= p.hidden) return;
  device const float *x = streams + ulong(row) * p.streams * p.hidden + d;
  float sum = 0.0f;
  for (uint s = 0; s < p.streams; ++s) sum += x[s * p.hidden];
  destination[ulong(p.row + row) * p.stride + p.column + d] = bfloat(sum / float(p.streams));
}

// GLM Flash's manifold-constrained hyper-connection. The Q8_0 projection
// reads the original block layout. Residuals and branch activations stay
// FP32 here so rounding can be placed at the surrounding operator boundary.
kernel void glm_flash_hc_rms(device const float *streams [[buffer(0)]],
                             device float *inverse [[buffer(1)]],
                             uint row [[threadgroup_position_in_grid]],
                             uint tid [[thread_index_in_threadgroup]],
                             uint lane [[thread_index_in_simdgroup]],
                             uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  threadgroup float partial[HYPER_CONNECTION_ROW_THREADS / 32];
  device const float *input = streams + ulong(row) * GLM_FLASH_HC_WIDTH;
  float squares = 0.0f;
  for (uint d = tid; d < GLM_FLASH_HC_WIDTH; d += HYPER_CONNECTION_ROW_THREADS)
    squares += input[d] * input[d];
  const float sum = simd_sum(squares);
  if (lane == 0) partial[simdGroup] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (tid == 0) {
    float total = 0.0f;
    for (uint group = 0; group < HYPER_CONNECTION_ROW_THREADS / 32; ++group)
      total += partial[group];
    inverse[row] = rsqrt(total / float(GLM_FLASH_HC_WIDTH) + GLM_FLASH_HC_RMS_EPSILON);
  }
}

kernel void glm_flash_hc_project(device const float *streams [[buffer(0)]],
                                 device const uchar *weights [[buffer(1)]],
                                 device const float *inverse [[buffer(2)]],
                                 device float *coefficients [[buffer(3)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint lane [[thread_index_in_simdgroup]]) {
  constexpr uint blocks = GLM_FLASH_HC_WIDTH / 32;
  device const float *input = streams + ulong(group.x) * GLM_FLASH_HC_WIDTH;
  device const uchar *projection = weights + group.y * blocks * 34;
  float dot = 0.0f;
  for (uint block = 0; block < blocks; ++block) {
    device const uchar *weight = projection + block * 34;
    const float scale = float(*reinterpret_cast<device const half *>(weight));
    const float value = float(reinterpret_cast<device const char *>(weight + 2)[lane]);
    dot += (scale * value) * input[block * 32 + lane];
  }
  const float sum = simd_sum(dot);
  if (lane == 0)
    coefficients[ulong(group.x) * GLM_FLASH_HC_MIXES + group.y] = sum * inverse[group.x];
}

kernel void glm_flash_hc_coefficients(device float *coefficients [[buffer(0)]],
                                      device const float *scale [[buffer(1)]],
                                      device const float *base [[buffer(2)]],
                                      uint row [[threadgroup_position_in_grid]]) {
  constexpr uint streams = GLM_FLASH_HC_STREAMS;
  constexpr float eps = GLM_FLASH_HC_EPSILON;
  device float *mix = coefficients + ulong(row) * GLM_FLASH_HC_MIXES;
  for (uint stream = 0; stream < streams; ++stream) {
    const float pre = mix[stream] * scale[0] + base[stream];
    const float post = mix[streams + stream] * scale[1] + base[streams + stream];
    mix[stream] = 1.0f / (1.0f + exp(-pre)) + eps;
    mix[streams + stream] = 2.0f / (1.0f + exp(-post));
  }

  // Source-major matrix. Start with a softmax over destinations, add
  // epsilon, then normalize over sources. Subsequent iterations alternate.
  float matrix[streams][streams];
  for (uint src = 0; src < streams; ++src) {
    float largest = -INFINITY;
    for (uint dst = 0; dst < streams; ++dst) {
      const uint index = 2 * streams + src * streams + dst;
      matrix[src][dst] = mix[index] * scale[2] + base[index];
      largest = max(largest, matrix[src][dst]);
    }
    float sum = 0.0f;
    for (uint dst = 0; dst < streams; ++dst) {
      matrix[src][dst] = exp(matrix[src][dst] - largest);
      sum += matrix[src][dst];
    }
    for (uint dst = 0; dst < streams; ++dst)
      matrix[src][dst] = matrix[src][dst] / sum + eps;
  }
  for (uint iteration = 0; iteration < GLM_FLASH_HC_SINKHORN_ITERATIONS; ++iteration) {
    if (iteration != 0) {
      for (uint src = 0; src < streams; ++src) {
        float sum = 0.0f;
        for (uint dst = 0; dst < streams; ++dst) sum += matrix[src][dst];
        for (uint dst = 0; dst < streams; ++dst) matrix[src][dst] /= sum + eps;
      }
    }
    for (uint dst = 0; dst < streams; ++dst) {
      float sum = 0.0f;
      for (uint src = 0; src < streams; ++src) sum += matrix[src][dst];
      for (uint src = 0; src < streams; ++src) matrix[src][dst] /= sum + eps;
    }
  }
  for (uint src = 0; src < streams; ++src)
    for (uint dst = 0; dst < streams; ++dst)
      mix[2 * streams + src * streams + dst] = matrix[src][dst];
}

kernel void glm_flash_hc_pre(device const float *streams [[buffer(0)]],
                             device const float *coefficients [[buffer(1)]],
                             device float *branch [[buffer(2)]],
                             uint2 group [[threadgroup_position_in_grid]],
                             uint tid [[thread_index_in_threadgroup]]) {
  constexpr uint hidden = GLM_FLASH_HC_HIDDEN;
  const uint channel = group.y * HYPER_CONNECTION_ROW_THREADS + tid;
  device const float *state = streams + ulong(group.x) * GLM_FLASH_HC_WIDTH + channel;
  device const float *mix = coefficients + ulong(group.x) * GLM_FLASH_HC_MIXES;
  float value = 0.0f;
  for (uint src = 0; src < GLM_FLASH_HC_STREAMS; ++src)
    value += state[src * hidden] * mix[src];
  branch[ulong(group.x) * hidden + channel] = value;
}

kernel void glm_flash_hc_post(device float *streams [[buffer(0)]],
                              device const float *branch [[buffer(1)]],
                              device const float *coefficients [[buffer(2)]],
                              uint2 group [[threadgroup_position_in_grid]],
                              uint tid [[thread_index_in_threadgroup]]) {
  constexpr uint hidden = GLM_FLASH_HC_HIDDEN, count = GLM_FLASH_HC_STREAMS;
  const uint channel = group.y * HYPER_CONNECTION_ROW_THREADS + tid;
  device float *state = streams + ulong(group.x) * GLM_FLASH_HC_WIDTH + channel;
  device const float *mix = coefficients + ulong(group.x) * GLM_FLASH_HC_MIXES;
  const float value = branch[ulong(group.x) * hidden + channel];
  float residual[count];
  for (uint src = 0; src < count; ++src) residual[src] = state[src * hidden];
  for (uint dst = 0; dst < count; ++dst) {
    float updated = value * mix[count + dst];
    for (uint src = 0; src < count; ++src)
      updated += residual[src] * mix[2 * count + src * count + dst];
    state[dst * hidden] = updated;
  }
}
