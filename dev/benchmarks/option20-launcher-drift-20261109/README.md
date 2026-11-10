# Option 20 launcher drift fix (2026-11-09)

The launcher that actually runs on this Mac, `~/startllamacpp.sh`, had drifted from the repo launcher `startllamacpp.sh`. `dev/benchmarks/test_bonsai_launcher.py` failed 29 of its tests against the drifted copy and passed all of them against the repo copy, so every option-20 number measured through the drifted copy came from an untested launcher.

Two independent deviations were in it:

- **Option 21** (`Qwen3.8-Flash-Next GSQ-RCO Q2_0` with a local BF16 DFlash2 draft, isolated prefix cache). Useful and working, but only ever written into the installed copy. It is now part of the repo launcher: menu entry, `--direct` range, choice validation, the Q2_0 model id, alias, display name, isolated cache directory, and the requirement that the cached BF16 draft exists before launching. Two new tests cover it (`test_option21_uses_the_q2_model_the_local_draft_and_its_own_cache`, `test_option21_requires_the_cached_bf16_draft`).
- **A 150K context variant** (`splash_context_max=150000` for options 20 and 21, plus accepting `SPLASH_FLASH_NEXT_MAX_CONTEXT=150000` in the stock-profile guard). Nothing in git history ever carried `150000` in the launcher; the repo launcher states 131K resident admission on a 16 GiB Mac, and the 2026-11-07 attempt at it lives only as artifacts under `build/validation/option20-context150k-20261107/` with no published result. This deviation was dropped when the installed copy was re-synced, so options 20 and 21 advertise 131,072 context tokens.

After the fix `~/startllamacpp.sh` and `startllamacpp.sh` are byte-identical (`524cebaf915258c9ad9f353960014246`), and the launcher suite reports 43 tests, OK, against both paths.

Files here:

- `startllamacpp.sh.drifted` the installed copy as it was before the fix, for rollback
- `startllamacpp.sh.synced` the launcher that replaced it
- `drift.diff` the exact difference between the two, which is the 150K variant plus the menu ranges

Rollback: `cp dev/benchmarks/option20-launcher-drift-20261109/startllamacpp.sh.drifted ~/startllamacpp.sh`. That reinstates the 150K variant and the untested launcher behaviour, and the launcher tests will fail again.
