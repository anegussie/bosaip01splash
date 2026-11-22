#include "model/InklingSequence.hpp"

#include "AwakeClock.hpp"
#include "model/InklingCheckpoint.hpp"
#include "ops/Embedding.hpp"
#include "ops/Inkling.hpp"
#include "ops/Linear.hpp"
#include "ops/RowCopy.hpp"

#include <algorithm>
#include <bit>
#include <bitset>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iterator>
#include <list>
#include <map>
#include <numeric>
#include <unistd.h>
#include <vector>

namespace splash::model {
namespace {

using metal::MetalBuffer;
using Layout = InklingCheckpoint;
using Clock = AwakeClock;
constexpr uint32_t hidden = Layout::hidden;
constexpr uint32_t queryWidth = Layout::queryHeads * Layout::headWidth;
constexpr uint32_t kvWidth = Layout::kvHeads * Layout::headWidth;
constexpr uint32_t relativeWidth = Layout::queryHeads * SPLASH_INKLING_RELATIVE_WIDTH;
constexpr uint32_t expertWidth = Layout::expertWidth;
constexpr uint32_t routes = Layout::expertsPerToken;
constexpr float clipThreshold = 22.627417f;
constexpr uint32_t blockLayers = 6;
constexpr uint32_t coreLayers = Layout::coreEnd - Layout::coreBegin;
constexpr bool isCoreLayer(uint32_t layer) noexcept {
  return layer >= Layout::coreBegin && layer < Layout::coreEnd;
}
constexpr uint32_t globalAttentionRows = 256;
constexpr uint32_t expertBatch = SPLASH_INKLING_EXPERT_BATCH;
constexpr uint32_t expertTileRows = SPLASH_INKLING_EXPERT_TILE_ROWS;
constexpr uint64_t kvRowBytes = 2 * kvWidth * sizeof(uint16_t);
constexpr uint64_t stagingReserveBytes = 128ull << 20;

uint64_t availableAfter(uint64_t total, uint64_t reserved) noexcept {
  return total > reserved ? total - reserved : 0;
}

double secondsSince(Clock::time_point start) noexcept {
  return std::chrono::duration<double>(Clock::now() - start).count();
}

template <class T = float> T *data(const MetalBuffer &buffer) { return static_cast<T *>(buffer.contents()); }

// Each layer visit keeps its own key/value history and convolution taps.
struct VisitState {
  MetalBuffer keys, values;
  std::array<MetalBuffer, 4> convolution;
  uint32_t slots = 0;
};

} // namespace

class InklingSequence::Impl final {
  using ExpertRanks = std::array<uint32_t, Layout::experts>;
  using ExpertMask = std::bitset<Layout::experts>;
  using ExpertRoutes = std::array<std::vector<uint32_t>, Layout::experts>;
  struct CachedExpert {
    uint32_t key;
    uint64_t bytes;
    ops::InklingExpertWeights weights;
    bool protectedEntry;
  };
  using ExpertCache = std::list<CachedExpert>;

public:
  Impl(metal::MetalBackend &backend, const std::filesystem::path &path, uint32_t capacity, InklingCacheBudget budget)
      : backend(backend), source({path}), checkpoint(source.file()), capacity(capacity), cacheBudget(std::move(budget)) {
    if (!capacity || capacity > InklingSequence::maximumContext)
      throw std::invalid_argument("Inkling context must be between 1 and " +
                                  std::to_string(InklingSequence::maximumContext));
    const uint32_t rows = std::min(capacity, InklingSequence::chunkRows);
    const auto floats = [&](uint64_t count) { return allocate(count, sizeof(float)); };
    const auto halves = [&](uint64_t count) { return allocate(count, sizeof(uint16_t)); };
    const auto words = [&](uint64_t count) { return allocate(count, sizeof(uint32_t)); };
    scratch.tokens = words(rows);
    scratch.embedding = halves(uint64_t{rows} * hidden);
    scratch.current = floats(uint64_t{rows} * hidden);
    scratch.next = floats(uint64_t{rows} * hidden);
    scratch.mixed = floats(uint64_t{rows} * 3 * hidden);
    scratch.messages = floats(uint64_t{rows} * 2 * hidden);
    scratch.messageKeys = floats(uint64_t{rows} * 2 * hidden);
    scratch.passOutput = floats(uint64_t{rows} * hidden);
    scratch.passEntry = floats(uint64_t{rows} * hidden);
    scratch.passBlock = floats(uint64_t{rows} * hidden);
    for (auto &buffer : scratch.packed) buffer = halves(uint64_t{rows} * hidden);
    scratch.controlNormalized = halves(uint64_t{rows} * 2 * hidden);
    scratch.controlDown = halves(uint64_t{rows} * SPLASH_INKLING_GATE_RANK);
    scratch.controlGain = floats(uint64_t{rows} * hidden);
    scratch.controlForget = floats(uint64_t{rows} * hidden);
    scratch.controlOutput = floats(uint64_t{rows} * hidden);
    scratch.query = floats(uint64_t{rows} * queryWidth);
    scratch.relative = floats(uint64_t{rows} * relativeWidth);
    scratch.sinks = floats(uint64_t{rows} * Layout::queryHeads);
    scratch.gate = floats(uint64_t{rows} * queryWidth);
    scratch.keys = floats(uint64_t{rows} * kvWidth);
    scratch.values = floats(uint64_t{rows} * kvWidth);
    scratch.dynamic = floats(uint64_t{rows} * SPLASH_INKLING_KV_HEADS * 4);
    scratch.attended = halves(uint64_t{rows} * queryWidth);
    if (const auto bytes = ops::inklingAttentionScratchBytes(std::min(rows, globalAttentionRows), capacity))
      scratch.attentionPartials = allocate(bytes, 1);
    scratch.attention = floats(uint64_t{rows} * hidden);
    scratch.feedForward = floats(uint64_t{rows} * hidden);
    scratch.expertSum = floats(uint64_t{rows} * hidden);
    scratch.scores = floats(uint64_t{rows} * Layout::experts);
    scratch.selected = words(uint64_t{rows} * routes);
    scratch.weights = floats(uint64_t{rows} * routes);
    scratch.order = words(uint64_t{rows} * routes);
    scratch.inverseOrder = words(uint64_t{rows} * routes);
    scratch.expertInput = halves(uint64_t{rows} * routes * hidden);
    scratch.expertGateUp = floats(uint64_t{rows} * routes * 2 * expertWidth);
    scratch.expertActive = halves(uint64_t{rows} * routes * expertWidth);
    scratch.expertOutput = floats(uint64_t{rows} * routes * hidden);
    for (uint32_t i = 0; i < scratch.expertEntries.size(); ++i) {
      scratch.expertEntries[i] = allocate(expertBatch, sizeof(InklingExpertEntry));
      scratch.expertTiles[i] = allocate(rows * routes / expertTileRows + expertBatch, sizeof(InklingExpertTile));
    }
    for (auto &buffer : scratch.blocks) buffer = floats(uint64_t{rows} * hidden);
    scratch.logits = floats(Layout::paddedVocabulary);

    const auto sliding = std::ranges::count_if(checkpoint.visits(), &Layout::Visit::sliding);
    // Include an idle prefix alongside the live sliding ring, and the old
    // buffer of one global visit while its KV allocation grows.
    const uint32_t oldGlobalSlots = capacity > 2048 ? std::bit_floor(capacity - 1) : 0;
    const uint64_t kvSlots = uint64_t(Layout::logicalLayers - sliding) * capacity +
                             2 * uint64_t(sliding) * (Layout::window + rows) + oldGlobalSlots;
    const uint64_t fixedBytes = backend.memoryStats().allocatedBytes + checkpoint.residentTensorBytes() +
                                kvSlots * kvRowBytes + stagingReserveBytes;
    maximumExpertBudget = availableAfter(cacheBudget.metalBytes, fixedBytes);
    refreshExpertBudget();
  }

