# Option 20 prefill matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-128-cold | 140 | 38.19 | 3.665 | 6.67 | 3 | 2.333 | 0 | 5/7 (71.4%) | 0 | True | True |
| pre-128-reuse | 140 | 10.92 | 1.099 | 6.57 | 3 | 2.333 | 128 | 5/7 (71.4%) | 0 | True | True |
| pre-512-cold | 524 | 100.9 | 5.193 | 6.57 | 3 | 2.333 | 0 | 5/7 (71.4%) | 0 | True | True |
| pre-512-reuse | 524 | 10.46 | 1.147 | 6.59 | 3 | 2.333 | 512 | 5/7 (71.4%) | 0 | True | True |
| pre-1024-cold | 1036 | 180.29 | 5.746 | 7.48 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-1024-reuse | 1036 | 10.64 | 1.128 | 7.49 | 3 | 2.333 | 1024 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 1024: cold prefill 180.29 tok/s in 5746.45 ms (TTFT 5.746 s); reuse TTFT 1.128 s = 5.1x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 736
- 512: cold prefill 100.9 tok/s in 5193.077 ms (TTFT 5.193 s); reuse TTFT 1.147 s = 4.5x, cached 512, disk KV read-back 0 tokens, spill pages 0, kv pages free 752
- 128: cold prefill 38.19 tok/s in 3666.264 ms (TTFT 3.665 s); reuse TTFT 1.099 s = 3.3x, cached 128, disk KV read-back 0 tokens, spill pages 0, kv pages free 764
draft acceptance 30/38 (78.9%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| pre-128-cold | 140 | 38.19 | 3.665 | 6.67 | 3 | 2.333 | 0 | 5/7 (71.4%) | 0 | True | True |
| pre-128-reuse | 140 | 10.92 | 1.099 | 6.57 | 3 | 2.333 | 128 | 5/7 (71.4%) | 0 | True | True |
| pre-512-cold | 524 | 100.9 | 5.193 | 6.57 | 3 | 2.333 | 0 | 5/7 (71.4%) | 0 | True | True |
| pre-512-reuse | 524 | 10.46 | 1.147 | 6.59 | 3 | 2.333 | 512 | 5/7 (71.4%) | 0 | True | True |
| pre-1024-cold | 1036 | 180.29 | 5.746 | 7.48 | 3 | 2.333 | 0 | 5/5 (100.0%) | 0 | True | True |
| pre-1024-reuse | 1036 | 10.64 | 1.128 | 7.49 | 3 | 2.333 | 1024 | 5/5 (100.0%) | 0 | True | True |

Prompt processing by prompt size (cold = dense prefill, reuse = same prompt right after):
- 1024: cold prefill 180.29 tok/s in 5746.45 ms (TTFT 5.746 s); reuse TTFT 1.128 s = 5.1x, cached 1024, disk KV read-back 0 tokens, spill pages 0, kv pages free 736
- 512: cold prefill 100.9 tok/s in 5193.077 ms (TTFT 5.193 s); reuse TTFT 1.147 s = 4.5x, cached 512, disk KV read-back 0 tokens, spill pages 0, kv pages free 752
- 128: cold prefill 38.19 tok/s in 3666.264 ms (TTFT 3.665 s); reuse TTFT 1.099 s = 3.3x, cached 128, disk KV read-back 0 tokens, spill pages 0, kv pages free 764
draft acceptance 30/38 (78.9%)
probes marked clean: 6/6
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
