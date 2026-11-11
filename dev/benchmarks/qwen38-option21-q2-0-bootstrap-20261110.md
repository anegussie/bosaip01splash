# Option 21 (Flash-Next Q2_0 + BF16 DFlash2): why it never booted, and what the launcher now runs

Two independent faults kept `Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` from ever reaching
`Ready` on this 16 GiB Mac. Both are fixed. The launcher revision that carries the
fix is `startllamacpp.sh`, byte-identical to `~/startllamacpp.sh`
(sha256 `11201d37caff46110599f1dedd42e5e4b1e7e016f990881b5645de44731b5e32`), and
`dev/benchmarks/test_bonsai_launcher.py` passes 51 tests against both copies.

## What the failing launch said

`~/.local/state/llama-server/qwen3.8-flash-next-q2-0-dflash2-bf16-splash-20261110-141211.log`:

```text
Launcher: ... server_context=131072 ... prefill_chunk=2048 cache_disk=16G cache_mode=persistent
Updating ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0: the GGUF metadata adapter changed.
Warning: keeping the installed ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF@ed59f92082b1;
cannot update it (the GGUF metadata adapter changed): the split GGUF in Q2_0/ is incomplete:
Q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00002-of-00002.gguf
...
error: runtime bootstrap failed [maximum_prefill]: maximum_prefill threw: Metal command 1095
failed: Caused GPU Timeout Error (00000002:kIOGPUCommandBufferCallbackErrorTimeout)
(host steps: 156 of 239 ran; the longest worked 5.157 s, step 156)
```

The memory plan the engine printed for that run (10.8G cap, 2,048-token chunks):

```text
hard budget:      11059.20 MiB
target weights:    6158.64 MiB
draft weights:      499.19 MiB
shared prefill:    1608.75 MiB
fixed runtime:     9333.23 MiB
elastic state/KV:  1725.97 MiB
routed experts:    2104 slots for 24576 experts (8%) in 2773 MiB, a store of 3224 MiB in 2 chunks
```

Every option-21 run in `~/.local/state/llama-server` (2026-11-07 x3, 2026-11-10 x2) ends
either at "not enough free memory to start" or at this timeout. None prints `Ready`.

## Fault 1: the installed assembly pointed at the external drive

The option-21 assembly (`install/models/.selections/be19a0828c...` ->
`.resolved/39661db5cf...`) was built on 2026-11-07 while `/Volumes/Untitled` was mounted, and
its two target GGUF symlinks named that volume. `69820c02ec7d0b45ef2ebb19d6620299db749fe2aded7f39f93c6b88b199b720`
(part 00001, 37,623,740,192 bytes) lived only there, so with the drive unmounted the assembly was
dangling, and the internal HF cache held only part 00002 of the split - which is what the engine's
warning reports, since `install/upstream.py:split_order` names the parts it *found* when a split is
incomplete (`Q2_0 is incomplete: ...00002-of-00002.gguf` means part 00001 was not there).

Fix, all on the internal volume:

1. `69820c02...` (37.6 GB) copied into
   `~/.cache/huggingface/hub/models--ISTA-DASLab--Qwen3.8-Flash-Next-GSQ-RCO-GGUF/blobs/` and
   verified against its blob name: sha256 matches.
2. Snapshot `ed59f92082b1e93c0e96d60a8b11aab089b52f09/Q2_0/` re-linked for both parts
   (part 00002, `316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113`, 28,800,138,432
   bytes, was already local and is shared with the IQ3_XXS variant).
3. Abandoned `~/Downloads/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf.crdownload`
   (7,606,912,754 bytes, a partial copy of the same part) deleted; volume free went 34 GiB -> 40 GiB.
4. The supported installer re-resolved the model:
   `.venv/bin/python install/models.py --model "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0"
   --draft-model ~/.cache/huggingface/hub/models--incoai--Qwen3.8-Flash-Next-DFlash2/snapshots/a22a1744e85c17364dcc54a6a420af7135d4c7f6
   --language-only prepare`, which reported `Reinstalling ...: [Errno 2] No such file or directory:
   .../.selections/be19a0828c.../target/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf`,
   fetched 2 files from the local cache in under a second (no re-download), installed a new assembly
   `.resolved/6199dfd71f9d942f55513ce049ad19b25dfc8a946887ef043b877807626f6bbf` whose every file
   resolves on `/`, and garbage-collected the external-path assembly.
5. `verify --full` over all 66 GB plus the draft: `Splash model
   ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0 preflight passed (full).`

## Fault 2: option 21 inherited option 20's 16 GiB preset, which the Q2_0 target cannot warm up

`splash_flash_next_host_defaults()` raises the Flash-Next profile on a 16 GiB host to a 10.8G cap
with 2,048-token prefill chunks. That pair is measured on option 20's IQ3_XXS target
(`qwen38-option20-prompt-processing-20261109.md`), and option 21 shares the same variables, so it
inherited them without ever being measured. With the Q2_0 target plus the local BF16 draft the plan
leaves only 1,726 MiB of elastic room against an 11,059 MiB budget, and the `maximum_prefill`
warmup of a 2,048-token chunk ran 156 of 239 host steps before one step took 5.157 s. The engine's
Metal event wait is a fixed 5,000 ms, so the command buffer is reported as a GPU timeout and
bootstrap dies; the launcher's retry only covers "not enough free memory to start", so it exits.

