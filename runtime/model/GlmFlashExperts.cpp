#include "model/GlmFlashExperts.hpp"

#include "model/GgufImageLayout.hpp"
#include "model/GgufPreparation.hpp"

#include <cstring>
#include <utility>

namespace splash::model {
namespace {

std::string expertPrefix(const GgufFile &source, uint32_t layer) {
  if (source.metadata().architecture() != "glm5-next" ||
      layer < kGlmFlashFirstMoeBlock || layer >= Glm5FlashCheckpoint::textLayers)
    throw GgufError("invalid GLM Flash expert layer");
  return "blk." + std::to_string(layer) + ".";
}

metal::MetalBuffer load(metal::MetalBackend &backend, const GgufFile &source, const GgufTensor &tensor) {
  const auto buffer = backend.allocateBuffer(tensor.bytes, metal::BufferStorage::Shared, tensor.name);
  source.source(tensor.file).readData(tensor.offset,
      {static_cast<uint8_t *>(buffer.contents()), static_cast<size_t>(tensor.bytes)});
  return buffer;
}

ops::QuantizedSegment sharedExpert(metal::MetalBackend &backend, const GgufFile &source,
                                   const GgufTensor &tensor, uint32_t rows, uint32_t columns) {
  gguf::Repack repack;
  repack.format = gguf_format_of(tensor.type);
  if (repack.format == GGUF_FMT_COUNT || tensor.dims != std::vector<uint64_t>{columns, rows})
    throw GgufError("invalid GLM Flash shared expert: " + tensor.name);
  repack.rows = rows;
  repack.columns = columns;
  const auto &format = kQuantFormats[repack.format];
  repack.sources.push_back({tensor.name, tensor.type, tensor.offset, rows, ggufRowBytes(format, columns), {},
                            &source.source(tensor.file)});
  const auto sizes = ggufPlaneBytes(format, rows, columns);
  const auto align = [](uint64_t bytes) { return (bytes + 16383) & ~uint64_t{16383}; };
  repack.plane1 = sizes.plane1 ? align(sizes.plane0) : 0;
  repack.meta = align(align(sizes.plane0) + sizes.plane1);
  gguf::Image plan;
  plan.bytes = repack.meta + sizes.meta;
  plan.repacks.push_back(repack);
  const auto image = backend.allocateBuffer(plan.bytes, metal::BufferStorage::Shared, tensor.name);
  writeGgufImage(backend, image, plan);
  return ops::QuantizedSegment::planes(repack.format, rows, columns,
      backend.view(image, 0, sizes.plane0),
      sizes.plane1 ? backend.view(image, repack.plane1, sizes.plane1) : metal::MetalBuffer{},
      backend.view(image, repack.meta, sizes.meta));
}

} // namespace

StreamedBlocks glmFlashExpertSources(std::shared_ptr<const OpenGguf> source) {
  if (!source) throw std::invalid_argument("GLM Flash expert sources require an open checkpoint");
  const auto &file = source->file();
  (void)Glm5FlashCheckpoint(file);
  StreamedBlocks result;
  result.sources = source;
  result.checks.push_back([source] { source->checkUnchanged(); });
  constexpr std::string_view projections[] = {"ffn_gate_exps.weight", "ffn_up_exps.weight", "ffn_down_exps.weight"};
  for (uint32_t layer = kGlmFlashFirstMoeBlock; layer < Glm5FlashCheckpoint::textLayers; ++layer) {
    auto &block = result.blocks.emplace_back();
    const std::string prefix = "blk." + std::to_string(layer) + ".";
    for (size_t i = 0; i < std::size(projections); ++i) {
      const auto &tensor = file.require(prefix + std::string(projections[i]));
      const auto format = gguf_format_of(tensor.type);
      if (format == GGUF_FMT_COUNT) throw GgufError("unsupported GLM Flash expert format: " + tensor.name);
      const auto rowBytes = ggufRowBytes(kQuantFormats[format], tensor.columns());
      auto &repack = block.projections[i];
      repack.format = format;
      repack.rows = tensor.rows();
      repack.columns = tensor.columns();
      repack.sources.push_back({tensor.name, tensor.type, tensor.offset, tensor.rows(), rowBytes, {},
                                &file.source(tensor.file)});
    }
  }
  source->checkUnchanged();
  return result;
}

ops::BlockMoeWeights loadGlmFlashMoeRouter(metal::MetalBackend &backend, const GgufFile &source, uint32_t layer) {
  const auto prefix = expertPrefix(source, layer);
  constexpr uint32_t hidden = kGlmFlashMoeShape.hiddenSize, experts = kGlmFlashMoeShape.experts;
  const auto &router = source.require(prefix + "ffn_gate_inp.weight");
  const auto &bias = source.require(prefix + "exp_probs_b.bias");
  if (router.type != ggml::kF32 || router.dims != std::vector<uint64_t>{hidden, experts} ||
      bias.type != ggml::kF32 || bias.dims != std::vector<uint64_t>{experts})
    throw GgufError("invalid GLM Flash expert router tensors");
  ops::BlockMoeWeights weights;
  weights.router = ops::QuantizedSegment::floats(experts, hidden, load(backend, source, router));
  weights.selectionBias = load(backend, source, bias);
  return weights;
}

ops::BlockMoeWeights loadGlmFlashMoeBlock(metal::MetalBackend &backend, const GgufFile &source, uint32_t layer) {
  const std::string prefix = expertPrefix(source, layer);
  auto weights = loadGlmFlashMoeRouter(backend, source, layer);
  constexpr uint32_t hidden = kGlmFlashMoeShape.hiddenSize, intermediate = kGlmFlashMoeShape.expertIntermediateSize;
  weights.gate.shared = sharedExpert(backend, source, source.require(prefix + "ffn_gate_shexp.weight"),
                                     intermediate, hidden);
  weights.up.shared = sharedExpert(backend, source, source.require(prefix + "ffn_up_shexp.weight"),
                                   intermediate, hidden);
  weights.down.shared = sharedExpert(backend, source, source.require(prefix + "ffn_down_shexp.weight"),
                                     hidden, intermediate);
  return weights;
}

namespace {
constexpr ops::MoeConfig moeConfig{ops::MoeExpertTile::M32};
}

GlmFlashMoeStep::GlmFlashMoeStep(metal::MetalBackend &backend, const GgufFile &source, ExpertStore &store,
                                 uint32_t layer, metal::MetalBuffer input, uint32_t maxRows)
    : weights_(loadGlmFlashMoeBlock(backend, source, layer)), maxRows_(maxRows) {
  const auto plan = ops::MoE::plan(kGlmFlashMoeShape, maxRows, moeConfig);
  store.bind(layer - kGlmFlashFirstMoeBlock, weights_);
  const auto allocate = [&](uint64_t bytes, const char *name) {
    return backend.allocateBuffer(bytes, metal::BufferStorage::Shared, name);
  };
  const uint64_t bytes = uint64_t{maxRows} * kGlmFlashMoeShape.hiddenSize * sizeof(uint16_t);
  buffers_.input = std::move(input);
  buffers_.residual = allocate(bytes, "glm expert zero residual");
  std::memset(buffers_.residual.contents(), 0, buffers_.residual.sizeBytes());
  buffers_.output = allocate(bytes, "glm expert result");
  for (const auto &field : ops::kMoeScratchFields)
    buffers_.scratch.*field.buffer = allocate(plan.workspace().*field.bytes, field.name);
}

const metal::MetalBuffer &GlmFlashMoeStep::add(metal::CommandGraph &graph, uint32_t rows) const {
  if (!rows || rows > maxRows_) throw std::invalid_argument("GLM Flash expert rows exceed allocation");
  const auto plan = ops::MoE::plan(kGlmFlashMoeShape, rows, moeConfig);
  ops::MoE::addRouting(graph, buffers_, weights_, plan);
  if (weights_.stream) {
    const ops::MoeLoadPart part{&buffers_, &plan};
    weights_.stream->addLoad(graph, {&part, 1}, weights_.streamBlock,
                             [&] { ops::MoE::addResident(graph, buffers_, weights_, plan); });
  }
  ops::MoE::addRouted(graph, buffers_, weights_, plan);
  return buffers_.output;
}

} // namespace splash::model
