#pragma once

#ifdef __METAL_VERSION__
#include <metal_stdlib>
#else
#include <stdint.h>
#endif

#define GLM_FLASH_DSA_CONTEXT 8192u
#define GLM_FLASH_DSA_HEADS 64u
#define GLM_FLASH_DSA_LATENT 512u
#define GLM_FLASH_DSA_INDEX_HEADS 32u
#define GLM_FLASH_DSA_INDEX_WIDTH 128u
#define GLM_FLASH_DSA_POOL 4u
#define GLM_FLASH_DSA_TOP_POOLS 512u
#define GLM_FLASH_DSA_SELECTION (GLM_FLASH_DSA_TOP_POOLS * GLM_FLASH_DSA_POOL + GLM_FLASH_DSA_POOL - 1u)
#define GLM_FLASH_DSA_SORT_THREADS 256u
#define GLM_FLASH_DSA_NORM_THREADS 128u
#define GLM_FLASH_DSA_SIMD_WIDTH 32u

struct GlmFlashDsaParams {
  uint32_t first;
  uint32_t rows;
  uint32_t pools; // Number of complete pools through the end of the chunk.
};

static_assert(sizeof(GlmFlashDsaParams) == 12);
