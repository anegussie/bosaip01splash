#include "TestBuffers.hpp"
#include "metal/abi/Inkling.h"
#include "metal/abi/QuantTables.h"
#include "ops/Inkling.hpp"
#include "ops/Linear.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <iostream>
#include <utility>
#include <vector>

namespace {
using namespace splash;
using metal::MetalBuffer;
using test::require;

template <class T> metal::MetalBuffer upload(metal::MetalBackend &backend, const std::vector<T> &data) {
  const auto buffer = test::sharedBuffer(backend, data.size() * sizeof(T));
  std::memcpy(buffer.contents(), data.data(), data.size() * sizeof(T));
  return buffer;
}

float value(size_t index, size_t period, float scale) {
  return float(int(index % period) - int(period / 2)) * scale;
}

float bf16(float value) {
  const uint32_t bits = std::bit_cast<uint32_t>(value);
  return std::bit_cast<float>((bits + 0x7fff + ((bits >> 16) & 1)) & 0xffff0000);
}

// Distance in BF16 units of the last place. Signed BF16 bit patterns are
// ordered by magnitude, so neighbours across zero are one step apart.
int bf16Distance(uint16_t a, uint16_t b) {
  const auto ordered = [](uint16_t x) { return x & 0x8000 ? -int((x & 0x7fff) + 1) : int(x & 0x7fff); };
  return std::abs(ordered(a) - ordered(b));
}

void checkAttention(metal::MetalBackend &backend, bool sliding) {
  constexpr uint32_t window = SPLASH_INKLING_WINDOW;
  constexpr uint32_t heads = SPLASH_INKLING_QUERY_HEADS, kvHeads = SPLASH_INKLING_KV_HEADS;
  constexpr uint32_t width = SPLASH_INKLING_HEAD_WIDTH, rel = SPLASH_INKLING_RELATIVE_WIDTH;
  constexpr uint32_t rows = 5, firstQuery = window + 3, end = firstQuery + rows;
  const uint32_t firstKey = sliding ? firstQuery - window + 1 : 0;
  const uint32_t slots = sliding ? window + rows - 1 : end;
  std::vector<float> q(rows * heads * width), r(rows * heads * rel), sinks(rows * heads), table(window * rel);
  std::vector<float> gate(q.size());
  std::vector<float> k((end - firstKey) * kvHeads * width), v(k.size());
  std::vector<uint16_t> kb(slots * kvHeads * width), vb(kb.size());
  for (size_t i = 0; i < q.size(); ++i) q[i] = value(i * 7, 37, 0.04f);
  for (size_t i = 0; i < gate.size(); ++i) gate[i] = value(i * 17, 43, 0.15f);
  for (size_t i = 0; i < r.size(); ++i) r[i] = value(i * 13, 17, 0.08f);
  for (size_t i = 0; i < table.size(); ++i) table[i] = value(i * 43, 71, 0.12f);
  for (size_t i = 0; i < sinks.size(); ++i) sinks[i] = value(i * 7, 9, 2.0f);
  sinks[0] = 30.0f;
  for (size_t i = 0; i < k.size(); ++i) {
    k[i] = value(i * 3, 31, 0.03125f);
    v[i] = value(i * 17, 127, 0.0625f);
    if (i < kvHeads * width) v[i] *= 16;
    const size_t row = i / (kvHeads * width), column = i % (kvHeads * width);
    const size_t slot = (row + firstKey) % slots * kvHeads * width + column;
    kb[slot] = uint16_t(std::bit_cast<uint32_t>(k[i]) >> 16);
    vb[slot] = uint16_t(std::bit_cast<uint32_t>(v[i]) >> 16);
  }
  const auto query = upload(backend, q), relative = upload(backend, r), relativeTable = upload(backend, table);
  const auto sinkValues = upload(backend, sinks), gateValues = upload(backend, gate);
  const auto keyHistory = upload(backend, kb), valueHistory = upload(backend, vb);
  const auto output = test::sharedBuffer(backend, q.size() * sizeof(uint16_t));
  const auto singleOutput = test::sharedBuffer(backend, q.size() * sizeof(uint16_t));
  std::memset(singleOutput.contents(), 0, singleOutput.sizeBytes());
  metal::CommandGraph graph;
  ops::addInklingAttention(graph, {query, relative, relativeTable, sinkValues, gateValues, keyHistory,
                                   valueHistory, output, {}}, firstQuery, rows, sliding, slots);
  // One query per dispatch uses the untiled kernel; its result must be identical.
  metal::CommandGraph single;
  for (uint32_t row = 0; row < rows; ++row) {
    const uint64_t queryOffset = uint64_t{row} * heads * width * sizeof(float);
    ops::addInklingAttention(single, {backend.view(query, queryOffset, heads * width * sizeof(float)),
                                      backend.view(relative, uint64_t{row} * heads * rel * sizeof(float),
                                                  heads * rel * sizeof(float)),
                                      relativeTable, backend.view(sinkValues, uint64_t{row} * heads * sizeof(float),
                                                  heads * sizeof(float)),
                                      backend.view(gateValues, queryOffset, heads * width * sizeof(float)),
                                      keyHistory, valueHistory,
                                      backend.view(singleOutput, queryOffset / 2, heads * width * sizeof(uint16_t)),
                                      {}}, firstQuery + row, 1, sliding, slots);
  }
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
  static_cast<void>(backend.submitCommandAsync(single.command()).wait());
  const auto *actual = static_cast<const uint16_t *>(output.contents());
  const auto *untiled = static_cast<const uint16_t *>(singleOutput.contents());
  for (size_t i = 0; i < q.size(); ++i)
    require(actual[i] == untiled[i], "Inkling tiled attention differs from the one-query kernel");
  for (uint32_t row = 0; row < rows; ++row) {
    const uint32_t position = firstQuery + row;
    for (uint32_t head = 0; head < heads; ++head) {
      const uint32_t qHead = row * heads + head;
      double denominator = std::exp(double(sinks[qHead]));
      double expected[width]{};
      const uint32_t begin = sliding ? position - window + 1 : 0;
      for (uint32_t key = begin; key <= position; ++key) {
        const uint32_t kv = ((key - firstKey) * kvHeads + head / (heads / kvHeads)) * width;
        double score = 0;
        for (uint32_t i = 0; i < width; ++i) score += double(q[qHead * width + i]) * k[kv + i];
        score /= std::sqrt(double(width));
        const uint32_t distance = position - key;
        if (distance < window)
          for (uint32_t i = 0; i < rel; ++i) score += double(r[qHead * rel + i]) * table[distance * rel + i];
        const double mass = std::exp(score);
        denominator += mass;
        for (uint32_t i = 0; i < width; ++i) expected[i] += mass * v[kv + i];
      }
      for (uint32_t i = 0; i < width; ++i) {
        const uint32_t column = qHead * width + i;
        const float expectedGated = bf16(float(expected[i] / denominator / (1 + std::exp(-gate[column]))));
        const uint16_t expectedBits = uint16_t(std::bit_cast<uint32_t>(expectedGated) >> 16);
        const int ulps = bf16Distance(actual[column], expectedBits);
        const float result = std::bit_cast<float>(uint32_t{actual[column]} << 16);
        if (ulps > 2 && std::abs(result - expectedGated) >= 3e-4f) {
          std::cerr << "attention sliding=" << sliding << " row=" << row << " head=" << head <<
              " column=" << i << " got=" << std::bit_cast<float>(uint32_t{actual[column]} << 16) <<
              " expected=" << expectedGated << " ulps=" << ulps << '\n';
        }
        require(ulps <= 2 || std::abs(result - expectedGated) < 3e-4f, "Inkling attention differs from the CPU reference");
      }
    }
  }
}

void checkLongAttention(metal::MetalBackend &backend) {
  constexpr uint32_t full = 131072, heads = SPLASH_INKLING_QUERY_HEADS, kvHeads = SPLASH_INKLING_KV_HEADS;
  constexpr uint32_t width = SPLASH_INKLING_HEAD_WIDTH, rel = SPLASH_INKLING_RELATIVE_WIDTH;
  constexpr uint32_t rows = 5, firstQuery = full - rows;
  const auto zeros = [&](uint64_t bytes) {
    const auto buffer = test::sharedBuffer(backend, bytes);
    std::memset(buffer.contents(), 0, bytes);
    return buffer;
  };
  const auto keys = zeros(uint64_t{full} * kvHeads * width * sizeof(uint16_t));
  const auto values = zeros(keys.sizeBytes());
  auto *v = static_cast<uint16_t *>(values.contents());
  // Every position has equal softmax mass. A few sparse values test that
  // both the oldest and newest tiles contribute exactly once.
  for (uint32_t kv = 0; kv < kvHeads; ++kv) {
    v[kv * width] = 0x4380; // BF16 256
    v[(uint64_t{firstQuery} * kvHeads + kv) * width] = 0x4300; // 128
    v[(uint64_t{firstQuery + 1} * kvHeads + kv) * width] = 0x4400; // 512
  }
  const uint64_t queryBytes = uint64_t{rows} * heads * width * sizeof(float);
  const auto output = zeros(queryBytes / 2), q = zeros(queryBytes);
  const ops::InklingAttentionBuffers buffers{
      q, zeros(uint64_t{rows} * heads * rel * sizeof(float)), zeros(1024 * rel * sizeof(float)),
      zeros(rows * heads * sizeof(float)), q, keys, values, output,
      test::sharedBuffer(backend, ops::inklingAttentionScratchBytes(rows, full)),
  };
  metal::CommandGraph graph;
  ops::addInklingAttention(graph, buffers, firstQuery, rows, false, full);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
  const auto *got = static_cast<const uint16_t *>(output.contents());
  for (uint32_t row = 0; row < rows; ++row) {
    const float expected = bf16(float(row ? 896 : 384) / (2.0f * (firstQuery + row + 2)));
    for (uint32_t head = 0; head < heads; ++head) {
      const uint32_t base = (row * heads + head) * width;
      require(std::bit_cast<float>(uint32_t{got[base]} << 16) == expected, "128K attention lost a key tile or the sink");
      for (uint32_t column = 1; column < width; ++column)
        require(got[base + column] == 0, "128K attention spilled an output into another channel");
    }
  }
}

void checkConvolution(metal::MetalBackend &backend, bool dynamic) {
  constexpr uint32_t rows = 5, channels = 12, heads = 3;
  std::vector<float> inputs(rows * channels), taps(channels * 4), initial(channels * 3), weights(rows * heads * 4);
  for (size_t i = 0; i < inputs.size(); ++i) inputs[i] = value(i * 3, 39, 0.07f);
  for (size_t i = 0; i < taps.size(); ++i) taps[i] = value(i * 7, 31, 0.06f);
  for (size_t i = 0; i < initial.size(); ++i) initial[i] = value(i * 17, 13, 0.25f);
  for (size_t i = 0; i < weights.size(); ++i) weights[i] = value(i * 11, 17, 0.2f);
  std::vector<float> expectedHistory = initial;
  std::vector<double> expected(inputs.size());
  for (uint32_t row = 0; row < rows; ++row)
    for (uint32_t channel = 0; channel < channels; ++channel) {
      float *past = expectedHistory.data() + channel * 3;
      const float input = inputs[row * channels + channel];
      const float window[]{past[0], past[1], past[2], input};
      double sum = input;
      for (uint32_t tap = 0; tap < 4; ++tap) {
        sum += double(taps[channel * 4 + tap]) * window[tap];
        if (dynamic)
          sum += double(weights[(row * heads + channel / (channels / heads)) * 4 + tap]) * window[3 - tap];
      }
      expected[row * channels + channel] = sum / std::sqrt(dynamic ? 9.0 : 5.0);
      std::copy_n(window + 1, 3, past);
    }

  const auto projection = upload(backend, inputs), history = upload(backend, initial);
  const auto staticWeights = upload(backend, taps), dynamicWeights = upload(backend, weights);
  // Separate commands exercise the history state at a prefill chunk boundary.
  for (uint32_t first : {0u, 1u}) {
    metal::CommandGraph graph;
    const uint32_t count = first == 0 ? 1 : rows - 1;
    ops::addInklingConvolution(graph, backend.view(projection, first * channels * 4, count * channels * 4),
                               staticWeights, history, count, channels,
                               backend.view(dynamicWeights, first * heads * 16, count * heads * 16), dynamic ? heads : 0);
    static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
  }
  const auto *computed = static_cast<const float *>(projection.contents());
  for (size_t i = 0; i < expected.size(); ++i)
    require(std::abs(computed[i] - expected[i]) < 2e-6, "Inkling convolution differs from the CPU reference");
  require(std::memcmp(history.contents(), expectedHistory.data(), expectedHistory.size() * sizeof(float)) == 0,
          "Inkling convolution raw history differs from the CPU reference");
}

void checkLoop(metal::MetalBackend &backend) {
  constexpr uint32_t rows = 2, hidden = SPLASH_INKLING_HIDDEN, rank = SPLASH_INKLING_GATE_RANK;
  constexpr uint32_t states = SPLASH_INKLING_MIX_STATES, queries = 3;
  std::vector<float> residuals[states], q(queries * hidden);
  std::vector<metal::MetalBuffer> stateBuffers;
  for (uint32_t state = 0; state < states; ++state) {
    auto &residual = residuals[state];
    residual.resize(rows * hidden);
    for (size_t i = 0; i < residual.size(); ++i)
      residual[i] = value(i * (3 + state), 37 + state * 2, 0.04f * state);
    stateBuffers.push_back(upload(backend, residual));
  }
  for (size_t i = 0; i < q.size(); ++i) q[i] = value(i * 11, 53, 0.08f);
  const auto mixedOutput = test::sharedBuffer(backend, rows * queries * hidden * sizeof(float));
  const auto current = stateBuffers.back();
  const auto message = backend.view(mixedOutput, rows * hidden * sizeof(float), rows * hidden * sizeof(float));

  std::vector<float> downWeight(rank * 2 * hidden), gainWeight(hidden * rank), forgetWeight(hidden * rank);
  for (size_t i = 0; i < downWeight.size(); ++i) downWeight[i] = value(i * 3, 47, 0.0006f);
  for (size_t i = 0; i < gainWeight.size(); ++i) {
    gainWeight[i] = value(i * 13, 29, 0.003f);
    forgetWeight[i] = value(i * 47, 57, 0.002f);
  }
  const ops::InklingControlWeights weights{
      ops::QuantizedSegment::floats(rank, 2 * hidden, upload(backend, downWeight)),
      ops::QuantizedSegment::floats(hidden, rank, upload(backend, gainWeight)),
      ops::QuantizedSegment::floats(hidden, rank, upload(backend, forgetWeight)),
  };
  const auto matrix = [&](uint32_t width, uint32_t bytes) { return test::sharedBuffer(backend, rows * width * bytes); };
  const ops::InklingControlBuffers control{
      current, message, matrix(hidden, 4), matrix(2 * hidden, 2), matrix(rank, 2), matrix(hidden, 4), matrix(hidden, 4),
  };
  metal::CommandGraph graph;
  ops::addInklingResidualMix(graph, stateBuffers, upload(backend, q), mixedOutput, rows, queries);
  ops::addInklingControl(graph, weights, control, rows);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());

