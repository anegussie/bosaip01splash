#include "model/GlmFlashRecurrentLayer.hpp"

#include "model/Glm5FlashCheckpoint.hpp"
#include "metal/abi/GlmFlashKda.h"
#include "ops/BufferExtent.hpp"

#include <cstring>
#include <utility>

namespace splash::model {
namespace {

constexpr uint32_t hidden = GLM_FLASH_HC_HIDDEN;
constexpr uint32_t channels = GLM_FLASH_KDA_CHANNELS, heads = GLM_FLASH_KDA_HEADS;
constexpr uint32_t head = GLM_FLASH_KDA_HEAD_DIM, intermediate = 12288;
constexpr uint32_t threads = metal::CommandGraph::kDefaultThreads;

void project(metal::CommandGraph &graph, const metal::MetalBuffer &input,
             const ops::QuantizedSegment &weight, const metal::MetalBuffer &output, uint32_t rows) {
  ops::addGgufFloat(graph, input, weight, output, rows, weight.outputSize, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Simdgroup);
}

void asBfloat(metal::CommandGraph &graph, const metal::MetalBuffer &src,
              const metal::MetalBuffer &dst, uint32_t rows, uint32_t width) {
  graph.add("glm_flash_bfloat", {src, dst}, width, {(width + threads - 1) / threads, rows, 1});
}

void normalize(metal::CommandGraph &graph, const metal::MetalBuffer &src,
               const metal::MetalBuffer &multipliers, const metal::MetalBuffer &dst, uint32_t rows) {
  graph.add("glm_flash_layer_rms", {src, multipliers, dst}, hidden, {rows, 1, 1});
}

} // namespace

GlmFlashRecurrentLayer::GlmFlashRecurrentLayer(metal::MetalBackend &backend, const GgufFile &source,
                                               uint32_t layer, uint32_t maxRows, ExpertStore *experts,
                                               ops::GlmFlashKdaState state)
    : state_(std::move(state)), maxRows_(maxRows) {
  if (source.metadata().architecture() != "glm5-next" || layer >= Glm5FlashCheckpoint::textLayers ||
      layer % 4 == 3 || !maxRows || (layer >= kGlmFlashFirstMoeBlock && !experts))
    throw std::invalid_argument("invalid GLM Flash recurrent layer, rows, or expert store");
  (void)Glm5FlashCheckpoint(source);
  const std::string prefix = "blk." + std::to_string(layer) + ".";
  const auto load = [&](const std::string &name) {
    const auto &tensor = source.require(prefix + name);
    auto buffer = backend.allocateBuffer(tensor.bytes, metal::BufferStorage::Shared, tensor.name);
    source.source(tensor.file).readData(tensor.offset,
        {static_cast<uint8_t *>(buffer.contents()), static_cast<size_t>(tensor.bytes)});
    return buffer;
  };
  const auto linear = [&](const std::string &name) {
    const auto &tensor = source.require(prefix + name);
    if (tensor.dims.size() != 2 || tensor.columns() > UINT32_MAX || tensor.dims[1] > UINT32_MAX)
      throw GgufError("invalid GLM Flash projection: " + tensor.name);
    return ops::QuantizedSegment::rows(gguf_format_of(tensor.type), uint32_t(tensor.dims[1]),
                                       uint32_t(tensor.columns()), load(name));
  };
  const auto allocate = [&](uint64_t elements, const char *name, uint32_t bytes = sizeof(float)) {
    return backend.allocateBuffer(elements * bytes, metal::BufferStorage::Shared, name);
  };
  const auto activation = [&](uint32_t width, const char *name, uint32_t bytes = sizeof(float)) {
    return allocate(uint64_t{maxRows} * width, name, bytes);
  };
  attentionMix_ = {load("hc_attn_fn.weight"), load("hc_attn_scale.weight"), load("hc_attn_base.weight")};
  ffnMix_ = {load("hc_ffn_fn.weight"), load("hc_ffn_scale.weight"), load("hc_ffn_base.weight")};
  attentionNorm_ = load("attn_norm.weight");
  ffnNorm_ = load("ffn_norm.weight");
  qkv_ = {linear("attn_q.weight"), linear("attn_k.weight"), linear("attn_v.weight")};
  recurrentWeights_ = {{load("ssm_conv1d_q.weight"), load("ssm_conv1d_k.weight"), load("ssm_conv1d_v.weight")},
                        load("ssm_a"), load("ssm_dt.bias"), load("ssm_norm.weight")};
  decay_ = {linear("ssm_f_a.weight"), linear("ssm_f_b.weight")};
  gate_ = {linear("ssm_g_a.weight"), linear("ssm_g_b.weight")};
  beta_ = linear("ssm_beta.weight");
  attentionOutput_ = linear("attn_output.weight");
  if (layer < kGlmFlashFirstMoeBlock)
    ffn_ = {linear("ffn_gate.weight"), linear("ffn_up.weight"), linear("ffn_down.weight")};
  if (!state_.recurrent) {
    for (auto &history : state_.convolution)
      history = allocate(uint64_t{channels} * GLM_FLASH_KDA_HISTORY, "glm convolution history");
    state_.recurrent = allocate(uint64_t{channels} * head, "glm recurrent matrix");
    resetState();
  }
  hyperScratch_ = {activation(1, "glm inverse rms"), activation(GLM_FLASH_HC_MIXES, "glm mix coefficients")};
  kdaScratch_ = {{activation(channels, "glm query"), activation(channels, "glm key"), activation(channels, "glm value")},
                  activation(channels, "glm decay"), activation(heads, "glm beta"),
                  activation(channels, "glm output gate"), activation(channels, "glm attention")};
  branch_ = activation(hidden, "glm branch");
  normalized_ = activation(hidden, "glm normalized", 2);
  lowDecay_ = activation(head, "glm low rank decay");
  lowGate_ = activation(head, "glm low rank output gate");
  lowDecayInput_ = activation(head, "glm low rank decay input", 2);
  lowGateInput_ = activation(head, "glm low rank output gate input", 2);
  attended_ = activation(channels, "glm attention projection input", 2);
  if (layer >= kGlmFlashFirstMoeBlock) {
    moe_.emplace(backend, source, *experts, layer, normalized_, maxRows);
  } else {
    ffnGate_ = activation(intermediate, "glm dense gate");
    ffnUp_ = activation(intermediate, "glm dense up");
    ffnIntermediate_ = activation(intermediate, "glm dense intermediate", 2);
  }
}

void GlmFlashRecurrentLayer::resetState() {
  // The caller waits for any previous graph before resetting a sequence.
  for (const auto &history : state_.convolution) std::memset(history.contents(), 0, history.sizeBytes());
  std::memset(state_.recurrent.contents(), 0, state_.recurrent.sizeBytes());
}

void GlmFlashRecurrentLayer::add(metal::CommandGraph &graph, metal::MetalBuffer streams, uint32_t rows) const {
  if (!rows || rows > maxRows_) throw std::invalid_argument("GLM Flash dense block rows exceed its allocation");
  ops::GlmFlashHyperConnection::addPre(graph, streams, attentionMix_, hyperScratch_, branch_, rows);
  normalize(graph, branch_, attentionNorm_, normalized_, rows);
  for (uint32_t i = 0; i < qkv_.size(); ++i)
    project(graph, normalized_, qkv_[i], kdaScratch_.qkv[i], rows);
  project(graph, normalized_, decay_[0], lowDecay_, rows);
  project(graph, normalized_, gate_[0], lowGate_, rows);
  project(graph, normalized_, beta_, kdaScratch_.beta, rows);
  asBfloat(graph, lowDecay_, lowDecayInput_, rows, head);
  asBfloat(graph, lowGate_, lowGateInput_, rows, head);
  project(graph, lowDecayInput_, decay_[1], kdaScratch_.decay, rows);
  project(graph, lowGateInput_, gate_[1], kdaScratch_.outputGate, rows);
  ops::GlmFlashKda::add(graph, recurrentWeights_, state_, kdaScratch_, rows);
  asBfloat(graph, kdaScratch_.output, attended_, rows, channels);
  project(graph, attended_, attentionOutput_, branch_, rows);
  ops::GlmFlashHyperConnection::addPost(graph, streams, branch_, hyperScratch_.coefficients, rows);

  ops::GlmFlashHyperConnection::addPre(graph, streams, ffnMix_, hyperScratch_, branch_, rows);
  normalize(graph, branch_, ffnNorm_, normalized_, rows);
  if (moe_) {
    const auto &output = moe_->add(graph, rows);
    graph.add("glm_flash_float", {output, branch_}, hidden, {hidden / threads, rows, 1});
  } else {
    project(graph, normalized_, ffn_[0], ffnGate_, rows);
    project(graph, normalized_, ffn_[1], ffnUp_, rows);
    graph.add("glm_flash_dense_swiglu", {ffnGate_, ffnUp_, ffnIntermediate_},
              intermediate, {intermediate / threads, rows, 1});
    project(graph, ffnIntermediate_, ffn_[2], branch_, rows);
  }
  ops::GlmFlashHyperConnection::addPost(graph, std::move(streams), branch_, hyperScratch_.coefficients, rows);
}

} // namespace splash::model
