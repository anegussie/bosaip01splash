# Option 20 prefill matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-1024-cold | 1036 | 146.07 | 7.092 | 6.62 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-1024-reuse | 1036 | 10.99 | 1.091 | 7.42 | 3 | 2.333 | 1024 | 5/5 (100.0%) | 0 | False | True |
| pre-2048-cold | 2060 | 227.23 | 9.066 | 5.28 | 4 | 1.75 | 0 | 4/7 (57.1%) | 0 | False | True |
| pre-2048-reuse | 2060 | 10.75 | 1.116 | 7.36 | 3 | 2.333 | 2048 | 5/5 (100.0%) | 0 | False | True |
| pre-4096-cold | 4108 | 297.16 | 13.824 | 7.45 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-4096-reuse | 4108 | 10.36 | 1.158 | 7.52 | 3 | 2.333 | 4096 | 4/5 (80.0%) | 0 | False | True |
| pre-8192-cold | 8204 | 333.08 | 24.63 | 7.38 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-8192-reuse | 8204 | 10.08 | 1.189 | 7.39 | 3 | 2.333 | 8192 | 5/5 (100.0%) | 0 | False | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 333.08 tok/s in 24630.671 ms (TTFT 24.63 s); reuse TTFT 1.189 s = 20.7x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 512
- 4096: cold prefill 297.16 tok/s in 13824.382 ms (TTFT 13.824 s); reuse TTFT 1.158 s = 11.9x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 640
- 2048: cold prefill 227.23 tok/s in 9065.7 ms (TTFT 9.066 s); reuse TTFT 1.116 s = 8.1x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 704
- 1024: cold prefill 146.07 tok/s in 7092.562 ms (TTFT 7.092 s); reuse TTFT 1.091 s = 6.5x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 736
draft acceptance 38/42 (90.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-1024-cold | 1036 | 146.07 | 7.092 | 6.62 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-1024-reuse | 1036 | 10.99 | 1.091 | 7.42 | 3 | 2.333 | 1024 | 5/5 (100.0%) | 0 | False | True |
| pre-2048-cold | 2060 | 227.23 | 9.066 | 5.28 | 4 | 1.75 | 0 | 4/7 (57.1%) | 0 | False | True |
| pre-2048-reuse | 2060 | 10.75 | 1.116 | 7.36 | 3 | 2.333 | 2048 | 5/5 (100.0%) | 0 | False | True |
| pre-4096-cold | 4108 | 297.16 | 13.824 | 7.45 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-4096-reuse | 4108 | 10.36 | 1.158 | 7.52 | 3 | 2.333 | 4096 | 4/5 (80.0%) | 0 | False | True |
| pre-8192-cold | 8204 | 333.08 | 24.63 | 7.38 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | False | True |
| pre-8192-reuse | 8204 | 10.08 | 1.189 | 7.39 | 3 | 2.333 | 8192 | 5/5 (100.0%) | 0 | False | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 8192: cold prefill 333.08 tok/s in 24630.671 ms (TTFT 24.63 s); reuse TTFT 1.189 s = 20.7x, cached 8192, disk KV read-back 0 tokens, spill pages 0, kv pages free 512
- 4096: cold prefill 297.16 tok/s in 13824.382 ms (TTFT 13.824 s); reuse TTFT 1.158 s = 11.9x, cached 4096, disk KV read-back 0 tokens, spill pages 0, kv pages free 640
- 2048: cold prefill 227.23 tok/s in 9065.7 ms (TTFT 9.066 s); reuse TTFT 1.116 s = 8.1x, cached 2048, disk KV read-back 0 tokens, spill pages 0, kv pages free 704
- 1024: cold prefill 146.07 tok/s in 7092.562 ms (TTFT 7.092 s); reuse TTFT 1.091 s = 6.5x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 736
draft acceptance 38/42 (90.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
