# Option 20 prefill matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-128-cold | 140 | 37.88 | 3.695 | 10.05 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-128-reuse | 140 | 10.82 | 1.108 | 6.58 | 3 | 2.333 | 128 | 5/7 (71.4%) | 0 | True | True |
| pre-1024-cold | 1036 | 142.75 | 7.257 | 9.75 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-1024-reuse | 1036 | 11.63 | 1.031 | 6.56 | 3 | 2.333 | 1024 | 5/7 (71.4%) | 0 | True | True |
| pre-4096-cold | 4108 | 191.72 | 21.427 | 6.06 | 3 | 2.333 | 0 | 5/8 (62.5%) | 0 | True | True |
| pre-4096-reuse | 4108 | 11.63 | 1.031 | 6.08 | 3 | 2.333 | 4096 | 5/8 (62.5%) | 0 | True | True |
| pre-8192-cold | 8204 | 196.5 | 41.75 | 6.59 | 3 | 2.333 | 0 | 4/7 (57.1%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.98 | 1.092 | 6.25 | 3 | 2.333 | 8192 | 5/8 (62.5%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 196.5 tok/s in 41751.041 ms (TTFT 41.75 s); reuse TTFT 1.092 s = 38.2x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 512
- 4096: cold prefill 191.72 tok/s in 21427.041 ms (TTFT 21.427 s); reuse TTFT 1.031 s = 20.8x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 348
- 1024: cold prefill 142.75 tok/s in 7257.305 ms (TTFT 7.257 s); reuse TTFT 1.031 s = 7.0x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 476
- 128: cold prefill 37.88 tok/s in 3695.489 ms (TTFT 3.695 s); reuse TTFT 1.108 s = 3.3x, cached 128, disk KV read-back 0 tokens, spill pages 0, kv pages free 508
draft acceptance 39/55 (70.9%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-128-cold | 140 | 37.88 | 3.695 | 10.05 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-128-reuse | 140 | 10.82 | 1.108 | 6.58 | 3 | 2.333 | 128 | 5/7 (71.4%) | 0 | True | True |
| pre-1024-cold | 1036 | 142.75 | 7.257 | 9.75 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-1024-reuse | 1036 | 11.63 | 1.031 | 6.56 | 3 | 2.333 | 1024 | 5/7 (71.4%) | 0 | True | True |
| pre-4096-cold | 4108 | 191.72 | 21.427 | 6.06 | 3 | 2.333 | 0 | 5/8 (62.5%) | 0 | True | True |
| pre-4096-reuse | 4108 | 11.63 | 1.031 | 6.08 | 3 | 2.333 | 4096 | 5/8 (62.5%) | 0 | True | True |
| pre-8192-cold | 8204 | 196.5 | 41.75 | 6.59 | 3 | 2.333 | 0 | 4/7 (57.1%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.98 | 1.092 | 6.25 | 3 | 2.333 | 8192 | 5/8 (62.5%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 196.5 tok/s in 41751.041 ms (TTFT 41.75 s); reuse TTFT 1.092 s = 38.2x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 512
- 4096: cold prefill 191.72 tok/s in 21427.041 ms (TTFT 21.427 s); reuse TTFT 1.031 s = 20.8x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 348
- 1024: cold prefill 142.75 tok/s in 7257.305 ms (TTFT 7.257 s); reuse TTFT 1.031 s = 7.0x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 476
- 128: cold prefill 37.88 tok/s in 3695.489 ms (TTFT 3.695 s); reuse TTFT 1.108 s = 3.3x, cached 128, disk KV read-back 0 tokens, spill pages 0, kv pages free 508
draft acceptance 39/55 (70.9%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