  const auto inverseRms = [](const auto *values) {
    double sum = 0.0;
    for (uint32_t i = 0; i < hidden; ++i) sum += double(values[i]) * values[i];
    return 1 / std::sqrt(sum / hidden + 1e-6);
  };
  const auto *computed = static_cast<const float *>(mixedOutput.contents());
  const auto *controlled = static_cast<const float *>(control.output.contents());
  for (uint32_t row = 0; row < rows; ++row) {
    std::vector<double> mixture[queries];
    for (uint32_t query = 0; query < queries; ++query) {
      auto &result = mixture[query];
      result.resize(hidden);
      double mass = 0.0;
      for (const auto &state : residuals) {
        const float *source = state.data() + row * hidden;
        const double scale = inverseRms(source);
        double dot = 0.0;
        for (uint32_t col = 0; col < hidden; ++col) dot += double(source[col]) * q[query * hidden + col];
        const double probability = std::exp(dot * scale / std::sqrt(double(hidden)));
        mass += probability;
        for (uint32_t col = 0; col < hidden; ++col) result[col] += source[col] * scale * probability;
      }
      for (uint32_t col = 0; col < hidden; ++col) {
        result[col] /= mass;
        require(std::abs(computed[(query * rows + row) * hidden + col] - result[col]) < 2e-5,
                "Inkling residual mix differs from the CPU reference");
      }
    }

    const float *base = residuals[states - 1].data() + row * hidden;
    const auto &messageValues = mixture[1];
    const double currentScale = inverseRms(base), messageScale = inverseRms(messageValues.data());
    float latent[rank]{};
    for (uint32_t i = 0; i < rank; ++i) {
      double dot = 0.0;
      const float *kernel = downWeight.data() + i * 2 * hidden;
      for (uint32_t col = 0; col < hidden; ++col) {
        dot += double(kernel[col]) * bf16(float(base[col] * currentScale));
        dot += double(kernel[col + hidden]) * bf16(float(messageValues[col] * messageScale));
      }
      latent[i] = bf16(float(dot));
    }
    for (uint32_t col = 0; col < hidden; ++col) {
      double gain = 0.0, forget = 0.0;
      for (uint32_t i = 0; i < rank; ++i) {
        gain += double(latent[i]) * gainWeight[col * rank + i];
        forget += double(latent[i]) * forgetWeight[col * rank + i];
      }
      const double expected = (1 - std::tanh(forget)) * base[col] + std::tanh(gain) * messageValues[col];
      require(std::abs(controlled[row * hidden + col] - expected) < 3e-4,
              "Inkling cross-pass controller differs from the CPU reference");
    }
  }
}

