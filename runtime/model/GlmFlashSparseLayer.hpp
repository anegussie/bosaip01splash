#pragma once

#include "model/GlmFlashExperts.hpp"
#include "ops/GlmFlashSparseAttention.hpp"
#include "ops/HyperConnection.hpp"

namespace splash::model {

// A GLM Flash indexed MLA block followed by its streamed MoE. The caller
// binds the routers for the other blocks before using read-ahead and owns the
// sequence position. Prefix rows below firstPosition must already be valid.
class GlmFlashSparseLayer final {
public:
  GlmFlashSparseLayer(metal::MetalBackend &backend, const GgufFile &source, ExpertStore &experts,
                      uint32_t layer, uint32_t capacity, uint32_t maxRows, ops::GlmFlashDsaCache cache = {});

  void add(metal::CommandGraph &graph, metal::MetalBuffer streams, uint32_t firstPosition,
           uint32_t rows) const;
  [[nodiscard]] const ops::GlmFlashDsaCache &cache() const noexcept { return cache_; }

private:
  ops::GlmFlashHyperWeights attentionMix_, ffnMix_;
  ops::GlmFlashHyperScratch hyperScratch_;
  ops::GlmFlashDsaWeights index_;
  ops::GlmFlashDsaCache cache_;
  ops::GlmFlashDsaBuffers attention_;
  ops::GlmFlashDsaScratch indexScratch_;
  ops::QuantizedSegment queryA_, queryB_, latent_, indexKey_, indexGate_, indexQuery_, indexHead_, output_;
  metal::MetalBuffer attentionNorm_, ffnNorm_, queryNorm_, latentNorm_, keyAbsorption_, valueProjection_;
  metal::MetalBuffer branch_, bfloat_, queryLow_, queryExpanded_, latentRaw_, attended_;
  std::optional<GlmFlashMoeStep> moe_;
  uint32_t maxRows_;
};

} // namespace splash::model
