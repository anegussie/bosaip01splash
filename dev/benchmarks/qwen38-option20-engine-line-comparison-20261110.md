# Qwen3.8 Flash-Next option 20: which engine line prompts faster

Measured on 2026-11-10 on the 16 GiB M5 that serves this model, with the two
engine lines compared inside one serving session, back to back, each with its
own empty 16 GiB prefix cache.

## The two candidates

| Line | Branch state | Native build identity |
| --- | --- | --- |
| **A, the line we run** | `option20-best-pp-20261106` (created 2026-11-10 at `0025f309`, "Record Qwen3.8 PP and TPS results", 2026-11-06 16:58; the tree of `3e2e1ebc`, the commit whose identity was written into the 2026-11-06 report) | `src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a` |
| **B, the line we did not run** | `splashmain` tip `2b52116b` ("Disable cycle-ahead prediction for shared-arena expert stores", 2026-11-07 21:18), built fresh in a scratch worktree | `src-81529c7c97580f531418c1c0ec9bf09bfd5997452ca96d8d0b8071fa40c86a6a` |

`3e2e1ebc`, `0025f309` and `c72fe592` hash to the same source identity `src-882891f8`,
the identity the live server reports. Between that identity and `2b52116b` 186 runtime
files change (16,607 insertions): the 1.6 GB memory rule, the elastic expert store,
34 prefill kernel selections, cycle-ahead expert reads and its later disable. That line
had never been built or measured until this run.

## Protocol (identical for both)

`--direct 20` stock profile: 131,072-token context, `--max-memory 10.8G` Metal cap,
`--prefill-chunk-tokens 2048`, `--max-cache-disk 16G`, expert memory `auto` (planned
2.09 GB store), `--ple-memory 64M`, persistent prefix cache on, one active native
request, bf16 state, int8 KV. Each line ran against its own empty cache directory.
Prefill ladder (2,048 / 4,096 / 8,192 tokens, one trial) then the pinned matrix (two
trials). Thermal state was `fair` for every probe in both runs.

For B the launcher was pointed at the scratch checkout's engine
(`SPLASH_BIN=/Users/mymac/splash/option20-tip-build/splash`), so A and B differ only
in the built line, and B's own status output confirmed `src-81529c7c`.

## Cold prefill, the prompt-processing number

| Prompt | A cold tok/s | A TTFT | B cold tok/s | B TTFT | A advantage |
| --- | --- | --- | --- | --- | --- |
| 2,048 | 215.66 | 9.552 s | 199.53 | 10.324 s | +8.1%, 0.772 s faster |
| 4,096 | 268.51 | 15.299 s | 242.10 | 16.968 s | +10.9%, 1.669 s faster |
| 8,192 | 324.27 | 25.299 s | 294.50 | 27.857 s | +10.1%, 2.558 s faster |

Warm reuse of the same prompt was the same on both lines: 1.087 / 1.111 / 1.100 s on A
against 1.126 / 1.167 / 1.100 s on B, with zero whole-page restores on both.

## Pinned matrix

| Run | 4K cold | 4K reuse TTFT | coding decode | draft accepted | spill pages / tokens | clean probes |
| --- | --- | --- | --- | --- | --- | --- |
| A, fresh cache dir, before B | 317.98 tok/s | 1.930 s | 11.23 tok/s, 6.257 tokens/cycle | 1061/1115 (95.2%) | 3 / 96 | 14/14 |
| B, fresh cache dir | 279.51 tok/s | 1.986 s | 11.05 tok/s, 6.275 | 1062/1131 (93.9%) | 0 / 0 | 14/14 |
| A, control after B, normal cache dir | 284.09 tok/s | 1.998 s | 11.20 tok/s, 6.447 | 1105/1167 (94.7%) | 3 / 96 | 14/14 |

A's own before/after pair spans 317.98 down to 284.09 tok/s, which is the drift band
for this machine across a busy day, so the single 4K pinned number is not decisive on
its own. The ladder is: at every prompt size, in the same session, A was 8-11% faster.
B never won a prompt size. Decode is the same on both (11.05-11.23 tok/s), which is
expected, decode was never the prompt side.

## Verdict

Run `option20-best-pp-20261106`. It is the fastest prompt-processing line measured on
this machine, and the only line with recorded prompt numbers: the 2026-11-06 report's
408.28 tok/s cold prefill and 1.536 s reuse belong to `src-882891f8`, the identity this
branch builds. `splashmain` stays available for the memory and safety work, but its
engine line is measurably slower at prompt processing, so a rebuild onto `2b52116b`
would be a regression, not an improvement. Any future prompt-side engine change should
be made on top of `src-882891f8` and measured against the ladder above.

## One trap worth writing down

The prefix cache quota is enforced across the whole cache root
(`~/Library/Caches/Splash`), not per cache directory. While the two scratch 16 GiB
instances were running, the engine evicted the serving instance's 16.0 GiB cache as
"the oldest cache nobody holds" and resumed with a fresh namespace. The scratch
directories were removed after the comparison, and the serving cache was rebuilding
(3.6 GiB within a few minutes of normal traffic). When A/B testing cache directories,
give the candidates smaller `--max-cache-disk` values, or move them outside the shared
root, so the live prefix cache is not the thing that gets evicted.

Index rows: `ab-a-restored-prefill`, `ab-b-tip-prefill`, `ab-a-restored-pinned`,
`ab-b-tip-pinned`, `ab-a-restored-stock-cache-pinned` under
`dev/benchmarks/option20-experiments/`.
