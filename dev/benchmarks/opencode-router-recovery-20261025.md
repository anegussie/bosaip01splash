# OpenCode router recovery, 2026-10-25

Implemented and installed four plugin changes into both `/Users/mymac/.config/opencode/plugins/` and `/Users/mymac/runtime/opencode/plugins/`. Seven existing regression test files were updated in the runtime mirror. Installation backed up prior contents, checked source preconditions, and verified all 15 installed hashes.

## Diagnosed failures

The periodic-table session `ses_e8b2a2678ffegylBDFcgcL71o8` performed 22 successful child delegations, 129 reads and 8 searches, without an edit or write call. Whole-file source-copy assignments bypassed a progress check that required numeric line ranges. Parent compaction could also reset that history.

The latest parent response reached its 2,048-token limit with 6,251 characters of incomplete delegation arguments. Recovery instructions were injected, but the worker policy incorrectly treated that pre-execution failure as a failed child and entered terminal handoff. The next response repeated action promises and ended normally without using a tool. The existing prose stream guard covered only children.

## Installed behavior

- `repeated-child-call-guard.ts`: also checks parent prose streams and returns an explicit `STATUS: PARTIAL` / `PARENT_LOOP_ABORTED` handoff when repetitive action promises trigger cancellation. Productive calls and protected source/code content remain covered by regression checks.
- `zz-parent-progress.ts`: tracks repeated whole-file copying, including the observed "organized by section" wording, and preserves parent read history across compaction. After the first blocked duplicate, corrective edit/check delegation remains available. Repeated refusal to leave the same source-copy scope ends with PARTIAL. Named sections, targeted evidence, changed source and authorized edits remain executable.
- `zzz-router-tool-recovery.ts`: after one incomplete parent delegation, restricts recovery to an actually offered delegation tool and requires a compact corrected call. A second incomplete attempt enters the existing terminal handoff.
- `worker-slice-policy.ts`: distinguishes pre-execution incomplete/schema/progress rejections from a failed child. Actual cancellations, resource failures and child loop aborts remain terminal.

Model selection, parent/worker output limits, memory, permissions and inference server settings were preserved. Existing configuration differences between global OpenCode and its runtime mirror were preserved.

## Verification

The failing native tests were run first with the actual installed OpenCode binary and isolated scripted providers. Baseline parent prose streamed all 90 chunks, repeated whole-file reading launched three readers, and truncated delegation left the target file unchanged. Candidate results:

- Parent prose cancelled after 12 chunks with an explicit partial result.
- Third duplicate whole-file reader blocked, including across one actual native compaction.
- A corrective worker after a duplicate-read rejection changed the file and verified exact readback.
- Truncated parent delegation recovered at the unchanged 2,048-token ceiling, then performed actual read/write/readback with quotes, backslashes and newlines preserved.
- A second incomplete delegation stopped with zero workers launched.
- Final runtime `npm test`: exit 0, 65 unit tests and 32 native case reports.
- Additional worker-slice policy unit tests: 9 passed.
- Global overlay focused unit set: 36 passed. Installed runtime focused set: 36 passed.
- Installed runtime `make check`: exit 0, including isolated installation/backup and source/config checks.

A separate isolated test used the already-running local `qwen3.6-35b-a3b-iq3-xxs-splash` model. It completed in 36.354 seconds with one successful delegation, two successful reads and one successful edit, zero tool errors, and exact final contents `beta\nkeep-this-line\n`. The test project was temporary; the periodic-table file was not modified. The local server passed readiness before this test.

## Evidence and remaining limits

Artifacts: `/Users/mymac/splash/splash/build/validation/router-recovery-20261025/` contains baseline/candidate/global snapshots, native evidence, full test logs, the reviewed patch, deployment plan/backups/result and `live-smoke-result.json`.

OpenCode's native idle `succeeded` value still describes turn completion. The fix makes loop failures visibly PARTIAL; it does not redefine that native database outcome or prove that every future model answer fulfills its task. Scripted providers validate the failure/recovery paths; the live model test validates a small successful edit workflow.

Restart OpenCode and begin a fresh session to load the installed plugins. No user client or inference server was stopped or restarted. No commit or push was performed.
