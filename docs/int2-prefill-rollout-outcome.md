# INT2 prefill rollout outcome (2026-11-23 to 2026-11-24)

The staged Q2_0 INT2 projection path was rolled back on the option 21 production
server. The rollback is live, and matched benchmarks show the INT2 path was
never used, so it had no measurable effect on prompt processing.

## What was rolled back

- `runtime/model/Qwen4Exp.cpp`, `Qwen4Exp.hpp`, `Qwen4ExpTarget.cpp` reverted to
  the pre-INT2 state with `git apply -R build/option21-prefill-rollback/int2-working-tree.patch`.
- `runtime/ops/GgufInt2.hpp` and `runtime/metal/kernels/runtime/GgufInt2Prefill.h`
  removed from the tree. Copies kept in
  `build/option21-prefill-rollback/int2-source/`.
- The committed decode expert read-ahead budget (`afd25837`) was kept.
- Production binary: `build/splash`, build id
  `src-3bfb02d0ff9f057dac8bb68b9f261d84512e49895174f6807ececad017813ddb`.
  The previous INT2 binary is archived at
  `build/option21-prefill-rollback/deployed-1795485701685413000/previous-splash`
  plus its `splash.metallib` and `host-step.metallib` in
  `build/option21-prefill-rollback/int2-arm/`.

## Matched prefill test

`build/option21-prefill-rollback/paired-ab.py` runs both binaries on port 1236 in
alternating order, each arm gated to four consecutive idle polls at nominal
thermals, same 8,129-token prompt, separate prefix cache per arm, 128 output
tokens.

| Arm | Build | Cold prefill tok/s | TTFT s | Decode tok/s | Thermal |
| --- | --- | ---: | ---: | ---: | --- |
| INT2 | src-6591f0cf | 379.1 | 21.45 | 26.1 | nominal to nominal |
| Rollback | src-3bfb02d0 | 384.8 | 21.13 | 26.1 | nominal to nominal |
| INT2 | src-6591f0cf | 385.8 | 21.07 | 26.1 | nominal to nominal |
| Rollback | src-3bfb02d0 | 384.7 | 21.13 | 26.0 | nominal to nominal |

Mean: INT2 382.4 tok/s, rollback 384.7 tok/s, a 0.6 percent difference. INT2
dispatch counters stayed at zero in every INT2 arm, so the INT2 path never
engaged for this workload. The 376 vs 391 tok/s gap from the earlier run
`build/option21-prefill-rollback/cooled-1795484530365226000` was thermal drift,
not the projection change.

## Where the latency actually comes from

Cached turns report throughput for the fresh suffix only, and each request pays a
fixed prefill cost before that suffix. Live traffic on 2026-11-24:

| Prompt tokens | Cached | Fresh tokens | Prefill s | Reported tok/s |
| ---: | ---: | ---: | ---: | ---: |
| 51,027 | 50,688 | 339 | 4.18 | 81.2 |
| 52,179 | 51,008 | 1,171 | 6.42 | 182.5 |
| 53,426 | 52,160 | 1,266 | 6.17 | 205.2 |
| 54,686 | 53,408 | 1,278 | 6.26 | 204.3 |

Around 3 seconds is fixed per request. Throughput on the fresh suffix matches the
cold numbers. Reducing fresh token volume per tool turn is the lever, not the
projection dtype.

## Pi read window extension

`~/.pi/agent/extensions/option21-read-window.ts` bounds oversized read previews
and archives the complete result to a file the model can reopen. Replaying the
two oversized read pairs from the failing session cut visible tool-result tokens
by 45.5 and 46.8 percent, with byte-identical archived output. A mock provider
wire test (`build/option21-prefill-rollback/pi-wire-smoke.py`) passed: 15,587 B
full, 3,044 B sent.

## Does the INT2 path help when it is actually enabled

Production never enabled it, so the paired test above compares staged Q2_0 with
staged Q2_0. `SPLASH_METAL_INT2=1` is required, and the 8-core M5 defaults to
staged. The archived INT2 serving run at `build/int2-prepacked/serving-1795477711933690000` forced it on and recorded dispatches (4 per 8K request, 16 per 32K request):

| Arm | Mode | Cold prefill tok/s | Cold TTFT s | Decode tok/s | Dispatches | Thermal |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A1 | staged | 412.1 | 19.73 | 26.38 | 0 | nominal to nominal |
| B1 | INT2 | 381.9 | 21.29 | 26.03 | 4 | nominal to nominal |
| B2 | INT2 | 346.0 | 23.49 | 25.74 | 4 | fair to fair |
| A2 | staged | 290.5 | 27.98 | 25.49 | 0 | fair to fair |

The only thermal-matched pair, A1 against B1, is 7.3 percent slower with INT2.
Run order and drift dominate the rest. The kernel benchmark agrees: at the PLE
key shape of 2,048 rows, staged Q2_0 takes 9.50 ms and prepacked INT2 takes 53.30
ms, plus a 0.17 ms pack. Four chunks per 8K request adds about 175 ms, roughly
0.8 percent of a 21 second prefill, so the expected effect is a small slowdown.

