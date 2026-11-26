#include "MoeFixture.hpp"
#include "MoeStep.hpp"
#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "ops/MoE.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
#include <numeric>
#include <vector>

namespace {
using namespace splash;
constexpr uint32_t experts = 288, hidden = 256, routes = 8, rows = 3;

template <class T>
metal::MetalBuffer upload(metal::MetalBackend &backend, std::span<const T> values) {
  auto buffer = test::sharedBuffer(backend, values.size_bytes());
  std::memcpy(buffer.contents(), values.data(), values.size_bytes());
  return buffer;
}

void check(metal::MetalBackend &backend) {
  const ops::MoeShape shape{.hiddenSize = hidden, .experts = experts, .expertsPerToken = routes,
                            .expertIntermediateSize = 256, .router = ops::MoeRouter::SigmoidNormalized,
                            .sharedSlices = 1, .sharedGate = false, .selectionBias = true};
  test::require(shape.valid(), "GLM Flash MoE shape is not supported");

  std::vector<uint16_t> input(rows * hidden, 0);
  for (uint32_t row = 0; row < rows; ++row) input[row * hidden + row] = 0x3f80; // BF16 1.
  std::vector<float> weights(experts * hidden, 0);
  std::vector<float> bias(experts, 0);
  bias[287] = 1.1f;
  bias[274] = 1.1f;
  bias[260] = 0.8f;
  for (uint32_t id = 0; id < experts; ++id) {
    weights[id * hidden] = float(int((id * 17) % 71) - 35) * 0.11f;
    weights[id * hidden + 1] = -16.0f + float(id % 4) * 0.125f;
    weights[id * hidden + 2] = 0.0f;
  }

  const auto inputBuffer = upload(backend, std::span<const uint16_t>(input));
  const auto router = ops::QuantizedSegment::floats(experts, hidden, upload(backend, std::span<const float>(weights)));
  const auto biasBuffer = upload(backend, std::span<const float>(bias));
  const auto scores = test::sharedBuffer(backend, rows * shape.routerWidth() * sizeof(float));
  const auto selected = test::sharedBuffer(backend, rows * (routes + 1) * sizeof(uint32_t));
  const auto mixture = test::sharedBuffer(backend, rows * (routes + 1) * sizeof(float));

  metal::CommandGraph graph;
  ops::MoE::addRoutes(graph, inputBuffer, router, {}, biasBuffer, scores, selected, mixture, rows, shape,
                     ops::FloatTile::Simdgroup);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());

  const auto *ids = static_cast<const uint32_t *>(selected.contents());
  const auto *values = static_cast<const float *>(mixture.contents());
  for (uint32_t row = 0; row < rows; ++row) {
    std::array<uint32_t, experts> ordered;
    std::iota(ordered.begin(), ordered.end(), 0u);
    std::array<double, experts> probabilities;
    for (uint32_t id = 0; id < experts; ++id)
      probabilities[id] = 1.0 / (1.0 + std::exp(-double(weights[id * hidden + row])));
    std::stable_sort(ordered.begin(), ordered.end(), [&](uint32_t a, uint32_t b) {
      return float(probabilities[a]) + bias[a] > float(probabilities[b]) + bias[b];
    });
    double sum = 0;
    for (uint32_t i = 0; i < routes; ++i) sum += probabilities[ordered[i]];
    const double denominator = std::max(sum, 0x1p-14);
    const auto offset = row * (routes + 1);
    for (uint32_t i = 0; i < routes; ++i) {
      const auto id = ordered[i];
      test::require(ids[offset + i] == id, "GLM Flash selected expert differs");
      test::require(std::abs(values[offset + i] - 2.5 * probabilities[id] / denominator) < 2e-6,
                    "GLM Flash routed weight differs");
    }
    test::require(ids[offset + routes] == experts && values[offset + routes] == 1.0f,
                  "GLM Flash shared expert must have weight one");
  }
}

