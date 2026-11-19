#include "engine/GlmFlashNative.hpp"

#include "StderrLine.hpp"
#include "engine/Json.hpp"
#include "engine/Protocol.hpp"
#include "model/GlmFlashSequence.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <csignal>
#include <poll.h>
#include <random>
#include <system_error>
#include <sysexits.h>
#include <unistd.h>

namespace splash::engine {
namespace {
using namespace protocol;
using Clock = std::chrono::steady_clock;

constexpr uint32_t vocabulary = model::GlmFlashSequence::vocabulary;
constexpr uint32_t maskWords = (vocabulary + 31) / 32;
constexpr std::array<uint32_t, 3> stopTokens{154820, 154827, 154829};

uint64_t elapsed(Clock::time_point start) {
  return std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - start).count();
}

uint64_t unixMicros() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::system_clock::now().time_since_epoch()).count();
}

class Pipe {
public:
  void send(const EngineEvent &event) const {
    auto encoded = serializeEvent(event, limits_);
    if (!encoded) throw std::runtime_error(encoded.issue->describe());
    std::span<const uint8_t> bytes = *encoded.value;
    while (!bytes.empty()) {
      const auto count = write(STDOUT_FILENO, bytes.data(), bytes.size());
      if (count < 0 && errno == EINTR) continue;
      if (count <= 0) throw std::system_error(errno, std::system_category(), "GLM protocol write");
      bytes = bytes.subspan(size_t(count));
    }
  }

  std::optional<ClientMessage> receive(int timeout) {
    while (!closed_) {
      if (offset_ < size_) {
        auto step = parser_.consume(std::span(buffer_).subspan(offset_, size_ - offset_));
        offset_ += step.consumedBytes;
        if (step.issue) throw std::runtime_error(step.issue->describe());
        if (!step.frame) continue;
        auto decoded = decodeFrame(std::move(*step.frame), limits_);
        if (decoded) return std::move(decoded.value);
        if (connectionMustClose(decoded.issue->failureClass))
          throw std::runtime_error(decoded.issue->describe());
        send(ErrorEvent{.requestId = decoded.issue->requestId, .code = "invalid_request",
                        .message = decoded.issue->describe()});
        continue;
      }

      pollfd input{STDIN_FILENO, POLLIN, 0};
      const int result = poll(&input, 1, timeout);
      if (result == 0) break;
      if (result < 0 && errno == EINTR) continue;
      if (result < 0) throw std::system_error(errno, std::system_category(), "GLM protocol poll");
      const auto count = read(STDIN_FILENO, buffer_.data(), buffer_.size());
      if (count < 0 && errno == EINTR) continue;
      if (count < 0) throw std::system_error(errno, std::system_category(), "GLM protocol read");
      if (count == 0) {
        closed_ = true;
        if (auto issue = parser_.finish()) throw std::runtime_error(issue->describe());
      }
      offset_ = 0;
      size_ = size_t(count);
    }
    return {};
  }

  [[nodiscard]] bool closed() const noexcept { return closed_; }

private:
  ProtocolLimits limits_;
  FrameParser parser_{limits_};
  std::array<uint8_t, 65536> buffer_{};
  size_t offset_ = 0;
  size_t size_ = 0;
  bool closed_ = false;
};

bool maskAllows(std::span<const uint32_t> mask, uint32_t token) {
  return mask.empty() || (mask[token / 32] & (1u << (token % 32)));
}

class Sampler {
public:
  explicit Sampler(const RequestFrame &request)
      : settings_(request.sampling), random_(settings_.seed), seen_(vocabulary), counts_(vocabulary) {
    for (const auto token : request.promptTokens) seen_[token] = true;
  }

  void record(uint32_t token) {
    seen_[token] = true;
    ++counts_[token];
  }

  std::optional<uint32_t> select(std::span<const float> logits, std::span<const uint32_t> mask) {
    struct Candidate { uint32_t token; double value; };
    std::vector<Candidate> candidates;
    if (settings_.temperature != 0) candidates.reserve(logits.size());
    std::optional<Candidate> best;
    for (uint32_t token = 0; token < logits.size(); ++token) {
      if (!maskAllows(mask, token)) continue;
      double logit = logits[token];
      if (seen_[token])
        logit = logit < 0 ? logit * settings_.repetitionPenalty : logit / settings_.repetitionPenalty;
      if (counts_[token])
        logit -= settings_.presencePenalty + double(settings_.frequencyPenalty) * counts_[token];
      const Candidate candidate{token, logit};
      if (!best || logit > best->value) best = candidate;
      if (settings_.temperature != 0) candidates.push_back(candidate);
    }
    if (!best) return {};
    if (settings_.temperature == 0) return best->token;

    const double cutoff = best->value + settings_.temperature * std::log(double(settings_.minP));
    std::erase_if(candidates, [&](const Candidate &row) { return row.value < cutoff; });
    const size_t keep = settings_.topK ? std::min<size_t>(settings_.topK, candidates.size()) : candidates.size();
    std::partial_sort(candidates.begin(), candidates.begin() + keep, candidates.end(),
        [](const Candidate &a, const Candidate &b) {
          return a.value == b.value ? a.token < b.token : a.value > b.value;
        });
    candidates.resize(keep);
    double mass = 0;
    for (auto &row : candidates) {
      row.value = std::exp((row.value - best->value) / settings_.temperature);
      mass += row.value;
    }
    double retained = 0;
    size_t prefix = 0;
    do {
      retained += candidates[prefix++].value;
    } while (prefix < candidates.size() && retained < mass * settings_.topP);
    double draw = std::generate_canonical<double, 53>(random_) * retained;
    for (size_t index = 0; index < prefix; ++index) {
      draw -= candidates[index].value;
      if (draw < 0) return candidates[index].token;
    }
    return candidates[prefix - 1].token;
  }

private:
  SamplingParameters settings_;
  std::mt19937_64 random_;
  std::vector<bool> seen_;
  std::vector<uint32_t> counts_;
};

