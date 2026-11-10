# Option 20 prefill matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-2048-cold | 2060 | 215.66 | 9.551 | 6.32 | 3 | 2.333 | 0 | 5/6 (83.3%) | 0 | True | True |
| pre-2048-reuse | 2060 | 11.04 | 1.087 | 6.82 | 3 | 2.333 | 2048 | 5/6 (83.3%) | 0 | True | True |
| pre-4096-cold | 4108 | 268.51 | 15.298 | 5.9 | 3 | 2.333 | 0 | 3/6 (50.0%) | 0 | True | True |
| pre-4096-reuse | 4108 | 10.8 | 1.111 | 6.84 | 3 | 2.333 | 4096 | 5/6 (83.3%) | 0 | True | True |
| pre-8192-cold | 8204 | 324.27 | 25.299 | 7.38 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.9 | 1.1 | 7.28 | 3 | 2.333 | 8192 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 324.27 tok/s in 25299.648 ms (TTFT 25.299 s); reuse TTFT 1.1 s = 23.0x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 256
- 4096: cold prefill 268.51 tok/s in 15298.975 ms (TTFT 15.298 s); reuse TTFT 1.111 s = 13.8x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 128
- 2048: cold prefill 215.66 tok/s in 9551.924 ms (TTFT 9.551 s); reuse TTFT 1.087 s = 8.8x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 192
draft acceptance 28/34 (82.4%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-2048-cold | 2060 | 215.66 | 9.551 | 6.32 | 3 | 2.333 | 0 | 5/6 (83.3%) | 0 | True | True |
| pre-2048-reuse | 2060 | 11.04 | 1.087 | 6.82 | 3 | 2.333 | 2048 | 5/6 (83.3%) | 0 | True | True |
| pre-4096-cold | 4108 | 268.51 | 15.298 | 5.9 | 3 | 2.333 | 0 | 3/6 (50.0%) | 0 | True | True |
| pre-4096-reuse | 4108 | 10.8 | 1.111 | 6.84 | 3 | 2.333 | 4096 | 5/6 (83.3%) | 0 | True | True |
| pre-8192-cold | 8204 | 324.27 | 25.299 | 7.38 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.9 | 1.1 | 7.28 | 3 | 2.333 | 8192 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 324.27 tok/s in 25299.648 ms (TTFT 25.299 s); reuse TTFT 1.1 s = 23.0x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 256
- 4096: cold prefill 268.51 tok/s in 15298.975 ms (TTFT 15.298 s); reuse TTFT 1.111 s = 13.8x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 128
- 2048: cold prefill 215.66 tok/s in 9551.924 ms (TTFT 9.551 s); reuse TTFT 1.087 s = 8.8x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 192
draft acceptance 28/34 (82.4%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
