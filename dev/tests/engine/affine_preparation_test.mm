// Loads a tiny DFlash2 draft checkpoint and prints each image's SHA-256.
// Every image must equal the independently serialized file in
// FIXTURE/expected, and again once the images are released and restored.
//
//   affine-preparation METALLIB FIXTURE
#include "model/AffinePlan.hpp"
#include "model/DFlashDraft.hpp"
#include "model/DraftCheckpoint.hpp"
#include "model/WeightImages.hpp"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using namespace splash;
namespace {

std::vector<uint8_t> fileBytes(const std::filesystem::path &path) {
  std::ifstream file(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(file), {}};
}

// Loads the fixture at root with Loader; open opens every file of the
// loader, in the order it plans them, through check.
template <class Loader, class Layout, class Open>
void prepare(metal::MetalBackend &backend, const std::filesystem::path &root, const Layout &layout, Open open) {
  model::WeightImages images(backend, "fixture");
  Loader loader(images, root, layout);
  open(loader, [](model::WeightFile weights) {
    static_cast<void>(weights.section(weights.record().declaredBytes - model::kWeightFileAlignment, {}));
    weights.finish();
  });
  std::vector<std::vector<uint8_t>> loaded;
  for (const auto &image : images.contents()) {
    loaded.emplace_back(image.bytes.begin(), image.bytes.end());
    if (loaded.back() != fileBytes(root / "expected" / std::filesystem::path(image.component).filename()))
      throw std::runtime_error("affine fixture differs: " + std::string(image.component));
    std::cout << "prepared " << image.component << ' ' << model::weightDigest(image.bytes) << '\n';
  }
  images.release();
  while (!images.restore()) {
  }
  for (size_t index = 0; index < loaded.size(); ++index) {
    const auto restored = images.contents()[index].bytes;
    if (!std::equal(restored.begin(), restored.end(), loaded[index].begin(), loaded[index].end()))
      throw std::runtime_error("a restored affine image differs: " + std::string(images.contents()[index].component));
  }
}

// The writer of each image, over memory of 0xFF bytes, writes its expected
// file: every byte of it.
void writeEveryByte(const std::filesystem::path &root, std::vector<model::affine::Image> images) {
  auto planned = std::make_shared<model::affine::PlannedCheckpoint>(root);
  planned->images = std::move(images);
  for (auto &image : planned->images) model::affine::bind(image, planned->source);
  for (size_t index = 0; index < planned->images.size(); ++index) {
    const model::ImagePlan plan = model::affine::imagePlan(planned, index, "");
    std::vector<uint8_t> bytes(plan.bytes, 0xFF);
    plan.write(bytes, {});
    if (bytes != fileBytes(root / "expected" / planned->images[index].name))
      throw std::runtime_error("an affine image left bytes unwritten: " + planned->images[index].name);
  }
}

// The draft fixture: two layers of width 256, one KV head.
model::DFlashDraftLayout tinyDraftLayout() {
  model::DFlashDraftLayout layout;
  layout.layers = 2;
  layout.hiddenSize = 256;
  layout.vocabularySize = 256;
  layout.dynamicSize = 256;
  layout.qkvSize = 256;
  layout.attentionSize = 128;
  layout.intermediateSize = 256;
  layout.attentionHeadDimension = 64;
  layout.rotaryTheta = 10'000'000.0F;
  layout.targetHiddenSize = 256;
  layout.selectorRank = 256;
  layout.kvHeads = 1;
  return layout;
}

} // namespace

int main(int argc, char **argv) {
  @autoreleasepool {
    try {
      if (argc != 3) throw std::runtime_error("usage: affine-preparation METALLIB FIXTURE");
      const std::filesystem::path root(argv[2]);
      metal::MetalBackend backend(argv[1]);
      const model::DFlashDraftLayout layout = tinyDraftLayout();
      prepare<model::DraftCheckpointLoader>(backend, root, layout, [](auto &loader, const auto &check) {
        check(loader.layer(0));
        check(loader.layer(1));
        check(loader.model());
      });
      writeEveryByte(root, model::draftCheckpointImages(layout));
      // The draft loader reads the images.
      model::WeightImages images(backend, "fixture");
      model::DraftCheckpointLoader files(images, root, layout);
      const model::DFlashDraftWeights draft = model::loadDFlashDraftWeights(backend, files, layout);
      const auto affine = [](const ops::Projection &p, uint32_t n, uint32_t k) {
        return p.layout() == ops::WeightLayout::Affine64 && p.outputSize == n && p.inputSize == k;
      };
      bool read = draft.layers.size() == layout.layers && draft.files.size() == layout.layers + 1 &&
                  affine(draft.contextProjection, layout.hiddenSize, layout.targetHiddenSize) &&
                  affine(draft.selectorProjection, layout.selectorRank, layout.hiddenSize);
      for (const auto &layer : draft.layers)
        read = read && affine(layer.attentionDynamic, layout.dynamicSize, layout.hiddenSize) &&
               affine(layer.qkvProjection, layout.qkvSize, layout.hiddenSize) &&
               affine(layer.outputProjection, layout.hiddenSize, layout.attentionSize) &&
               affine(layer.downProjection, layout.hiddenSize, layout.intermediateSize);
      if (!read) throw std::runtime_error("the draft loader misread the draft images");
      std::cout << "affine preparation: exact independent draft fixture, quantization edge cases, fused qkv, "
                   "restore, draft read PASS\n";
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
