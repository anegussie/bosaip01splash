#pragma once

#include "metal/CommandGraph.hpp"
#include "metal/abi/GlmFlashKda.h"

#include <array>

namespace splash::ops {

struct GlmFlashKdaWeights {
  // Q, K and V, each [channels][4], oldest tap first.
  std::array<metal::MetalBuffer, 3> convolution;
  metal::MetalBuffer decayScale; // [heads], stored as -exp(A_log).
  metal::MetalBuffer decayBias;  // [channels].
  metal::MetalBuffer outputNorm; // [headDim], shared by heads.
};

struct GlmFlashKdaState {
  // One [channels][3] history per Q, K and V, oldest input first.
  std::array<metal::MetalBuffer, 3> convolution;
  // [head][value channel][key channel].
  metal::MetalBuffer recurrent;
};

struct GlmFlashKdaBuffers {
  // Projections in [rows][channels]. Rewritten in place to convolved Q/K/V.
  std::array<metal::MetalBuffer, 3> qkv;
  metal::MetalBuffer decay;      // [rows][channels], becomes exp(log decay).
  metal::MetalBuffer beta;       // [rows][heads], becomes sigmoid(beta).
  metal::MetalBuffer outputGate; // [rows][channels] raw gate inputs.
  metal::MetalBuffer output;     // [rows][channels] before output projection.
};

class GlmFlashKda final {
public:
  // Single sequence, sequential rows. All buffers hold FP32. The caller
  // supplies distinct storage and owns initializing, committing and
  // restoring the state. Successive calls consume consecutive rows.
  static void add(metal::CommandGraph &graph, const GlmFlashKdaWeights &weights,
                  const GlmFlashKdaState &state, const GlmFlashKdaBuffers &buffers, uint32_t rows);
};

} // namespace splash::ops
