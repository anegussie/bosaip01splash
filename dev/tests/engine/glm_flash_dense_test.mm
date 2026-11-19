#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "model/GgufTarget.hpp"
#include "model/GlmFlashRecurrentLayer.hpp"
#include "model/GlmFlashSparseLayer.hpp"

#include <array>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <vector>

namespace {
using namespace splash;

constexpr uint32_t rows = 32, width = GLM_FLASH_HC_WIDTH;

std::vector<float> read(const std::filesystem::path &path) {
  std::vector<float> values(rows * width);
  std::ifstream input(path, std::ios::binary);
  input.read(reinterpret_cast<char *>(values.data()), std::streamsize(values.size() * sizeof(float)));
  test::require(bool(input) && input.peek() == std::ifstream::traits_type::eof(), "unexpected tensor size: " + path.string());
  return values;
}

template <class Encode>
std::vector<float> run(metal::MetalBackend &backend, Encode encode, std::span<const float> input,
                       std::span<const uint32_t> chunks) {
  const auto streams = test::sharedBuffer(backend, input.size_bytes());
  std::memcpy(streams.contents(), input.data(), input.size_bytes());
  uint32_t first = 0;
  for (const uint32_t count : chunks) {
    metal::CommandGraph graph;
    const auto view = backend.view(streams, uint64_t{first} * width * sizeof(float),
                                   uint64_t{count} * width * sizeof(float));
    encode(graph, view, first, count);
    static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
    first += count;
  }
  test::require(first == rows, "GLM Flash dense layer fixture has incomplete chunks");
  const auto *result = static_cast<const float *>(streams.contents());
  return {result, result + input.size()};
}

double relativeError(std::span<const float> got, std::span<const float> expected, std::span<const float> base) {
  double error = 0, reference = 0;
  for (size_t i = 0; i < got.size(); ++i) {
    const double delta = double(expected[i]) - base[i];
    const double difference = double(got[i]) - expected[i];
    error += difference * difference;
    reference += delta * delta;
  }
  return std::sqrt(error / reference);
}

template <class Encode>
void compareBlock(metal::MetalBackend &backend, const std::filesystem::path &directory,
                   const char *inputFile, const char *outputFile, const char *label, Encode encode,
                   double referenceTolerance, double splitTolerance) {
  const auto input = read(directory / inputFile);
  const auto expected = read(directory / outputFile);
  const auto single = run(backend, encode, input, std::array<uint32_t, 1>{32});
  const auto split = run(backend, encode, input, std::array<uint32_t, 3>{1, 7, 24});
  const double referenceError = relativeError(single, expected, input);
  const double splitError = relativeError(split, single, input);
  std::cout << label << " residual-update relative RMS error: " << referenceError
            << " vs llama.cpp, " << splitError << " vs split execution\n";
  test::require(referenceError < referenceTolerance, "GLM Flash block residual update differs from llama.cpp");
  test::require(splitError < splitTolerance, "GLM Flash block differs across chunk boundaries");
}

} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      const bool sparse = argc == 5 && std::string_view(argv[4]) == "--sparse";
      test::require(argc == 4 || sparse,
                    "usage: glm-flash-dense METALLIB GGUF_DIRECTORY REFERENCE_DIRECTORY [--sparse]");
      const std::filesystem::path reference(argv[3]);
      metal::MetalBackend backend(argv[1]);
      const auto source = std::make_shared<model::OpenGguf>(model::findTargetGgufs(argv[2]));
      if (sparse) {
        auto blocks = model::glmFlashExpertSources(source);
        const uint64_t minimum = model::ExpertStore::minimumBytes(blocks, model::kGlmFlashMoeShape);
        model::ExpertStore experts(backend, std::move(blocks), model::kGlmFlashMoeShape,
            {.memoryBytes = minimum, .floorBytes = minimum, .readers = std::make_shared<model::SsdReaders>(8)});
        auto next = model::loadGlmFlashMoeRouter(backend, source->file(), 4);
        experts.bind(1, next);
        model::GlmFlashSparseLayer layer(backend, source->file(), experts, 3, 8192, rows);
        source->checkUnchanged();
        compareBlock(backend, reference, "l_out-2.f32", "l_out-3.f32", "GLM Flash sparse block 3",
            [&](auto &graph, auto streams, uint32_t first, uint32_t count) {
              layer.add(graph, streams, first, count);
            }, 0.08, 0.01);
        const auto &use = experts.stats().uses[0];
        std::cout << "GLM Flash expert source bytes across both comparisons: " << use.readBytes << '\n';
      } else {
        constexpr std::array inputs{"hc_init.f32", "l_out-0.f32", "l_out-1.f32"};
        constexpr std::array outputs{"l_out-0.f32", "l_out-1.f32", "l_out-2.f32"};
        for (uint32_t block = 0; block < inputs.size(); ++block) {
          if (block > 0 && !std::filesystem::exists(reference / outputs[block])) break;
          model::GlmFlashRecurrentLayer layer(backend, source->file(), block, rows);
          source->checkUnchanged();
          const std::string label = "GLM Flash dense block " + std::to_string(block);
          compareBlock(backend, reference, inputs[block], outputs[block], label.c_str(),
              [&](auto &graph, auto streams, uint32_t first, uint32_t count) {
                if (!first) layer.resetState();
                layer.add(graph, streams, count);
              }, 0.04, 0.002);
        }
      }
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
