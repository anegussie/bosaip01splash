# Selected upstream fixes on splashmain

This records the selective 2026-10-05 port. The full 2026-10-07 integration is
documented in [the upstream merge validation](upstream-merge-2026-10-07.md).

Integrated on 2026-10-05 against local base `13dafc9`, using upstream
`35c828c` as the comparison point. This is a selective port of the fixes below;
the complete upstream refactoring and optional idle-release changes are not
included.

| Upstream source | Behavior |
| --- | --- |
| `d4066a9` | Preserve tool argument names, ordering, strings, and framed content; constrain argument schemas for strict tools. |
| `4133d89`, `8bfbdbf` | Pass reasoning `none` consistently to templates; read and validate `enable_thinking` once. |
| `d94f6cd`, `3c60bc6` | Use macOS awake time for engine deadlines, watchdogs, cache timing, residency, and model timing. |
| `bcf3ebb` | Validate operator buffer extents before encoding GPU dispatches. |
| `25e4e8d` | Reject unsupported F32 Q4-sum norms and partial groups before kernel lookup. |

The buffer checks use `BufferExtent.hpp` from `a61f5df` and the RoPE dimension
constants introduced by `88cc762`. The broad helper refactoring from those
commits was not needed. Attention boundary tests additionally cover query,
output, and page-table views one byte below the active extent, including reused
allocations whose padded size exceeds the current chunk's requirements.

Local PTQ1_0 support, shared scratch arenas, context-sized attention workspace,
startup admission rules, configurable resource waits, and prefill chunk sizing
are retained. The existing Metal-backend idle-sleep assertion remains in place.
The configurable prefill warmup retains its actual chunk bound while switching
its timing to the awake clock.

## Validation

- Production build and build identity: passed.
- Python engine discovery: 823 tests, passed with 7 skips.
- Server, GGUF metadata, model, upstream, and installer-restart tests: 347 tests,
  passed.
- Full native CPU suite: passed.
- All native Metal suite commands: passed with shader validation, except the
  suite's capability check that runs without it by design. The first Metal run
  stopped at a new negative-test fixture that trimmed allocation padding rather
  than active page-table bytes. The corrected attention test and every remaining
  suite command subsequently passed; earlier successful numerical tests were
  not repeated.
- Architecture check, launcher shell syntax, and Git whitespace check: passed.

The first concurrent Python run's three build-configuration failures occurred
while integration was still changing compiler input headers. The focused test
and the complete rerun passed after source inputs stabilized. Socket, Metal
compiler-cache, and GPU checks ran with normal macOS access after sandbox
denials.

## Actual option-14 run

Started through `/Users/mymac/startllamacpp.sh --direct 14`, using:

- Apple M5, 16 GiB RAM, 8 GPU cores, macOS 26.5.2.
- `prism-ml/Ternary-Bonsai-2-27B-gguf:PTQ1_0` and its installed draft.
- 24,576 server context / 22,528 OpenCode context, reasoning `none`, INT8 KV.
- 512-token prefill chunks, one active request, 60-second resource wait.
- 8 GiB persistent prefix-cache quota and the launcher's existing cache path.

| Check | Result |
| --- | --- |
| Non-streamed tool call | Preserved `start="12:00"` and `code="0800"`. |
| Streamed tool call | Preserved both strings and completed SSE. |
| Thinking option | Null followed reasoning `none`; non-boolean returned 400 before native admission. |
| Multi-chunk prefill | Correct answer at 4,892 input tokens and 96 output tokens, with zero cached input tokens. |
| Cached repeat | Correct answer; reused 4,864 input tokens. |
| Plain-text streaming | Correctly counted 1 through 20 and completed SSE. |
| Longer prompt | Correct final-record answer at 12,251 input tokens, with zero cached input tokens. |

All seven native requests completed; none failed or was cancelled. Final Metal
status was healthy. The 4,892-token request reported 190.5 PP tokens/s and 34.4
decode tokens/s, taking 28.40 seconds end to end. Its cached repeat took 3.26
seconds. The 12,251-token request reported 176.4 PP tokens/s and took 69.46
seconds. These are single-run smoke measurements, not a controlled performance
comparison.

Memory pressure remained at warning. B1 and 512-row production warmups passed;
B2-B4 production warmups were memory-limited. Peak reported Metal memory was
8,868,446,208 bytes. System swap rose from 1,964.62 to 2,536.38 MiB during the
live tests; the process responsible was not measured. Testing filled up to
12,251 tokens, not the entire configured context. Physical Mac sleep/resume was
not exercised; awake-clock architecture checks and native watchdog tests passed.

Live results are in `build/validation/option14-upstream.json` and
`build/validation/option14-extended.json`. The reusable regression command is:

```sh
.venv/bin/python dev/tests/option14_upstream_smoke.py
```

The test launcher log is `/private/tmp/splash-option14-test.log`; its permanent
run log is
`/Users/mymac/.local/state/llama-server/bonsai-27b-splash-20261005-171218.log`.
