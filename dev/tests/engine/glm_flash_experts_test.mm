#include "MoeFixture.hpp"
#include "MoeStep.hpp"
#include "TestBuffers.hpp"
#include "TestChecks.hpp"
#include "model/GgufTarget.hpp"
#include "model/GlmFlashExperts.hpp"

#include <cmath>
#include <cstring>
#include <iostream>

namespace {
using namespace splash;
using test::require;

} // namespace

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      require(argc == 3, "usage: glm-flash-experts METALLIB GGUF_DIRECTORY");
      metal::MetalBackend backend(argv[1]);
      const auto source = std::make_shared<model::OpenGguf>(model::findTargetGgufs(argv[2]));
      auto blocks = model::glmFlashExpertSources(source);
      require(blocks.blocks.size() == 42, "missing GLM Flash expert layers");
      constexpr auto shape = model::kGlmFlashMoeShape;
      const uint64_t minimum = model::ExpertStore::minimumBytes(blocks, shape);
      std::cout << "GLM Flash expert store minimum bytes: " << minimum << std::endl;
      model::ExpertStore store(backend, std::move(blocks), shape,
          {.memoryBytes = minimum, .floorBytes = minimum, .readers = std::make_shared<model::SsdReaders>(8)});
      const auto &file = source->file();
      auto weights = model::loadGlmFlashMoeBlock(backend, file, 3);
      auto next = model::loadGlmFlashMoeRouter(backend, file, 4);
      store.bind(0, weights);
      store.bind(1, next);
      require(weights.stream != nullptr, "expected the first GLM Flash MoE block to stream");

      const auto plan = ops::MoE::plan(shape, 1, ops::MoeConfig{ops::MoeExpertTile::M8});
      moe_fixture::Buffers scratch;
      moe_fixture::allocate(backend, scratch, plan);
      const uint64_t bytes = shape.hiddenSize * sizeof(__bf16);
      scratch.moe.input = test::sharedBuffer(backend, bytes);
      auto *input = static_cast<__bf16 *>(scratch.moe.input.contents());
      for (uint32_t d = 0; d < shape.hiddenSize; ++d)
        input[d] = __bf16(std::sin(float(d) * 0.27f));
      scratch.moe.residual = moe_fixture::zeros(backend, bytes, "glm expert residual");
      scratch.moe.output = moe_fixture::zeros(backend, bytes, "glm expert output");
      auto run = [&] {
        metal::CommandGraph graph;
        test::addMoeStep(graph, scratch.moe, weights, plan);
        static_cast<void>(backend.submitCommandAsync(graph.command()).wait());
      };
      run();
      const auto cold = store.stats();
      require(cold.uses[0].read >= shape.expertsPerToken && cold.uses[0].readBytes > 0,
              "GLM Flash expert store did not read selected weights from the shards");
      const auto *output = static_cast<const __bf16 *>(scratch.moe.output.contents());
      bool nonzero = false;
      for (uint32_t d = 0; d < shape.hiddenSize; ++d) {
        require(std::isfinite(float(output[d])), "GLM Flash streamed MoE output is not finite");
        nonzero |= float(output[d]) != 0.0f;
      }
      require(nonzero, "GLM Flash streamed MoE output is zero");
      std::vector<uint8_t> baseline(bytes);
      std::memcpy(baseline.data(), output, bytes);
      run();
      const auto warm = store.stats();
      require(cold.uses[0].read == warm.uses[0].read, "GLM Flash MoE reread resident weights");
      require(std::memcmp(baseline.data(), output, bytes) == 0, "GLM Flash MoE replay changed");
      std::cout << "GLM Flash MoE streamed " << cold.uses[0].read << " experts and " << cold.uses[0].readBytes
                << " bytes from the cached shards. Warm replay was bitwise identical.\n";
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
