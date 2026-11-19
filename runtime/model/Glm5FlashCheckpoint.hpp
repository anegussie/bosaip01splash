#pragma once

#include "model/GgufFile.hpp"

namespace splash::model {

enum class Glm5FlashTensorRole { Target, RoutedExpert, Auxiliary };

struct Glm5FlashTensor {
  const GgufTensor *tensor;
  Glm5FlashTensorRole role;
  // A routed expert occupies one contiguous slice in GGUF tensor order.
  uint64_t expertStrideBytes = 0;
};

struct Glm5FlashCheckpoint {
  static constexpr uint32_t textLayers = 45;
  static constexpr uint32_t experts = 288;
  static constexpr uint32_t expertsPerToken = 8;

  // The format and layout of the supported Flash target. Kernel support
  // and Metal allocation are separate from validating the source.
  explicit Glm5FlashCheckpoint(const GgufFile &file);

  // Tensor pointers borrow the GgufFile for the lifetime of the inventory.
  std::vector<Glm5FlashTensor> tensors;
  uint64_t targetBytes = 0;
  uint64_t routedExpertBytes = 0;
  uint64_t auxiliaryBytes = 0;
};

} // namespace splash::model
