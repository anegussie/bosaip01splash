// The staged GGUF tile's dequantization (dequant32, kernels/shared/gguf_linear.metal, which the test kernels of
// gguf_dequant_test.metal expose before the matmul): every weight of every format is the half rounding of its
// GGML fp32 value, the CPU reference that gguf-reference pins to llama.cpp's golden hashes.
#include "GgufFormatReference.hpp"
#include "TestBuffers.hpp"
#include "metal/CommandGraph.hpp"
#include "metal/MetalBackend.hpp"
#include "metal/abi/Gguf.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <vector>

using namespace gguf_reference;
using splash::metal::CommandGraph;
using splash::metal::MetalBackend;
using splash::metal::MetalBuffer;
using splash::test::sharedBuffer;

namespace {

MetalBuffer upload(MetalBackend &backend, const std::vector<uint8_t> &bytes) {
  MetalBuffer buffer = sharedBuffer(backend, bytes.size());
  std::memcpy(buffer.contents(), bytes.data(), bytes.size());
  return buffer;
}

} // namespace

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 2) {
      std::cerr << "usage: gguf-dequant <gguf-dequant.metallib>\n";
      return 2;
    }
    // One thread per row and group of 32 weights, 32 threads per threadgroup (gguf_dequant_test.metal).
    constexpr uint32_t N = 256, K = 1024, kGroup = 32, kThreads = 32;
    std::mt19937 rng(42);
    int failures = 0;
    try {
      MetalBackend backend(argv[1]);
      for (int fi = 0; fi < FMT_COUNT; ++fi) {
        const Fmt f = Fmt(fi);
        // Ternary decode may select among scaled values. Exercise signed
        // zero, subnormal and extreme finite scales as well as model-like ones.
        for (int trial = 0; trial < (f == PTQ10 ? 2 : 1); ++trial) {
          constexpr std::array<uint16_t, 12> scales = {
              0x0000, 0x8000, 0x0001, 0x8001, 0x03FF, 0x83FF,
              0x0400, 0x8400, 0x3C00, 0xBC00, 0x7BFF, 0xFBFF};
          size_t nextScale = 0;
          const auto native = trial == 0 ? makeNative(f, N, K, rng)
                                        : makeNative(f, N, K, rng, [&] { return scales[nextScale++ % scales.size()]; });
          std::vector<float> values;
          const Packed planes = repack(f, native, N, K, &values);
          const MetalBuffer w0 = upload(backend, planes.w0), meta = upload(backend, planes.meta);
          const MetalBuffer w1 = kQuantFormats[f].plane1_bytes ? upload(backend, planes.w1) : meta;
          const MetalBuffer output = sharedBuffer(backend, uint64_t{N} * K * 2);
          std::vector<std::string> kernels{fmtName(f)};
          if (f == PTQ10) kernels.push_back("ptq10_lookup");
          for (const std::string &kernel : kernels) {
            CommandGraph graph;
            graph.add(std::string("gguf_test_dequant_") + kernel, {w0, w1, meta, output}, GgufDecodeParams{K, 1, N, 0, 0},
                      {N * (K / kGroup) / kThreads, 1, 1}, {kThreads, 1, 1});
            static_cast<void>(backend.submitCommandAsync(graph.dispatches()).wait());
            const auto *got = static_cast<const uint16_t *>(output.contents());
            size_t differ = 0;
            for (size_t i = 0; i < values.size(); ++i) differ += got[i] != f2h(values[i]);
            std::cout << kernel << (trial ? " boundary scales" : "") << ": " << differ << " of " << values.size()
                      << " weights differ from FP16(GGML fp32 dequantization) " << (differ ? "FAIL" : "ok") << '\n';
            failures += differ != 0;
          }
        }
      }
    } catch (const std::exception &e) {
      std::cerr << "gguf-dequant: FAIL: " << e.what() << '\n';
      return 1;
    }
    return failures ? 1 : 0;
  }
}