class Worker {
public:
  Worker(Pipe &pipe, model::GlmFlashSequence &sequence, uint32_t capacity)
      : pipe_(pipe), sequence_(sequence), capacity_(capacity) {}

  void run() {
    pipe_.send(ReadyEvent{.maxConcurrentRequests = 1, .maxContextTokens = capacity_,
                          .vocabularySize = vocabulary, .stopTokens = {stopTokens.begin(), stopTokens.end()},
                          .maskRows = 1});
    while (auto message = pipe_.receive(-1)) {
      @autoreleasepool {
        if (auto *request = std::get_if<RequestFrame>(&*message)) {
          try {
            generate(*request);
          } catch (const std::exception &error) {
            if (!pipe_.closed()) {
              pipe_.send(ErrorEvent{.failureClass = FailureClass::EngineUnhealthy,
                                    .requestId = request->requestId, .code = "engine_unhealthy",
                                    .message = error.what()});
            }
            throw;
          }
          sequence_.reset();
        } else {
          control(*message, 0);
        }
      }
    }
  }

private:
  void status(uint64_t correlation, bool active) {
    json::Writer writer;
    writer.object([&] {
      writer.field("schema_version", kStatusSchemaVersion)
          .field("ready", true)
          .field("architecture", "glm5-next")
          .field("backend", "metal")
          .field("max_context_tokens", capacity_)
          .field("prefill_chunk_tokens", model::GlmFlashSequence::chunkRows)
          .field("active_requests", uint32_t(active))
          .field("expert_read_bytes", sequence_.expertReadBytes());
      writer.object("weights", [&] { writer.field("released", false).field("restoring", false); });
    });
    pipe_.send(StatusJsonEvent{correlation, writer.str()});
  }

  void requestError(uint64_t id, const char *code, const char *message, bool retryable = false) {
    pipe_.send(ErrorEvent{.requestId = id, .retryable = retryable, .code = code, .message = message});
  }

  void control(const ClientMessage &message, uint64_t active) {
    if (const auto *statusFrame = std::get_if<StatusRequestFrame>(&message))
      status(statusFrame->correlationId, active != 0);
    else if (const auto *release = std::get_if<ReleaseRequestFrame>(&message))
      status(release->correlationId, active != 0);
    else if (const auto *cancel = std::get_if<CancelFrame>(&message); cancel && cancel->requestId == active)
      cancelled_ = true;
    else if (const auto *stop = std::get_if<StopFrame>(&message); stop && stop->requestId == active)
      stopped_ = true;
    else if (const auto *request = std::get_if<RequestFrame>(&message))
      requestError(request->requestId, "overloaded", "GLM Flash already has an active request", true);
  }

