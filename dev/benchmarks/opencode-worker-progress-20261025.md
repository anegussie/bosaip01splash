# OpenCode completed-slice and worker continuity fix

Installed 2026-10-25 into global OpenCode and its runtime mirror. No model, context, memory, sampling, cache, or permission configuration was changed. No inference server or user client was restarted or cancelled. Start a new OpenCode session to load the changed plugins; existing sessions keep their loaded code.

## Behavior

The worker slice policy now records successful and partial worker handoffs in the existing parent-session progress ledger. Exact matching uses structured OBJECTIVE, absolute file TARGET (including section/range), and DONE WHEN, bound to the actual parent user request and the file's stat revision. Only explicit successful STATUS: DONE read-only reviews are eligible for reuse. A repeated completed assignment is converted to a short child handoff with no advertised source tools; its findings are identified as reused evidence rather than new verification. The hook API does not short-circuit delegation, so this still costs one child completion.

Different objectives, review lenses, named sections, changed source revisions, actual new user requests, and authorized edits/checks remain executable. Approval/continuation preserves prior progress. Pasted or inline WORKER_SLICE_ID markers cannot bypass runtime provenance. Completion is accepted only from the actual completed child whose parentID matches the delegating session. Inventory-only output never completes the original broad review.

Fresh followups receive prior findings and recorded coverage, including partial handoffs and changed-file edit handoffs. Coverage is historical metadata, not retained source or proof of review completion. Necessary targeted rereads remain allowed. The existing first-compaction checkpoint policy remains in place. The 4-8 KiB source guidance stays soft; no hard source or tool-call cap was introduced.

Stored handoffs are limited to 4096 characters and marked when excerpted, with the complete result retained in its worker session. Excerpted handoffs are never eligible for automatic completed-scope reuse. Followup/context excerpts are bounded and explicitly labelled. Ledger write failure fails open and records a diagnostic rather than discarding a successful worker result.

## Validation

The same final native mock-provider fixture failed against the baseline because the repeated review retained source tools, was not cached, and the subsequent implementation lost confirmed findings. The candidate passed unchanged assertions: the duplicate child had no source tools, retained prior findings, and a later distinct worker performed an actual file write and source reread. Post-install native validation also passed.

- Focused guard/compaction/progress unit set: 23 passed.
- Latest installed worker-slice unit set: 9 passed, including new-user identity, quoted inline fake markers, revision invalidation, different sections/lenses/actions, explicit re-review, partial/error handoffs, persistence, checkpoint behavior, and worker tool availability.
- Native inventory lifecycle: passed.
- Native first-compaction checkpoint and sequential continuation: passed.
- Native completed-scope / real edit-and-reread fixture: passed before and after install.
- Six target hashes verified after deployment; backups and concurrent-change preconditions retained.

Native fixtures use isolated temporary projects/databases and scripted localhost providers. No real model performance matrix was run. This establishes source-work prevention and continuity behavior, not a measured token-rate or wall-time improvement. A duplicate handoff still incurs one child completion, and conservatively exact matching will not catch paraphrased/ambiguous tasks or non-absolute TARGET descriptions. Actual live-session performance benefit remains unmeasured.

## Installed files and evidence

Global: `/Users/mymac/.config/opencode/plugins/worker-slice-policy.ts` and `plugins/lib/progress-ledger.ts`.

Runtime mirror: `/Users/mymac/runtime/opencode/plugins/worker-slice-policy.ts`, `plugins/lib/progress-ledger.ts`, `tests/worker-slice-policy.test.ts`, and `tests/worker-slice-e2e.test.mjs`.

Artifacts: `/Users/mymac/splash/splash/build/validation/worker-progress-20261025/`. Native failure/pass results are saved under `native-evidence/`; `deploy-manifest.json` preserves original/candidate hashes and target paths; `deployment-before/` contains original files. No commit or push was performed.