Option 21 then held the stock Flash-Next pair instead: a 10G cap with 1,024-token chunks.
Halving the chunk halves the work in any one host step (that 5.157 s step is roughly 2.6 s of
work) and returns about 800 MiB of the prefill scratch to the expert store, which cuts the SSD
expert reads that fill those steps. `splash_flash_next_q2_profile()` computed the pair.

**That decision has since been reversed by measurement.** The 5.157 s step was one cold boot
with the expert store at its floor, not a property of the chunk: measured on the same Mac, a
2,048-token chunk warms up fine and is 40-57% faster on long prompts (411.8 against 282.3
tok/s at 8,204 prompt tokens), with decode unchanged. Option 21 now runs option 20's pair, and
the launch loop retries a `GPU Timeout` bootstrap once with 10G / 1,024 for hosts that cannot
warm the larger chunk. See
[qwen38-option21-chunk-2048-20261110.md](qwen38-option21-chunk-2048-20261110.md).
Settings given explicitly always win: `SPLASH_FLASH_NEXT_MAX_MEMORY` and
`SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS` still reach the engine for either option, so raising
the pair for an experiment is one command away. What option 21 runs shows up in the log:

```text
Flash-Next: text only; expert and PLE streaming within a 10.8G Metal cap; reasoning low; download cache /Users/mymac/.cache/huggingface/hub.
Option 21 profile: 10.8G Metal cap with 2048-token prefill chunks, the pair option 20 uses on a
16 GiB Mac; ... If the warmup trips the engine's 5 s Metal event window, the launcher retries
with 10G and 1,024-token chunks.
```

## Also fixed: shutdown noise in every run log

- `wait "$splash_logger_pid"` cannot wait on a process substitution in bash 3.2 (it is not a job),
  so each attempt ended with `wait: pid N is not a child of this shell` and drained nothing.
  `splash_drain_run_log()` now polls the writer for up to 2 s after `exec 3>&-`, which keeps the
  engine's last lines ahead of the launcher's own without hanging on a grandchild that still holds
  the log fd.
- `splash_stop_monitor()` used to `pkill -P` the outstanding `sleep` of the pressure watchdog and
  the monitor. bash then reports the reaped child, and `Terminated: 15 sleep ...` lines landed in
  the run log on every startup failure, retry, and Ctrl-C. The watchdog now sleeps as its own job
  and traps TERM (`splash_watchdog_wait`), and the stop path signals only the loop's shell.

## Tests

`dev/benchmarks/test_bonsai_launcher.py`, 51 tests, all pass against `startllamacpp.sh` and
`~/startllamacpp.sh`:

- `test_option21_shares_the_raised_pair_option_20_uses` - both options get 10.8G / 2,048 on a
  16 GiB host, the banner says so, and `--list` shows each option's own pair.
- `test_option21_explicit_raised_pair_still_reaches_the_engine`,
  `test_option21_explicit_cap_outside_the_stock_set_keeps_the_chunk` - overrides are honored, and
  a cap outside the preset's set (12G) does not buy the bigger chunk.
- `test_option21_falls_back_to_the_stock_chunk_after_a_warmup_timeout` - a mock server that prints
  the `GPU Timeout` bootstrap failure is retried once at 10G / 1,024, with the draft attached.
- `test_option21_streamed_override_note_names_the_pair_it_holds` - the note that advises 10.8G /
  2,048 appears for option 21 as well as option 20.
- `test_option21_uses_the_q2_model_the_local_draft_and_its_own_cache` - expectations moved from
  10G / 1,024 back to 10.8G / 2,048.
- `test_failed_startup_drains_the_log_without_a_bash_job_error` and the extra assertions in
  `test_term_reaches_server_and_drains_logs` - no `not a child of this shell`, no `Terminated`.

## What is still open

The chunk raise is a marginal call: 2,048 tokens is about 4.6-5.0 s of GPU work per host step,
and Metal's event wait is 5,000 ms, so a host that cannot keep the expert store resident will
cross it. The launcher's fallback covers that, but it fires only once per launch. Watch
`maximum_prefill` in
`~/.local/state/llama-server/qwen3.8-flash-next-q2-0-dflash2-bf16-splash-latest.log` if a
launch does not reach `Ready`. Prompts under 1,024 tokens are the other open case: at 524
tokens the 2,048 chunk measured 123.1 tok/s against 147.3 with 1,024.

Rollback: `git checkout -- startllamacpp.sh dev/benchmarks/test_bonsai_launcher.py` then
`cp startllamacpp.sh /Users/mymac/startllamacpp.sh`. The model install itself (local blobs, the
rebuilt assembly) does not depend on the launcher revision.
