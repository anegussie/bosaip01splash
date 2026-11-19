#include "TestChecks.hpp"
#include "model/GgufTarget.hpp"
#include "model/GlmFlashRecurrentLayer.hpp"
#include "model/GlmFlashSparseLayer.hpp"
#include "ops/Embedding.hpp"

#include <charconv>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <span>
#include <vector>

namespace {
using namespace splash;
using test::require;

constexpr uint32_t vocabulary = 154880, hidden = GLM_FLASH_HC_HIDDEN;
constexpr uint32_t threads = metal::CommandGraph::kDefaultThreads;

metal::MetalBuffer rawTensor(metal::MetalBackend &backend, const model::GgufFile &file, std::string_view name) {
  const auto &tensor = file.require(name);
  auto result = backend.allocateBuffer(tensor.bytes, metal::BufferStorage::Shared, tensor.name);
  file.source(tensor.file).readData(tensor.offset,
      {static_cast<uint8_t *>(result.contents()), static_cast<size_t>(tensor.bytes)});
  return result;
}

void evaluate(metal::MetalBackend &backend, const std::shared_ptr<const model::OpenGguf> &source,
              std::span<const uint32_t> tokens, const std::filesystem::path &logitsPath) {
  const uint32_t rows = uint32_t(tokens.size());
  const auto allocate = [&](uint64_t bytes, const char *name) {
    return backend.allocateBuffer(bytes, metal::BufferStorage::Shared, name);
  };
  const auto run = [&](metal::CommandGraph &graph) {
    static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
  };
  const auto &file = source->file();
  const auto streams = allocate(uint64_t{rows} * GLM_FLASH_HC_WIDTH * sizeof(float), "glm flash residual");
  {
    auto ids = allocate(tokens.size_bytes(), "glm flash token ids");
    std::memcpy(ids.contents(), tokens.data(), tokens.size_bytes());
    const auto embedded = allocate(uint64_t{rows} * hidden * 2, "glm flash token embeddings");
    const auto format = gguf_format_of(file.require("token_embd.weight").type);
    const ops::EmbeddingWeights embedding(vocabulary, hidden,
        {rawTensor(backend, file, "token_embd.weight"), format});
    metal::CommandGraph graph;
    ops::Embedding::add(graph, ids, embedding, embedded, rows);
    ops::HyperConnection::addInit(graph, embedded, streams, {hidden, GLM_FLASH_HC_STREAMS, 0}, rows);
    run(graph);
  }

  auto blocks = model::glmFlashExpertSources(source);
  constexpr auto shape = model::kGlmFlashMoeShape;
  const uint64_t minimum = model::ExpertStore::minimumBytes(blocks, shape);
  model::ExpertStore experts(backend, std::move(blocks), shape,
      {.memoryBytes = minimum, .floorBytes = minimum, .readers = std::make_shared<model::SsdReaders>(8)});
  // Read-ahead requires a router for the layer that follows each streamed block.
  for (uint32_t layer = model::kGlmFlashFirstMoeBlock; layer < model::Glm5FlashCheckpoint::textLayers; ++layer) {
    auto router = model::loadGlmFlashMoeRouter(backend, file, layer);
    experts.bind(layer - model::kGlmFlashFirstMoeBlock, router);
  }

  const auto start = std::chrono::steady_clock::now();
  for (uint32_t layer = 0; layer < model::Glm5FlashCheckpoint::textLayers; ++layer) {
    @autoreleasepool {
      metal::CommandGraph graph;
      // For this one-shot fixture the weights and state of a finished
      // layer can be released. A serving runtime must retain the state.
      if (layer % 4 == 3) {
        model::GlmFlashSparseLayer block(backend, file, experts, layer, rows, rows);
        block.add(graph, streams, 0, rows);
        run(graph);
      } else {
        model::GlmFlashRecurrentLayer block(backend, file, layer, rows, &experts);
        block.add(graph, streams, rows);
        run(graph);
      }
    }
    if (layer % 8 == 7 || layer + 1 == model::Glm5FlashCheckpoint::textLayers)
      std::cout << "Finished GLM Flash layer " << layer + 1 << std::endl;
  }
  const auto stats = experts.stats();
  require(stats.failure.empty(), "GLM Flash expert store failed: " + stats.failure);
  const auto last = backend.view(streams, uint64_t{rows - 1} * GLM_FLASH_HC_WIDTH * sizeof(float),
                                   GLM_FLASH_HC_WIDTH * sizeof(float));
  const auto reduced = allocate(hidden * sizeof(float), "glm reduced residual");
  const auto normalized = allocate(hidden * sizeof(uint16_t), "glm normalized output");
  const auto norm = rawTensor(backend, file, "output_norm.weight");
  const auto logits = allocate(vocabulary * sizeof(float), "glm logits");
  const auto output = ops::QuantizedSegment::rows(gguf_format_of(file.require("output.weight").type),
                                                vocabulary, hidden, rawTensor(backend, file, "output.weight"));
  metal::CommandGraph graph;
  graph.add("glm_flash_mean_f32", {last, reduced}, {hidden / threads, 1, 1});
  graph.add("glm_flash_layer_rms", {reduced, norm, normalized}, hidden, {1, 1, 1});
  ops::addGgufFloat(graph, normalized, output, logits, 1, vocabulary, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Simdgroup);
  run(graph);
  source->checkUnchanged();

  const auto *values = static_cast<const float *>(logits.contents());
  uint32_t best = 0;
  for (uint32_t i = 0; i < vocabulary; ++i) {
    require(std::isfinite(values[i]), "GLM Flash logit is not finite");
    if (values[i] > values[best]) best = i;
  }
  std::ofstream out(logitsPath, std::ios::binary);
  out.write(reinterpret_cast<const char *>(values), vocabulary * sizeof(float));
  require(bool(out), "could not write GLM Flash logits");
  const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  std::cout << "GLM Flash greedy token: " << best << "\n"
            << "Layer and head wall time: " << wall << " s\n"
            << "Expert source bytes: " << stats.uses[0].readBytes << "\n";
}
} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      require(argc >= 5 && argc <= 36, "usage: glm-flash-forward METALLIB GGUF_DIRECTORY LOGITS_FILE TOKEN [TOKEN...]");
      std::vector<uint32_t> tokens;
      for (int i = 4; i < argc; ++i) {
        const std::string_view text(argv[i]);
        uint32_t token = 0;
        const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), token);
        require(error == std::errc{} && end == text.data() + text.size() && token < vocabulary,
                "invalid GLM Flash token id");
        tokens.push_back(token);
      }
      metal::MetalBackend backend(argv[1]);
      const auto source = std::make_shared<model::OpenGguf>(model::findTargetGgufs(argv[2]));
      evaluate(backend, source, tokens, argv[3]);
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
