#pragma once

#ifdef __METAL_VERSION__
#include <metal_stdlib>
using namespace metal;
#else
#include <cstdint>
#endif

#define SPLASH_INKLING_QUERY_HEADS 24u
#define SPLASH_INKLING_KV_HEADS 8u
#define SPLASH_INKLING_HEAD_WIDTH 128u
#define SPLASH_INKLING_RELATIVE_WIDTH 16u
#define SPLASH_INKLING_WINDOW 1024u
#define SPLASH_INKLING_CONTEXT 1048576u
#define SPLASH_INKLING_HIDDEN 2304u
#define SPLASH_INKLING_GATE_RANK 64u
#define SPLASH_INKLING_MIX_STATES 5u
#define SPLASH_INKLING_MIX_THREADS 128u
#define SPLASH_INKLING_EXPERTS 128u
#define SPLASH_INKLING_TOP_K 8u
#define SPLASH_INKLING_EXPERT_WIDTH 1152u
#define SPLASH_INKLING_CLIP_THREADS 32u
#define SPLASH_INKLING_STORE_THREADS 128u
#define SPLASH_INKLING_ATTENTION_TILE 2048u
#define SPLASH_INKLING_QUERY_TILE 4u
#define SPLASH_INKLING_ATTENTION_PARTIAL (SPLASH_INKLING_HEAD_WIDTH + 2u)
#define SPLASH_INKLING_EXPERT_BATCH 16u
#define SPLASH_INKLING_EXPERT_TILE_ROWS 32u

struct InklingExpertEntry {
  uint32_t firstRow;
  uint32_t rows;
  float gateScale;
  float downScale;
};

struct InklingExpertTile {
  uint32_t expert;
  uint32_t tile;
};

struct InklingExpertParams {
  float scale;
};

// RMS scaling of one row, optionally by stored multipliers, written as BF16.
struct InklingNormParams {
  uint32_t width;
};

// Per-head QK or relative clipping: values * weight scaled by a threshold,
// or RMS normalized when `normalize` is set, then by the depth factor.
struct InklingClipParams {
  uint32_t firstQuery;
  uint32_t heads;
  uint32_t width;
  float threshold;
  uint32_t scalePosition;
  uint32_t normalize;
  uint32_t weighted;
};

// KV rows for query positions firstQuery .. firstQuery + rows - 1 land in
// slot position % slots of the visit's history.
struct InklingStoreParams {
  uint32_t firstQuery;
  uint32_t slots;
  uint32_t width;
};

// Gather one source row per route and add each route's expert output back to
// its row, scaled by the route's weight.
struct InklingRouteParams {
  uint32_t routes;
  uint32_t width;
  uint32_t topK;
};

struct InklingCapParams {
  uint32_t count;
  float cap;
};

struct InklingMixParams {
  uint32_t rows;
  uint32_t states;
};

struct InklingAttentionParams {
  uint32_t firstQuery;
  uint32_t window;
  uint32_t slots;
  uint32_t tiles;
  uint32_t rows;
};

struct InklingConvolutionParams {
  uint32_t rows;
  uint32_t channels;
  uint32_t channelsPerHead;
};
