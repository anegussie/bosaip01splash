# OpenCode IQ3 worker output budget, 2026-10-25

Installed in global OpenCode and its runtime mirror. This change makes 4,096 output tokens available to the two editing-capable worker roles, while retaining smaller parent and auxiliary limits. No inference throughput or task-time improvement was measured.

| Exact IQ3 request role/path | Maximum output tokens |
| --- | ---: |
| `general_worker`, `context_worker`, native primary request after trusted context | 4,096 |
| Router, General, LongAnalysis, unknown role, or request-only replay | 2,048 |
| IQ3 title | 64 |
| IQ3 built-in auxiliary session requests | 2,048 |
| Stateless concise-compaction checkpoint | 2,048 using `bounded-compaction` variant |

The ceiling is the minimum of the role limit and any valid native/request `max_tokens` or `max_completion_tokens` value. The plugin never raises a smaller request. Worker identity comes from native session context and the exact local IQ3 model, with a bounded 128-entry cache and a single-use grant for the next primary request. Unknown, changed, or request-only reused sessions fall back to 2,048. Thinking stays disabled. Both configured workers have editing tools; there is no separate configured read-only worker role.

The IQ3 model declaration allows 4,096. Global already declared 4,096 before this task, but its final wire plugin still capped every role at 2,048. Runtime declaration increased from 2,048 to 4,096. Client context remains 22,528 and server context remains 24,576. The global compaction buffer changed from 1,536 to 4,096, while runtime changed from 2,048 to 4,096. Native 2.1.3 compacts at client context minus this buffer, approximately 18,432 tokens, so a 4,096-token response fits within the client budget with 2,048 additional tokens of server margin. This is a shared compaction setting: parents also compact earlier. Native dynamic output reductions remain effective because the wire cap uses the minimum.

Native `ctx.generate.text` bypasses session HTTP hooks and does not accept generation limits. A same-model `bounded-compaction` variant supplies `max_tokens: 2048`, `reasoning_effort: none`, and `chat_template_kwargs.enable_thinking: false` for stateless checkpoints. The model ID, artifact, normal worker model reference, sampling, tools, permissions, memory, cache, and speculation settings remain unchanged. Global small_model remains its existing Qwen3.5 9B setting; runtime preserves its existing small_model. Existing differences between global and runtime prompts, continuation instructions, and compaction binding-text policy were preserved rather than synchronized wholesale.

Validation:

- Initial native regression reproduced worker 2,048 versus required 4,096, then passed after the fix.
- Final runtime candidate: 10/10 focused unit tests and 9/9 real OpenCode native protocol cases using a deterministic localhost provider. These test the actual OpenCode binary rather than model inference.
- Native Router-to-worker repair deliberately emitted truncated tool JSON, recovered to a bounded write, then read and verified the file. Parent, worker, title, same IQ3 model identity, and thinking limits were checked on actual upstream payloads.
- Native smaller explicit output request reached the provider at 512 tokens. Unit tests also cover minimum alternate-token fields, unknown roles, role/model changes, single-use grants, and cache eviction.
- Native measured prompts of 19,000 and 20,867 tokens, each with a 14,000-token cached prefix, caused one compaction before the next 4,096-token worker request. An 18,000-token prompt with 14,000 cached tokens did not compact, confirming that cached tokens were not counted twice. Actual checkpoint payloads used the same IQ3 model ID, 2,048 output tokens, and disabled thinking.
- Preserved global candidate: 8/10 unit tests passed, with two preexisting binding-instruction preservation failures. The unchanged global baseline independently produced the exact same two failures at `event.result.summary.includes(assignment)` in the tests for complete assignments and failed checkpoint generation. Its existing clipping behavior was preserved. All six wire tests and the new variant test passed; those seven tests passed again from the installed global paths.
- An attempted full global native run was interrupted during an approval/tool wait after 180.2 seconds, with no result or session returned. It is not counted as a test pass. The final runtime native cases and scoped installed global tests are the completed validation.
- Guarded installation verified all 16 installed hashes across both targets and preserved unrelated target differences. Production policy changes affect four files per target: `opencode.json`, `AGENTS.md`, `plugins/zzzzz-bonsai-no-thinking.ts`, and `plugins/concise-compaction.ts`. Package/test updates add regression coverage.

No user OpenCode client or model server was restarted or cancelled. Start a new OpenCode session to load the new plugin and instructions. No commit or push was performed.

Artifacts: `build/validation/worker-output-budget-20261025/validation-summary.json`, `native-results-runtime.json`, `deployment.json`, `global-final.diff`, `runtime-final.diff`, and `installation-backup/`. The installer checks each prior hash before writing, creates backups, uses atomic replacements, and verifies installed hashes.
