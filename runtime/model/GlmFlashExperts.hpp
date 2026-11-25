#pragma once

#include "model/ExpertStore.hpp"
#include "model/Glm5FlashCheckpoint.hpp"

namespace splash::model {

inline constexpr uint32_t kGlmFlashFirstMoeBlock = 3;
inline constexpr ops::MoeShape kGlmFlashMoeShape{
    .hiddenSize = 4096,
    .experts = Glm5FlashCheckpoint::experts,
    .expertsPerToken = Glm5FlashCheckpoint::expertsPerToken,
    .expertIntermediateSize = 2048,
    .router = ops::MoeRouter::SigmoidNormalized,
    .sharedSlices = 1,
    .sharedGate = false,
    .selectionBias = true,
};

// Plans streamed rows in the original shards. The plan holds the open files
// alive for the entire expert store lifetime.
[[nodiscard]] StreamedBlocks glmFlashExpertSources(std::shared_ptr<const OpenGguf> source);

[[nodiscard]] ops::BlockMoeWeights loadGlmFlashMoeRouter(metal::MetalBackend &backend, const GgufFile &source,
                                                       uint32_t layer);
[[nodiscard]] ops::BlockMoeWeights loadGlmFlashMoeBlock(metal::MetalBackend &backend, const GgufFile &source,
                                                      uint32_t layer);

class GlmFlashMoeStep final {
public:
  GlmFlashMoeStep(metal::MetalBackend &backend, const GgufFile &source, ExpertStore &store,
                   uint32_t layer, metal::MetalBuffer input, uint32_t maxRows);
  // Input and output both use BF16. The caller composes its own residual.
  [[nodiscard]] const metal::MetalBuffer &add(metal::CommandGraph &graph, uint32_t rows) const;

private:
  ops::BlockMoeWeights weights_;
  ops::MoeBuffers buffers_;
  uint32_t maxRows_;
};

} // namespace splash::model
