#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "ops/GlmFlashKda.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
#include <span>
#include <vector>

namespace {
using namespace splash;
using test::require;
constexpr uint32_t heads = 64, dim = 128, channels = heads * dim, rows = 2048;
using Qkv = std::array<std::vector<float>, 3>;

float sample(uint32_t i, uint32_t period, float amplitude) {
  return float(int(i % period) - int(period / 2)) * amplitude;
}

double sigmoid(double x) { return 1.0 / (1.0 + std::exp(-x)); }

struct Fixture {
  Qkv projected, weights, history;
  std::vector<float> matrix, decay, beta, gates, scale, bias, norm;

  Fixture() : matrix(channels * dim), decay(rows * channels), beta(rows * heads),
              gates(rows * channels), scale(heads), bias(channels), norm(dim) {
    for (uint32_t qkv = 0; qkv < 3; ++qkv) {
      projected[qkv].resize(rows * channels);
      weights[qkv].resize(channels * 4);
      history[qkv].resize(channels * 3);
      for (uint32_t i = 0; i < rows * channels; ++i)
        projected[qkv][i] = sample(i * 11 + qkv * 17, 59, 0.065f);
      for (uint32_t i = 0; i < channels * 4; ++i)
        weights[qkv][i] = sample(i * 3 + qkv * 7, 29, 0.04f);
      for (uint32_t i = 0; i < channels * 3; ++i)
        history[qkv][i] = sample(i * 23 + qkv * 19, 61, 0.04f);
    }
    for (uint32_t i = 0; i < channels * dim; ++i) matrix[i] = sample(i * 19, 67, 0.004f);
    for (uint32_t i = 0; i < rows * channels; ++i) {
      decay[i] = sample(i * 7, 41, 0.19f);
      gates[i] = sample(i * 13, 79, 0.04f);
    }
    for (uint32_t i = 0; i < rows * heads; ++i) beta[i] = sample(i * 11, 17, 0.18f);
    for (uint32_t i = 0; i < heads; ++i) scale[i] = -0.2f - 0.03f * i;
    for (uint32_t i = 0; i < channels; ++i) bias[i] = sample(i * 13, 29, 0.11f);
    for (uint32_t i = 0; i < dim; ++i) norm[i] = 1.0f + sample(i * 13, 23, 0.013f);
    // Exercise near-zero Q and K independently of the nonzero-state path.
    for (uint32_t qk = 0; qk < 2; ++qk) {
      std::fill_n(history[qk].begin(), dim * 3, 0.0f);
      std::fill_n(projected[qk].begin(), dim, 0.0f);
    }
  }
};

struct Expected {
  Qkv history;
  std::vector<double> matrix;
  std::vector<double> output;
};

Expected reference(const Fixture &f) {
  Expected expected{f.history, std::vector<double>(f.matrix.begin(), f.matrix.end()),
                    std::vector<double>(rows * channels)};
  for (uint32_t row = 0; row < rows; ++row) {
    for (uint32_t head = 0; head < heads; ++head) {
      const uint32_t base = row * channels + head * dim;
      std::array<std::array<double, dim>, 3> convolved;
      for (uint32_t s = 0; s < 3; ++s) {
        double squares = 0.0;
        for (uint32_t d = 0; d < dim; ++d) {
          const uint32_t ch = head * dim + d;
          auto *history = expected.history[s].data() + ch * 3;
          const float *w = f.weights[s].data() + ch * 4;
          const float fresh = f.projected[s][base + d];
          double conv = double(w[3]) * fresh;
          for (uint32_t tap = 0; tap < 3; ++tap) conv += double(w[tap]) * history[tap];
          history[0] = history[1];
          history[1] = history[2];
          history[2] = fresh;
          convolved[s][d] = conv * sigmoid(conv);
          squares += convolved[s][d] * convolved[s][d];
        }
        if (s < 2)
          for (auto &element : convolved[s]) element /= std::sqrt(squares + 1e-6);
      }
      const auto &[q, k, v] = convolved;
      std::array<double, dim> decay{};
      for (uint32_t d = 0; d < dim; ++d)
        decay[d] = std::exp(-5 * sigmoid(-(double(f.decay[base + d]) + f.bias[head * dim + d]) * f.scale[head]));
      const double beta = sigmoid(f.beta[row * heads + head]);
      auto *output = expected.output.data() + base;
      double squares = 0.0;
      for (uint32_t j = 0; j < dim; ++j) {
        auto *state = expected.matrix.data() + (head * dim + j) * dim;
        double predicted = 0.0;
        for (uint32_t d = 0; d < dim; ++d) {
          state[d] *= decay[d];
          predicted += state[d] * k[d];
        }
        const double delta = (v[j] - predicted) * beta;
        double attended = 0.0;
        for (uint32_t d = 0; d < dim; ++d) {
          state[d] += delta * k[d];
          attended += state[d] * q[d];
        }
        output[j] = attended / std::sqrt(double(dim));
        squares += output[j] * output[j];
      }
      for (uint32_t d = 0; d < dim; ++d)
        output[d] = output[d] * f.norm[d] * sigmoid(f.gates[base + d]) / std::sqrt(squares / dim + 1e-5);
    }
  }
  return expected;
}

metal::MetalBuffer upload(metal::MetalBackend &backend, const std::vector<float> &values) {
  const auto bytes = values.size() * sizeof(float);
  auto result = test::sharedBuffer(backend, bytes);
  std::memcpy(result.contents(), values.data(), bytes);
  return result;
}

template <class Values>
void compare(const Values &expected, const metal::MetalBuffer &result, double tolerance, const char *label) {
  const auto *actual = static_cast<const float *>(result.contents());
  for (size_t i = 0; i < expected.size(); ++i)
    if (!(std::abs(actual[i] - expected[i]) <= tolerance))
      throw std::runtime_error(std::string(label) + " differs at " + std::to_string(i));
}

void check(metal::MetalBackend &backend, const Fixture &f, const Expected &expected, std::span<const uint32_t> chunks) {
  const auto volumes = [&](const Qkv &qkv) {
    return std::array{upload(backend, qkv[0]), upload(backend, qkv[1]), upload(backend, qkv[2])};
  };
  const ops::GlmFlashKdaState state{volumes(f.history), upload(backend, f.matrix)};
  const ops::GlmFlashKdaWeights weights{volumes(f.weights), upload(backend, f.scale),
                                       upload(backend, f.bias), upload(backend, f.norm)};
  const auto qkv = volumes(f.projected);
  const auto decay = upload(backend, f.decay), beta = upload(backend, f.beta), gate = upload(backend, f.gates);
  const auto output = test::sharedBuffer(backend, f.gates.size() * sizeof(float));
  uint32_t start = 0;
  for (const uint32_t chunk : chunks) {
    const auto slice = [&](const metal::MetalBuffer &buf, uint32_t width) {
      const uint64_t rowBytes = width * sizeof(float);
      return backend.view(buf, start * rowBytes, chunk * rowBytes);
    };
    const ops::GlmFlashKdaBuffers buffers{
        {slice(qkv[0], channels), slice(qkv[1], channels), slice(qkv[2], channels)},
        slice(decay, channels), slice(beta, heads), slice(gate, channels), slice(output, channels)};
    metal::CommandGraph graph;
    ops::GlmFlashKda::add(graph, weights, state, buffers, chunk);
    static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
    start += chunk;
  }
  require(start == rows, "GLM Flash KDA fixture has incomplete chunks");
  compare(expected.output, output, 2e-5, "GLM Flash KDA output");
  compare(expected.matrix, state.recurrent, 2e-6, "GLM Flash KDA recurrent state");
  for (uint32_t s = 0; s < 3; ++s)
    compare(expected.history[s], state.convolution[s], 0, "GLM Flash KDA convolution history");
}
} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      require(argc == 2, "usage: glm-flash-kda METALLIB");
      metal::MetalBackend backend(argv[1]);
      const Fixture fixture;
      const Expected expected = reference(fixture);
      check(backend, fixture, expected, std::array<uint32_t, 1>{rows});
      check(backend, fixture, expected, std::array<uint32_t, 9>{1, 7, 24, 96, 128, 128, 128, 512, 1024});
      std::cout << "GLM Flash KDA output and state match the CPU oracle for " << rows << " rows and split chunks\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