void checkExperts(metal::MetalBackend &backend) {
  constexpr uint32_t experts = SPLASH_INKLING_EXPERTS, topK = SPLASH_INKLING_TOP_K;
  constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, width = SPLASH_INKLING_EXPERT_WIDTH;
  const auto sigmoid = [](double x) { return 1 / (1 + std::exp(-x)); };
  std::vector<float> scores(2 * experts), bias(experts);
  for (size_t i = 0; i < experts; ++i) {
    scores[experts + i] = value(i * 17, 17, 0.1f) + value(i, 15, 0.5f);
    bias[i] = i % 3 == 0 ? 1.0f : 0.0f;
  }
  const auto ids = test::sharedBuffer(backend, 2 * topK * sizeof(uint32_t));
  const auto routes = test::sharedBuffer(backend, 2 * topK * sizeof(float));
  metal::CommandGraph graph;
  ops::addInklingRouting(graph, upload(backend, scores), upload(backend, bias), ids, routes, 2);

  std::vector<uint16_t> input(hidden);
  input[0] = 0x3f80; // BF16 1.0
  std::vector<float> gateUp(2 * width * hidden);
  for (size_t i = 0; i < 2 * width; ++i) gateUp[i * hidden] = value(i * 17, 27, 0.71f);
  constexpr uint32_t blocks = width / 64, stride = blocks * 36;
  std::vector<uint8_t> packed(hidden * stride);
  // Each output uses one of the four groups of the final 64-value block.
  // A high-bit scale still decodes as 1.0, while 0x7f contributes zero.
  for (uint32_t i = 0; i < hidden; ++i) {
    uint8_t *block = packed.data() + i * stride + (blocks - 1) * 36;
    const uint32_t group = i % 4;
    block[group] = i % 5 ? 0xb8 : 0x7f;
    block[4 + group * 8 + i % 8] = 0xa2; // E2M1 +1 and -1 in the two halves.
  }
  const ops::InklingExpertBuffers buffers{
      upload(backend, input), test::sharedBuffer(backend, 2 * width * sizeof(float)),
      test::sharedBuffer(backend, width * sizeof(uint16_t)), test::sharedBuffer(backend, hidden * sizeof(float)),
  };
  constexpr float gateScale = 0.42f, downScale = 0.371f;
  ops::addInklingExpert(graph, {ops::QuantizedSegment::floats(2 * width, hidden, upload(backend, gateUp)),
                                upload(backend, packed), true, gateScale, downScale}, buffers, 1);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());

  const auto *actualIds = static_cast<const uint32_t *>(ids.contents());
  const auto *actualRoutes = static_cast<const float *>(routes.contents());
  for (uint32_t row = 0; row < 2; ++row) {
    std::vector<uint32_t> expected(experts);
    for (uint32_t i = 0; i < experts; ++i) expected[i] = i;
    const auto probability = [&](uint32_t expert) { return sigmoid(scores[row * experts + expert]); };
    std::stable_sort(expected.begin(), expected.end(), [&](uint32_t a, uint32_t b) {
      return probability(a) + bias[a] > probability(b) + bias[b];
    });
    double sum = 0.0;
    for (uint32_t i = 0; i < topK; ++i) sum += probability(expected[i]);
    for (uint32_t i = 0; i < topK; ++i) {
      require(actualIds[row * topK + i] == expected[i], "Inkling expert IDs differ from the CPU reference");
      require(std::abs(actualRoutes[row * topK + i] - 8 * probability(expected[i]) / sum) < 3e-6,
              "Inkling routing weights differ from the CPU reference");
    }
  }
  const auto activation = [&](uint32_t i) {
    const float gate = gateScale * gateUp[i * hidden], up = gateScale * gateUp[(width + i) * hidden];
    return bf16(float(100 * std::tanh(gate / 4.0) * sigmoid(gate) * std::tanh(up / 25.0)));
  };
  const auto *result = static_cast<const float *>(buffers.output.contents());
  for (uint32_t i = 0; i < hidden; ++i) {
    const uint32_t j = width - 64 + (i % 4) * 16 + i % 8;
    const double expected = i % 5 ? downScale * (activation(j) - activation(j + 8)) : 0;
    require(std::abs(result[i] - expected) < 2e-4, "Inkling expert output differs from the CPU reference");
  }
}

