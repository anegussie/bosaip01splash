#include "metal/abi/GlmFlashSparseAttention.h"

using namespace metal;

constant constexpr uint kIndexWidth = GLM_FLASH_DSA_INDEX_WIDTH;
constant constexpr uint kIndexHeads = GLM_FLASH_DSA_INDEX_HEADS;
constant constexpr uint kLatent = GLM_FLASH_DSA_LATENT;
constant constexpr uint kHeads = GLM_FLASH_DSA_HEADS;
constant constexpr uint kPool = GLM_FLASH_DSA_POOL;
constant constexpr uint kTopPools = GLM_FLASH_DSA_TOP_POOLS;
constant constexpr uint kSelection = GLM_FLASH_DSA_SELECTION;
constant constexpr uint kSimd = GLM_FLASH_DSA_SIMD_WIDTH;
constant constexpr uint kUnused = 0xffffffffu;

inline float glm_flash_dsa_sum(float value, threadgroup float *partial, uint lane, uint simdGroup) {
  const float localSum = simd_sum(value);
  if (lane == 0) partial[simdGroup] = localSum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float total = 0.0f;
  for (uint group = 0; group < kIndexWidth / kSimd; ++group) total += partial[group];
  threadgroup_barrier(mem_flags::mem_threadgroup);
  return total;
}

kernel void glm_flash_dsa_cache(device const float *rawKey [[buffer(0)]],
                                 device const float *rawGate [[buffer(1)]],
                                 device const float *latent [[buffer(2)]],
                                 device const float *norm [[buffer(3)]],
                                 device const float *bias [[buffer(4)]],
                                 device float *keys [[buffer(5)]],
                                 device float *gates [[buffer(6)]],
                                 device float *latents [[buffer(7)]],
                                 constant GlmFlashDsaParams &p [[buffer(8)]],
                                 uint row [[threadgroup_position_in_grid]],
                                 uint d [[thread_index_in_threadgroup]],
                                 uint lane [[thread_index_in_simdgroup]],
                                 uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  threadgroup float scratch[kIndexWidth / kSimd];
  const uint from = row * kIndexWidth + d;
  const uint to = (p.first + row) * kIndexWidth + d;
  const float raw = rawKey[from];
  const float mean = glm_flash_dsa_sum(raw, scratch, lane, simdGroup) / float(kIndexWidth);
  const float centered = raw - mean;
  const float variance = glm_flash_dsa_sum(centered * centered, scratch, lane, simdGroup) / float(kIndexWidth);
  keys[to] = (centered * rsqrt(variance + 1e-6f)) * norm[d] + bias[d];
  gates[to] = rawGate[from];
  for (uint i = d; i < kLatent; i += kIndexWidth)
    latents[(p.first + row) * kLatent + i] = latent[row * kLatent + i];
}

kernel void glm_flash_dsa_pool(device const float *keys [[buffer(0)]],
                                device const float *gates [[buffer(1)]],
                                device const float *poolBias [[buffer(2)]],
                                device float *pooled [[buffer(3)]],
                                constant GlmFlashDsaParams &p [[buffer(4)]],
                                uint group [[threadgroup_position_in_grid]],
                                uint d [[thread_index_in_threadgroup]]) {
  const uint index = p.first / kPool + group;
  const uint first = index * kPool * kIndexWidth + d;
  float logits[kPool];
  float largest = -INFINITY;
  for (uint i = 0; i < kPool; ++i) {
    logits[i] = gates[first + i * kIndexWidth] + poolBias[i * kIndexWidth + d];
    largest = max(largest, logits[i]);
  }
  float total = 0.0f, weighted = 0.0f;
  for (uint i = 0; i < kPool; ++i) {
    const float weight = exp(logits[i] - largest);
    weighted += keys[first + i * kIndexWidth] * weight;
    total += weight;
  }
  pooled[index * kIndexWidth + d] = weighted / total;
}

