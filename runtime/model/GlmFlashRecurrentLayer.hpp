#pragma once

#include "model/GgufFile.hpp"
#include "model/GlmFlashExperts.hpp"
#include "ops/GlmFlashKda.hpp"
#include "ops/HyperConnection.hpp"

namespace splash::model {

// A GLM Flash KDA block with a dense FFN or a streamed MoE. The block
// takes one sequence and owns its recurrent state.
class GlmFlashRecurrentLayer final {
public:
  GlmFlashRecurrentLayer(metal::MetalBackend &backend, const GgufFile &source, uint32_t layer, uint32_t maxRows,
                         ExpertStore *experts = nullptr, ops::GlmFlashKdaState state = {});

  void add(metal::CommandGraph &graph, metal::MetalBuffer streams, uint32_t rows) const;
  void resetState();
  [[nodiscard]] const ops::GlmFlashKdaState &state() const noexcept { return state_; }

private:
  ops::GlmFlashHyperWeights attentionMix_, ffnMix_;
  metal::MetalBuffer attentionNorm_, ffnNorm_;
  ops::GlmFlashKdaWeights recurrentWeights_;
  ops::GlmFlashKdaState state_;
  std::array<ops::QuantizedSegment, 3> qkv_, ffn_;
  std::array<ops::QuantizedSegment, 2> decay_, gate_;
  ops::QuantizedSegment beta_, attentionOutput_;
  ops::GlmFlashHyperScratch hyperScratch_;
  ops::GlmFlashKdaBuffers kdaScratch_;
  metal::MetalBuffer branch_, normalized_, lowDecay_, lowGate_, lowDecayInput_, lowGateInput_;
  metal::MetalBuffer attended_, ffnGate_, ffnUp_, ffnIntermediate_;
  std::optional<GlmFlashMoeStep> moe_;
  uint32_t maxRows_;
};

} // namespace splash::model
