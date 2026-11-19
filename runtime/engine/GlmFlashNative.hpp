#pragma once

#include <cstdint>
#include <filesystem>

namespace splash::engine {
int serveGlmFlash(const std::filesystem::path &metallib, const std::filesystem::path &directory, uint32_t capacity);
} // namespace splash::engine
