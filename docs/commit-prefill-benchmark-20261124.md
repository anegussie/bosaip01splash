# Prompt processing across the last four commits (2026-11-24)

Question: of the four newest commits on `option20-best-pp-20261106`, which serves
the option 21 model with the highest prompt processing?

| Commit | What it changes | Engine build id |
| --- | --- | --- |
| `afd25837` Add a decode expert read-ahead budget | `runtime/model/ExpertStore.{cpp,hpp}`, `runtime/model/ModelFactory.cpp` | `src-3bfb02d0` |
| `d9098fa2` Add Inkling IQ1_S launcher option 26 | `startllamacpp.sh` only | `src-37fac205` |
| `a3c2224a` Improve Inkling prefill and decode performance | `runtime/model/InklingSequence.{cpp,hpp}`, `runtime/metal/kernels/shared/inkling.metal`, `runtime/engine/GlmFlashNative.mm` | `src-37fac205` |
| `436e44b0` Serve Inkling 2 Mini natively in Splash | Inkling kernels and checkpoint, `runtime/main.mm`, `runtime/metal/kernels/shared/gguf_float.metal` | `src-0ae0496c` |

`d9098fa2` and `a3c2224a` hash to the same engine build because the launcher is not
part of the production source set. Between `436e44b0` and `HEAD` the only Metal
kernel that moves is `inkling.metal`, so the Q2_0 prefill tile, the staged GGUF
tile and the PLE gather path are the same object code in all four builds. The only
engine change on the serving path is the decode read-ahead knob, and it applies to
`LoadUse::Decode` with its default still at 100 percent.

## Method

Each commit was built with `make build/splash` in its own checkout (about two
minutes each), then served on port 1236 with the production option 21 command line
(Q2_0 target, BF16 DFlash2 draft, 10.8G cap, 2,048-token prefill chunks, 64M PLE
row cache, 131,072 context). Production on port 1235 was stopped for each run and
restored after.

`build/commit-bench/commit-pp-ab.py` measures one cold 8,129 token ledger prompt
per launch. `build/commit-bench/pp-triple.py` measures three cold prompts with
different cache salts in the same launch, so the three numbers share one thermal
environment. 28 launches in total, four to nine per commit. Prompt processing is
prompt tokens over prefill milliseconds from the serve record.

Binaries kept at `build/commit-bench/bin/<sha>/`.

## Results

| Commit | Launches | Per-launch median PP, tok/s | Median | Mean | Decode tok/s |
| --- | ---: | --- | ---: | ---: | ---: |
| `afd25837` HEAD | 9 | 247.1 264.9 265.7 268.0 268.9 271.3 290.9 308.9 314.8 | 268.9 | 277.8 | 24.78 |
| `d9098fa2` | 4 | 249.8 265.9 296.8 303.6 | 281.4 | 279.0 | 24.35 |
| `a3c2224a` | 7 | 255.6 269.6 271.7 272.4 286.5 288.4 374.4 | 272.4 | 288.4 | 24.87 |
| `436e44b0` | 8 | 243.8 253.5 261.3 268.2 289.7 358.4 385.7 391.3 | 278.9 | 306.5 | 24.28 |

The spread inside one commit is wider than the spread between commits: the same
binary measured 247.1 tok/s on a warm machine and 391.3 tok/s after twenty minutes
of idle, and every launch reported `fair` thermal in both cases.

Paired windows, arms launched back to back in the same session:

| Window | HEAD `afd25837` | `a3c2224a` | `436e44b0` |
| --- | ---: | ---: | ---: |
| 1 | 247.1 | 255.6 | - |
| 2 | - | - | 374.9 |
| 3 | 291.4 | 279.5 | - |
| 4 | 265.3 | - | 260.9 |

HEAD wins three of the four pairings by 1.7 to 4.3 percent; window 1 goes to
`a3c2224a` by 3.4 percent. That is the size of the run-to-run noise here.

## Answer

None of the four commits changes prompt processing for the option 21 server. The
highest single number belongs to `436e44b0` (391.3 tok/s median of three, 385.7
tok/s single run) and the highest mean is also `436e44b0` at 306.5 tok/s, but both
come from launches that ran while the machine was cooler, not from its code: its
engine differs from HEAD only in Inkling kernels, `main.mm` and `gguf_float.metal`,
none of which the Q2_0 prefill path touches. In head to head windows it is
indistinguishable from HEAD, 268.2 against 264.9 and 253.5 against 265.7.

The only real difference between the commits is on the decode side, where HEAD
carries the expert read-ahead budget: decode averaged 24.78 tok/s on HEAD against
24.35 and 24.28 on the older builds. Keep HEAD.