  void run(metal::CommandGraph &graph) {
    static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
  }

  MetalBuffer allocate(uint64_t count, uint32_t bytes = sizeof(float)) {
    return backend.allocateBuffer(count * bytes, metal::BufferStorage::Shared, "Inkling sequence");
  }

  // The leading `count` elements of a scratch buffer, as the dispatch sees it.
  MetalBuffer slice(const MetalBuffer &buffer, uint64_t count, uint32_t bytes) {
    return backend.view(buffer, 0, count * bytes);
  }

  MetalBuffer rows(const MetalBuffer &buffer, uint32_t row, uint32_t count, uint32_t width, uint32_t bytes) {
    return backend.view(buffer, uint64_t{row} * width * bytes, uint64_t{count} * width * bytes);
  }

  MetalBuffer read(const GgufTensor &tensor, uint64_t index = 0, uint64_t slices = 1) {
    if (!slices || index >= slices || tensor.bytes % slices)
      throw GgufError("invalid Inkling tensor slice: " + tensor.name);
    const uint64_t bytes = tensor.bytes / slices;
    auto result = allocate(bytes, 1);
    source.file().source(tensor.file).readData(tensor.offset + index * bytes, {data<uint8_t>(result), size_t(bytes)});
    return result;
  }

  const MetalBuffer &weight(const std::string &name) {
    auto found = resident.find(name);
    if (found == resident.end()) found = resident.emplace(name, read(source.file().require(name))).first;
    return found->second;
  }

  ops::QuantizedSegment matrix(const std::string &name) {
    const auto &tensor = source.file().require(name);
    const uint32_t format = tensor.type == ggml::kF32 ? ops::QuantizedSegment::kFloat32 : gguf_format_of(tensor.type);
    return ops::QuantizedSegment::rows(format, uint32_t(tensor.dims[1]), uint32_t(tensor.dims[0]), weight(name));
  }

  void project(metal::CommandGraph &graph, const MetalBuffer &input, const std::string &name, MetalBuffer output,
               uint32_t rows, uint32_t outputs = 0) {
    auto weights = matrix(name);
    if (outputs) weights.outputSize = outputs;
    ops::addGgufFloat(graph, input, weights, output, rows, weights.outputSize, 0, ops::FloatOutput::Float32,
                      rows == 1 && weights.outputSize >= 256 ? ops::FloatTile::Vector : ops::FloatTile::Simdgroup);
  }

