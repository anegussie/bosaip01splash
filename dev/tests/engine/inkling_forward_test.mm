#include "TestChecks.hpp"
#include "model/InklingSequence.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <iostream>

int main(int argc, const char **argv) {
  @autoreleasepool {
    try {
      using splash::test::require;
      require(argc >= 6, "usage: inkling-forward METALLIB GGUF EXPECTED_TOP_ID TOKEN TOKEN [TOKEN ...]");
      const auto readToken = [](std::string_view text) {
        uint32_t token = 0;
        const char *end = text.data() + text.size();
        const auto result = std::from_chars(text.data(), end, token);
        require(result.ec == std::errc{} && result.ptr == end, "invalid token ID");
        return token;
      };
      const uint32_t expected = readToken(argv[3]);
      std::vector<uint32_t> tokens;
      for (int i = 4; i < argc; ++i) tokens.push_back(readToken(argv[i]));
      splash::metal::MetalBackend backend(argv[1]);
      splash::model::InklingSequence sequence(backend, argv[2], uint32_t(tokens.size()));
      const auto neverStop = [] { return false; };
      const auto full = sequence.evaluate(tokens, true, neverStop);
      const auto top = uint32_t(std::ranges::max_element(full) - full.begin());
      std::cout << "Inkling full prompt top token " << top << '\n' << std::flush;
      require(top == expected, "Inkling top token differs from the offline reference");
      const std::vector<float> retained(full.begin(), full.end());

      sequence.reset();
      static_cast<void>(sequence.evaluate(std::span(tokens).first(tokens.size() - 1), false, neverStop));
      const auto incremental = sequence.evaluate(std::span(tokens).last(1), true, neverStop);
      require(uint32_t(std::ranges::max_element(incremental) - incremental.begin()) == expected,
              "Inkling incremental attention changed the top token");
      float error = 0.0f;
      for (size_t i = 0; i < retained.size(); ++i) error = std::max(error, std::abs(retained[i] - incremental[i]));
      std::cout << "Inkling incremental max logit error " << error << '\n';
      require(error < 0.2f, "Inkling full and incremental logits diverged");
      return 0;
    } catch (const std::exception &error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
}
