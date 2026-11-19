#include "ops/GlmFlashSparseAttention.hpp"

#include "ops/BufferExtent.hpp"

namespace splash::ops {

void GlmFlashSparseAttention::add(metal::CommandGraph &graph, const GlmFlashDsaWeights &weights,
                                  const GlmFlashDsaCache &cache, const GlmFlashDsaBuffers &buffers,
                                  const GlmFlashDsaScratch &scratch, uint32_t firstPosition, uint32_t rows) {
  if (!rows || cache.capacity > GLM_FLASH_DSA_CONTEXT ||
      uint64_t{firstPosition} + rows > cache.capacity)
    throw std::invalid_argument("invalid GLM Flash sparse attention range");
  constexpr uint32_t width = GLM_FLASH_DSA_INDEX_WIDTH, latent = GLM_FLASH_DSA_LATENT;
  constexpr uint32_t indexHeads = GLM_FLASH_DSA_INDEX_HEADS, heads = GLM_FLASH_DSA_HEADS;
  constexpr uint32_t pool = GLM_FLASH_DSA_POOL;
  const uint32_t pools = (firstPosition + rows) / pool;
  const uint32_t previousPools = firstPosition / pool;
  const bool sparse = pools > GLM_FLASH_DSA_TOP_POOLS;
  const auto bytes = [](uint32_t count, uint32_t stride) { return uint64_t{count} * stride * sizeof(float); };
  requireBytes(weights.keyNorm, bytes(1, width), "GLM Flash index key norm");
  requireBytes(weights.keyBias, bytes(1, width), "GLM Flash index key bias");
  requireBytes(weights.poolBias, bytes(pool, width), "GLM Flash index pool bias");
  requireBytes(cache.keys, bytes(cache.capacity, width), "GLM Flash cached index keys");
  requireBytes(cache.gates, bytes(cache.capacity, width), "GLM Flash cached index gates");
  requireBytes(cache.pools, bytes(cache.capacity / pool, width), "GLM Flash pooled index keys");
  requireBytes(cache.latents, bytes(cache.capacity, latent), "GLM Flash latent cache");
  requireBytes(buffers.indexKey, bytes(rows, width), "GLM Flash index key");
  requireBytes(buffers.indexGate, bytes(rows, width), "GLM Flash index gate");
  requireBytes(buffers.latent, bytes(rows, latent), "GLM Flash latent input");
  requireBytes(buffers.query, bytes(rows, heads * latent), "GLM Flash query");
  requireBytes(buffers.output, bytes(rows, heads * latent), "GLM Flash attention output");
  if (sparse) {
    requireBytes(buffers.indexQuery, bytes(rows, indexHeads * width), "GLM Flash index query");
    requireBytes(buffers.indexWeights, bytes(rows, indexHeads), "GLM Flash index head weights");
    requireBytes(scratch.scores, bytes(rows, pools), "GLM Flash index scores");
    requireBytes(scratch.selected, uint64_t{rows} * GLM_FLASH_DSA_SELECTION * sizeof(uint32_t),
                 "GLM Flash selected indices");
  }

  const GlmFlashDsaParams p{firstPosition, rows, pools};
  graph.add("glm_flash_dsa_cache",
            {buffers.indexKey, buffers.indexGate, buffers.latent, weights.keyNorm, weights.keyBias,
             cache.keys, cache.gates, cache.latents},
            p, {rows, 1, 1}, {GLM_FLASH_DSA_NORM_THREADS, 1, 1});
  if (pools > previousPools)
    graph.add("glm_flash_dsa_pool", {cache.keys, cache.gates, weights.poolBias, cache.pools},
              p, {pools - previousPools, 1, 1}, {width, 1, 1});
  if (sparse) {
    graph.add("glm_flash_dsa_score", {buffers.indexQuery, buffers.indexWeights, cache.pools, scratch.scores},
              p, {pools, rows, 1}, {GLM_FLASH_DSA_SORT_THREADS, 1, 1});
    graph.add("glm_flash_dsa_select", {scratch.scores, scratch.selected},
              p, {rows, 1, 1}, {GLM_FLASH_DSA_SORT_THREADS, 1, 1});
    graph.add("glm_flash_dsa_sparse",
              {buffers.query, cache.latents, scratch.selected, buffers.output}, p,
              {heads, rows, 1}, {GLM_FLASH_DSA_SIMD_WIDTH, 1, 1});
  } else {
    graph.add("glm_flash_dsa_dense", {buffers.query, cache.latents, buffers.output}, p,
              {heads, rows, 1}, {GLM_FLASH_DSA_SIMD_WIDTH, 1, 1});
  }
}

} // namespace splash::ops