  uint32_t stateHistory(VisitState &state, bool sliding, uint32_t rows) {
    const uint32_t needed = sliding ? Layout::window + std::min(capacity, InklingSequence::chunkRows) : position + rows;
    if (state.slots >= needed) return state.slots;
    const uint32_t slots = sliding ? needed : std::min(capacity, std::bit_ceil(std::max(needed, 2048u)));
    auto keys = allocate(uint64_t{slots} * kvWidth, sizeof(uint16_t));
    auto values = allocate(uint64_t{slots} * kvWidth, sizeof(uint16_t));
    if (state.slots) {
      const uint64_t bytes = uint64_t{position} * kvWidth * sizeof(uint16_t);
      std::memcpy(keys.contents(), state.keys.contents(), bytes);
      std::memcpy(values.contents(), state.values.contents(), bytes);
    }
    state.keys = std::move(keys);
    state.values = std::move(values);
    state.slots = slots;
    return state.slots;
  }

  void trimExperts(uint64_t target) noexcept {
    while (expertBytes > target) {
      auto &cache = expertCache.empty() ? protectedExperts : expertCache;
      const auto &victim = cache.back();
      expertBytes -= victim.bytes;
      if (victim.protectedEntry) protectedExpertBytes -= victim.bytes;
      expertIndex.erase(victim.key);
      cache.pop_back();
    }
  }

  uint64_t protectedBudget() const noexcept { return expertBudget * 3 / 4; }

  void demoteExpert(ExpertCache::iterator entry) noexcept {
    protectedExpertBytes -= entry->bytes;
    entry->protectedEntry = false;
    expertCache.splice(expertCache.end(), protectedExperts, entry);
  }

  void refreshExpertBudget() {
    expertBudget = cacheBudget.hostCap ? std::min(maximumExpertBudget, cacheBudget.hostCap(maximumExpertBudget, expertBytes))
                                       : maximumExpertBudget;
    while (protectedExpertBytes > protectedBudget()) demoteExpert(std::prev(protectedExperts.end()));
    trimExperts(expertBudget);
  }

  ExpertMask preferCoreExperts(uint32_t physical, const ExpertRoutes &grouped, const GgufTensor &gate,
                               const GgufTensor &down) {
    ExpertMask preferred;
    if (!isCoreLayer(physical)) return preferred;

    auto &ranks = expertRanks[physical - Layout::coreBegin];
    ExpertRanks order;
    std::iota(order.begin(), order.end(), 0u);
    for (uint32_t expert : order) ranks[expert] = ranks[expert] / 2 + uint32_t(grouped[expert].size());

    // Workloads that touch every expert in layer order can flush the entire
    // cache between passes. Give each repeated layer a share, ranked by the
    // number of routed rows with a decaying contribution from earlier visits.
    const auto sliceBytes = [&](const GgufTensor &tensor) {
      const uint64_t bytes = tensor.bytes / Layout::experts;
      return (bytes + expertPageBytes - 1) / expertPageBytes * expertPageBytes;
    };
    const uint64_t bytes = sliceBytes(gate) + sliceBytes(down);
    const auto count = std::min<uint64_t>(Layout::experts, protectedBudget() / coreLayers / bytes);
    std::partial_sort(order.begin(), order.begin() + count, order.end(), [&](uint32_t left, uint32_t right) {
      return ranks[left] == ranks[right] ? left < right : ranks[left] > ranks[right];
    });
    for (uint32_t expert : std::span(order).first(count)) {
      if (ranks[expert]) preferred.set(expert);
    }
    for (auto entry = protectedExperts.begin(); entry != protectedExperts.end();) {
      const auto current = entry++;
      if (current->key / Layout::experts == physical && !preferred.test(current->key % Layout::experts))
        demoteExpert(current);
    }
    return preferred;
  }

  void shortConv(metal::CommandGraph &graph, const MetalBuffer &projection, VisitState &state, uint32_t channel,
                 const std::string &name, uint32_t width, uint32_t rows, const MetalBuffer &dynamic) {
    auto &history = state.convolution[channel];
    if (!history) {
      history = allocate(width * 3);
      std::memset(history.contents(), 0, history.sizeBytes());
    }
    ops::addInklingConvolution(graph, projection, weight(name), history, rows, width, dynamic,
                               dynamic ? Layout::kvHeads : 0);
  }

  // Each pass of the looped core mixes the blocks and the previous pass with
  // its learned queries; the four messages feed attention, K, V and the FFN.
  void loopMessages(metal::CommandGraph &graph, const Layout::Visit &visit,
                    std::span<const MetalBuffer> previous, const MetalBuffer &previousOutput, uint32_t rows) {
    const uint32_t index = 2 * (visit.physicalLayer - Layout::coreBegin);
    const auto attentionQueries = view(weight("loop_res_query.weight"), uint64_t{index} * hidden * sizeof(float),
                                       2 * hidden * sizeof(float));
    const auto keyQueries = view(weight("loop_kv_res_query.weight"), uint64_t{index} * hidden * sizeof(float),
                                 2 * hidden * sizeof(float));
    std::vector<MetalBuffer> states(previous.begin(), previous.end());
    states.push_back(previousOutput);
    ops::addInklingResidualMix(graph, states, attentionQueries, scratch.messages, rows, 2);
    ops::addInklingResidualMix(graph, states, keyQueries, scratch.messageKeys, rows, 2);
  }

