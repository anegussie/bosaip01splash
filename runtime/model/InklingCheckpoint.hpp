#pragma once

#include "metal/abi/Inkling.h"
#include "model/GgufFile.hpp"

namespace splash::model {

// The layout used by the original Unsloth Inkling 2 Mini text GGUF.
class InklingCheckpoint final {
public:
  static constexpr uint32_t physicalLayers = 24, logicalLayers = 48;
  static constexpr uint32_t coreBegin = 6, coreEnd = 18, passes = 3;
  static constexpr uint32_t window = SPLASH_INKLING_WINDOW, context = SPLASH_INKLING_CONTEXT;
  static constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, queryHeads = SPLASH_INKLING_QUERY_HEADS;
  static constexpr uint32_t kvHeads = SPLASH_INKLING_KV_HEADS, headWidth = SPLASH_INKLING_HEAD_WIDTH;
  static constexpr uint32_t experts = SPLASH_INKLING_EXPERTS, expertsPerToken = SPLASH_INKLING_TOP_K;
  static constexpr uint32_t expertWidth = SPLASH_INKLING_EXPERT_WIDTH;
  static constexpr uint32_t vocabulary = 200'058, paddedVocabulary = 201'024;

  struct Visit {
    uint32_t physicalLayer;
    uint32_t stateSlot;
    uint32_t pass;
    bool sliding;
  };

  explicit InklingCheckpoint(const GgufFile &file);

  [[nodiscard]] const std::array<Visit, logicalLayers> &visits() const noexcept { return visits_; }
  [[nodiscard]] uint64_t residentTensorBytes() const noexcept { return residentTensorBytes_; }
  [[nodiscard]] uint64_t expertTensorBytes() const noexcept { return expertTensorBytes_; }
  // Raw BF16 K and V payload for one sequence. Page alignment and
  // the convolution histories are accounted for separately.
  [[nodiscard]] uint64_t bf16KvBytes(uint32_t tokens) const;

private:
  std::array<Visit, logicalLayers> visits_{};
  uint64_t residentTensorBytes_ = 0;
  uint64_t expertTensorBytes_ = 0;
};

} // namespace splash::model
