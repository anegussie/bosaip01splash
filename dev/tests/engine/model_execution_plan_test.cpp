#include "TestChecks.hpp"
#include "TestRuntimeGeometry.hpp"
#include "model/ModelFactory.hpp"
#include "model/QwenTargetLoader.hpp"
#include "model/RuntimeArenas.hpp"

#include "metal/abi/QuantFormat.h"

#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <vector>

namespace {

using namespace splash;

using splash::test::require;


void checkMixedLayouts() {
  auto mixed = test::runtimeGeometryPackage<model::Qwen3_8Weights>();
  auto &target = std::get<model::Qwen3_8Weights>(mixed.target);
  auto &up = target.layers.front().upProjection;
  up = ops::Projection(up.outputSize, up.inputSize,
                       ops::BlockWeights{{ops::QuantizedSegment::planes(GGUF_FMT_Q4K, up.outputSize,
                                                                        up.inputSize, {}, {}, {})}});
  bool mismatchRejected = false;
  try { static_cast<void>(model::qwenTargetGeometry(target)); }
  catch (const model::WeightStoreError &) { mismatchRejected = true; }
  require(mismatchRejected, "incompatible fused gate/up layouts reached execution");
  target.layers.front().gateProjection = up;
  require(target.logitsProjection.layout() == ops::WeightLayout::Affine64,
          "mixed fixture must keep an affine vocabulary head");
  for (uint32_t family : {9U, 10U, 11U}) {
    DeviceCapabilities device;
    device.appleGpuFamily = family;
    device.gpuCoreCount = 16;
    ops::ExecutionPlans plans(device);
    const auto geometry = model::RuntimeGeometry::from(mixed, kv::Format::Int8);
    const auto head = target.logitsProjection.shape();
    const auto containsHead = [&](const auto &shapes) {
      return std::find(shapes.begin(), shapes.end(), head) != shapes.end();
    };
    require(!containsHead(geometry.target.prefillProjections) &&
                containsHead(geometry.target.decodeProjections),
            "vocabulary head must reserve workspace only in decode");
    const auto scratch = model::DecodeArena::linearScratchSize(geometry, plans);
    for (uint32_t lanes = 1; lanes <= model::kLaneCount; ++lanes) {
      const auto plan = plans.linear().plan({{up.outputSize, up.inputSize}, lanes * model::kDecodeRows,
          ops::LinearPhase::Decode, ops::LinearEpilogue::GateUp}, up);
      const auto required = plan.scratchSize();
      require(scratch.input >= required.input && scratch.sums >= required.sums &&
                  scratch.partials >= required.partials && scratch.counters >= required.counters,
              "affine head hid a block-quantized layer's scratch requirement");
      require(model::DecodeArena::gateScratchBytes(geometry, plans) >= plan.gateScratchBytes(),
              "mixed gate/up workspace is too small");
    }
    const auto sizes = model::prefillTensorBytes(geometry, plans);
    for (uint32_t rows : {1U, 8U, 17U, 32U}) {
      const auto required = plans.linear().plan({{up.outputSize, up.inputSize}, rows,
          ops::LinearPhase::Prefill, ops::LinearEpilogue::None}, up).scratchSize();
      require(sizes[uint32_t(model::PrefillTensor::LinearPartials)] >= required.partials &&
                  sizes[uint32_t(model::PrefillTensor::LinearCounters)] >= required.counters,
              "mixed short-prefill split scratch is too small");
    }
  }
  // Every MoE block of a target shares one layout, which the geometry's one
  // MoE shape records: no source mixes them.
  auto sparse = test::runtimeGeometryPackage<model::Qwen3_6MoeWeights>();
  auto &moe = std::get<model::Qwen3_6MoeWeights>(sparse.target);
  require(model::qwenTargetGeometry(moe).moeShape().weightLayout == ops::WeightLayout::Affine64,
          "the MoE shape lost the blocks' layout");
  for (auto &layer : moe.layers) layer.ffn = ops::BlockMoeWeights{};
  require(model::qwenTargetGeometry(moe).moeShape().weightLayout == ops::WeightLayout::Block32 &&
              moe.logitsProjection.layout() == ops::WeightLayout::Affine64,
          "the MoE shape must follow the expert layers, not the head");
  moe.layers.back().ffn = ops::AffineMoeWeights{};
  bool mixedRejected = false;
  try { static_cast<void>(model::qwenTargetGeometry(moe)); }
  catch (const model::WeightStoreError &) { mixedRejected = true; }
  require(mixedRejected, "a target mixing MoE layouts reached execution");
}

void checkPrefillSharing(const model::ModelPackage &package) {
  using model::PrefillLifetime;
  using model::PrefillTensor;
  for (uint32_t family : {9U, 10U, 11U}) for (auto kvFormat : {kv::Format::Int8, kv::Format::BFloat16}) {
    DeviceCapabilities device;
    device.appleGpuFamily = family;
    device.gpuCoreCount = 8;
    ops::ExecutionPlans plans(device);
    const auto geometry = model::RuntimeGeometry::from(package, kvFormat);
    const auto layout = model::planPrefillArena(geometry, plans);
    const auto decode = model::decodeTensorBytes(geometry, plans);
    uint64_t decodeOwn = 0, decodeShared = 0;
    for (uint32_t i = 0; i < model::decodeTensorCount; ++i) {
      auto &bytes = model::isSharedDecodeTensor(model::DecodeTensor(i)) ? decodeShared : decodeOwn;
      bytes += alignUp(decode[i] * model::kLaneCount);
    }
    require(decodeOwn == model::decodeArenaBaseBytes(geometry, plans) &&
                decodeShared == model::sharedDecodeWorkspaceBytes(geometry, plans) &&
                decodeShared <= layout.workspaceBytes &&
                layout.workspaceOffset + layout.workspaceBytes == layout.bytes,
            "decode scratch does not fit the shared prefill workspace");
    for (auto tensor : {model::DecodeTensor::Hidden0, model::DecodeTensor::InputTokens,
                       model::DecodeTensor::Logits, model::DecodeTensor::PenaltyState,
                       model::DecodeTensor::PageTable, model::DecodeTensor::ConstraintMasks,
                       model::DecodeTensor::SamplingUniforms})
      require(!model::isSharedDecodeTensor(tensor), "prefill sampling or persistent state borrowed phase scratch");
    uint64_t separate = 0;
    for (uint32_t i = 0; i < model::prefillTensorCount; ++i) {
      separate += alignUp(layout.sizes[i]);
      require(layout.offsets[i] % kHostPageBytes == 0 &&
                  layout.offsets[i] <= layout.bytes && layout.sizes[i] <= layout.bytes - layout.offsets[i],
              "prefill tensor is unaligned or outside its arena");
      for (uint32_t j = 0; j < i; ++j) {
        if (!layout.sizes[i] || !layout.sizes[j]) continue;
        const bool overlap = layout.offsets[i] < layout.offsets[j] + layout.sizes[j] &&
                             layout.offsets[j] < layout.offsets[i] + layout.sizes[i];
        const auto a = model::prefillLifetime(PrefillTensor(i)), b = model::prefillLifetime(PrefillTensor(j));
        const bool residualPair = a == PrefillLifetime::MixerResidual && b == PrefillLifetime::MixerResidual;
        const bool scratchPair = a != b && a != PrefillLifetime::Persistent && b != PrefillLifetime::Persistent &&
                                 a != PrefillLifetime::MixerResidual && b != PrefillLifetime::MixerResidual;
        require(!overlap || residualPair || scratchPair,
                "prefill buffers with overlapping lifetimes share storage");
      }
    }
    require(layout.bytes == model::plannedPrefillBytes(geometry, plans) &&
                separate > layout.bytes && separate - layout.bytes > 200ULL * 1024 * 1024,
            "prefill workspace sharing did not reduce planned memory");
    for (auto tensor : {PrefillTensor::Hidden0, PrefillTensor::Hidden1, PrefillTensor::Normalized,
                       PrefillTensor::Captured, PrefillTensor::RopeCos, PrefillTensor::RopeSin,
                       PrefillTensor::DraftRopeCos, PrefillTensor::DraftRopeSin,
                       PrefillTensor::LinearRotated, PrefillTensor::LinearCounters})
      require(model::prefillLifetime(tensor) == PrefillLifetime::Persistent,
              "live prefill or shared operator scratch was recycled");
  }
}

// One decode arena serves every lane count, and on Apple10 and later a
// Split128 plan's partials grow with the rows. The arena must hold every
// lane's plan of every affine target and draft projection at the measured
// core counts.
void checkLaneScratch(const model::ModelPackage &package) {
  const auto geometry = model::RuntimeGeometry::from(package, kv::Format::Int8);
  const auto &d = geometry.draft;
  std::vector<ops::LinearMatrix> matrices{
      {d.dynamicSize, d.hiddenSize}, {d.qkvSize, d.hiddenSize}, {d.contextKvSize(), d.hiddenSize},
      {d.hiddenSize, d.attentionSize},
      {d.intermediateSize, d.hiddenSize}, {d.hiddenSize, d.intermediateSize},
      {d.selectorRank, d.hiddenSize}, {d.hiddenSize, d.targetHiddenSize}};
  for (const auto &p : geometry.target.decodeProjections)
    if (p.layout == ops::WeightLayout::Affine64) matrices.push_back({p.outputSize, p.inputSize});
  for (uint32_t family : {10U, 11U})
    for (uint32_t cores : {12U, 20U, 40U}) {
      DeviceCapabilities device;
      device.appleGpuFamily = family;
      device.gpuCoreCount = cores;
      const ops::ExecutionPlans plans(device);
      const auto scratch = model::DecodeArena::linearScratchSize(geometry, plans);
      for (const auto matrix : matrices)
        for (uint32_t lanes = 1; lanes <= model::kLaneCount; ++lanes)
          for (auto epilogue : {ops::LinearEpilogue::None, ops::LinearEpilogue::Residual,
                                ops::LinearEpilogue::GateUp}) {
            const auto need = plans.linear().plan({matrix, lanes * model::kDecodeRows,
                ops::LinearPhase::Decode, epilogue}).scratchSize();
            require(scratch.partials >= need.partials && scratch.counters >= need.counters,
                    "decode arena scratch below a lane's affine plan");
          }
    }
}

// Arenas are sized from the projections the weights hold, so each must have
// sizes; an empty one would drop its workspace from the bound silently.
void checkUnsizedProjection() {
  auto broken = test::runtimeGeometryPackage<model::Qwen3_8Weights>();
  std::get<model::Qwen3_8Weights>(broken.target).layers.back().downProjection = ops::Projection();
  bool rejected = false;
  try { static_cast<void>(model::RuntimeGeometry::from(broken, kv::Format::Int8)); }
  catch (const std::invalid_argument &) { rejected = true; }
  require(rejected, "a target projection without sizes reached arena sizing");
}

// The GDN value rows are sized with attentionWidth, so a layout whose value
// heads span another width is refused before loading. Arena sizing checks
// the GDN shape, whose packed rows must also hold the two gates of every
// value head.
void checkGdnWidths() {
  const auto sparse = test::runtimeGeometryPackage<model::Qwen3_6MoeWeights>();
  const auto layoutRejected = [](const model::Qwen3_6MoeLayout &layout) {
    try { model::requireQwenLayout(layout); }
    catch (const model::WeightStoreError &) { return true; }
    return false;
  };
  const auto geometryRejected = [&](const model::Qwen3_6MoeLayout &layout) {
    auto broken = sparse;
    std::get<model::Qwen3_6MoeWeights>(broken.target).layout = layout;
    try { static_cast<void>(model::RuntimeGeometry::from(broken, kv::Format::Int8)); }
    catch (const std::invalid_argument &) { return true; }
    return false;
  };
  const model::Qwen3_6MoeLayout shipped;
  require(!layoutRejected(shipped) && !geometryRejected(shipped),
          "the shipped sparse layout was refused");
  auto narrowValues = shipped;
  narrowValues.gdnValueHeads = narrowValues.gdnKeyHeads;
  narrowValues.convolutionDimension = 3 * narrowValues.gdnKeyHeads * narrowValues.gdnHeadDimension;
  require(layoutRejected(narrowValues),
          "a GDN value width other than attentionWidth was accepted");
  auto withoutGates = shipped;
  withoutGates.packedGdnWidth = shipped.convolutionDimension + shipped.attentionWidth;
  require(geometryRejected(withoutGates), "packed GDN rows without the gates reached arena sizing");
}

} // namespace

int main() {
  try {
    checkUnsizedProjection();
    checkGdnWidths();
    checkMixedLayouts();
    const auto dense = test::runtimeGeometryPackage<model::Qwen3_8Weights>();
    const auto sparse = test::runtimeGeometryPackage<model::Qwen3_6MoeWeights>();
    checkLaneScratch(dense);
    checkLaneScratch(sparse);
    checkPrefillSharing(dense);
    checkPrefillSharing(sparse);
    std::cout << "model execution plans: PASS (two paired geometries)\n";
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