  MetalBuffer view(const MetalBuffer &buffer, uint64_t offset, uint64_t bytes) {
    return backend.view(buffer, offset, bytes);
  }

  void copyResidual(metal::CommandGraph &graph, const MetalBuffer &source, const MetalBuffer &destination,
                    uint32_t rows) {
    // RowCopy moves 16-bit elements bit-for-bit, two for each FP32 value.
    constexpr uint32_t words = 2 * hidden;
    ops::RowCopy::add(graph, source, {0, words, 0}, destination, {0, words, 0}, rows, words);
  }

  MetalBuffer block(metal::CommandGraph &graph, const Layout::Visit &visit, std::vector<MetalBuffer> &blocks,
             const std::array<MetalBuffer, 4> &messages, uint32_t rows) {
    const std::string prefix = "blk." + std::to_string(visit.physicalLayer) + ".";
    VisitState &state = states[visit.stateSlot];
    const MetalBuffer current = scratch.current;

    std::array<MetalBuffer, 3> inputs{current, current, current};
    if (visit.physicalLayer) {
      std::vector<MetalBuffer> states = blocks;
      states.push_back(current);
      ops::addInklingResidualMix(graph, states, weight(prefix + "attn_res_query.weight"), scratch.mixed, rows,
                                visit.sliding ? 1 : 3);
      const uint64_t bytes = uint64_t{rows} * hidden * sizeof(float);
      for (uint32_t i = 0; i < 3; ++i) inputs[i] = backend.view(scratch.mixed, (visit.sliding ? 0 : i) * bytes, bytes);
    }

    const bool sharedNorm = visit.sliding && !messages[0];
    auto packed = scratch.packed;
    constexpr std::array<std::string_view, 3> projection{"q", "k", "v"};
    constexpr std::array<std::string_view, 3> control{"attn", "k", "v"};
    for (uint32_t i = 0; i < 3; ++i) {
      if (sharedNorm && i) {
        packed[i] = packed[0];
        continue;
      }
      MetalBuffer source = inputs[i];
      if (messages[i]) {
        const ops::InklingControlWeights weights{matrix(prefix + "loop_" + std::string(control[i]) + "_down.weight"),
                                                matrix(prefix + "loop_" + std::string(control[i]) + "_gain.weight"),
                                                matrix(prefix + "loop_" + std::string(control[i]) + "_forget.weight")};
        const ops::InklingControlBuffers buffers{source, messages[i], scratch.controlOutput, scratch.controlNormalized,
                                                scratch.controlDown, scratch.controlGain, scratch.controlForget};
        ops::addInklingControl(graph, weights, buffers, rows);
        source = scratch.controlOutput;
      }
      const std::string norm =
          visit.sliding ? "attn_norm.weight" : "attn_" + std::string(projection[i]) + "_inp_norm.weight";
      ops::addInklingNorm(graph, source, weight(prefix + norm), packed[i], rows, hidden);
    }

    project(graph, packed[0], prefix + "attn_q.weight", scratch.query, rows);
    project(graph, packed[0], prefix + "attn_rel.weight", scratch.relative, rows);
    project(graph, packed[0], prefix + "attn_sink_proj.weight", scratch.sinks, rows);
    project(graph, packed[0], prefix + "attn_gate.weight", scratch.gate, rows);
    project(graph, packed[1], prefix + "attn_k.weight", scratch.keys, rows);
    project(graph, packed[2], prefix + "attn_v.weight", scratch.values, rows);

    if (!visit.sliding)
      project(graph, packed[1], prefix + "attn_k_conv_proj.weight", scratch.dynamic, rows);
    shortConv(graph, scratch.keys, state, 0, prefix + "attn_k_conv.weight", kvWidth, rows,
              visit.sliding ? MetalBuffer{} : scratch.dynamic);
    if (!visit.sliding)
      project(graph, packed[2], prefix + "attn_v_conv_proj.weight", scratch.dynamic, rows);
    shortConv(graph, scratch.values, state, 1, prefix + "attn_v_conv.weight", kvWidth, rows,
              visit.sliding ? MetalBuffer{} : scratch.dynamic);

    const MetalBuffer taps = weight(prefix + "attn_q_clip.weight");
    ops::addInklingHeadClip(graph, scratch.query, taps, position, rows, Layout::queryHeads, Layout::headWidth,
                            clipThreshold, !visit.sliding, false, true);
    ops::addInklingHeadClip(graph, scratch.relative, weight(prefix + "attn_rel_clip.weight"), position, rows,
                            Layout::queryHeads, SPLASH_INKLING_RELATIVE_WIDTH, 8.0f, !visit.sliding, false, true);
    ops::addInklingHeadClip(graph, scratch.keys, taps, position, rows, Layout::kvHeads, Layout::headWidth,
                            clipThreshold, false, false, false);
    ops::addInklingHeadClip(graph, scratch.values, taps, position, rows, Layout::kvHeads, Layout::headWidth,
                            0.0f, false, true, false);

    const uint32_t slots = stateHistory(state, visit.sliding, rows);
    ops::addInklingKeyValueStore(graph, scratch.keys, scratch.values, state.keys, state.values, position, rows, slots);
    const auto relativeTable = weight(prefix + "attn_rel_bias.weight");
    const uint32_t queryBatch = visit.sliding ? rows : globalAttentionRows;
    for (uint32_t first = 0; first < rows; first += queryBatch) {
      const uint32_t count = std::min(queryBatch, rows - first);
      const auto sliceRows = [&](const MetalBuffer &buffer, uint32_t width, uint32_t bytes = sizeof(float)) {
        return this->rows(buffer, first, count, width, bytes);
      };
      ops::addInklingAttention(graph, {sliceRows(scratch.query, queryWidth), sliceRows(scratch.relative, relativeWidth),
                                       relativeTable, sliceRows(scratch.sinks, Layout::queryHeads),
                                       sliceRows(scratch.gate, queryWidth), state.keys, state.values,
                                       sliceRows(scratch.attended, queryWidth, sizeof(uint16_t)), scratch.attentionPartials},
                              position + first, count, visit.sliding, slots);
    }
    project(graph, scratch.attended, prefix + "attn_output.weight", scratch.attention, rows);
    shortConv(graph, scratch.attention, state, 2, prefix + "attn_post_conv.weight", hidden, rows, {});

    MetalBuffer ffnResidual = scratch.attention;
    if (visit.physicalLayer % blockLayers == 0) {
      // Save inpSA, the layer-entry residual before Q/K/V mixing. The block's
      // first layer starts a new residual stream from the attention output.
      const auto &saved = scratch.blocks.at(blocks.size());
      copyResidual(graph, current, saved, rows);
      blocks.push_back(saved);
    } else {
      ops::addInklingAdd(graph, scratch.attention, current, scratch.next, rows * hidden);
      ffnResidual = scratch.next;
    }

    std::vector<MetalBuffer> states = blocks;
    states.push_back(ffnResidual);
    ops::addInklingResidualMix(graph, states, weight(prefix + "ffn_res_query.weight"), scratch.feedForward, rows, 1);
    MetalBuffer ffnSource = scratch.feedForward;
    if (messages[3]) {
      const ops::InklingControlWeights weights{matrix(prefix + "loop_mlp_down.weight"),
                                              matrix(prefix + "loop_mlp_gain.weight"),
                                              matrix(prefix + "loop_mlp_forget.weight")};
      const ops::InklingControlBuffers buffers{scratch.feedForward, messages[3], scratch.controlOutput,
                                              scratch.controlNormalized, scratch.controlDown, scratch.controlGain,
                                              scratch.controlForget};
      ops::addInklingControl(graph, weights, buffers, rows);
      ffnSource = scratch.controlOutput;
    }
    ops::addInklingNorm(graph, ffnSource, weight(prefix + "ffn_norm.weight"), scratch.packed[0], rows,
                        hidden);
    project(graph, scratch.packed[0], prefix + "ffn_gate_inp.weight", scratch.scores, rows);
    ops::addInklingRouting(graph, scratch.scores, weight(prefix + "exp_probs_b.bias"), scratch.selected,
                           scratch.weights, rows);
    return ffnResidual;
  }

