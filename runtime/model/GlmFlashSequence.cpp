#include "model/GlmFlashSequence.hpp"

#include "model/GgufTarget.hpp"
#include "ops/Embedding.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace splash::model {
namespace {
constexpr uint32_t hidden = GLM_FLASH_HC_HIDDEN;
constexpr uint32_t threads = metal::CommandGraph::kDefaultThreads;

metal::MetalBuffer rawTensor(metal::MetalBackend &backend, const GgufFile &file, std::string_view name) {
  const auto &tensor = file.require(name);
  auto result = backend.allocateBuffer(tensor.bytes, metal::BufferStorage::Shared, tensor.name);
  file.source(tensor.file).readData(tensor.offset,
      {static_cast<uint8_t *>(result.contents()), static_cast<size_t>(tensor.bytes)});
  return result;
}
}

GlmFlashSequence::GlmFlashSequence(metal::MetalBackend &backend, const std::filesystem::path &directory,
                                   uint32_t capacity)
    : backend_(backend), source_(std::make_shared<OpenGguf>(findTargetGgufs(directory))), capacity_(capacity) {
  if (!capacity_ || capacity_ > GLM_FLASH_DSA_CONTEXT)
    throw std::invalid_argument("GLM Flash context must be between 1 and 8192");
  auto blocks = glmFlashExpertSources(source_);
  const uint64_t minimum = ExpertStore::minimumBytes(blocks, kGlmFlashMoeShape);
  experts_ = std::make_unique<ExpertStore>(backend_, std::move(blocks), kGlmFlashMoeShape,
      ExpertStoreOptions{.memoryBytes = minimum, .floorBytes = minimum, .readers = std::make_shared<SsdReaders>(8)});
  const auto &file = source_->file();
  for (uint32_t layer = kGlmFlashFirstMoeBlock; layer < Glm5FlashCheckpoint::textLayers; ++layer) {
    auto router = loadGlmFlashMoeRouter(backend_, file, layer);
    experts_->bind(layer - kGlmFlashFirstMoeBlock, router);
  }
  embedding_ = ops::EmbeddingWeights(vocabulary, hidden, {rawTensor(backend_, file, "token_embd.weight"),
                                      gguf_format_of(file.require("token_embd.weight").type)});
  output_ = ops::QuantizedSegment::rows(gguf_format_of(file.require("output.weight").type), vocabulary, hidden,
                                        rawTensor(backend_, file, "output.weight"));
  norm_ = rawTensor(backend_, file, "output_norm.weight");
  const auto allocate = [&](uint64_t bytes, const char *name) {
    return backend_.allocateBuffer(bytes, metal::BufferStorage::Shared, name);
  };
  tokens_ = allocate(chunkRows * sizeof(uint32_t), "glm token ids");
  embedded_ = allocate(chunkRows * hidden * sizeof(uint16_t), "glm token embeddings");
  residual_ = allocate(chunkRows * GLM_FLASH_HC_WIDTH * sizeof(float), "glm residual streams");
  reduced_ = allocate(hidden * sizeof(float), "glm reduced residual");
  normalized_ = allocate(hidden * sizeof(uint16_t), "glm normalized output");
  logits_ = allocate(vocabulary * sizeof(float), "glm logits");
  source_->checkUnchanged();
}

void GlmFlashSequence::reset() noexcept {
  position_ = 0;
  recurrent_ = {};
  sparse_ = {};
}

std::span<const float> GlmFlashSequence::evaluate(std::span<const uint32_t> tokens, bool logits,
                                                   const std::function<bool()> &interrupt) {
  if (tokens.empty() || tokens.size() > chunkRows || uint64_t{position_} + tokens.size() > capacity_ ||
      std::ranges::any_of(tokens, [](uint32_t id) { return id >= vocabulary; }))
    throw std::invalid_argument("invalid GLM Flash input chunk");
  const uint32_t rows = uint32_t(tokens.size());
  const auto run = [&](metal::CommandGraph &graph) {
    static_cast<void>(backend_.submitCommandAsync(graph.command()).wait());
  };
  std::memcpy(tokens_.contents(), tokens.data(), tokens.size_bytes());
  {
    metal::CommandGraph graph;
    ops::Embedding::add(graph, tokens_, embedding_, embedded_, rows);
    ops::HyperConnection::addInit(graph, embedded_, residual_, {hidden, GLM_FLASH_HC_STREAMS, 0}, rows);
    run(graph);
  }
  const auto &file = source_->file();
  for (uint32_t layer = 0; layer < Glm5FlashCheckpoint::textLayers; ++layer) {
    if (interrupt()) return {};
    metal::CommandGraph graph;
    if (layer % 4 == 3) {
      GlmFlashSparseLayer block(backend_, file, *experts_, layer, capacity_, rows, sparse_[layer]);
      block.add(graph, residual_, position_, rows);
      run(graph);
      sparse_[layer] = block.cache();
    } else {
      GlmFlashRecurrentLayer block(backend_, file, layer, rows, experts_.get(), recurrent_[layer]);
      block.add(graph, residual_, rows);
      run(graph);
      recurrent_[layer] = block.state();
    }
  }
  source_->checkUnchanged();
  position_ += rows;
  if (!logits || interrupt()) return {};

  const auto last = backend_.view(residual_, uint64_t{rows - 1} * GLM_FLASH_HC_WIDTH * sizeof(float),
                                  GLM_FLASH_HC_WIDTH * sizeof(float));
  metal::CommandGraph graph;
  graph.add("glm_flash_mean_f32", {last, reduced_}, {hidden / threads, 1, 1});
  graph.add("glm_flash_layer_rms", {reduced_, norm_, normalized_}, hidden, {1, 1, 1});
  ops::addGgufFloat(graph, normalized_, output_, logits_, 1, vocabulary, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Simdgroup);
  run(graph);
  std::span<const float> values{static_cast<const float *>(logits_.contents()), vocabulary};
  if (std::ranges::any_of(values, [](float value) { return !std::isfinite(value); }))
    throw std::runtime_error("GLM Flash produced non-finite logits");
  return values;
}

uint64_t GlmFlashSequence::expertReadBytes() const { return experts_->readBytes(); }

} // namespace splash::model
