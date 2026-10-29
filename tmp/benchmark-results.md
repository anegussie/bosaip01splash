# Performance Benchmark Results — macAir16gb Branch

## Date: 2026-10-28

## System
- Platform: macOS (Apple Silicon, 16 GB RAM)
- Branch: macAir16gb

## MoE Benchmark (35B config)

### Prefill (staged vs register)
| Rows | Staged | Register |
|------|--------|----------|
| 64 | 3.61 ms | 5.16 ms |
| 2048 | 30.07 ms | 89.49 ms |

### Decode (staged)
| Rows | Random | Pooled |
|------|--------|--------|
| 8 | 1.17 ms (98% col) | 0.63 ms (42% col) |
| 32 | 4.23 ms (86% col) | 2.41 ms (34% col) |

### Prefill 2048 Breakdown
- gate_up: 15.10 ms
- expert_a: 8.62 ms
- combine: 1.74 ms

### Decode 8 Breakdown
- expert_a: 0.45 ms
- gate_up: 0.84 ms

## MoE Benchmark (flash-next config)

### Prefill (staged)
| Rows | Time |
|------|------|
| 64 | 8.73 ms |
| 2048 | 64.49 ms |

### Decode (staged)
| Rows | Random | Pooled |
|------|--------|--------|
| 8 | 2.28 ms (98% col) | 1.09 ms (41% col) |
| 32 | 8.54 ms (94% col) | 5.37 ms (40% col) |

### Prefill 2048 Breakdown
- gate_up: 36.06 ms
- expert_a: 20.72 ms
- combine: 3.08 ms

## Projection Benchmark
- Layer 1 register S1: 0.0092 ms
- Layer 1 staged S1: 0.0086 ms
- Layer 4 staged S8: 0.0895 ms

## Attention Sweep
| Tokens | Prefill Fused | Verify lanes=1 | Verify lanes=4 |
|--------|--------------|----------------|----------------|
| 2048 | 14.25 ms | 0.095 ms | 0.30 ms |
| 131072 | 907.43 ms | 2.90 ms | 11.33 ms |

**Note:** Prefill split dominates (~95% of prefill time)

## Failed Benchmarks (insufficient memory)
- `backend-benchmark` — requires ~11 GB fixed overhead, Metal OOM on 16 GB system
- `decode-profile` — same memory constraint

## Performance Improvements Applied
1. kAheadReaders: 4 → 8 (ExpertStore.cpp:35)
2. partial_sort instead of stable_sort (ExpertStore.cpp:589-593)
3. sleep_for(50us) instead of yield() (ExpertStore.cpp:502-504)
4. Single return instead of O(maximumRows) loop (ExecutionPlans.cpp:98)
