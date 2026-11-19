#include "model/GlmFlashSparseLayer.hpp"

#include <utility>

namespace splash::model {
namespace {

constexpr uint32_t hidden = GLM_FLASH_HC_HIDDEN, heads = GLM_FLASH_DSA_HEADS;
constexpr uint32_t keyWidth = GLM_FLASH_DSA_INDEX_WIDTH, indexHeads = GLM_FLASH_DSA_INDEX_HEADS;
constexpr uint32_t latentWidth = GLM_FLASH_DSA_LATENT, mlaHead = 256, queryRank = 1536;
constexpr uint32_t threads = metal::CommandGraph::kDefaultThreads;

void project(metal::CommandGraph &graph, const metal::MetalBuffer &input, const ops::QuantizedSegment &weight,
             const metal::MetalBuffer &output, uint32_t rows) {
  ops::addGgufFloat(graph, input, weight, output, rows, weight.outputSize, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Simdgroup);
}

void cast(metal::CommandGraph &graph, const char *kernel, const metal::MetalBuffer &input,
          const metal::MetalBuffer &output, uint32_t rows, uint32_t width) {
  graph.add(kernel, {input, output}, width, {(width + threads - 1) / threads, rows, 1});
}

void rms(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weight,
         const metal::MetalBuffer &output, uint32_t rows, uint32_t width, bool fp32 = false) {
  graph.add(fp32 ? "glm_flash_layer_rms_f32" : "glm_flash_layer_rms", {input, weight, output}, width, {rows, 1, 1});
}

void projectHeads(metal::CommandGraph &graph, const metal::MetalBuffer &input, const metal::MetalBuffer &weights,
                  const metal::MetalBuffer &output, uint32_t rows, uint32_t in, uint32_t out) {
  graph.add("glm_flash_head_projection", {input, weights, output}, in, {rows, heads, out}, {32, 1, 1});
}

} // namespace

GlmFlashSparseLayer::GlmFlashSparseLayer(metal::MetalBackend &backend, const GgufFile &source,
                                         ExpertStore &experts, uint32_t layer, uint32_t capacity, uint32_t maxRows,
                                         ops::GlmFlashDsaCache cache)
    : cache_(std::move(cache)), maxRows_(maxRows) {
  if (source.metadata().architecture() != "glm5-next" || layer >= Glm5FlashCheckpoint::textLayers ||
      layer % 4 != 3 || capacity > GLM_FLASH_DSA_CONTEXT || !maxRows || maxRows > capacity ||
      (cache_.capacity && cache_.capacity != capacity))
    throw std::invalid_argument("invalid GLM Flash indexed MLA layer or capacity");
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
    return ops::QuantizedSegment::rows(gguf_format_of(tensor.type), uint32_t(tensor.dims[1]),
                                       uint32_t(tensor.columns()), load(name));
  };
  const auto alloc = [&](uint64_t bytes, const char *name) {
    return backend.allocateBuffer(bytes, metal::BufferStorage::Shared, name);
  };
  const auto fp32 = [&](uint32_t width, const char *name) { return alloc(uint64_t{maxRows} * width * 4, name); };
  attentionMix_ = {load("hc_attn_fn.weight"), load("hc_attn_scale.weight"), load("hc_attn_base.weight")};
  ffnMix_ = {load("hc_ffn_fn.weight"), load("hc_ffn_scale.weight"), load("hc_ffn_base.weight")};
  attentionNorm_ = load("attn_norm.weight");
  ffnNorm_ = load("ffn_norm.weight");
  queryNorm_ = load("attn_q_a_norm.weight");
  latentNorm_ = load("attn_kv_a_norm.weight");
  keyAbsorption_ = load("attn_k_b.weight");
  valueProjection_ = load("attn_v_b.weight");
  index_ = {load("indexer.k_norm.weight"), load("indexer.k_norm.bias"), load("indexer_compressor_ape.weight")};
  queryA_ = linear("attn_q_a.weight");
  queryB_ = linear("attn_q_b.weight");
  latent_ = linear("attn_kv_a_mqa.weight");
  indexKey_ = linear("indexer.attn_k.weight");
  indexGate_ = linear("indexer_compressor_gate.weight");
  indexQuery_ = linear("indexer.attn_q_b.weight");
  indexHead_ = ops::QuantizedSegment::floats(indexHeads, hidden, load("indexer.proj.weight"));
  output_ = linear("attn_output.weight");

