#pragma once

#include <functional>
#include <variant>

namespace splash::model {

// Names the files a target is read from without the loaders' headers, so a
// family's header declares its loader alone; QwenTargetLoader.hpp reads the
// files.
class AffineTargetLoader;
class GgufTargetLoader;

// The files a target is read from: the images a loader writes from an MLX or
// GGUF source.
using QwenTargetFiles =
    std::variant<std::reference_wrapper<AffineTargetLoader>, std::reference_wrapper<GgufTargetLoader>>;

} // namespace splash::model
