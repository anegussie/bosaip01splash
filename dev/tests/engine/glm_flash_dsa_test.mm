#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "ops/GlmFlashSparseAttention.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <numeric>
#include <span>
#include <vector>

namespace {
using namespace splash;
using test::require;
constexpr uint32_t indexWidth = 128, indexHeads = 32, heads = 64, latentWidth = 512;
constexpr uint32_t poolWidth = 4, topPools = 512, selectionWidth = 2051;
constexpr uint32_t unused = std::numeric_limits<uint32_t>::max();

float value(uint32_t i, uint32_t seed) {
  uint32_t x = i ^ seed;
  x ^= x >> 16;
  x *= 0x7feb352d;
  x ^= x >> 15;
  return float(int(x % 10001) - 5000) / 5000.0f;
}

metal::MetalBuffer upload(metal::MetalBackend &backend, const std::vector<float> &values) {
  const auto bytes = values.size() * sizeof(float);
  auto output = test::sharedBuffer(backend, bytes);
  std::memcpy(output.contents(), values.data(), bytes);
  return output;
}

struct Fixture {
  uint32_t first, rows, end;
  std::vector<float> rawKeys, gates, latents, keyNorm, keyBias, poolBias, indexQueries, indexWeights, queries;
  std::vector<float> keys, pools;

  Fixture(uint32_t prefix, uint32_t tokens)
      : first(prefix), rows(tokens), end(prefix + tokens), rawKeys(end * indexWidth), gates(end * indexWidth),
        latents(end * latentWidth), keyNorm(indexWidth), keyBias(indexWidth), poolBias(poolWidth * indexWidth),
        indexQueries(rows * indexHeads * indexWidth), indexWeights(rows * indexHeads), queries(rows * heads * latentWidth),
        keys(end * indexWidth), pools((end / poolWidth) * indexWidth) {
    for (uint32_t i = 0; i < rawKeys.size(); ++i) {
      rawKeys[i] = value(i, 11);
      gates[i] = value(i, 23) * 2.7f;
    }
    for (uint32_t i = 0; i < latents.size(); ++i) latents[i] = value(i, 31);
    for (uint32_t i = 0; i < indexWidth; ++i) {
      keyNorm[i] = 1.02f + value(i, 41) * 0.27f;
      keyBias[i] = value(i, 59) * 0.32f;
    }
    for (uint32_t i = 0; i < poolBias.size(); ++i) poolBias[i] = value(i, 61);
    for (uint32_t i = 0; i < indexQueries.size(); ++i) indexQueries[i] = value(i, 73);
    for (uint32_t i = 0; i < indexWeights.size(); ++i) indexWeights[i] = value(i, 79);
    for (uint32_t i = 0; i < queries.size(); ++i) queries[i] = value(i, 89) * 0.65f;
    if (first) {
      // Force an exact tie after crossing the sparse threshold.
      std::fill_n(indexQueries.end() - indexHeads * indexWidth, indexHeads * indexWidth, 0.0f);
    }

    for (uint32_t t = 0; t < end; ++t) {
      auto input = rawKeys.begin() + t * indexWidth;
      const double mean = std::accumulate(input, input + indexWidth, 0.0) / indexWidth;
      double variance = 0.0;
      for (uint32_t d = 0; d < indexWidth; ++d) variance += (input[d] - mean) * (input[d] - mean);
      const double inv = 1 / std::sqrt(variance / indexWidth + 1e-6);
      for (uint32_t d = 0; d < indexWidth; ++d)
        keys[t * indexWidth + d] = float((input[d] - mean) * inv * keyNorm[d] + keyBias[d]);
    }
    for (uint32_t p = 0; p < end / poolWidth; ++p) {
      for (uint32_t d = 0; d < indexWidth; ++d) {
        double total = 0, weighted = 0;
        for (uint32_t i = 0; i < poolWidth; ++i) {
          const auto idx = (p * poolWidth + i) * indexWidth + d;
          const double w = std::exp(double(gates[idx]) + poolBias[i * indexWidth + d]);
          total += w;
          weighted += keys[idx] * w;
        }
        pools[p * indexWidth + d] = float(weighted / total);
      }
    }
  }

  double score(uint32_t row, uint32_t p) const {
    double score = 0;
    for (uint32_t h = 0; h < indexHeads; ++h) {
      const auto *q = indexQueries.data() + (row * indexHeads + h) * indexWidth;
      const auto *k = pools.data() + p * indexWidth;
      double dot = 0;
      for (uint32_t d = 0; d < indexWidth; ++d) dot += double(q[d]) * k[d];
      score += std::max(dot, 0.0) * indexWeights[row * indexHeads + h];
    }
    return score / 64.0;
  }

