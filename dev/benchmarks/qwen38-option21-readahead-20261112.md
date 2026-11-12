# Option 21 launcher profile and prepared expert read-ahead

The launcher now retains its measured 16 GiB fast profile when only the
configured context, prefix-cache quota or prefix persistence changes.
Previously those settings could silently select 10G / 1,024 instead of
10.8G / 2,048. Explicit memory/chunk settings, single-request admission,
raised expert/PLE store safeguards and the GPU-timeout fallback are preserved.
The repository's option-21 prefix-cache default is aligned with the installed
launcher's existing 3G setting. The installed launcher received only the
profile-selection fix; its other independent changes were preserved.

Prepared expert records now participate in the same forecast batch and SSD
reader pool as native GGUF rows. Forecasts own bounded places in the existing
staging arena. A completed, validated prepared record is copied into its GPU
slot only at the existing host-step boundary. An unfinished unrelated read
keeps its staging place until drained; missing or corrupt records retain the
complete native loading/repack path. Release drains outstanding reads before
storage is reused. The fixed-memory calculation reserves the maximum of native
rows and prepared-plane bytes for each staging projection before expert slots
are planned.

Demand reads retain priority in the SSD pool. A consumed prepared forecast is
not read again on demand and does not submit a native repack over its planes.
Native source/read-ahead byte counters exclude prepared-cache payload bytes,
which remain in the separate plane-cache counters. Whole-expert forecast and
consumption counters include both sources.

## Validation

- The new mock-server regression reproduced the slow-profile selection for
  32K context, a changed prefix-cache quota, and disabled prefix persistence.
- All 11 option-21 launcher tests pass against both repository and installed
  launchers, including explicit overrides and context/timeout recovery.
- The full expert-store GPU suite passes on the rebuilt candidate. It covers
  mixed formats, exact slot/output comparisons, native read failures,
  forecasting, eviction, source changes, shrink/regrowth, and release/restore.
- The final focused prepared-cache GPU test passes. It warms every fixture
  expert, waits for forecast completion, then proves consumption adds neither
  another cache hit nor native source reads. It also covers long prefill,
  outstanding-forecast release and corrupt-record fallback.
- The expert-plane-cache unit test, launcher shell parsing, Python lint and
  formatting, and `git diff --check` pass.

Build validation found and corrected a stale copied object: the initial copied
build had retained the old ExpertStore implementation. The final build log
explicitly records recompilation of `runtime/model/ExpertStore.cpp`, and the
full suite and serving checks use that rebuilt implementation.

## Real serving checks

Q2_0 target with the existing BF16 DFlash2 draft on the 16 GiB M5. Both arms
used 131,072 configured context, 10.8G cap, 2,048-token prefill, BF16 state,
INT8 KV, automatic expert-memory sizing, automatic verification width, one
active request and isolated persistent 3G prefix-cache namespaces.
Each arm ran one 8K fresh-prompt request, the identical prompt again, and an
executable Python longest-common-prefix task. Thinking was disabled in these
requests; output budgets were 96 tokens for recall/counting and 192 for code.

| Candidate path | Filled prompt | Fresh PP tok/s | Fresh decode TPS | Fresh first token | Reused decode TPS | Reused first token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Prepared cache enabled, 512 MiB quota | 8,204 | 440.91 | 22.24 | 18.614 s | 24.35 | 0.769 s |
| Prepared cache disabled | 8,204 | 421.33 | 22.33 | 19.480 s | 24.53 | 0.765 s |

Both paths passed recall/counting, executable-code correctness, and prefix
reuse gates; the repeated requests reused 8,192 prompt tokens. There were no
failed requests or new macOS swap-outs in either arm. Memory pressure was
warning; the prepared arm was nominal thermally and the default arm fair.
Prepared-cache status reported 2,634 hits, 372 writes, zero errors and zero
corruptions, within its quota.

These are short correctness checks, not a matched old-versus-new scheduler
benchmark. The prepared arm also filled its new cache, and thermal conditions
differed. No throughput improvement is established; prepared caching remains
optional and disabled by default. The launcher fix is installed, while the
engine experiment is built separately at
`build/option21-readahead-candidate/splash`. The original production binary was
not replaced. The original service was restored on port 1235 with its prior
model/build identity and serving settings after validation.

Raw logs, per-request responses/timings/status, build identity, system
snapshots, pre-edit copies and a serving reproduction script are saved under
`build/validation/option21-read-ahead-20261112/`. The first automatic restore
attempt failed because the original Python `-P` invocation lacked the
launcher's `PYTHONPATH`. Restoration was corrected with the repository module
path; `production-restored.json` records verified readiness and identity.

## Repeated performance follow-up

The [matched A/B/B/A performance test](qwen38-option21-readahead-performance-20261112.md)
now covers 4K, 8K and 16K fresh/reused prompts on both binaries with the same
frozen prepared cache, plus cache-disabled controls. All 34 timed requests
passed, with no new swap-outs or KV spill. The candidate did not show a
consistent prefill or decode improvement; keep the original production engine
and prepared caching disabled by default. The original service is restored.
Only the new read-ahead prototype and its extra GPU regression changes were
restored to their pre-experiment snapshots. The rejected binary and source
snapshots remain available locally; earlier independent experimental work was
preserved. The retained launcher fix and performance evidence are published.
