#pragma once

#include "model/GlmFlashRecurrentLayer.hpp"
#include "model/GlmFlashSparseLayer.hpp"

#include <functional>

namespace splash::model {

// A single native GLM sequence. Resident memory holds recurrent state and
// the expert arena. Layer weights are read into Metal one block at a time.
class GlmFlashSequence final {
public:
  static constexpr uint32_t vocabulary = 154880;
  static constexpr uint32_t chunkRows = 2048;

  GlmFlashSequence(metal::MetalBackend &backend, const std::filesystem::path &directory, uint32_t capacity);
  void reset() noexcept;
  // Advances consecutive positions. An interrupted evaluation returns no
  // logits. The caller resets the sequence before starting another request.
  [[nodiscard]] std::span<const float> evaluate(std::span<const uint32_t> tokens, bool logits,
                                                const std::function<bool()> &interrupt);
  [[nodiscard]] uint64_t expertReadBytes() const;

private:
  metal::MetalBackend &backend_;
  std::shared_ptr<const OpenGguf> source_;
  std::unique_ptr<ExpertStore> experts_;
  ops::EmbeddingWeights embedding_;
  ops::QuantizedSegment output_;
  metal::MetalBuffer norm_, logits_, tokens_, embedded_, residual_, reduced_, normalized_;
  std::array<ops::GlmFlashKdaState, Glm5FlashCheckpoint::textLayers> recurrent_{};
  std::array<ops::GlmFlashDsaCache, Glm5FlashCheckpoint::textLayers> sparse_{};
  uint32_t capacity_;
  uint32_t position_ = 0;
};

} // namespace splash::model