// Zero codes in IQ4_NL are the first codebook value, -127.
void checkQuantizedRow(metal::MetalBackend &backend, uint32_t kSize) {
  constexpr uint32_t columns = 8, format = GGUF_FMT_IQ4NL;
  const uint64_t bytes = ops::QuantizedSegment::rowBytes(format, kSize);
  std::vector<uint8_t> weight(size_t{columns} * bytes, 0);
  for (size_t i = 0; i < weight.size(); i += 18) weight[i + 1] = 0x3f; // FP16 1.75
  std::vector<uint16_t> activation(kSize, 0x3f80); // BF16 1
  const auto input = upload(backend, activation), weights = upload(backend, weight);
  const auto output = test::sharedBuffer(backend, columns * sizeof(float));
  metal::CommandGraph graph;
  ops::addGgufFloat(graph, input, ops::QuantizedSegment::rows(format, columns, kSize, weights), output, 1, columns, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Vector);
  static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
  const auto *found = static_cast<const float *>(output.contents());
  for (uint32_t column = 0; column < columns; ++column)
    require(found[column] == -127.0f * 1.75f * float(kSize), "IQ4_NL vector dot differs from the CPU result");
}

void checkRowVisibility(metal::MetalBackend &backend) {
  constexpr uint32_t rows = 41, hidden = SPLASH_INKLING_HIDDEN, columns = 8;
  std::vector<uint16_t> activations(size_t{rows} * hidden);
  for (size_t i = 0; i < activations.size(); ++i)
    activations[i] = uint16_t(std::bit_cast<uint32_t>(bf16(value(i * 7, 23, 0.02f))) >> 16);
  std::vector<float> weight(size_t{columns} * hidden, 0.0f);
  weight[0] = 1.0f;
  const auto input = upload(backend, activations);
  const auto weightBuffer = backend.allocateBuffer(size_t{columns} * hidden * sizeof(float), metal::BufferStorage::Shared,
                                                  "visibility weights", metal::BufferReach::Addressed);
  std::memcpy(weightBuffer.contents(), weight.data(), weight.size() * sizeof(float));
  const auto weights = weightBuffer;
  const auto output = test::sharedBuffer(backend, size_t{rows} * columns * sizeof(float));
  metal::CommandGraph graph;
  ops::addGgufFloat(graph, input, ops::QuantizedSegment::floats(columns, hidden, weights), output, rows, columns, 0,
                    ops::FloatOutput::Float32, ops::FloatTile::Simdgroup);
  static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
  const auto *found = static_cast<const float *>(output.contents());
  for (uint32_t row = 0; row < rows; ++row)
    require(std::abs(found[row * columns] - std::bit_cast<float>(uint32_t(activations[size_t{row} * hidden]) << 16)) < 1e-6,
            "a float projection does not see the rows written on the CPU");
}