void checkExpertClamp(metal::MetalBackend &backend, uint32_t count) {
  const ops::MoeShape shape{.hiddenSize = hidden, .experts = experts, .expertsPerToken = routes,
                           .expertIntermediateSize = hidden, .router = ops::MoeRouter::SigmoidNormalized,
                           .sharedSlices = 1, .sharedGate = false, .selectionBias = true};
  const auto quantized = [&](uint32_t numRows, uint32_t period) {
    std::vector<float> values(uint64_t{numRows} * hidden);
    for (uint32_t row = 0; row < numRows; ++row)
      std::fill_n(values.data() + uint64_t{row} * hidden, hidden,
                  (row / period) % 2 ? -0.125f : 0.125f);
    const auto native = gguf_reference::quantizeQ8_0(values);
    return moe_fixture::planeSegment(backend, gguf_reference::Q80,
        gguf_reference::repack(gguf_reference::Q80, native, numRows, hidden, nullptr), numRows, hidden);
  };
  const auto routedGate = quantized(experts * hidden, 1);
  const auto routedUp = quantized(experts * hidden, 2);
  const auto sharedGate = quantized(hidden, 1);
  const auto sharedUp = quantized(hidden, 2);
  ops::BlockMoeWeights weights;
  weights.router = moe_fixture::floatSegment(backend, std::vector<float>(experts * hidden, 0), experts, hidden);
  weights.selectionBias = test::sharedBuffer(backend, experts * sizeof(float));
  std::memset(weights.selectionBias.contents(), 0, weights.selectionBias.sizeBytes());
  weights.gate = {routedGate, sharedGate};
  weights.up = {routedUp, sharedUp};
  weights.down = {routedUp, sharedUp};
  weights.slotTable = model::residentExpertSlots(backend, experts);
  weights.slots = experts;
  weights.chunks = ops::residentExpertChunks(weights);

  const auto plan = ops::MoE::plan(shape, count, ops::MoeConfig{ops::MoeExpertTile::M32});
  moe_fixture::Buffers buffers;
  std::vector<uint16_t> ones(count * hidden, 0x3f80);
  buffers.moe.input = upload(backend, std::span<const uint16_t>(ones));
  buffers.moe.residual = moe_fixture::zeros(backend, ones.size() * 2, "residual");
  buffers.moe.output = moe_fixture::zeros(backend, ones.size() * 2, "output");
  moe_fixture::allocate(backend, buffers, plan);
  metal::CommandGraph graph;
  test::addMoeStep(graph, buffers.moe, weights, plan);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());

  const auto &scratch = buffers.moe.scratch;
  const auto *grouped = static_cast<const uint32_t *>(scratch.routeRows.contents());
  const auto *intermediate = static_cast<const __bf16 *>(scratch.expertIntermediate.contents());
  const float limit = moe_fixture::bf16(100.0 / (1.0 + std::exp(-10.0)));
  for (uint32_t route = 0; route < count * (routes + 1); ++route) {
    const auto *row = intermediate + uint64_t{grouped[route]} * hidden;
    test::require(float(row[0]) == limit && float(row[2]) == -limit,
                  "GLM Flash expert did not clamp its positive gate and signed up activation");
    test::require(std::abs(float(row[1])) < 1e-9f && std::abs(float(row[3])) < 1e-9f,
                  "GLM Flash expert changed its negative gate");
  }
}
} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      test::require(argc == 2, "usage: glm-flash-moe METALLIB");
      metal::MetalBackend backend(argv[1]);
      check(backend);
      checkExpertClamp(backend, 1);
      checkExpertClamp(backend, 32);
      checkExpertClamp(backend, 128);
      checkExpertClamp(backend, 512);
      checkExpertClamp(backend, 1024);
      checkExpertClamp(backend, 2048);
      std::cout << "GLM Flash MoE routes, weights and clamped expert activations match CPU oracle\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
