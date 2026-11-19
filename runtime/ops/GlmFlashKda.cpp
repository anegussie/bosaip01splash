#include "ops/GlmFlashKda.hpp"

#include "ops/BufferExtent.hpp"

namespace splash::ops {

void GlmFlashKda::add(metal::CommandGraph &graph, const GlmFlashKdaWeights &weights,
                     const GlmFlashKdaState &state, const GlmFlashKdaBuffers &buffers, uint32_t rows) {
  constexpr uint32_t channels = GLM_FLASH_KDA_CHANNELS;
  constexpr uint32_t heads = GLM_FLASH_KDA_HEADS;
  constexpr uint32_t headDim = GLM_FLASH_KDA_HEAD_DIM;
  constexpr uint32_t convolutionThreads = 256;
  constexpr uint32_t scanThreads = 128;
  constexpr uint32_t valuesPerScanGroup = scanThreads / 32;
  if (!rows) throw std::invalid_argument("GLM Flash KDA requires rows");
  const auto rowBytes = uint64_t{rows} * channels * sizeof(float);
  for (size_t i = 0; i < buffers.qkv.size(); ++i) {
    requireBytes(weights.convolution[i], channels * GLM_FLASH_KDA_CONV_TAPS * sizeof(float),
                 "GLM Flash KDA convolution weights");
    requireBytes(state.convolution[i], channels * GLM_FLASH_KDA_HISTORY * sizeof(float),
                 "GLM Flash KDA convolution history");
    requireBytes(buffers.qkv[i], rowBytes, "GLM Flash KDA QKV");
  }
  requireBytes(state.recurrent, channels * headDim * sizeof(float), "GLM Flash KDA recurrent state");
  requireBytes(weights.decayScale, heads * sizeof(float), "GLM Flash KDA decay scale");
  requireBytes(weights.decayBias, channels * sizeof(float), "GLM Flash KDA decay bias");
  requireBytes(weights.outputNorm, headDim * sizeof(float), "GLM Flash KDA output norm");
  requireBytes(buffers.decay, rowBytes, "GLM Flash KDA decay");
  requireBytes(buffers.beta, uint64_t{rows} * heads * sizeof(float), "GLM Flash KDA beta");
  requireBytes(buffers.outputGate, rowBytes, "GLM Flash KDA output gate");
  requireBytes(buffers.output, rowBytes, "GLM Flash KDA output");

  for (size_t i = 0; i < buffers.qkv.size(); ++i)
    graph.add("glm_flash_kda_convolve",
              {buffers.qkv[i], weights.convolution[i], state.convolution[i]},
              rows, {channels / convolutionThreads, 1, 1}, {convolutionThreads, 1, 1});
  graph.add("glm_flash_kda_prepare", {buffers.qkv[0], buffers.qkv[1], buffers.decay,
                                      buffers.beta, weights.decayScale, weights.decayBias},
            {heads, rows, 1}, {headDim, 1, 1});
  graph.add("glm_flash_kda_scan", {buffers.qkv[0], buffers.qkv[1], buffers.qkv[2], buffers.decay,
                                   buffers.beta, state.recurrent, buffers.output},
            rows, {heads, headDim / valuesPerScanGroup, 1}, {scanThreads, 1, 1});
  graph.add("glm_flash_kda_output", {buffers.output, weights.outputNorm, buffers.outputGate},
            {heads, rows, 1}, {headDim, 1, 1});
}

} // namespace splash::ops