void checkExpertBatch(metal::MetalBackend &backend, uint32_t gateFormat, bool nvfp4, bool singleToken) {
  constexpr uint32_t hidden = SPLASH_INKLING_HIDDEN, width = SPLASH_INKLING_EXPERT_WIDTH;
  constexpr uint32_t experts = 3, firstRow = 2;
  const uint32_t counts[]{singleToken ? 1u : 33u, singleToken ? 1u : 5u, 1u};
  const uint32_t rows = firstRow + counts[0] + counts[1] + counts[2];
  std::vector<uint16_t> inputValues;
  for (uint32_t i = 0; i < rows * hidden; ++i)
    inputValues.push_back(uint16_t(std::bit_cast<uint32_t>(bf16(value(i * 7, 23, 0.02f))) >> 16));
  const auto input = upload(backend, inputValues);
  const auto allocateScratch = [&] {
    return ops::InklingExpertBuffers{
        input, test::sharedBuffer(backend, uint64_t{rows} * 2 * width * sizeof(float)),
        test::sharedBuffer(backend, uint64_t{rows} * width * sizeof(uint16_t)),
        test::sharedBuffer(backend, uint64_t{rows} * hidden * sizeof(float))};
  };
  const auto actual = allocateScratch(), expected = allocateScratch();
  std::array<MetalBuffer, 2 * experts> weights;
  std::vector<InklingExpertEntry> entries(experts);
  std::vector<InklingExpertTile> tiles;
  metal::CommandGraph individual;
  uint32_t start = firstRow;
  for (uint32_t expert = 0; expert < experts; ++expert) {
    const auto allocate = [&](size_t bytes) {
      return backend.allocateBuffer(bytes, metal::BufferStorage::Shared, "Inkling test expert",
                                   metal::BufferReach::Addressed);
    };
    const auto packed = [&](uint32_t format, uint32_t outputs, uint32_t inputs) {
      auto buffer = allocate(size_t{outputs} * ops::QuantizedSegment::rowBytes(format, inputs));
      auto *bytes = static_cast<uint8_t *>(buffer.contents());
      for (size_t i = 0; i < buffer.sizeBytes(); ++i) bytes[i] = uint8_t((13 * i + 11 * expert + 7 * (i / 19)) % 64);
      const uint32_t blockWidth = format == GGUF_FMT_IQ4NL ? 32 : 256;
      const uint64_t blockBytes = ops::QuantizedSegment::rowBytes(format, blockWidth);
      for (size_t i = 0; i < buffer.sizeBytes(); i += blockBytes) {
        bytes[i] = 0;
        bytes[i + 1] = 0x1c; // FP16 1/256
      }
      return buffer;
    };
    auto gate = packed(gateFormat, 2 * width, hidden);
    auto down = nvfp4 ? allocate(size_t{hidden} * width / 64 * 36) : packed(GGUF_FMT_IQ4NL, hidden, width);
    if (nvfp4) {
      auto *bytes = static_cast<uint8_t *>(down.contents());
      for (size_t i = 0; i < down.sizeBytes(); ++i) bytes[i] = i % 36 < 4 ? 0x28 : uint8_t((i * 31 + 13 * expert) % 64);
    }
    weights[2 * expert] = gate;
    weights[2 * expert + 1] = down;
    const float gateScale = nvfp4 ? 0.8f : 1.0f, downScale = nvfp4 ? 0.2f : 1.0f;
    entries[expert] = {start, counts[expert], gateScale, downScale};
    for (uint32_t row = 0; row < counts[expert]; row += SPLASH_INKLING_EXPERT_TILE_ROWS)
      tiles.push_back({expert, row / SPLASH_INKLING_EXPERT_TILE_ROWS});
    const auto rowsOf = [&](const MetalBuffer &buffer, uint32_t count, uint32_t bytes) {
      const uint64_t stride = uint64_t{count} * bytes;
      return backend.view(buffer, start * stride, counts[expert] * stride);
    };
    ops::addInklingExpert(individual, {ops::QuantizedSegment::rows(gateFormat, 2 * width, hidden, gate),
                                        down, nvfp4, gateScale, downScale},
                          {rowsOf(expected.input, hidden, sizeof(uint16_t)),
                           rowsOf(expected.gateUp, 2 * width, sizeof(float)),
                           rowsOf(expected.activated, width, sizeof(uint16_t)),
                           rowsOf(expected.output, hidden, sizeof(float))}, counts[expert]);
    start += counts[expert];
  }
  metal::CommandGraph grouped;
  const auto table = upload(backend, entries);
  ops::addInklingExpertBatch(grouped, actual, table, upload(backend, tiles),
                             std::make_shared<std::vector<MetalBuffer>>(weights.begin(), weights.end()),
                             experts, uint32_t(tiles.size()),
                             ops::QuantizedSegment::rows(gateFormat, 2 * width, hidden, MetalBuffer{}).name(),
                             nvfp4, singleToken);
  static_cast<void>(backend.submitCommandAsync(individual.command()).wait());
  static_cast<void>(backend.submitCommandAsync(grouped.command()).wait());
  for (const auto &[batched, plain] : {std::pair{actual.gateUp, expected.gateUp},
                                      std::pair{actual.output, expected.output}}) {
    const auto *found = static_cast<const float *>(batched.contents());
    const auto *wanted = static_cast<const float *>(plain.contents());
    for (uint32_t i = firstRow * hidden; i < rows * hidden; ++i) {
      if (!(std::abs(found[i] - wanted[i]) < 1e-5f))
        std::cerr << "grouped gate=" << gateFormat << " nvfp4=" << nvfp4 << " single=" << singleToken
                  << " row=" << i / hidden << " column=" << i % hidden << " got=" << found[i]
                  << " expected=" << wanted[i] << '\n';
      require(std::abs(found[i] - wanted[i]) < 1e-5f, "Grouped expert projection differs from individual dispatches");
    }
  }
}

