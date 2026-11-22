#pragma once

#include "metal/MetalBackend.hpp"

#include <filesystem>
#include <functional>
#include <memory>
#include <span>

namespace splash::model {

struct InklingExpertCacheStats {
  uint64_t lookups = 0;
  uint64_t hits = 0;
  uint64_t readBytes = 0;
};

struct InklingExecutionStats {
  double attentionAndRoutingSeconds = 0;
  double expertStageSeconds = 0;
  double expertWaitSeconds = 0;
  double expertGpuSeconds = 0;
  uint64_t expertCommands = 0;
};

struct InklingCacheBudget {
  uint64_t metalBytes = 0;
  std::function<uint64_t(uint64_t maximum, uint64_t resident)> hostCap;
};

// Target-only reference path for the native Inkling graphs. It stages selected
// expert slices from the GGUF and keeps a separate cache for each layer visit.
class InklingSequence final {
public:
  static constexpr uint32_t chunkRows = 2048;
  static constexpr uint32_t maximumContext = 131'072;

  InklingSequence(metal::MetalBackend &backend, const std::filesystem::path &gguf, uint32_t capacity,
                  InklingCacheBudget cacheBudget = {});
  ~InklingSequence();
  void reset() noexcept;
  // One reusable prompt boundary. Global KV is append-only and can share
  // storage. Sliding KV and convolution state are copied before reuse.
  [[nodiscard]] uint32_t restorePrefix(std::span<const uint32_t> tokens);
  [[nodiscard]] std::span<const float> prefixLogits() const noexcept;
  void rememberPrompt(std::span<const uint32_t> tokens, std::span<const float> logits);
  void releasePrefix() noexcept;
  void releaseExperts() noexcept;
  [[nodiscard]] uint64_t expertReadBytes() const noexcept;
  [[nodiscard]] uint64_t expertCacheBytes() const noexcept;
  [[nodiscard]] uint64_t protectedExpertCacheBytes() const noexcept;
  [[nodiscard]] uint64_t expertBudgetBytes() const noexcept;
  [[nodiscard]] uint64_t maximumExpertBudgetBytes() const noexcept;
  // Ordinary layers first, followed by one entry per core pass.
  [[nodiscard]] std::span<const InklingExpertCacheStats> expertCacheStats() const noexcept;
  [[nodiscard]] std::span<const InklingExecutionStats> executionStats() const noexcept;
  [[nodiscard]] metal::MetalMemoryStats memoryStats() const noexcept;
  [[nodiscard]] std::span<const float> evaluate(std::span<const uint32_t> tokens, bool logits,
                                                const std::function<bool()> &interrupted);

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace splash::model
