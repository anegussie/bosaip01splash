#pragma once

// Synthetic installed models: the target/, draft/ and vision/ directories of
// an MLX model of given layouts, each a safetensors shard holding every tensor
// its loader reads, all zero, which loadModel loads as it loads an installed
// model.

#include "TestChecks.hpp"
#include "model/AffinePreparation.hpp"
#include "model/AffineTarget.hpp"
#include "model/DFlashDraft.hpp"
#include "model/DraftCheckpoint.hpp"
#include "model/VisionLoader.hpp"
#include "ops/Vision.hpp"

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace splash::test {

struct SyntheticTensor final {
  std::string name;
  std::string dtype;
  std::vector<uint64_t> shape;
};

// A safetensors shard of tensors whose values are all zero: the data is a
// hole in the file, so a large model costs no disk.
inline void writeSyntheticShard(const std::filesystem::path &path,
                                const std::vector<SyntheticTensor> &tensors) {
  std::string header = "{";
  uint64_t offset = 0;
  for (const SyntheticTensor &tensor : tensors) {
    uint64_t bytes = tensor.dtype == "U32" || tensor.dtype == "F32" ? 4 : 2;
    std::string shape;
    for (uint64_t dimension : tensor.shape) {
      bytes *= dimension;
      shape += (shape.empty() ? "" : ",") + std::to_string(dimension);
    }
    header += (header.size() > 1 ? ",\"" : "\"") + tensor.name + R"(":{"dtype":")" + tensor.dtype +
              R"(","shape":[)" + shape + R"(],"data_offsets":[)" + std::to_string(offset) + "," +
              std::to_string(offset + bytes) + "]}";
    offset += bytes;
  }
  header += "}";
  std::filesystem::create_directories(path.parent_path());
  {
    std::ofstream file(path, std::ios::binary);
    const uint64_t length = header.size();
    file.write(reinterpret_cast<const char *>(&length), sizeof length);
    file << header;
    require(bool(file), "unable to write a synthetic safetensors shard");
  }
  std::filesystem::resize_file(path, sizeof(uint64_t) + header.size() + offset);
}

// The checkpoint tensors the images read, each in the first dtype its input
// takes.
inline std::vector<SyntheticTensor> imageTensors(const std::vector<model::affine::Image> &images) {
  std::vector<SyntheticTensor> result;
  const auto add = [&](const model::affine::Input &input) {
    result.push_back({input.name, input.dtypes.front(), input.shape});
  };
  for (const model::affine::Image &image : images)
    for (const model::affine::Section &section : image.sections) {
      if (section.parts.empty()) add(section.input);
      for (const model::affine::ProjectionPart &part : section.parts)
        for (const model::affine::Input &field : part.fields) add(field);
    }
  return result;
}

// The MLX vision tower's tensors of layout, as model/VisionLoader.cpp reads
// them: the patch embedding over two frames of RGB patches, the position
// table, then each block's and the merger's norms and projections.
inline std::vector<SyntheticTensor> visionTensors(const ops::VisionLayout &layout) {
  std::vector<SyntheticTensor> result;
  const auto add = [&](const std::string &name, std::vector<uint64_t> shape) {
    result.push_back({"vision_tower." + name, "BF16", std::move(shape)});
  };
  const auto affine = [&](const std::string &name, uint64_t rows, uint64_t columns) {
    add(name + ".weight", {rows, columns});
    add(name + ".bias", {rows});
  };
  const auto norm = [&](const std::string &name) {
    add(name + ".weight", {layout.hiddenSize});
    add(name + ".bias", {layout.hiddenSize});
  };
  add("patch_embed.proj.weight", {layout.hiddenSize, 2, layout.patchSize, layout.patchSize, 3});
  add("patch_embed.proj.bias", {layout.hiddenSize});
  add("pos_embed.weight", {uint64_t{layout.positionGridSide} * layout.positionGridSide, layout.hiddenSize});
  for (uint32_t block = 0; block < layout.depth; ++block) {
    const std::string at = "blocks." + std::to_string(block) + ".";
    norm(at + "norm1");
    affine(at + "attn.qkv", 3ull * layout.hiddenSize, layout.hiddenSize);
    affine(at + "attn.proj", layout.hiddenSize, layout.hiddenSize);
    norm(at + "norm2");
    affine(at + "mlp.linear_fc1", layout.intermediateSize, layout.hiddenSize);
    affine(at + "mlp.linear_fc2", layout.hiddenSize, layout.intermediateSize);
  }
  norm("merger.norm");
  affine("merger.linear_fc1", layout.mergedHiddenSize, layout.mergedHiddenSize);
  affine("merger.linear_fc2", layout.outputHiddenSize, layout.mergedHiddenSize);
  return result;
}

// The bytes of each role's images.
struct SyntheticAccounting final {
  uint64_t targetBytes = 0;
  uint64_t draftBytes = 0;
  uint64_t visionBytes = 0;
};

// Writes an installed MLX model of these layouts under root: its target,
// DFlash2 draft and vision tower. Returns the bytes of the images it loads
// into.
template <class Layout>
SyntheticAccounting writeSyntheticModel(const std::filesystem::path &root, const Layout &target,
                                        const model::DFlashDraftLayout &draft,
                                        const ops::VisionLayout &vision) {
  const std::vector<model::affine::Image> targetImages = model::affineTargetImages(target);
  const std::vector<model::affine::Image> draftImages = model::draftCheckpointImages(draft);
  writeSyntheticShard(root / "target" / "model.safetensors", imageTensors(targetImages));
  writeSyntheticShard(root / "draft" / "model.safetensors", imageTensors(draftImages));
  writeSyntheticShard(root / "vision" / "model.safetensors", visionTensors(vision));
  const auto bytes = [](const std::vector<model::affine::Image> &images) {
    uint64_t total = 0;
    for (const model::affine::Image &image : images) total += image.bytes;
    return total;
  };
  return {bytes(targetImages), bytes(draftImages), model::visionImageBytes(vision)};
}

} // namespace splash::test