  // The routing decided on the GPU, so the experts it picked are gathered here.
  bool experts(uint32_t rows, const Layout::Visit &visit, const MetalBuffer &ffnResidual,
               const std::function<bool()> &stop) {
    const uint32_t physical = visit.physicalLayer;
    const std::string prefix = "blk." + std::to_string(physical) + ".";
    const uint32_t routeCount = rows * routes;
    auto &cacheStats = expertStats[isCoreLayer(physical) ? visit.pass + 1 : 0];
    const auto *selected = data<uint32_t>(scratch.selected);
    ExpertRoutes grouped;
    for (uint32_t route = 0; route < routeCount; ++route) grouped.at(selected[route]).push_back(route);
    auto *order = data<uint32_t>(scratch.order);
    auto *inverseOrder = data<uint32_t>(scratch.inverseOrder);
    uint32_t index = 0;
    for (const auto &group : grouped) {
      for (uint32_t route : group) {
        order[index] = route;
        inverseOrder[route] = index++;
      }
    }

    const auto &gate = source.file().require(prefix + "ffn_gate_up_exps.weight");
    const auto &down = source.file().require(prefix + "ffn_down_exps.weight");
    const auto preferred = preferCoreExperts(physical, grouped, gate, down);
    const bool nvfp4 = down.type == ggml::kNVFP4;
    const float *gateScales = nvfp4 ? data(weight(prefix + "ffn_gate_up_exps.scale")) : nullptr;
    const float *downScales = nvfp4 ? data(weight(prefix + "ffn_down_exps.scale")) : nullptr;

    auto &timing = execution[rows == 1];
    const ops::InklingExpertBuffers buffers{scratch.expertInput, scratch.expertGateUp,
                                            scratch.expertActive, scratch.expertOutput};
    metal::CommandGraph graph;
    ops::addInklingRouteGather(graph, scratch.packed[0], scratch.order, scratch.expertInput, routeCount, hidden);
    uint32_t start = 0, slot = 0, batchSize = 0, tileCount = 0;
    auto batchWeights = std::make_shared<std::vector<MetalBuffer>>();
    batchWeights->reserve(2 * expertBatch);
    std::optional<metal::CommandTicket> pending;
    const auto waitPending = [&] {
      if (!pending) return;
      const auto began = Clock::now();
      timing.expertGpuSeconds += pending->wait().gpuSeconds;
      timing.expertWaitSeconds += secondsSince(began);
      pending.reset();
    };
    const auto gateFormat = ops::QuantizedSegment::rows(gguf_format_of(gate.type), 2 * expertWidth, hidden,
                                                       MetalBuffer{}).name();
    const auto dispatch = [&](bool last) {
      waitPending();
      auto &entries = scratch.expertEntries[slot];
      ops::addInklingExpertBatch(graph, buffers, entries, scratch.expertTiles[slot],
                                batchWeights, batchSize, tileCount, gateFormat, nvfp4, rows == 1);
      if (last) {
        // Sum in original route order, convolve, then add the FFN residual.
        ops::addInklingRouteAccumulate(graph, scratch.expertOutput, scratch.inverseOrder, scratch.weights,
                                      scratch.expertSum, routeCount, hidden);
        shortConv(graph, scratch.expertSum, states[visit.stateSlot], 3, prefix + "ffn_post_conv.weight", hidden, rows, {});
        ops::addInklingAdd(graph, ffnResidual, scratch.expertSum, scratch.current, rows * hidden);
      }
      pending.emplace(backend.submitCommandAsync(graph.command()));
      ++timing.expertCommands;
      graph = metal::CommandGraph{};
      slot ^= 1;
      if (!last) {
        batchWeights = std::make_shared<std::vector<MetalBuffer>>();
        batchWeights->reserve(2 * expertBatch);
      }
      batchSize = tileCount = 0;
    };
    for (uint32_t expert = 0; expert < Layout::experts; ++expert) {
      const uint32_t count = uint32_t(grouped[expert].size());
      if (!count) continue;
      if (stop()) return false;
      const auto began = Clock::now();
      const auto weights = cachedExpert(physical, expert, gate, down, nvfp4, gateScales, downScales, cacheStats,
                                        preferred.test(expert));
      timing.expertStageSeconds += secondsSince(began);
      data<InklingExpertEntry>(scratch.expertEntries[slot])[batchSize] = {
          start, count, weights.gateUpScale, weights.downScale};
      auto *tiles = data<InklingExpertTile>(scratch.expertTiles[slot]);
      for (uint32_t tile = 0; tile * expertTileRows < count; ++tile) tiles[tileCount++] = {batchSize, tile};
      batchWeights->push_back(weights.gateUp.plane0);
      batchWeights->push_back(weights.down);
      start += count;
      ++batchSize;
      if (batchSize == expertBatch && start < routeCount) dispatch(false);
    }
    dispatch(true);
    waitPending();
    return true;
  }

