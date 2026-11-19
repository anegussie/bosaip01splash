#pragma once

#include "metal/CommandGraph.hpp"
#include "metal/abi/GlmFlashSparseAttention.h"

namespace splash::ops {

struct GlmFlashDsaWeights {
  metal::MetalBuffer keyNorm;  // FP32 [128] LayerNorm weight.
  metal::MetalBuffer keyBias;  // FP32 [128] LayerNorm bias.
  metal::MetalBuffer poolBias; // FP32 [4][128] position-dependent pool bias.
};

struct GlmFlashDsaCache {
  uint32_t capacity = 0;
  metal::MetalBuffer keys;     // FP32 [capacity][128].
  metal::MetalBuffer gates;    // FP32 [capacity][128].
  metal::MetalBuffer pools;    // FP32 [capacity / 4][128].
  metal::MetalBuffer latents;  // FP32 [capacity][512], used as keys and values.
};

struct GlmFlashDsaBuffers {
  metal::MetalBuffer indexKey;     // FP32 [rows][128], before LayerNorm.
  metal::MetalBuffer indexGate;    // FP32 [rows][128].
  metal::MetalBuffer indexQuery;   // FP32 [rows][32][128].
  metal::MetalBuffer indexWeights; // FP32 [rows][32], before scaling.
  metal::MetalBuffer latent;       // FP32 [rows][512], already RMS normalized.
  metal::MetalBuffer query;        // FP32 [rows][64][512], after absorbing wk_b.
  metal::MetalBuffer output;       // FP32 [rows][64][512], before per-head wv_b.
};

struct GlmFlashDsaScratch {
  metal::MetalBuffer scores;   // FP32 [rows][complete pools].
  metal::MetalBuffer selected; // U32 [rows][GLM_FLASH_DSA_SELECTION], UINT32_MAX padding.
};

class GlmFlashSparseAttention final {
public:
  // Single sequence, contiguous positions. Only the completed prefix before
  // firstPosition is read from an earlier call. The caller owns the logical
  // position and state snapshots. All inputs and outputs use distinct storage.
  static void add(metal::CommandGraph &graph, const GlmFlashDsaWeights &weights,
                  const GlmFlashDsaCache &cache, const GlmFlashDsaBuffers &buffers,
                  const GlmFlashDsaScratch &scratch, uint32_t firstPosition, uint32_t rows);
};

} // namespace splash::ops
