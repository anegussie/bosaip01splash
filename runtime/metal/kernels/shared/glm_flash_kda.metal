#include "metal/abi/GlmFlashKda.h"
#include "metal/kernels/common/activation.h"

constant constexpr uint kHeads = GLM_FLASH_KDA_HEADS;
constant constexpr uint kHeadDim = GLM_FLASH_KDA_HEAD_DIM;
constant constexpr uint kChannels = GLM_FLASH_KDA_CHANNELS;

kernel void glm_flash_kda_convolve(device float *projection [[buffer(0)]],
                                   device const float *weight [[buffer(1)]],
                                   device float *history [[buffer(2)]],
                                   constant uint &rows [[buffer(3)]],
                                   uint channel [[thread_position_in_grid]]) {
  float a = history[3 * channel], b = history[3 * channel + 1], c = history[3 * channel + 2];
  const float4 taps = reinterpret_cast<device const float4 *>(weight)[channel];
  for (uint row = 0; row < rows; ++row) {
    const ulong index = ulong(row) * kChannels + channel;
    const float d = projection[index];
    projection[index] = splash_silu(dot(taps, float4(a, b, c, d)));
    a = b;
    b = c;
    c = d;
  }
  history[3 * channel] = a;
  history[3 * channel + 1] = b;
  history[3 * channel + 2] = c;
}

kernel void glm_flash_kda_prepare(device float *q [[buffer(0)]],
                                  device float *k [[buffer(1)]],
                                  device float *decay [[buffer(2)]],
                                  device float *beta [[buffer(3)]],
                                  device const float *scale [[buffer(4)]],
                                  device const float *bias [[buffer(5)]],
                                  uint2 group [[threadgroup_position_in_grid]],
                                  uint tid [[thread_index_in_threadgroup]],
                                  uint lane [[thread_index_in_simdgroup]],
                                  uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  threadgroup float2 partial[kHeadDim / 32];
  const ulong channel = group.x * kHeadDim + tid;
  const ulong index = ulong(group.y) * kChannels + channel;
  const float2 pair(q[index], k[index]);
  const float2 square = simd_sum(pair * pair);
  if (lane == 0) partial[simdGroup] = square;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float2 sums(0.0f);
  for (uint i = 0; i < kHeadDim / 32; ++i) sums += partial[i];
  const float2 normalized = pair * rsqrt(sums + GLM_FLASH_KDA_L2_EPSILON);
  q[index] = normalized.x;
  k[index] = normalized.y;
  const float projected = -(decay[index] + bias[channel]) * scale[group.x];
  decay[index] = exp(GLM_FLASH_KDA_GATE_LOWER_BOUND * splash_sigmoid(projected));
  if (tid == 0) {
    const ulong betaIndex = ulong(group.y) * kHeads + group.x;
    beta[betaIndex] = splash_sigmoid(beta[betaIndex]);
  }
}

kernel void glm_flash_kda_scan(device const float *q [[buffer(0)]],
                               device const float *k [[buffer(1)]],
                               device const float *v [[buffer(2)]],
                               device const float *decay [[buffer(3)]],
                               device const float *beta [[buffer(4)]],
                               device float *state [[buffer(5)]],
                               device float *output [[buffer(6)]],
                               constant uint &rows [[buffer(7)]],
                               uint2 group [[threadgroup_position_in_grid]],
                               uint lane [[thread_index_in_simdgroup]],
                               uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  // One SIMD group updates all key channels for one value channel.
  const uint value = group.y * 4 + simdGroup;
  const uint head = group.x * kHeadDim;
  device float *stateRow = state + ulong(head + value) * kHeadDim;
  float recurrent[kHeadDim / 32];
  for (uint i = 0; i < kHeadDim / 32; ++i) recurrent[i] = stateRow[32 * i + lane];
  for (uint row = 0; row < rows; ++row) {
    const ulong base = ulong(row) * kChannels + head;
    float keys[kHeadDim / 32], prediction = 0.0f;
    for (uint i = 0; i < kHeadDim / 32; ++i) {
      const ulong index = base + 32 * i + lane;
      keys[i] = k[index];
      recurrent[i] *= decay[index];
      prediction += recurrent[i] * keys[i];
    }
    const float predicted = simd_sum(prediction);
    const float delta = (v[base + value] - predicted) * beta[ulong(row) * kHeads + group.x];
    float mixed = 0.0f;
    for (uint i = 0; i < kHeadDim / 32; ++i) {
      recurrent[i] += delta * keys[i];
      mixed += recurrent[i] * q[base + 32 * i + lane];
    }
    const float attended = simd_sum(mixed);
    if (lane == 0) output[base + value] = attended * rsqrt(float(kHeadDim));
  }
  for (uint i = 0; i < kHeadDim / 32; ++i) stateRow[32 * i + lane] = recurrent[i];
}

kernel void glm_flash_kda_output(device float *output [[buffer(0)]],
                                 device const float *norm [[buffer(1)]],
                                 device const float *gate [[buffer(2)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint tid [[thread_index_in_threadgroup]],
                                 uint lane [[thread_index_in_simdgroup]],
                                 uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  threadgroup float partial[kHeadDim / 32];
  const ulong index = ulong(group.y) * kChannels + group.x * kHeadDim + tid;
  const float value = output[index];
  const float square = simd_sum(value * value);
  if (lane == 0) partial[simdGroup] = square;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float sum = 0.0f;
  for (uint i = 0; i < kHeadDim / 32; ++i) sum += partial[i];
  output[index] = value * rsqrt(sum / float(kHeadDim) + GLM_FLASH_KDA_OUTPUT_EPSILON)
                  * norm[tid] * splash_sigmoid(gate[index]);
}
