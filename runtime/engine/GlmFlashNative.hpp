#pragma once

#include <cstdint>
#include <filesystem>

namespace splash::engine {
int serveGlmFlash(const std::filesystem::path &metallib, const std::filesystem::path &directory, uint32_t capacity);
[[nodiscard]] uint32_t inklingMaximumContext() noexcept;
int serveInkling(const std::filesystem::path &metallib, const std::filesystem::path &gguf, uint32_t capacity);
} // namespace splash::engine
