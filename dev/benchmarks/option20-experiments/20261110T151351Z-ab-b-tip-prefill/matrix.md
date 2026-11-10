# Option 20 prefill matrix

cache state: fresh | thermal gate: none | build: src-81529c7c97580f531418c1c0ec9bf09bfd5997452ca96d8d0b8071fa40c86a6a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-2048-cold | 2060 | 199.53 | 10.324 | 5.91 | 3 | 2.333 | 0 | 4/7 (57.1%) | 0 | True | True |
| pre-2048-reuse | 2060 | 10.66 | 1.126 | 7.35 | 3 | 2.333 | 2048 | 5/5 (100.0%) | 0 | True | True |
| pre-4096-cold | 4108 | 242.1 | 16.967 | 7.52 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-4096-reuse | 4108 | 10.28 | 1.167 | 7.51 | 2 | 3.5 | 4096 | 5/5 (100.0%) | 0 | True | True |
| pre-8192-cold | 8204 | 294.5 | 27.857 | 6.53 | 2 | 3.5 | 0 | 5/8 (62.5%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.9 | 1.1 | 7.49 | 2 | 3.5 | 8192 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 294.5 tok/s in 27857.367 ms (TTFT 27.857 s); reuse TTFT 1.1 s = 25.3x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 257
- 4096: cold prefill 242.1 tok/s in 16968.137 ms (TTFT 16.967 s); reuse TTFT 1.167 s = 14.5x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 385
- 2048: cold prefill 199.53 tok/s in 10324.34 ms (TTFT 10.324 s); reuse TTFT 1.126 s = 9.2x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 513
draft acceptance 29/35 (82.9%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-2048-cold | 2060 | 199.53 | 10.324 | 5.91 | 3 | 2.333 | 0 | 4/7 (57.1%) | 0 | True | True |
| pre-2048-reuse | 2060 | 10.66 | 1.126 | 7.35 | 3 | 2.333 | 2048 | 5/5 (100.0%) | 0 | True | True |
| pre-4096-cold | 4108 | 242.1 | 16.967 | 7.52 | 2 | 3.5 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-4096-reuse | 4108 | 10.28 | 1.167 | 7.51 | 2 | 3.5 | 4096 | 5/5 (100.0%) | 0 | True | True |
| pre-8192-cold | 8204 | 294.5 | 27.857 | 6.53 | 2 | 3.5 | 0 | 5/8 (62.5%) | 0 | True | True |
| pre-8192-reuse | 8204 | 10.9 | 1.1 | 7.49 | 2 | 3.5 | 8192 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 294.5 tok/s in 27857.367 ms (TTFT 27.857 s); reuse TTFT 1.1 s = 25.3x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 257
- 4096: cold prefill 242.1 tok/s in 16968.137 ms (TTFT 16.967 s); reuse TTFT 1.167 s = 14.5x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 385
- 2048: cold prefill 199.53 tok/s in 10324.34 ms (TTFT 10.324 s); reuse TTFT 1.126 s = 9.2x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 513
draft acceptance 29/35 (82.9%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