  ops::InklingExpertWeights cachedExpert(uint32_t physical, uint32_t expert, const GgufTensor &gate,
                                         const GgufTensor &down, bool nvfp4, const float *gateScales,
                                         const float *downScales, InklingExpertCacheStats &stats, bool preferred) {
    const uint32_t key = physical * Layout::experts + expert;
    ++stats.lookups;
    if (const auto found = expertIndex.find(key); found != expertIndex.end()) {
      ++stats.hits;
      const auto entry = found->second;
      if (entry->protectedEntry) {
        protectedExperts.splice(protectedExperts.begin(), protectedExperts, entry);
      } else if (preferred && protectedExpertBytes + entry->bytes <= protectedBudget()) {
        protectedExpertBytes += entry->bytes;
        entry->protectedEntry = true;
        protectedExperts.splice(protectedExperts.begin(), expertCache, entry);
      } else {
        expertCache.splice(expertCache.begin(), expertCache, entry);
      }
      return entry->weights;
    }
    const uint64_t payload = (gate.bytes + down.bytes) / Layout::experts;
    if (payload <= expertBudget) trimExperts(expertBudget - payload);
    ops::InklingExpertWeights weights{
        ops::QuantizedSegment::rows(gguf_format_of(gate.type), 2 * expertWidth, hidden,
                                    read(gate, expert, Layout::experts)),
        read(down, expert, Layout::experts), nvfp4, gateScales ? gateScales[expert] : 1.0f,
        downScales ? downScales[expert] : 1.0f,
    };
    const uint64_t bytes = weights.gateUp.plane0.allocatedBytes() + weights.down.allocatedBytes();
    readExpertBytes += payload;
    stats.readBytes += payload;
    if (bytes > expertBudget) return weights;
    trimExperts(expertBudget - bytes);
    const bool protect = preferred && protectedExpertBytes + bytes <= protectedBudget();
    auto &cache = protect ? protectedExperts : expertCache;
    cache.push_front({key, bytes, weights, protect});
    expertIndex.emplace(key, cache.begin());
    if (protect) protectedExpertBytes += bytes;
    expertBytes += bytes;
    return weights;
  }

