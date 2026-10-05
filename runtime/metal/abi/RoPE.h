#pragma once

// Parameter layouts shared by host dispatch code and Metal kernels.
#ifdef __METAL_VERSION__
#include <metal_stdlib>
#else
#include <stdint.h>
#endif

// Rotary pairs read by the target (partial rotary) and draft attention kernels.
#define SPLASH_TARGET_ROPE_PAIRS 32u
#define SPLASH_DRAFT_ROPE_PAIRS 64u

struct RopeTableParams {
  uint32_t target_rows;
  uint32_t draft_rows;
};

static_assert(sizeof(RopeTableParams) == 8,
              "RoPE table parameters are 8 bytes on both sides");