  const uint32_t poolCount = capacity / GLM_FLASH_DSA_POOL;
  if (!cache_.capacity)
    cache_ = {capacity, alloc(uint64_t{capacity} * keyWidth * 4, "glm index keys"),
              alloc(uint64_t{capacity} * keyWidth * 4, "glm index gates"),
              poolCount ? alloc(uint64_t{poolCount} * keyWidth * 4, "glm index pools") : metal::MetalBuffer{},
              alloc(uint64_t{capacity} * latentWidth * 4, "glm latent cache")};
  if (poolCount > GLM_FLASH_DSA_TOP_POOLS) {
    indexScratch_ = {fp32(poolCount, "glm index scores"),
                     fp32(GLM_FLASH_DSA_SELECTION, "glm selected tokens")};
  }
  attention_ = {fp32(keyWidth, "glm index key"), fp32(keyWidth, "glm index gate"),
                fp32(indexHeads * keyWidth, "glm index query"), fp32(indexHeads, "glm index weights"),
                fp32(latentWidth, "glm normalized latent"), fp32(heads * latentWidth, "glm absorbed query"),
                fp32(heads * latentWidth, "glm attended latent")};
  hyperScratch_ = {fp32(1, "glm inverse rms"), fp32(GLM_FLASH_HC_MIXES, "glm mix coefficients")};
  branch_ = fp32(hidden, "glm branch");
  bfloat_ = alloc(uint64_t{maxRows} * heads * mlaHead * 2, "glm bf16 scratch");
  queryLow_ = fp32(queryRank, "glm query latent");
  queryExpanded_ = fp32(heads * mlaHead, "glm expanded query");
  latentRaw_ = fp32(latentWidth, "glm latent");
  attended_ = fp32(heads * mlaHead, "glm attention output");

  moe_.emplace(backend, source, experts, layer, bfloat_, maxRows);
}

void GlmFlashSparseLayer::add(metal::CommandGraph &graph, metal::MetalBuffer streams, uint32_t firstPosition,
                              uint32_t rows) const {
  if (!rows || rows > maxRows_ || uint64_t{firstPosition} + rows > cache_.capacity)
    throw std::invalid_argument("GLM Flash indexed MLA rows exceed its allocation");
  ops::GlmFlashHyperConnection::addPre(graph, streams, attentionMix_, hyperScratch_, branch_, rows);
  rms(graph, branch_, attentionNorm_, bfloat_, rows, hidden);
  project(graph, bfloat_, queryA_, queryLow_, rows);
  project(graph, bfloat_, latent_, latentRaw_, rows);
  project(graph, bfloat_, indexKey_, attention_.indexKey, rows);
  project(graph, bfloat_, indexGate_, attention_.indexGate, rows);
  project(graph, bfloat_, indexHead_, attention_.indexWeights, rows);
  rms(graph, queryLow_, queryNorm_, bfloat_, rows, queryRank);
  project(graph, bfloat_, queryB_, queryExpanded_, rows);
  project(graph, bfloat_, indexQuery_, attention_.indexQuery, rows);
  rms(graph, latentRaw_, latentNorm_, attention_.latent, rows, latentWidth, true);
  projectHeads(graph, queryExpanded_, keyAbsorption_, attention_.query, rows, mlaHead, latentWidth);
  ops::GlmFlashSparseAttention::add(graph, index_, cache_, attention_, indexScratch_, firstPosition, rows);
  projectHeads(graph, attention_.output, valueProjection_, attended_, rows, latentWidth, mlaHead);
  cast(graph, "glm_flash_bfloat", attended_, bfloat_, rows, heads * mlaHead);
  project(graph, bfloat_, output_, branch_, rows);
  ops::GlmFlashHyperConnection::addPost(graph, streams, branch_, hyperScratch_.coefficients, rows);

  ops::GlmFlashHyperConnection::addPre(graph, streams, ffnMix_, hyperScratch_, branch_, rows);
  rms(graph, branch_, ffnNorm_, bfloat_, rows, hidden);
  const auto &expertOutput = moe_->add(graph, rows);
  cast(graph, "glm_flash_float", expertOutput, branch_, rows, hidden);
  ops::GlmFlashHyperConnection::addPost(graph, std::move(streams), branch_, hyperScratch_.coefficients, rows);
}

} // namespace splash::model