INT2 is functionally correct, 512 of 512 exact matches against the CPU GGUF
reference in the probe, but it is not faster on this GPU and this checkpoint. To
make it worth pursuing, profile the matmul, packing, and scale correction with a
Metal GPU trace, amortize the pack across chunks, and dispatch only where the
packed kernel beats staged on the real shape.

## Health during the tests

Zero failed requests, zero KV spills, zero swapouts, zero capacity denials. Peak
live memory 9,474 MiB against an 11,596 MiB cap.

## Which prefill kernel is fastest, measured (2026-11-24)

Two questions, answered at the kernel level and end to end.

`dev/benchmarks/gguf_projection_benchmark.mm` times one GGUF projection through
`ops::Linear` with the weights kept DRAM-cold by a ring of copies, 10 rounds,
medians, on the 8-core M5. For the PLE key shape, 10,240 outputs by 2,560
inputs, in Q2_0:

| Chunk rows | Tile the device policy picks | Median ms | GFLOP/s |
| ---: | --- | ---: | ---: |
| 128 | `prefill128` | 0.685 | 4.9 |
| 512 | `prefill128` | 2.670 | 9.7 |
| 1024 | `prefill128` | 5.338 | 9.8 |
| 2048 | `prefill128` | 10.661 | 10.1 |

That is 5.36 microseconds a row at 128 rows and 5.20 at 2,048: the bigger chunk
amortizes the weight reload, and 10.1 TFLOP/s is close to what this GPU does.
Q2_0 is not in the int8 prefill tile's format list (`runtime/metal/abi/QuantFormat.h`:
`quant_prefill_int8_format` takes only af4g64 and af5g64), so the staged 128-row
prefill tile is the only prefill tile this checkpoint can run, and it is the
fastest of the tiles measured. The engine's prefill budget is 2,048 rows
(`runtime/metal/abi/ExecutionGeometry.h`, `SPLASH_PREFILL_TOKEN_BUDGET 2048u`),
exactly sixteen of those tiles.

End to end, `build/option21-prefill-rollback/kernel-ab.py` runs the staged build
and the archived INT2 build alternately six times on the same prompt, INT2
forced on with `SPLASH_METAL_INT2=1` in its arm:

| Arm | Median cold prefill tok/s | Mean TTFT s | Median decode tok/s | INT2 dispatches |
| --- | ---: | ---: | ---: | ---: |
| staged | 265.9 | 30.42 | 24.2 | 0 |
| INT2 forced | 261.1 | 31.06 | 23.9 | 6 per request |

Staged wins every prefill comparison but one (264.9 against 263.1). INT2 engaged
six times per request and made prompt processing 1.8 percent slower. The kernel
benchmark's 9.50 ms against 53.30 ms at 2,048 rows is the reason: the packed path
is correct but its matmul is far from the staged tile's rate.

## Configuration sweeps on the same build (2026-11-24)

Six alternating trials each, same 8,129-token cold prompt, 128 output tokens,
`build/option21-prefill-rollback/`:

| Knob | Values tried | Median prefill tok/s | Median TTFT s | Median decode tok/s |
| --- | --- | ---: | ---: | ---: |
| prefill chunk (`chunk-ab.py`) | 2048 | 278.2 | 29.22 | 24.9 |
| prefill chunk | 1024 | 221.0 | 36.79 | 28.8 |
| PLE row cache (`ple-ab.py`) | 64M | 270.0 | 30.10 | 24.7 |
| PLE row cache | 128M | 271.2 | 29.98 | 24.4 |
| PLE row cache | 256M | 268.5 | 30.28 | 23.1 |
| expert store (`expert-ab.py`) | auto | 274.2 | 29.65 | 23.6 |
| expert store | 3072M | 254.4 | 31.95 | 24.7 |
| expert store | 4096M | 270.2 | 30.08 | 24.1 |

The 2,048-token chunk is the only setting that changes anything: 26 percent more
prefill throughput and 20 percent less time to the first token, at the cost of 14
percent of decode speed. Over a request the larger chunk still wins, 34.3 s of
wall time against 41.2 s. The PLE row cache and the expert store make no
measurable difference; the memory plan gives the expert arena 2.30 GiB in every
arm, so an explicit `--expert-memory` above the floor is clamped, and a 2,048-row
prompt never fills the 438,834-row PLE cache, so a bigger cache changes nothing
for a single request.

## What this means for the launcher

`startllamacpp.sh` pins the pair these measurements support for option 21 on a
16 GiB Mac: the staged build at `build/splash`, a 10.8G Metal cap and 2,048-token
prefill chunks, with the 1,024-token chunk kept only as the bootstrap fallback.
There is no INT2 switch to set: the packed kernel is out of the tree, and the
staged tile is the fastest path measured.