kernel void glm_flash_dsa_score(device const float *queries [[buffer(0)]],
                                 device const float *weights [[buffer(1)]],
                                 device const float *pooled [[buffer(2)]],
                                 device float *scores [[buffer(3)]],
                                 constant GlmFlashDsaParams &p [[buffer(4)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint tid [[thread_index_in_threadgroup]],
                                 uint lane [[thread_index_in_simdgroup]],
                                 uint simdGroup [[simdgroup_index_in_threadgroup]]) {
  constexpr uint simdGroups = GLM_FLASH_DSA_SORT_THREADS / kSimd;
  const uint visible = (p.first + group.y + 1) / kPool;
  if (visible <= kTopPools || group.x >= visible) return;
  threadgroup float partial[simdGroups];
  const device float *key = pooled + group.x * kIndexWidth;
  float total = 0.0f;
  for (uint head = simdGroup; head < kIndexHeads; head += simdGroups) {
    const device float *query = queries + (ulong(group.y) * kIndexHeads + head) * kIndexWidth;
    float dot = 0.0f;
    for (uint d = lane; d < kIndexWidth; d += kSimd) dot += key[d] * query[d];
    total += max(simd_sum(dot), 0.0f) * weights[group.y * kIndexHeads + head];
  }
  if (lane == 0) partial[simdGroup] = total;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (tid == 0) {
    float score = 0.0f;
    for (uint head = 0; head < simdGroups; ++head) score += partial[head];
    scores[ulong(group.y) * p.pools + group.x] = score * rsqrt(float(kIndexHeads * kIndexWidth));
  }
}

kernel void glm_flash_dsa_select(device const float *scores [[buffer(0)]],
                                  device uint *selected [[buffer(1)]],
                                  constant GlmFlashDsaParams &p [[buffer(2)]],
                                  uint row [[threadgroup_position_in_grid]],
                                  uint tid [[thread_index_in_threadgroup]]) {
  constexpr uint width = GLM_FLASH_DSA_SORT_THREADS;
  constexpr uint maxPools = GLM_FLASH_DSA_CONTEXT / kPool;
  threadgroup float values[maxPools];
  threadgroup uint ids[maxPools];
  const uint end = p.first + row + 1, visible = end / kPool;
  if (visible <= kTopPools) return; // These rows still use dense causal attention.
  uint sortCount = 1;
  while (sortCount < visible) sortCount *= 2;
  for (uint i = tid; i < sortCount; i += width) {
    values[i] = i < visible ? scores[ulong(row) * p.pools + i] : -INFINITY;
    ids[i] = i < visible ? i : kUnused;
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  // Descending by score. Equal finite scores prefer the earlier pool.
  for (uint size = 2; size <= sortCount; size *= 2) {
    for (uint distance = size / 2; distance; distance /= 2) {
      for (uint i = tid; i < sortCount; i += width) {
        const uint j = i ^ distance;
        if (j <= i) continue;
        const float a = values[i], b = values[j];
        const uint ia = ids[i], ib = ids[j];
        const bool descend = (i & size) == 0;
        const bool aBefore = a > b || (a == b && ia < ib);
        if (aBefore != descend) {
          values[i] = b;
          values[j] = a;
          ids[i] = ib;
          ids[j] = ia;
        }
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
    }
  }
  device uint *output = selected + ulong(row) * kSelection;
  for (uint i = tid; i < kSelection; i += width) {
    if (i < kTopPools * kPool)
      output[i] = ids[i / kPool] * kPool + i % kPool;
    else {
      const uint tail = visible * kPool + i - kTopPools * kPool;
      output[i] = tail < end ? tail : kUnused;
    }
  }
}

template <bool Sparse>
inline void glm_flash_dsa_attend(device const float *queries, device const float *latents,
                                 device const uint *selected, device float *output,
                                 constant GlmFlashDsaParams &p, uint2 group, uint lane) {
  constexpr uint columns = kLatent / kSimd;
  const ulong start = (ulong(group.y) * kHeads + group.x) * kLatent;
  const uint end = p.first + group.y + 1;
  const bool useSelection = Sparse && end / kPool > kTopPools;
  const uint count = useSelection ? kTopPools * kPool + end % kPool : end;
  float query[columns], result[columns] = {};
  for (uint i = 0; i < columns; ++i) query[i] = queries[start + i * kSimd + lane];
  float largest = -INFINITY, denominator = 0.0f;
  for (uint row = 0; row < count; ++row) {
    const uint index = useSelection ? selected[ulong(group.y) * kSelection + row] : row;
    const device float *keyValue = latents + index * kLatent;
    float value[columns], dot = 0.0f;
    for (uint i = 0; i < columns; ++i) {
      value[i] = keyValue[i * kSimd + lane];
      dot += value[i] * query[i];
    }
    // The scale uses the unabsorbed MLA head width (256), not the
    // latent rank (512), as in the GLM reference graph.
    const float score = simd_sum(dot) * 0.0625f;
    const float nextLargest = max(largest, score);
    const float keep = exp(largest - nextLargest), weight = exp(score - nextLargest);
    denominator = denominator * keep + weight;
    for (uint i = 0; i < columns; ++i) result[i] = result[i] * keep + value[i] * weight;
    largest = nextLargest;
  }
  for (uint i = 0; i < columns; ++i) output[start + i * kSimd + lane] = result[i] / denominator;
}

kernel void glm_flash_dsa_dense(device const float *queries [[buffer(0)]],
                                 device const float *latents [[buffer(1)]],
                                 device float *output [[buffer(2)]],
                                 constant GlmFlashDsaParams &p [[buffer(3)]],
                                 uint2 group [[threadgroup_position_in_grid]],
                                 uint lane [[thread_index_in_simdgroup]]) {
  glm_flash_dsa_attend<false>(queries, latents, nullptr, output, p, group, lane);
}

kernel void glm_flash_dsa_sparse(device const float *queries [[buffer(0)]],
                                  device const float *latents [[buffer(1)]],
                                  device const uint *selected [[buffer(2)]],
                                  device float *output [[buffer(3)]],
                                  constant GlmFlashDsaParams &p [[buffer(4)]],
                                  uint2 group [[threadgroup_position_in_grid]],
                                  uint lane [[thread_index_in_simdgroup]]) {
  glm_flash_dsa_attend<true>(queries, latents, selected, output, p, group, lane);
}
