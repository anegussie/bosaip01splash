#include "model/Glm5FlashCheckpoint.hpp"

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <set>
#include <tuple>

namespace splash::model {
namespace {

constexpr uint64_t width = 4096, vocabulary = 154880;
constexpr uint64_t heads = 64, kdaHead = 128, kdaChannels = heads * kdaHead;
constexpr uint64_t mlaHead = 256, kvRank = 512, qRank = 1536;
constexpr uint64_t indexHeads = 32, indexWidth = 128, pool = 4;
constexpr uint64_t conv = 4, denseLayers = 3, denseWidth = 12288, expertWidth = 2048;
constexpr uint64_t streams = 4, mixes = streams * (2 + streams);
constexpr uint32_t blocks = Glm5FlashCheckpoint::textLayers + 1;

constexpr uint32_t q4k = 12, q5k = 13, q6k = 14;
constexpr uint32_t iq2xxs = 16, iq3xxs = 18, iq2s = 22, iq4xs = 23;

void checkMetadata(const GgufFile &file) {
  const auto &metadata = file.metadata();
  if (metadata.architecture() != "glm5-next")
    throw GgufError("GLM-5.3-Flash requires a glm5-next GGUF");

  auto number = [&](std::string_view key, uint64_t expected) {
    const std::string name = "glm5-next." + std::string(key);
    if (metadata.unsignedValue(name) != expected)
      throw GgufError(name + " must be " + std::to_string(expected) + " for GLM-5.3-Flash");
  };
  auto real = [&](std::string_view key, double expected) {
    const std::string name = "glm5-next." + std::string(key);
    const auto value = metadata.floatValue(name);
    if (!value || !std::isfinite(*value) || std::abs(*value - expected) > std::abs(expected) * 1e-6)
      throw GgufError(name + " differs from the GLM-5.3-Flash configuration");
  };
  number("block_count", blocks);
  number("nextn_predict_layers", 1);
  number("embedding_length", width);
  number("vocab_size", vocabulary);
  number("attention.head_count", heads);
  number("attention.q_lora_rank", qRank);
  number("attention.kv_lora_rank", kvRank);
  number("attention.key_length_mla", mlaHead);
  number("attention.value_length_mla", mlaHead);
  number("rope.dimension_count", 0);
  number("attention.indexer.head_count", indexHeads);
  number("attention.indexer.key_length", indexWidth);
  number("attention.indexer.kpool", pool);
  number("attention.indexer.top_k", 2048);
  number("ssm.conv_kernel", conv);
  number("kda.head_dim", kdaHead);
  number("hyper_connection.count", streams);
  number("hyper_connection.sinkhorn_iterations", 20);
  number("leading_dense_block_count", denseLayers);
  number("feed_forward_length", denseWidth);
  number("expert_count", Glm5FlashCheckpoint::experts);
  number("expert_used_count", Glm5FlashCheckpoint::expertsPerToken);
  number("expert_shared_count", 1);
  number("expert_feed_forward_length", expertWidth);
  number("expert_shared_feed_forward_length", expertWidth);
  number("expert_group_count", 1);
  number("expert_group_used_count", 1);
  number("expert_gating_func", 2); // GGML sigmoid
  number("expert_weights_norm", 1);
  real("expert_weights_scale", 2.5);
  real("kda.gate_lower_bound", -5);
  real("hyper_connection.epsilon", 1e-6);
  real("attention.layer_norm_rms_epsilon", 1e-5);
  real("attention.layer_norm_epsilon", 1e-6);

  for (const auto key : {"glm5-next.swiglu_clamp_exp", "glm5-next.swiglu_clamp_shexp"}) {
    const auto clamp = file.numericArray(key);
    if (!clamp || clamp->size() != blocks || !std::ranges::all_of(*clamp, [](double v) { return v == 10.0; }))
      throw GgufError(std::string(key) + " must describe a clamp of 10 for every block");
  }
  const auto kvHeads = file.numericArray("glm5-next.attention.head_count_kv");
  if (!kvHeads || kvHeads->size() != blocks)
    throw GgufError("GLM-5.3-Flash requires a KV head count for each block");
  for (uint32_t layer = 0; layer < blocks; ++layer) {
    const bool sparse = layer % 4 == 3 || layer == blocks - 1;
    if ((*kvHeads)[layer] != static_cast<double>(sparse))
      throw GgufError("unexpected GLM-5.3-Flash attention type at block " + std::to_string(layer));
  }
}

void checkRanges(std::vector<Glm5FlashTensor> &tensors) {
  std::ranges::sort(tensors, {}, [](const Glm5FlashTensor &entry) {
    return std::tuple{entry.tensor->file, entry.tensor->offset, std::string_view(entry.tensor->name)};
  });
  const GgufTensor *previous = nullptr;
  for (const auto &entry : tensors) {
    const GgufTensor &tensor = *entry.tensor;
    if (previous && previous->file == tensor.file && previous->bytes > tensor.offset - previous->offset)
      throw GgufError("overlapping GLM-5.3-Flash tensors: " + previous->name + " and " + tensor.name);
    previous = &tensor;
  }
}

} // namespace

Glm5FlashCheckpoint::Glm5FlashCheckpoint(const GgufFile &file) {
  checkMetadata(file);
  const auto check = [&](const std::string &name, std::initializer_list<uint64_t> dimensions,
                         std::initializer_list<uint32_t> formats,
                         Glm5FlashTensorRole role = Glm5FlashTensorRole::Target) {
    const auto &tensor = file.require(name);
    if (!std::ranges::equal(tensor.dims, dimensions))
      throw GgufError("unexpected GLM-5.3-Flash tensor shape: " + name);
    if (std::ranges::find(formats, tensor.type) == formats.end())
      throw GgufError("unexpected GLM-5.3-Flash tensor format: " + name + " (" + ggmlTypeName(tensor.type) + ")");
    if (role == Glm5FlashTensorRole::RoutedExpert) {
      routedExpertBytes += tensor.bytes;
      tensors.push_back({&tensor, role, tensor.bytes / experts});
    } else {
      targetBytes += tensor.bytes;
      tensors.push_back({&tensor, role});
    }
  };
  check("token_embd.weight", {width, vocabulary}, {q4k});
  check("output.weight", {width, vocabulary}, {q4k});
  check("output_norm.weight", {width}, {ggml::kF32});
  for (uint32_t layer = 0; layer < textLayers; ++layer) {
    const std::string prefix = "blk." + std::to_string(layer) + ".";
    auto weight = [&](std::string_view name, std::initializer_list<uint64_t> dims,
                      std::initializer_list<uint32_t> formats) {
      check(prefix + std::string(name), dims, formats);
    };
    weight("attn_norm.weight", {width}, {ggml::kF32});
    weight("ffn_norm.weight", {width}, {ggml::kF32});
    for (std::string_view part : {"hc_attn_", "hc_ffn_"}) {
      weight(std::string(part) + "fn.weight", {streams * width, mixes}, {ggml::kQ8_0});
      weight(std::string(part) + "base.weight", {mixes}, {ggml::kF32});
      weight(std::string(part) + "scale.weight", {3}, {ggml::kF32});
    }
    if (layer % 4 == 3) {
      weight("attn_q_a.weight", {width, qRank}, {q5k, q6k});
      weight("attn_q_a_norm.weight", {qRank}, {ggml::kF32});
      weight("attn_q_b.weight", {qRank, heads * mlaHead}, {ggml::kQ8_0});
      weight("attn_kv_a_mqa.weight", {width, kvRank}, {ggml::kQ8_0});
      weight("attn_kv_a_norm.weight", {kvRank}, {ggml::kF32});
      weight("attn_k_b.weight", {mlaHead, kvRank, heads}, {ggml::kQ8_0});
      weight("attn_v_b.weight", {kvRank, mlaHead, heads}, {ggml::kQ8_0});
      weight("attn_output.weight", {heads * mlaHead, width}, {q5k, q6k});
      weight("indexer.attn_k.weight", {width, indexWidth}, {ggml::kQ8_0});
      weight("indexer.attn_q_b.weight", {qRank, indexHeads * indexWidth}, {ggml::kQ8_0});
      weight("indexer.k_norm.bias", {indexWidth}, {ggml::kF32});
      weight("indexer.k_norm.weight", {indexWidth}, {ggml::kF32});
      weight("indexer.proj.weight", {width, indexHeads}, {ggml::kF32});
      weight("indexer_compressor_ape.weight", {indexWidth, pool}, {ggml::kF32});
      weight("indexer_compressor_gate.weight", {width, indexWidth}, {ggml::kQ8_0});
    } else {
      for (std::string_view channel : {"q", "k", "v"}) {
        weight("attn_" + std::string(channel) + ".weight", {width, kdaChannels}, {q5k});
        weight("ssm_conv1d_" + std::string(channel) + ".weight", {conv, 1, kdaChannels}, {ggml::kF32});
      }
      weight("attn_output.weight", {kdaChannels, width}, {q5k, q6k});
      weight("ssm_a", {heads}, {ggml::kF32});
      weight("ssm_beta.weight", {width, heads}, {ggml::kQ8_0});
      weight("ssm_dt.bias", {kdaChannels}, {ggml::kF32});
      for (std::string_view gate : {"ssm_f_", "ssm_g_"}) {
        weight(std::string(gate) + "a.weight", {width, kdaHead}, {ggml::kQ8_0});
        weight(std::string(gate) + "b.weight", {kdaHead, kdaChannels}, {ggml::kQ8_0});
      }
      weight("ssm_norm.weight", {kdaHead}, {ggml::kF32});
    }
    if (layer < denseLayers) {
      weight("ffn_gate.weight", {width, denseWidth}, {q5k});
      weight("ffn_up.weight", {width, denseWidth}, {q5k});
      weight("ffn_down.weight", {denseWidth, width}, {q6k});
    } else {
      weight("ffn_gate_inp.weight", {width, experts}, {ggml::kF32});
      weight("exp_probs_b.bias", {experts}, {ggml::kF32});
      weight("ffn_gate_shexp.weight", {width, expertWidth}, {q5k, q6k});
      weight("ffn_up_shexp.weight", {width, expertWidth}, {q5k, q6k});
      weight("ffn_down_shexp.weight", {expertWidth, width}, {ggml::kQ8_0, q6k});
      check(prefix + "ffn_gate_exps.weight", {width, expertWidth, experts}, {iq2xxs, iq2s},
            Glm5FlashTensorRole::RoutedExpert);
      check(prefix + "ffn_up_exps.weight", {width, expertWidth, experts}, {iq2xxs, iq2s},
            Glm5FlashTensorRole::RoutedExpert);
      check(prefix + "ffn_down_exps.weight", {expertWidth, width, experts}, {iq3xxs, iq4xs},
            Glm5FlashTensorRole::RoutedExpert);
    }
  }
  const std::string auxPrefix = "blk." + std::to_string(textLayers) + ".";
  (void)file.require(auxPrefix + "nextn.eh_proj.weight");
  for (const auto &tensor : file.tensors()) {
    if (tensor.name.starts_with(auxPrefix)) {
      auxiliaryBytes += tensor.bytes;
      tensors.push_back({&tensor, Glm5FlashTensorRole::Auxiliary});
    }
  }
  if (tensors.size() != file.tensors().size()) {
    std::set<std::string_view> recognized;
    for (const auto &entry : tensors) recognized.insert(entry.tensor->name);
    for (const auto &tensor : file.tensors())
      if (!recognized.contains(tensor.name)) throw GgufError("unrecognized GLM-5.3-Flash tensor: " + tensor.name);
  }
  checkRanges(tensors);
}

} // namespace splash::model
