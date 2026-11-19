#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "ops/HyperConnection.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
#include <vector>

namespace {

using namespace splash;

constexpr uint32_t hidden = 4096, channels = 4, width = hidden * channels;
constexpr uint32_t mixes = 24, blockSize = 32, blockBytes = 34;
constexpr double epsilon = 1e-6;

struct Fixture {
  std::vector<uint8_t> projection = std::vector<uint8_t>(mixes * width / blockSize * blockBytes);
  std::array<float, 3> scale{0.6f, -1.2f, 1.3f};
  std::array<float, mixes> bias{};

  Fixture() {
    for (uint32_t i = 0; i < mixes; ++i) {
      bias[i] = float(int((i * 13) % 23) - 11) * (i < 8 ? 0.08f : 0.55f);
      for (uint32_t b = 0; b < width / blockSize; ++b) {
        uint8_t *dst = projection.data() + (i * (width / blockSize) + b) * blockBytes;
        dst[1] = (b % 5 == 0) ? 0x24 : 0x20; // FP16 1/64 or 1/128.
        for (uint32_t lane = 0; lane < blockSize; ++lane)
          dst[2 + lane] = uint8_t(int((73 * i + 29 * b + 13 * lane) % 31) - 15);
      }
    }
  }

  double weight(uint32_t i, uint32_t d) const {
    const uint32_t block = d / blockSize;
    const uint8_t *src = projection.data() + (i * width / blockSize + block) * blockBytes;
    return double(static_cast<int8_t>(src[2 + d % blockSize])) * (block % 5 == 0 ? 1 / 64.0 : 1 / 128.0);
  }
};

std::array<double, mixes> coefficients(const Fixture &fixture, const float *input) {
  double squares = 0;
  for (uint32_t d = 0; d < width; ++d) squares += double(input[d]) * input[d];
  const double rms = std::sqrt(squares / width + 1e-5);
  std::array<double, mixes> mix{};
  for (uint32_t i = 0; i < mixes; ++i) {
    double dot = 0;
    for (uint32_t d = 0; d < width; ++d) dot += fixture.weight(i, d) * double(input[d]) / rms;
    mix[i] = dot * fixture.scale[i < 4 ? 0 : i < 8 ? 1 : 2] + fixture.bias[i];
    if (i < 4) mix[i] = 1 / (1 + std::exp(-mix[i])) + epsilon;
    else if (i < 8) mix[i] = 2 / (1 + std::exp(-mix[i]));
  }
  for (uint32_t s = 0; s < channels; ++s) {
    double *row = mix.data() + 8 + s * channels;
    const double max = *std::max_element(row, row + channels);
    double sum = 0;
    for (uint32_t d = 0; d < channels; ++d) sum += std::exp(row[d] - max);
    for (uint32_t d = 0; d < channels; ++d) row[d] = std::exp(row[d] - max) / sum + epsilon;
  }
  auto normalize = [&](bool columns) {
    const uint32_t step = columns ? channels : 1;
    for (uint32_t i = 0; i < channels; ++i) {
      auto *first = mix.data() + 8 + i * (columns ? 1 : channels);
      double sum = epsilon;
      for (uint32_t j = 0; j < channels; ++j) sum += first[j * step];
      for (uint32_t j = 0; j < channels; ++j) first[j * step] /= sum;
    }
  };
  normalize(true);
  for (uint32_t i = 1; i < 20; ++i) {
    normalize(false);
    normalize(true);
  }
  return mix;
}

template <class Values>
metal::MetalBuffer upload(metal::MetalBackend &backend, const Values &values) {
  const auto bytes = values.size() * sizeof(typename Values::value_type);
  auto buffer = test::sharedBuffer(backend, bytes);
  std::memcpy(buffer.contents(), values.data(), bytes);
  return buffer;
}

void run(metal::MetalBackend &backend, metal::CommandGraph &graph) {
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
}

void check(metal::MetalBackend &backend, uint32_t rows) {
  const Fixture fixture;
  std::vector<float> original(rows * width);
  std::vector<float> branch(rows * hidden);
  for (uint32_t r = 0; r < rows; ++r) {
    for (uint32_t d = 0; d < width; ++d)
      original[r * width + d] = (rows > 1 && r == 0) ? 0.0f
          : std::sin(float(29 * r + 37 * d + 7) * 0.013f) + float(d / hidden) * 0.2f;
    for (uint32_t d = 0; d < hidden; ++d)
      branch[r * hidden + d] = std::cos(float(41 * r + d) * 0.02f);
  }
  const auto streams = upload(backend, original);
  const auto branchOutput = upload(backend, branch);
  const auto branchInput = test::sharedBuffer(backend, branch.size() * sizeof(float));
  const ops::GlmFlashHyperWeights weights{
      upload(backend, fixture.projection), upload(backend, fixture.scale), upload(backend, fixture.bias)};
  const ops::GlmFlashHyperScratch scratch{
      test::sharedBuffer(backend, rows * sizeof(float)), test::sharedBuffer(backend, rows * mixes * sizeof(float))};
  metal::CommandGraph graph;
  ops::GlmFlashHyperConnection::addPre(graph, streams, weights, scratch, branchInput, rows);
  ops::GlmFlashHyperConnection::addPost(graph, streams, branchOutput, scratch.coefficients, rows);
  run(backend, graph);

  const auto *mixed = static_cast<const float *>(branchInput.contents());
  const auto *state = static_cast<const float *>(streams.contents());
  const auto *gates = static_cast<const float *>(scratch.coefficients.contents());
  for (uint32_t r = 0; r < rows; ++r) {
    const auto *old = original.data() + r * width;
    const auto mix = coefficients(fixture, old);
    for (uint32_t i = 0; i < mixes; ++i)
      test::require(std::abs(mix[i] - gates[r * mixes + i]) < 2e-5, "GLM hyper-connection coefficient mismatch");
    for (uint32_t d = 0; d < hidden; ++d) {
      double pre = 0;
      for (uint32_t s = 0; s < channels; ++s) pre += mix[s] * old[s * hidden + d];
      test::require(std::abs(pre - mixed[r * hidden + d]) < 4e-5, "GLM hyper-connection input mismatch");
      for (uint32_t dst = 0; dst < channels; ++dst) {
        double post = mix[4 + dst] * branch[r * hidden + d];
        for (uint32_t src = 0; src < channels; ++src)
          post += mix[8 + src * channels + dst] * old[src * hidden + d];
        test::require(std::abs(post - state[r * width + dst * hidden + d]) < 4e-5,
                      "GLM hyper-connection residual mismatch");
      }
    }
  }
}

} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      test::require(argc == 2, "usage: glm-flash-hyper METALLIB");
      metal::MetalBackend backend(argv[1]);
      check(backend, 1);
      check(backend, 32);
      std::cout << "GLM Flash hyper-connections match the CPU oracle for 1 and 32 rows\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
