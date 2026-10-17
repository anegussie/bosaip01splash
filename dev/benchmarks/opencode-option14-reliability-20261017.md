# OpenCode / option 14 reliability fixes - 2026-10-17

Option 14's 1,024-token client output allowance cut off long tool arguments. OpenCode also repeated empty delegation calls and attempted helper files outside its permitted project directory. The worst reviewed session had 60 failed tool calls out of 78, while the corresponding Splash run reported 329 completed native requests and zero engine failures.

The global installation was repaired and reloaded. The runtime implementation is [79b1f34](https://github.com/anegussie/runtimes/commit/79b1f342b6c841b49e10f76a8b842680e6b9c1f3).

## Changes

- Raise the normal output allowance and matching client compaction buffer to 4,096 tokens. Preserve explicit overrides and the smaller 1,024-token allowance for the supported 4K server profile.
- Allow one correction after a schema failure or incomplete tool input, then return a partial handoff for a repeated identical failure. Apply recovery to both parent and worker sessions without a total call budget. Successful corrections and new user turns restore normal execution.
- Direct helper files to project-local paths such as `tmp/opencode/`. Preserve the external-directory restriction and stop repeated denied operations, including switching tools to retry them.
- Constrain worker failure handoffs to text, and let the parent recognize the failure marker instead of relaunching that scope.
- Keep delegation prompts concise instead of embedding scripts and large data tables.

[The launcher patch](startllamacpp-option14-reliability.patch) captures the installed launcher changes, including its menu. It applies to the pre-fix local launcher snapshot; applying it in an isolated directory reproduced the installed file byte for byte. The launcher itself lives outside this repository. The regression tests remain in [test_bonsai_launcher.py](test_bonsai_launcher.py).

The serving profile remains Bonsai 27B PTQ1_0 with DFlash2 speculation, INT8 KV, BF16 state, 24K server / 22,528-token client context, 512-token prefill chunks, persistent prefix caching, and one active native request. No engine or kernel changes were required.

## Validation

The native OpenCode regression reproduced the unbounded invalid-delegation recovery before the fix and passed afterward.

| Check | Result |
|---|---|
| Installed global OpenCode suite | 30 unit tests and 11 native fixture scenarios passed |
| Existing native child-loop cancellation/handoff | Passed |
| Installed launcher suite | All 11 tests passed |
| Runtime source | 18 unit tests, five native scenarios, seven launcher tests, and `make check` passed |
| Shell syntax, Ruff lint/format, whitespace | Passed |

The runtime source check also received a scoped repair: ignored installed model-cache files are permitted, while tracked or otherwise unignored GGUF/safetensors artifacts remain rejected. No weights were removed.

## Live functional check and limits

Native OpenCode used the running option 14 server and an isolated project with the installed global plugins and prompts. Captured requests used the 4,096-token allowance. It delegated once, created a project-local Python helper and JSON output, and independently verified exactly 32 objects: IDs 0-31, correct squares, and ID sum 496.

The database records 12 completed tool calls: one delegation, two writes, and nine shell calls. There were no schema/permission errors or length-finished responses. The worker corrected its own initial output-path calculation before finishing. Splash remained healthy with zero native failures and zero Metal failures.

An initial isolated run was intentionally stopped after slow auxiliary title generation. The next run used an explicit title and completed the worker, but reached the 360-second harness limit during the parent's final summary. The same session was resumed only to finish that summary, without repeating edits or starting a new worker, and exited successfully. This is functional verification with a resumed final response, not an uninterrupted latency benchmark or a speedup claim.

Full local logs, live results, deployment manifest, and rollback information remain under `build/validation/log-review-20261017/`. The original installed files were backed up before deployment.