  std::vector<uint32_t> expectedSelection(uint32_t row) const {
    const uint32_t count = first + row + 1, complete = count / poolWidth;
    std::vector<uint32_t> picked;
    if (complete <= topPools) {
      picked.resize(count);
      std::iota(picked.begin(), picked.end(), 0u);
      return picked;
    }
    std::vector<double> scores(complete);
    std::vector<uint32_t> order(complete);
    std::iota(order.begin(), order.end(), 0u);
    for (uint32_t i = 0; i < complete; ++i) scores[i] = score(row, i);
    std::stable_sort(order.begin(), order.end(), [&](uint32_t a, uint32_t b) { return scores[a] > scores[b]; });
    for (uint32_t i = 0; i < topPools; ++i)
      for (uint32_t member = 0; member < poolWidth; ++member)
        picked.push_back(order[i] * poolWidth + member);
    for (uint32_t t = complete * poolWidth; t < count; ++t) picked.push_back(t);
    return picked;
  }
};

void validateAttention(const Fixture &f, uint32_t row, std::span<const uint32_t> picked, const float *output) {
  for (const uint32_t h : {0u, 23u, 63u}) {
    const auto *q = f.queries.data() + (row * heads + h) * latentWidth;
    std::array<double, latentWidth> sum{};
    double denominator = 0;
    for (const uint32_t id : picked) {
      const auto *kv = f.latents.data() + id * latentWidth;
      double dot = 0;
      for (uint32_t d = 0; d < latentWidth; ++d) dot += double(q[d]) * kv[d];
      const double w = std::exp(dot / 16.0);
      for (uint32_t d = 0; d < latentWidth; ++d) sum[d] += kv[d] * w;
      denominator += w;
    }
    for (uint32_t d = 0; d < latentWidth; ++d)
      require(std::abs(float(sum[d] / denominator) - output[h * latentWidth + d]) < 1e-5f,
              "GLM Flash MLA output differs");
  }
}

void check(metal::MetalBackend &backend, const Fixture &f, std::span<const uint32_t> chunks) {
  const auto prefix = [](const std::vector<float> &reference, uint32_t validElements) {
    std::vector<float> seeded(reference.size());
    std::copy_n(reference.begin(), validElements, seeded.begin());
    return seeded;
  };
  const ops::GlmFlashDsaWeights weights{upload(backend, f.keyNorm), upload(backend, f.keyBias),
                                       upload(backend, f.poolBias)};
  const ops::GlmFlashDsaCache cache{f.end, upload(backend, prefix(f.keys, f.first * indexWidth)),
      upload(backend, prefix(f.gates, f.first * indexWidth)),
      upload(backend, prefix(f.pools, (f.first / poolWidth) * indexWidth)),
      upload(backend, prefix(f.latents, f.first * latentWidth))};
  const auto newKeys = upload(backend, f.rawKeys), newGates = upload(backend, f.gates);
  const auto newLatents = upload(backend, f.latents), iq = upload(backend, f.indexQueries);
  const auto iw = upload(backend, f.indexWeights), q = upload(backend, f.queries);
  uint32_t start = 0;
  for (const uint32_t count : chunks) {
    const uint32_t position = f.first + start;
    const auto slice = [&](const metal::MetalBuffer &buffer, uint32_t at, uint32_t width) {
      return backend.view(buffer, uint64_t{at} * width * sizeof(float), uint64_t{count} * width * sizeof(float));
    };
    const auto output = test::sharedBuffer(backend, count * heads * latentWidth * sizeof(float));
    const ops::GlmFlashDsaBuffers buffers{
        slice(newKeys, position, indexWidth), slice(newGates, position, indexWidth),
        slice(iq, start, indexHeads * indexWidth), slice(iw, start, indexHeads),
        slice(newLatents, position, latentWidth), slice(q, start, heads * latentWidth), output};

    const auto numPools = (position + count) / poolWidth;
    ops::GlmFlashDsaScratch scratch;
    if (numPools > topPools) {
      scratch.scores = test::sharedBuffer(backend, count * numPools * sizeof(float));
      scratch.selected = test::sharedBuffer(backend, count * selectionWidth * sizeof(uint32_t));
    }
    metal::CommandGraph graph;
    ops::GlmFlashSparseAttention::add(graph, weights, cache, buffers, scratch, position, count);
    static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
    for (uint32_t row = 0; row < count; ++row) {
      auto selection = f.expectedSelection(start + row);
      if ((position + row + 1) / poolWidth > topPools) {
        const auto *ids = static_cast<const uint32_t *>(scratch.selected.contents()) + row * selectionWidth;
        auto ordered = selection;
        auto actual = std::vector<uint32_t>(ids, ids + selection.size());
        std::sort(ordered.begin(), ordered.end());
        std::sort(actual.begin(), actual.end());
        require(ordered == actual, "GLM Flash pool selection differs");
        for (uint32_t i = uint32_t(selection.size()); i < selectionWidth; ++i)
          require(ids[i] == unused, "GLM Flash sparse tail must be padded");
      }
      validateAttention(f, start + row, selection,
                        static_cast<const float *>(output.contents()) + row * heads * latentWidth);
    }
    start += count;
  }
  require(start == f.rows, "GLM Flash sparse attention fixture has incomplete chunks");
  const auto *actualPools = static_cast<const float *>(cache.pools.contents());
  for (uint32_t d = 0; d < f.pools.size(); ++d)
    require(std::abs(f.pools[d] - actualPools[d]) < 2e-6f, "GLM Flash pooled key differs");
  const auto *actualKeys = static_cast<const float *>(cache.keys.contents());
  for (uint32_t d = 0; d < f.keys.size(); ++d)
    require(std::abs(f.keys[d] - actualKeys[d]) < 2e-6f, "GLM Flash index key cache differs");
  require(std::memcmp(cache.gates.contents(), f.gates.data(), f.gates.size() * sizeof(float)) == 0,
          "GLM Flash index gate cache differs");
  require(std::memcmp(cache.latents.contents(), f.latents.data(), f.latents.size() * sizeof(float)) == 0,
          "GLM Flash latent cache differs");
}

} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      require(argc == 2, "usage: glm-flash-dsa METALLIB");
      metal::MetalBackend backend(argv[1]);
      const Fixture dense(0, 32);
      check(backend, dense, std::array<uint32_t, 1>{32});
      check(backend, dense, std::array<uint32_t, 4>{3, 1, 9, 19});
      const Fixture sparse(2046, 8);
      check(backend, sparse, std::array<uint32_t, 1>{8});
      check(backend, sparse, std::array<uint32_t, 3>{5, 1, 2});
      std::cout << "GLM Flash DSA cache, causal pool selection and latent attention match the CPU oracle\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
