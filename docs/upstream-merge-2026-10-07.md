# Upstream integration validated on 2026-10-07

Merged upstream `0d5a035ea26d1cc566e3c7ee4e08e5e06fa68cf7` into local
`splashmain` based on `ffec1d0b094dd299f9acfac29f74edb80c8510f1`.
The branches had 92 incoming commits, 15 local commits and 51 conflicted files.
All conflicts were reconciled; the upstream server, model validation,
Neural Engine prefill, test layout and asynchronous Metal interfaces are retained.

## Local behavior retained

- PTQ1_0 loading, dequantization, embedding rotation and the exact decode lookup.
  The native embedding decoder now lives in upstream's shared format header.
- Configurable prefill chunks (128 through 2048 in multiples of 128; default 512),
  shared prefill/decode phase scratch, and context-sized attention workspace.
- Essential startup admission above the protected macOS reserve, with ordinary
  idle growth still obeying host-pressure pacing and critical pressure refusing growth.
- Configurable resource-wait timeout and FIFO single-request serving for option 14.
  Queued HTTP streams keep alive and disconnect before native submission;
  this was reproduced over HTTP before the callback was restored to `_submit`.
- The Metal backend's lifetime idle-sleep assertion, now honoring explicit
  `--allow-idle-sleep` without losing the local default.
- Local arena, context-boundary, PTQ lookup and FIFO coverage, adapted to the
  relocated upstream tests. Exact duplicate ported definitions were removed.

The external `/Users/mymac/startllamacpp.sh` was not edited. Its SHA-256 was
checked before and after the live test: `a9e957134fc4e4d7631b5864ed47f596c901a600014da4c6f00c877417a8d668`.
The launcher test used temporary client configuration, logs and a dedicated cache.

## Validation

| Check | Result |
| --- | --- |
| Production build and build identity | Passed |
| Architecture and whitespace checks | Passed |
| Ruff over server, installer and development code | Passed |
| Full Python discovery | 1,244 tests; passed, 7 skips |
| Native CPU suite | Passed |
| Native Metal suite | Passed; shader validation enabled for the suite's GPU checks |
| All native tests and developer tools (`check-native-build`) | Built successfully |
| PTQ1_0 dequantization and lookup | Zero mismatches against FP16 reference |
| PTQ1_0 rotated embedding | Zero mismatches against BF16 FP32 butterflies |
| Shared scratch GPU lifetime tests | Passed at both 512 and 2048 rows |
| External option-14 tools | Complete and streaming calls preserved `12:00` and `0800` strings |
| Prefix reuse after clean restart | 4,864 of 4,892 tokens reused |
| Long-context request | 24,081 input tokens, correct `VIOLET` answer, healthy Metal, zero failed native requests |
| Launcher shutdowns | Both clean; no server remained listening |

The live profile was Bonsai PTQ1_0 with its installed DFlash draft, language-only,
INT8 KV, 24,576 context tokens, 512-token prefill chunks, one active request,
60-second resource wait and an 8 GiB persistent SSD cache, on the 16 GiB M5.
Requests used greedy sampling and reasoning effort none. The rotated model
correctly reported ANE off because the split requires unrotated projection planes.

The uncached long prompt completed in 193.11 seconds.
The restarted 4,892-token request completed in 2.79 seconds,
with 394.028 ms of reported prefill.
That is cache reuse, not a matched benchmark of prefill compute speed.
Planned shared prefill/decode memory was 187.45/
54.53 MiB; reported peak Metal allocation after
long-context serving was 8.64 GiB.

System swap used was 5,237.75 MiB before the long request and 5,663.44 MiB after,
an increase of 425.69 MiB with warning pressure. The owner of that increase was
not measured. Python regressions also ran during the live check. These are
functional capacity results on repetitive records, not isolated coding-speed
benchmarks or a claim of swap-free 24K operation.

Full responses, status snapshots, timings and swap samples are saved in
[`bonsai-upstream-merge.json`](../dev/benchmarks/bonsai-upstream-merge.json).

To repeat the external launcher validation after native GPU tests:

```sh
.venv/bin/python dev/tests/option14_merge_validation.py
```
