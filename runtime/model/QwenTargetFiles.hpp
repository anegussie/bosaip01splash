#pragma once

#include <functional>
#include <variant>

namespace splash::model {

// Names the files a target is read from without the loaders' headers, so a
// family's header declares its loader alone; QwenTargetLoader.hpp reads the
// files.
class AffineTargetLoader;
class GgufTargetLoader;
class MlxTargetLoader;

// The files a target is read from: the images a loader writes from an MLX
// source (affine images, or block images in its MLX formats) or a GGUF.
using QwenTargetFiles =
    std::variant<std::reference_wrapper<AffineTargetLoader>, std::reference_wrapper<GgufTargetLoader>,
                 std::reference_wrapper<MlxTargetLoader>>;

} // namespace splash::model
