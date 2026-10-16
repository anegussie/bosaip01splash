# Option-14 speculation on/off benchmark, 2026-10-16

The isolated target-only path completed the 4K and 12K unconstrained comparison workloads. The 20K tool-schema case was excluded because it triggers a grammar constraint that this experimental path rejects. Both modes were measured on the real option-14 launcher on the same experimental engine. The results below measure this target-only implementation; Splash currently has no supported production speculation-off switch.

Decision: retain the existing speculation-enabled production configuration. The experimental target-only path was not installed in production.

Apple M5, eight GPU cores, 16 GiB unified memory. Target `prism-ml/Ternary-Bonsai-2-27B-gguf:PTQ1_0`, revision `b072e1d3b35a0a630cece372c2127528e0994386`; draft `incoai/Qwen3.8-27B-DFlash2`, revision `015e795645c74b1a0eeef3b570031fb62e769bc5`. Splash Metal, INT8 KV, BF16 recurrent state, 512-token prefill chunks, 24,576 configured context and one active request. Greedy, seed 42, reasoning none, top_p 0.8 and top_k 20.

Four fresh server sessions contributed paired on/off/off/on measurements at 4K and 12K. Sessions ran at port 1236 through `/Users/mymac/startllamacpp.sh --direct 14`, with `SPLASH_BIN` selecting an isolated checkout and separate OpenCode config, logs and persistent prefix caches. Each test cache had a 2 GiB quota. Target and draft artifacts and runtime allocations were retained in both modes; target+draft prefill stayed identical. A one-token cold request primed each prefix before two measured repeats. Therefore request-latency comparisons below describe repeated-prefix requests, not cold end-to-end requests.

Production commit: `c431edc320de59e45ea03ea0615e3809dbb2287b`. Test build: `src-3c2034df7761e960e384e73ce31902b6fa3f498327c026eff8c7a3a834988bdb`.

| Filled prompt / task | Speculation on, decode tok/s | Speculation off, decode tok/s | Observed on/off speed ratio | Decode spread | Controlled comparison |
| --- | ---: | ---: | ---: | ---: | --- |
| 4,026 / merge_intervals | 37.47 | 5.90 | 6.35x | 12.02% | inconclusive |
| 12,258 / review_intervals | 21.89 | 4.74 | 4.62x | 27.60% | inconclusive |

Each phase contributes the median of two native decode costs in ms/token. On/off costs average their two phases; rates are the reciprocals. Spread is the larger within-mode ABBA spread, as defined by `abba.py`. A controlled speed claim also requires matching thermal transitions, identical output and at most 5% within-phase decode spread. Noisy ratios remain observations, not stable speedup claims. Native counters include batch work and differ slightly from streamed response timing fields, which are retained in the JSON.

| Task | On request seconds | Off request seconds | On draft acceptance | All outputs identical |
| --- | ---: | ---: | ---: | --- |
| 4096-merge_intervals | 3.750 | 22.390 | 82.7% | True |
| 12288-review_intervals | 11.909 | 53.851 | 48.5% | False |

All 16 paired measured completions passed executable function checks. The 4K outputs matched exactly across modes; the 12K outputs differed (247 tokens on versus 252 off), so exact greedy-output parity was not established. Two additional 20K speculation-on completions passed but have no valid off-mode comparison. Code-review cases also checked discussion of mutation, nested intervals and touching endpoints, then executed the corrected function. The excluded 20K stable-unique case included a tool schema with `tool_choice=none`, which nevertheless activates a grammar constraint in this serving path. The experimental target-only guard rejected it; the server returned 503 and entered recovery. This was a test-path limitation, not evidence of target-only throughput at 20K. Grammar-constrained tool generation and nonzero-temperature sampling are outside the valid comparison. No measured response ended at its output limit.

## Target-only implementation and limits

The experimental branch submits one actual target token at a time through the existing one-row target operators and a single-row vocabulary projection. It omits draft forward, speculative acceptance and draft-context commit during decode. Draft counters were exactly zero in both off sessions and positive in both on sessions. The target forward reuses the existing one-row prefill/GDN/attention operators. Quantized projections still pad small inputs to the existing eight-row staged tiles. This is not a separately tuned target-only runtime or a prediction of its maximum possible speed; a dedicated single-token decode implementation could perform differently. Draft weights and arenas remain allocated, so the test does not measure memory savings from removing the draft model.

Prefill, tokenizer and target quantization remain the same. Prefix states are only published during prefill; the target-only branch does not publish its draft-incomplete generated states. It accepts only greedy unconstrained requests with one active lane. Its internal bootstrap still uses the standard warmup; all measured request counters are recorded after startup.

An initial baseline pilot and two unsuccessful test-only smoke attempts were excluded before the four-phase experiment. The paired 4K/12K measurements from the second session completed before its later excluded 20K grammar failure; the remaining two sessions were then resumed using only the valid 4K/12K cases. The corrected target-only smoke returned the expected text and zero draft counters.

## Resources and verification

| Phase | Aggregate native decode tok/s | Swap before | Swap after | Failed requests | Metal healthy |
| --- | ---: | --- | --- | ---: | --- |
| round-1-on | 29.03 | vm.swapusage: total = 4096.00M  used = 2868.00M  free = 1228.00M  (encrypted) | vm.swapusage: total = 4096.00M  used = 2860.00M  free = 1236.00M  (encrypted) | 0 | True |
| round-2-off | 5.06 | vm.swapusage: total = 4096.00M  used = 2860.00M  free = 1236.00M  (encrypted) | unrecorded after excluded grammar-constraint failure | 0 | True |
| round-3-off | 5.10 | vm.swapusage: total = 4096.00M  used = 2590.81M  free = 1505.19M  (encrypted) | vm.swapusage: total = 4096.00M  used = 2574.81M  free = 1521.19M  (encrypted) | 0 | True |
| round-4-on | 22.82 | vm.swapusage: total = 4096.00M  used = 2574.81M  free = 1521.19M  (encrypted) | vm.swapusage: total = 4096.00M  used = 2558.81M  free = 1537.19M  (encrypted) | 0 | True |

The second session has a recorded transport failure from the excluded 20K grammar case; its final status is stale and its post-session swap value was not captured. This failure occurred after all its paired 4K/12K measurements. All other final session statuses were healthy.

Swap values are host-wide, not attributable solely to Splash. Full before/after thermal and memory-pressure states, cache-token counts, per-request latency and metric deltas are in the JSON. Resource and thermal drift can limit timing comparisons even when outputs match.

Both production binary and launcher hashes are unchanged. All four test servers stopped and port 1236 was released. No production settings or runtime source files were modified.

The [measured data](bonsai-speculation-abba-20261016.json) includes the summary and all 28 completed requests (10 one-token cold-prefix primes, 16 paired measured completions and two unpaired 20K speculation-on completions), plus the excluded failure status. Raw logs, full status snapshots, runner, analysis scripts, experimental source patch and artifact hashes remain in `build/validation/speculation-abba-20261016/`.