void checkExpertResidual(metal::MetalBackend &backend) {
  constexpr uint32_t rows = 2, width = 13, topK = SPLASH_INKLING_TOP_K, routes = rows * topK;
  std::vector<uint32_t> order(routes), inverse(routes);
  std::vector<float> weights(routes, 1.0f / topK);
  std::vector<float> expert(routes * width), taps(width * 4), residual(rows * width);
  for (uint32_t route = 0; route < routes; ++route) {
    order[route] = (route * 5 + 3) % routes;
    inverse[order[route]] = route;
    for (uint32_t column = 0; column < width; ++column)
      expert[route * width + column] = float(1 + order[route] + column);
  }
  for (uint32_t i = 0; i < width; ++i) {
    taps[i * 4 + 2] = 0.5f;
    taps[i * 4 + 3] = -0.25f;
    residual[i] = 10.0f - float(i);
    residual[width + i] = 4.0f + float(i);
  }
  const auto sum = upload(backend, std::vector<float>(rows * width, 99.0f));
  const auto history = upload(backend, std::vector<float>(width * 3, 0.0f));
  const auto output = test::sharedBuffer(backend, rows * width * sizeof(float));
  metal::CommandGraph graph;
  ops::addInklingRouteAccumulate(graph, upload(backend, expert), upload(backend, inverse), upload(backend, weights),
                                 sum, routes, width);
  ops::addInklingConvolution(graph, sum, upload(backend, taps), history, rows, width);
  ops::addInklingAdd(graph, upload(backend, residual), sum, output, rows * width);
  static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());

  const auto *computed = static_cast<const float *>(output.contents());
  const auto *rawHistory = static_cast<const float *>(history.contents());
  for (uint32_t column = 0; column < width; ++column) {
    const float first = 4.5f + column, second = first + topK;
    const float scale = 1.0f / std::sqrt(5.0f);
    require(std::abs(computed[column] - (residual[column] + 0.75f * first * scale)) < 1e-5f,
            "Inkling convolved the first FFN residual instead of its expert sum");
    require(std::abs(computed[width + column] -
                     (residual[width + column] + (0.75f * second + 0.5f * first) * scale)) < 1e-5f,
            "Inkling failed to apply the FFN convolution before the residual add");
    require(rawHistory[column * 3 + 1] == first && rawHistory[column * 3 + 2] == second,
            "Inkling FFN history must record the raw expert sums");
  }
}
} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      require(argc == 2, "usage: inkling-ops METALLIB");
      splash::metal::MetalBackend backend(argv[1]);
      checkQuantizedRow(backend, 32);
      checkQuantizedRow(backend, SPLASH_INKLING_HIDDEN);
      checkRowVisibility(backend);
      for (const uint32_t gate : {GGUF_FMT_IQ2XXS, GGUF_FMT_IQ2XS, GGUF_FMT_IQ2S, GGUF_FMT_IQ3XXS}) {
        checkExpertBatch(backend, gate, true, false);
        checkExpertBatch(backend, gate, false, true);
      }
      checkAttention(backend, false);
      checkAttention(backend, true);
      checkLongAttention(backend);
      checkConvolution(backend, false);
      checkConvolution(backend, true);
      checkLoop(backend);
      checkExperts(backend);
      checkExpertResidual(backend);
      std::cout << "Inkling Metal attention, convolution, loop and expert operations match the CPU reference\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
