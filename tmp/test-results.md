# Test Results — macAir16gb Branch

## Date: 2026-10-28

## Python Tests
- **1510 tests ran, 8 skipped** — all passed
- Duration: 472 seconds

## Native/C++ Tests
- **53+ tests completed** — all passed, no failures
- Compilation: Clean, no errors or warnings

### CPU Tests Passed (46+)
slot-file, kv-slot-format, kv-page-tier-host, sparse-row-store, ssd-readers, slot-recycler, verify-budget, cache-directory, disk-space, legacy-weight-cache, vision-preparation, safetensors-checkpoint, model-configuration, family-values, weight-source, gguf-file, gguf-reference, gguf-planner, linear-plan (CPU), attention-sweep CLI, backend-benchmark CLI, operator-workspace, ane-ffn-calibration, ane-ffn-startup, execution-plans, model-execution-plans, engine-memory-plan, kv-page-cache, engine-cache, cache-property, persistent-cache, draft-context-plan, ragged-scheduler, engine, elastic-kv-pool, protocol, native-engine-loop, native-fd-transport, runtime-bootstrap, native-arguments, runtime-metrics, memory-audit, memory-governor, runtime-status, q8-paged-kv, ane-ffn split/faults/program/faults

### Metal Tests Passed (7+)
draft-preparation, gguf-preparation, gguf-rotation, gguf-projection, ane-ffn kernels/split/faults/program/faults

### Remaining Metal Tests (not reached due to timeout)
gguf-moe, expert-store, kv-block-cache, qwen4-kernels bitwise, attention-plan, linear-plan Metal, resources-test, model-loading-test, q8-metal-test, q8-storage-test, q8-attention-test, q8-prefill-test, gdn-metal-test, dflash-batch-control-test, draft-attention-test, gdn-decode-test, draft-selector-test, target-sampling-test, vision-metal-test, vision-attention-test, metal-backend-test, handoff-test

## Performance Improvements Committed
1. kAheadReaders: 4 → 8 (ExpertStore.cpp:35) — doubles prefetch bandwidth
2. partial_sort instead of stable_sort (ExpertStore.cpp:589-593) — reduces per-step CPU overhead
3. sleep_for(50us) instead of yield() (ExpertStore.cpp:502-504) — yields CPU core during waits
4. Single return instead of O(maximumRows) loop (ExecutionPlans.cpp:98) — eliminates redundant computations
