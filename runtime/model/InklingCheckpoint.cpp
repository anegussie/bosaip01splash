#include "model/InklingCheckpoint.hpp"

#include "model/ModelDescriptor.hpp"

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <tuple>

namespace splash::model {
namespace {

constexpr uint32_t q4k = 12, q5k = 13, q6k = 14;
constexpr uint32_t iq2xxs = 16, iq2xs = 17, iq3xxs = 18, iq4nl = 20, iq2s = 22;
constexpr uint32_t queryWidth = InklingCheckpoint::queryHeads * InklingCheckpoint::headWidth;
constexpr uint32_t kvWidth = InklingCheckpoint::kvHeads * InklingCheckpoint::headWidth;
constexpr uint32_t relativeWidth = SPLASH_INKLING_RELATIVE_WIDTH, gateRank = SPLASH_INKLING_GATE_RANK;
constexpr uint32_t convolutionTaps = 4;
constexpr uint32_t blockLayers = 6, dynamicTaps = InklingCheckpoint::kvHeads * convolutionTaps;

void requireScalar(const GgufMetadata &metadata, std::string_view key, uint64_t expected) {
  const std::string name = "inkling2." + std::string(key);
  if (metadata.unsignedValue(name) != expected)
    throw GgufError(name + " must be " + std::to_string(expected) + " for Inkling 2 Mini");
}

void requireReal(const GgufMetadata &metadata, std::string_view key, double expected) {
  const std::string name = "inkling2." + std::string(key);
  const auto value = metadata.floatValue(name);
  if (!value || !std::isfinite(*value) || std::abs(*value - expected) > std::abs(expected) * 1e-6)
    throw GgufError(name + " differs from the Inkling 2 Mini configuration");
}

void requireHeads(const GgufFile &file, std::string_view name, uint32_t heads) {
  const auto values = file.numericArray(name);
  if (!values || values->size() != InklingCheckpoint::logicalLayers ||
      !std::ranges::all_of(*values, [heads](double value) { return value == heads; }))
    throw GgufError(std::string(name) + " must describe every logical Inkling layer");
}

} // namespace

InklingCheckpoint::InklingCheckpoint(const GgufFile &file) {
  const auto &metadata = file.metadata();
  if (metadata.architecture() != "inkling2" || metadata.unsignedValue("inkling2.num_loops") != passes)
    throw GgufError("Inkling 2 Mini requires the fixed-loop Unsloth inkling2 GGUF layout");
  if (file.rotation()) throw GgufError("Inkling 2 Mini GGUF rotation is unsupported");
  const std::pair<std::string_view, uint32_t> scalars[]{
      {"block_count", logicalLayers}, {"context_length", context}, {"embedding_length", hidden},
      {"feed_forward_length", expertWidth}, {"expert_feed_forward_length", expertWidth},
      {"expert_count", experts}, {"expert_used_count", expertsPerToken},
      {"loop.core_start", coreBegin}, {"loop.core_end", coreEnd}, {"loop.gate_rank", gateRank},
      {"vocab_size", paddedVocabulary}, {"vocab_size_unpadded", vocabulary},
      {"attention.key_length", headWidth}, {"attention.value_length", headWidth},
      {"attention.key_length_swa", headWidth}, {"attention.value_length_swa", headWidth},
      {"attention.sliding_window", window}, {"attention.relative_length", relativeWidth},
      {"attention.relative_extent", window}, {"attention.log_scale_floor", 8192},
      {"shortconv.l_cache", convolutionTaps}, {"attn_res.block_size", blockLayers}, {"rope.dimension_count", 0},
  };
  for (const auto &[name, expected] : scalars) requireScalar(metadata, name, expected);
  const std::pair<std::string_view, double> reals[]{
      {"attention.layer_norm_rms_epsilon", 1e-6}, {"attention.qk_clip", std::sqrt(512.0)},
      {"attention.relative_clip", 8}, {"attention.log_scale_alpha", 0.1}, {"expert_weights_scale", 8},
      {"activation.situ_beta", 4}, {"activation.situ_linear_beta", 25}, {"final_logit_softcapping", 30},
  };
  for (const auto &[name, expected] : reals) requireReal(metadata, name, expected);
  requireHeads(file, "inkling2.attention.head_count", queryHeads);
  requireHeads(file, "inkling2.attention.head_count_kv", kvHeads);
  if (metadata.stringValue("tokenizer.ggml.pre") != std::string_view("inkling2") ||
      metadata.stringValue("tokenizer.ggml.model") != std::string_view("gpt2"))
    throw GgufError("Inkling 2 Mini GGUF requires the Inkling tokenizer");

  const auto windows = file.numericArray("inkling2.attention.sliding_window_pattern");
  if (!windows || windows->size() != logicalLayers)
    throw GgufError("Inkling sliding-window pattern must describe every logical layer");
  uint32_t next = 0;
  const auto append = [&](uint32_t begin, uint32_t end, uint32_t pass) {
    for (uint32_t physical = begin; physical < end; ++physical) {
      const bool sliding = physical % blockLayers != blockLayers - 1;
      if ((*windows)[next] != static_cast<double>(sliding))
        throw GgufError("unexpected Inkling sliding-window pattern at logical layer " + std::to_string(next));
      visits_[next] = {physical, next, pass, sliding};
      ++next;
    }
  };
  append(0, coreBegin, 0);
  for (uint32_t pass = 0; pass < passes; ++pass) append(coreBegin, coreEnd, pass);
  append(coreEnd, physicalLayers, 0);

  size_t checked = 0;
  const auto requireTensor = [&](const std::string &name, std::initializer_list<uint64_t> shape,
                                 std::initializer_list<uint32_t> formats, bool expert = false) {
    const auto &tensor = file.require(name);
    if (!std::ranges::equal(tensor.dims, shape)) throw GgufError("unexpected Inkling tensor shape: " + name);
    if (std::ranges::find(formats, tensor.type) == formats.end())
      throw GgufError("unexpected Inkling tensor format: " + name + " (" + ggmlTypeName(tensor.type) + ")");
    ++checked;
    (expert ? expertTensorBytes_ : residentTensorBytes_) += tensor.bytes;
  };
  requireTensor("token_embd.weight", {hidden, paddedVocabulary}, {q4k});
  requireTensor("output.weight", {hidden, paddedVocabulary}, {q5k});
  for (const auto name : {"token_embd_norm.weight", "output_norm.weight", "output_res_query.weight"})
    requireTensor(name, {hidden}, {ggml::kF32});
  for (const auto name : {"loop_res_query.weight", "loop_kv_res_query.weight"})
    requireTensor(name, {hidden, 2 * (coreEnd - coreBegin)}, {ggml::kF32});

  for (uint32_t layer = 0; layer < physicalLayers; ++layer) {
    const bool sliding = layer % blockLayers != blockLayers - 1;
    const std::string prefix = "blk." + std::to_string(layer) + ".";
    const auto weight = [&](std::string_view name, std::initializer_list<uint64_t> shape,
                            std::initializer_list<uint32_t> formats = {ggml::kF32}) {
      requireTensor(prefix + std::string(name), shape, formats);
    };
    weight("attn_q.weight", {hidden, queryWidth}, {ggml::kQ8_0, q4k, q5k, q6k});
    weight("attn_gate.weight", {hidden, queryWidth}, {ggml::kQ8_0, q5k, q6k});
    weight("attn_output.weight", {queryWidth, hidden}, {ggml::kQ8_0, q6k});
    weight("attn_q_clip.weight", {headWidth, queryHeads});
    weight("attn_rel.weight", {hidden, relativeWidth * queryHeads}, {ggml::kQ8_0, q5k, q6k});
    weight("attn_rel_clip.weight", {relativeWidth, queryHeads});
    weight("attn_rel_bias.weight", {relativeWidth, window});
    weight("attn_sink_proj.weight", {hidden, queryHeads}, {ggml::kBF16});
    weight("attn_post_conv.weight", {convolutionTaps, hidden});
    weight("attn_k.weight", {hidden, kvWidth}, {ggml::kQ8_0, q5k, q6k});
    weight("attn_v.weight", {hidden, kvWidth}, {ggml::kQ8_0, q6k});
    for (const auto name : {"attn_k_conv.weight", "attn_v_conv.weight"}) weight(name, {convolutionTaps, kvWidth});
    if (sliding) {
      weight("attn_norm.weight", {hidden});
      if (layer) weight("attn_res_query.weight", {hidden});
    } else {
      weight("attn_res_query.weight", {hidden, 3});
      for (const auto name : {"attn_q_inp_norm.weight", "attn_k_inp_norm.weight", "attn_v_inp_norm.weight"})
        weight(name, {hidden});
      for (const auto name : {"attn_k_conv_proj.weight", "attn_v_conv_proj.weight"})
        weight(name, {hidden, dynamicTaps}, {ggml::kBF16});
    }
    weight("ffn_norm.weight", {hidden});
    weight("ffn_res_query.weight", {hidden});
    weight("ffn_post_conv.weight", {convolutionTaps, hidden});
    weight("ffn_gate_inp.weight", {hidden, experts});
    weight("exp_probs_b.bias", {experts});
    requireTensor(prefix + "ffn_gate_up_exps.weight", {hidden, 2 * expertWidth, experts},
                  {iq2xxs, iq2xs, iq2s, iq3xxs}, true);
    if (layer < 20) {
      requireTensor(prefix + "ffn_down_exps.weight", {expertWidth, hidden, experts}, {ggml::kNVFP4}, true);
      weight("ffn_down_exps.scale", {experts});
      weight("ffn_gate_up_exps.scale", {experts});
    } else {
      requireTensor(prefix + "ffn_down_exps.weight", {expertWidth, hidden, experts}, {iq4nl}, true);
    }
    if (layer >= coreBegin && layer < coreEnd) {
      for (const auto channel : {"attn", "k", "v", "mlp"}) {
        const std::string control = "loop_" + std::string(channel);
        weight(control + "_down.weight", {2 * hidden, gateRank});
        weight(control + "_gain.weight", {gateRank, hidden});
        weight(control + "_forget.weight", {gateRank, hidden});
      }
    }
  }
  if (checked != file.tensors().size()) throw GgufError("unexpected tensor in the Inkling 2 Mini checkpoint");

  std::vector<const GgufTensor *> byOffset;
  byOffset.reserve(checked);
  for (const auto &tensor : file.tensors()) byOffset.push_back(&tensor);
  std::ranges::sort(byOffset, {}, [](const GgufTensor *tensor) { return std::tie(tensor->file, tensor->offset); });
  const GgufTensor *previous = nullptr;
  for (const auto *tensor : byOffset) {
    if (previous && tensor->file == previous->file && previous->bytes > tensor->offset - previous->offset)
      throw GgufError("overlapping Inkling tensors: " + previous->name + " and " + tensor->name);
    previous = tensor;
  }
}

uint64_t InklingCheckpoint::bf16KvBytes(uint32_t tokens) const {
  if (tokens > context) throw std::invalid_argument("Inkling KV estimate exceeds the checkpoint context");
  uint64_t positions = 0;
  for (const auto &visit : visits_) positions += visit.sliding ? std::min(tokens, window) : tokens;
  return positions * kvHeads * headWidth * 2 * sizeof(uint16_t);
}

InklingSourceFacts inspectInklingSource(const std::filesystem::path &path) {
  const OpenGguf source({path});
  const InklingCheckpoint checkpoint(source.file());
  InklingSourceFacts facts{source.file().metadata().architecture(), checkpoint.physicalLayers,
                           checkpoint.logicalLayers, source.file().tensors().size(),
                           checkpoint.residentTensorBytes(), checkpoint.expertTensorBytes(), {}};
  for (const uint32_t context : {4096, 16384, 32768, 65536, 131072})
    facts.bf16KvBytes.emplace_back(context, checkpoint.bf16KvBytes(context));
  source.checkUnchanged();
  return facts;
}

} // namespace splash::model
