# OpenCode subagent task sizing guidance - 2026-10-25

Installed a compact self-contained assignment template in global instructions. Router and General explicitly reference it; LongAnalysis already uses Router. The template carries objective, exact target, confirmed evidence/completed checks, completion verification, and exclusions. It explains that fresh workers lack parent conversation and serialized tool-call JSON shares the parent response budget.

The existing under-500-token handoff and 4-8 KB source guidance remain soft planning targets. No hard cap, token estimator, truncation, plugin change, or model/context/sampling/tool change was introduced. Existing sequential continuation and first-compaction checkpoint behavior remain intact. Runtime mirror received only the same targeted edits; unrelated pre-existing differences and its path placeholder were preserved.

Validation: 7/7 existing slice-policy tests; native mock-provider delegation tests passed for Router, General, and LongAnalysis (parents expose only question/subagent, worker source remains outside parent); inventory and compaction checkpoint E2Es passed, including sequential fresh-worker continuation. A sandbox localhost listen EPERM in the inventory E2E was rerun through supported approval and passed. No local model inference or performance benchmark was run. This validates configuration and orchestration compatibility, not a measured speedup.

Deployment: guarded baseline hashes, per-file backups, installed content/hash verification, unchanged global/runtime opencode.json hashes. Artifacts and backups: `build/validation/subagent-task-sizing-20261025/`. Start a new OpenCode session to load the revised instructions. No service restart, commit, or push.
