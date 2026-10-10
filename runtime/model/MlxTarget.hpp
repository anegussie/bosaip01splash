#pragma once

// Source adapter for a safetensors target, MLX's or Model Optimizer's: its
// block images (model/MlxImage.hpp) are written into memory, and
// QwenTargetLoader reads them as block-quantized weights (BlockTargetFormat).

#include "model/GgufImage.hpp"
#include "model/QwenHybridLayout.hpp"
#include "model/SafetensorsCheckpoint.hpp"
#include "model/WeightImages.hpp"

#include <filesystem>
#include <memory>
#include <vector>

namespace splash::model {

class MlxTargetLoader final {
public:
  // Plans every image of the checkpoint in directory once.
  MlxTargetLoader(metal::MetalBackend &backend, WeightImages &images, const std::filesystem::path &directory,
                  const QwenTargetDimensions &geometry);
  MlxTargetLoader(const MlxTargetLoader &) = delete;
  MlxTargetLoader &operator=(const MlxTargetLoader &) = delete;

  [[nodiscard]] WeightFile layer(uint32_t index);
  [[nodiscard]] WeightFile head();
  [[nodiscard]] WeightFile embedding();
  // Whether its images hold F32 norms (mlx::float32Norms).
  [[nodiscard]] bool float32Norms() const noexcept { return float32Norms_; }

private:
  // The checkpoint and its images, which their writers share.
  struct Planned {
    explicit Planned(const std::filesystem::path &directory) : checkpoint(directory) {}
    SafetensorsCheckpoint checkpoint;
    std::vector<gguf::Image> images; // layers, head, embedding
  };
  [[nodiscard]] WeightFile open(size_t index);

  metal::MetalBackend &backend_;
  WeightImages &images_;
  std::shared_ptr<Planned> planned_;
  bool float32Norms_ = false;
};

// The bytes of every image of the safetensors target in directory.
[[nodiscard]] uint64_t mlxTargetImageBytes(const std::filesystem::path &directory,
                                           const QwenTargetDimensions &geometry);

} // namespace splash::model