  std::span<const float> evaluate(std::span<const uint32_t> tokens, bool logits, const std::function<bool()> &stop) {
    if (tokens.empty() || tokens.size() > InklingSequence::chunkRows || tokens.size() + position > capacity ||
        std::ranges::any_of(tokens, [](uint32_t token) { return token >= Layout::vocabulary; }))
      throw std::invalid_argument("invalid Inkling input chunk");
    const uint32_t rows = uint32_t(tokens.size());
    refreshExpertBudget();
    std::memcpy(scratch.tokens.contents(), tokens.data(), tokens.size_bytes());

    metal::CommandGraph embedding;
    ops::Embedding::add(embedding, scratch.tokens, ops::EmbeddingWeights(Layout::paddedVocabulary, hidden,
        {weight("token_embd.weight"), GGUF_FMT_Q4K}), scratch.embedding, rows);
    ops::addInklingEmbedNorm(embedding, scratch.embedding, weight("token_embd_norm.weight"), scratch.current, rows);
    run(embedding);

    std::vector<MetalBuffer> blocks, prelude, previousPass;
    for (const auto &visit : checkpoint.visits()) {
      if (stop()) return {};
      metal::CommandGraph graph;
      if (visit.physicalLayer == Layout::coreBegin) {
        if (!visit.pass) {
          prelude = blocks;
          copyResidual(graph, scratch.current, scratch.passEntry, rows);
        } else {
          // The fixed two-block core reads the second block's entry and
          // the final output of the prior pass, even after those slots are reused.
          copyResidual(graph, blocks.at(prelude.size() + 1), scratch.passBlock, rows);
          copyResidual(graph, scratch.current, scratch.passOutput, rows);
          previousPass = {scratch.passBlock};
          blocks = prelude;
          copyResidual(graph, scratch.passEntry, scratch.current, rows);
        }
      }
      std::array<MetalBuffer, 4> messages{};
      if (visit.pass) {
        loopMessages(graph, visit, previousPass, scratch.passOutput, rows);
        const auto first = [&](uint32_t index) {
          return backend.view(scratch.messages, uint64_t{index} * rows * hidden * sizeof(float),
                             uint64_t{rows} * hidden * sizeof(float));
        };
        const auto key = [&](uint32_t index) {
          return backend.view(scratch.messageKeys, uint64_t{index} * rows * hidden * sizeof(float),
                             uint64_t{rows} * hidden * sizeof(float));
        };
        messages = {first(0), key(0), key(1), first(1)};
      }
      const auto began = Clock::now();
      const auto ffnResidual = block(graph, visit, blocks, messages, rows);
      run(graph);
      execution[rows == 1].attentionAndRoutingSeconds += secondsSince(began);
      if (!experts(rows, visit, ffnResidual, stop)) return {};
    }
    source.checkUnchanged();
    position += rows;
    if (!logits || stop()) return {};

    std::vector<MetalBuffer> states = blocks;
    states.push_back(scratch.current);
    metal::CommandGraph graph2;
    ops::addInklingResidualMix(graph2, states, weight("output_res_query.weight"), scratch.feedForward, rows, 1);
    ops::addInklingNorm(graph2, scratch.feedForward, weight("output_norm.weight"), scratch.packed[0], rows, hidden);
    const auto last = this->rows(scratch.packed[0], rows - 1, 1, hidden, sizeof(uint16_t));
    project(graph2, last, "output.weight", scratch.logits, 1, Layout::paddedVocabulary);
    ops::addInklingLogitCap(graph2, scratch.logits, Layout::vocabulary, 30.0f);
    run(graph2);
    const std::span<float> result{data(scratch.logits), Layout::vocabulary};
    if (std::ranges::any_of(result, [](float value) { return !std::isfinite(value); }))
      throw std::runtime_error("Inkling produced non-finite logits");
    return result;
  }