  void generate(const RequestFrame &request) {
    const auto id = request.requestId;
    constexpr auto outOfRange = [](uint32_t token) { return token >= vocabulary; };
    if (request.promptTokens.empty() || request.promptTokens.size() > capacity_ ||
        std::ranges::any_of(request.promptTokens, outOfRange) ||
        std::ranges::any_of(request.scoreTokens, outOfRange) ||
        (request.thinkingBudget && std::ranges::any_of(request.thinkingBudget->end, outOfRange)) ||
        !request.imageSpans.empty()) {
      requestError(id, "invalid_request", "GLM Flash requires a text prompt and valid token IDs within its context");
      return;
    }
    const auto now = unixMicros();
    if (request.absoluteDeadlineUnixMicros <= now) {
      requestError(id, "deadline_exceeded", "request deadline expired");
      return;
    }
    const auto start = Clock::now();
    const auto remaining = std::min(request.absoluteDeadlineUnixMicros - now, request.remainingDeadlineMicros);
    const auto expired = [&] { return elapsed(start) >= remaining; };
    const auto interrupt = [&] {
      while (auto message = pipe_.receive(0)) control(*message, id);
      return pipe_.closed() || cancelled_ || stopped_ || expired();
    };

    cancelled_ = stopped_ = false;
    pipe_.send(StartEvent{.requestId = id});
    const uint32_t promptCount = uint32_t(request.promptTokens.size());
    const uint32_t outputLimit = std::min(request.logicalMaxOutputTokens, capacity_ - promptCount + 1);
    DoneEvent done{.requestId = id, .reason = EngineFinishReason::Length, .promptTokens = promptCount};
    std::span<const float> logits;
    for (uint32_t offset = 0; offset < promptCount && !interrupt();) {
      const auto count = std::min(model::GlmFlashSequence::chunkRows, promptCount - offset);
      const bool last = offset + count == promptCount;
      logits = sequence_.evaluate(std::span(request.promptTokens).subspan(offset, count), last, interrupt);
      offset += count;
      if (!interrupt() && (request.flags & kReturnProgressFlag))
        pipe_.send(PromptProgressEvent{id, offset, elapsed(start)});
    }
    done.prefillMicros = elapsed(start);
    const auto decodeStart = Clock::now();

    if (!interrupt() && !request.scoreTokens.empty()) {
      done.reason = EngineFinishReason::Stop;
      for (const uint32_t token : request.scoreTokens) done.optionLogits.push_back(logits[token]);
    } else if (!interrupt()) {
      Sampler sampler(request);
      bool thinking = request.thinkingBudget.has_value();
      size_t ending = 0;
      for (uint32_t index = 0; index < outputLimit && !interrupt(); ++index) {
        std::vector<uint32_t> mask;
        if (request.constraint != ConstraintMode::None) {
          const uint64_t maskId = uint64_t(index) + 1;
          pipe_.send(MaskRequestEvent{id, maskId, maskWords, {}, {}});
          while (!pipe_.closed() && !cancelled_ && !stopped_ && !expired()) {
            auto message = pipe_.receive(100);
            if (!message) continue;
            if (auto *response = std::get_if<MaskResponseFrame>(&*message);
                response && response->requestId == id && response->maskRequestId == maskId) {
              if (response->maskWords.size() != maskWords)
                throw std::runtime_error("invalid GLM Flash constraint mask size");
              mask = std::move(response->maskWords);
              break;
            }
            control(*message, id);
          }
          if (mask.empty() || interrupt()) break;
        }

        auto token = sampler.select(logits, mask);
        if (thinking) {
          const auto &budget = *request.thinkingBudget;
          if (index >= budget.tokens && maskAllows(mask, budget.end[ending])) token = budget.end[ending++];
          if (token && (*token == budget.end.back() || *token == budget.alsoEnds)) thinking = false;
        }
        if (!token) {
          requestError(id, "invalid_constraint", "constraint admits no GLM Flash token");
          return;
        }
        if (!(request.flags & RequestIgnoreEndOfSequence) &&
            std::ranges::find(stopTokens, *token) != stopTokens.end()) {
          done.reason = EngineFinishReason::Stop;
          break;
        }
        pipe_.send(TokensEvent{id, done.completionTokens, {*token}});
        ++done.completionTokens;
        sampler.record(*token);
        if (index + 1 < outputLimit && !interrupt())
          logits = sequence_.evaluate(std::span(&*token, 1), true, interrupt);
      }
      done.decodeMicros = elapsed(decodeStart);
      done.bounded = done.reason == EngineFinishReason::Length && outputLimit < request.logicalMaxOutputTokens;
    }
    if (pipe_.closed()) return;
    if (cancelled_ || (stopped_ && !done.completionTokens)) done.reason = EngineFinishReason::Cancelled;
    else if (stopped_) done.reason = EngineFinishReason::Stop;
    else if (expired()) {
      requestError(id, "deadline_exceeded", "request deadline expired");
      return;
    }
    if (done.reason != EngineFinishReason::Length) done.bounded = false;
    if (done.reason == EngineFinishReason::Cancelled) done.optionLogits.clear();
    done.wallMicros = elapsed(start);
    pipe_.send(done);
  }

  Pipe &pipe_;
  model::GlmFlashSequence &sequence_;
  uint32_t capacity_;
  bool cancelled_ = false;
  bool stopped_ = false;
};
} // namespace

int serveGlmFlash(const std::filesystem::path &metallib, const std::filesystem::path &directory, uint32_t capacity) {
  signal(SIGPIPE, SIG_IGN);
  Pipe pipe;
  std::unique_ptr<metal::MetalBackend> backend;
  std::unique_ptr<model::GlmFlashSequence> sequence;
  try {
    backend = std::make_unique<metal::MetalBackend>(metallib);
    sequence = std::make_unique<model::GlmFlashSequence>(*backend, directory, capacity);
  } catch (const std::exception &error) {
    pipe.send(StartFailedEvent{.message = error.what()});
    return EX_SOFTWARE;
  }
  Worker worker(pipe, *sequence, capacity);
  worker.run();
  return EX_OK;
}

} // namespace splash::engine