  metal::MetalBackend &backend;
  OpenGguf source;
  InklingCheckpoint checkpoint;
  uint32_t capacity, position = 0;
  InklingCacheBudget cacheBudget;
  std::map<std::string, MetalBuffer, std::less<>> resident;
  struct Scratch {
    MetalBuffer tokens, embedding, current, next, mixed, messages, messageKeys, passOutput, passEntry, passBlock;
    std::array<MetalBuffer, 3> packed;
    MetalBuffer controlNormalized, controlDown, controlGain, controlForget, controlOutput;
    MetalBuffer query, relative, sinks, gate, keys, values, dynamic;
    MetalBuffer attended, attentionPartials, attention, feedForward, expertSum, scores, selected, weights, order, inverseOrder;
    MetalBuffer expertInput, expertGateUp, expertActive, expertOutput;
    std::array<MetalBuffer, 2> expertEntries, expertTiles;
    std::array<MetalBuffer, 5> blocks;
    MetalBuffer logits;
  };
  Scratch scratch;
  const uint64_t expertPageBytes = uint64_t(getpagesize());
  uint64_t maximumExpertBudget = 0;
  uint64_t expertBudget = 0;
  uint64_t expertBytes = 0;
  uint64_t protectedExpertBytes = 0;
  uint64_t readExpertBytes = 0;
  std::array<InklingExpertCacheStats, 1 + Layout::passes> expertStats{};
  std::array<InklingExecutionStats, 2> execution{};
  std::array<ExpertRanks, coreLayers> expertRanks{};
  ExpertCache expertCache, protectedExperts;
  std::map<uint32_t, ExpertCache::iterator> expertIndex;
  std::array<VisitState, Layout::logicalLayers> states{};
  struct Prefix {
    std::vector<uint32_t> tokens;
    std::vector<float> logits;
    std::array<VisitState, Layout::logicalLayers> states;
  };
  std::optional<Prefix> prefix;

  std::array<VisitState, Layout::logicalLayers> copyStates(
      const std::array<VisitState, Layout::logicalLayers> &original) {
    std::array<VisitState, Layout::logicalLayers> copy;
    const auto clone = [&](const MetalBuffer &buffer) {
      if (!buffer) return MetalBuffer{};
      auto result = allocate(buffer.sizeBytes(), 1);
      std::memcpy(result.contents(), buffer.contents(), buffer.sizeBytes());
      return result;
    };
    for (size_t slot = 0; slot < original.size(); ++slot) {
      copy[slot].slots = original[slot].slots;
      const bool sliding = checkpoint.visits()[slot].sliding;
      copy[slot].keys = sliding ? clone(original[slot].keys) : original[slot].keys;
      copy[slot].values = sliding ? clone(original[slot].values) : original[slot].values;
      for (size_t channel = 0; channel < original[slot].convolution.size(); ++channel)
        copy[slot].convolution[channel] = clone(original[slot].convolution[channel]);
    }
    return copy;
  }
};

InklingSequence::InklingSequence(metal::MetalBackend &backend, const std::filesystem::path &gguf, uint32_t capacity,
                                 InklingCacheBudget cacheBudget)
    : impl_(std::make_unique<Impl>(backend, gguf, capacity, std::move(cacheBudget))) {}
InklingSequence::~InklingSequence() = default;

void InklingSequence::reset() noexcept {
  impl_->position = 0;
  impl_->states = {};
}

uint32_t InklingSequence::restorePrefix(std::span<const uint32_t> tokens) {
  const auto &prefix = impl_->prefix;
  if (!prefix || tokens.size() < prefix->tokens.size() ||
      !std::ranges::equal(tokens.first(prefix->tokens.size()), prefix->tokens)) {
    releasePrefix();
    return 0;
  }
  impl_->source.checkUnchanged();
  impl_->states = impl_->copyStates(prefix->states);
  impl_->position = uint32_t(prefix->tokens.size());
  if (tokens.size() > impl_->position) releasePrefix();
  return impl_->position;
}

std::span<const float> InklingSequence::prefixLogits() const noexcept {
  if (!impl_->prefix) return {};
  return impl_->prefix->logits;
}

void InklingSequence::rememberPrompt(std::span<const uint32_t> tokens, std::span<const float> logits) {
  if (tokens.size() != impl_->position || logits.size() != Layout::vocabulary)
    throw std::logic_error("cannot cache an incomplete Inkling prompt");
  Impl::Prefix snapshot{{tokens.begin(), tokens.end()}, {logits.begin(), logits.end()},
                        impl_->copyStates(impl_->states)};
  impl_->prefix = std::move(snapshot);
}

void InklingSequence::releasePrefix() noexcept { impl_->prefix.reset(); }

void InklingSequence::releaseExperts() noexcept {
  impl_->trimExperts(0);
  impl_->expertRanks = {};
}

uint64_t InklingSequence::expertReadBytes() const noexcept { return impl_->readExpertBytes; }
uint64_t InklingSequence::expertCacheBytes() const noexcept { return impl_->expertBytes; }
uint64_t InklingSequence::protectedExpertCacheBytes() const noexcept { return impl_->protectedExpertBytes; }
uint64_t InklingSequence::expertBudgetBytes() const noexcept { return impl_->expertBudget; }
uint64_t InklingSequence::maximumExpertBudgetBytes() const noexcept { return impl_->maximumExpertBudget; }
std::span<const InklingExpertCacheStats> InklingSequence::expertCacheStats() const noexcept { return impl_->expertStats; }
std::span<const InklingExecutionStats> InklingSequence::executionStats() const noexcept { return impl_->execution; }
metal::MetalMemoryStats InklingSequence::memoryStats() const noexcept { return impl_->backend.memoryStats(); }

std::span<const float> InklingSequence::evaluate(std::span<const uint32_t> tokens, bool logits,
                                                 const std::function<bool()> &interrupted) {
  return impl_->evaluate(tokens, logits, interrupted);
}

} // namespace splash::model
