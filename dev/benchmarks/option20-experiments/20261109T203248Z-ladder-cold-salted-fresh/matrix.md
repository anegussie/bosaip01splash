# Option 20 ladder matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1197 | 146.05 | 8.195 | 5.21 | 12 | 2.583 | 0 | 8/17 (47.1%) | 0 | True | True |
| turn-2 | 3027 | 184.2 | 10.005 | 7.83 | 4 | 3.0 | 1184 | 8/8 (100.0%) | 0 | True | True |
| turn-3 | 4857 | 194.56 | 9.503 | 9.52 | 2 | 6.0 | 3008 | 10/10 (100.0%) | 0 | True | True |
| turn-4 | 6687 | 207.57 | 8.936 | 9.93 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 0 | True | True |
| turn-5 | 8517 | 214.83 | 8.662 | 10.25 | 2 | 6.0 | 6656 | 10/10 (100.0%) | 0 | True | True |
| turn-6 | 10347 | 219.25 | 8.515 | 10.33 | 2 | 6.0 | 8480 | 10/10 (100.0%) | 0 | True | True |
| turn-7 | 12177 | 222.72 | 8.265 | 10.39 | 2 | 6.0 | 10336 | 10/10 (100.0%) | 0 | True | True |
| turn-8 | 14007 | 222.39 | 8.31 | 10.21 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 0 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1197 prompt tokens, cached 0 (0%), TTFT 8.195 s, prefill 146.05 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-2: 3027 prompt tokens, cached 1184 (39%), TTFT 10.005 s, prefill 184.2 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-3: 4857 prompt tokens, cached 3008 (62%), TTFT 9.503 s, prefill 194.56 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-4: 6687 prompt tokens, cached 4832 (72%), TTFT 8.936 s, prefill 207.57 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-5: 8517 prompt tokens, cached 6656 (78%), TTFT 8.662 s, prefill 214.83 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-6: 10347 prompt tokens, cached 8480 (82%), TTFT 8.515 s, prefill 219.25 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-7: 12177 prompt tokens, cached 10336 (85%), TTFT 8.265 s, prefill 222.72 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-8: 14007 prompt tokens, cached 12160 (87%), TTFT 8.31 s, prefill 222.39 tok/s, disk KV read-back 0 tokens, spill pages 0
draft acceptance 76/85 (89.4%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1197 | 146.05 | 8.195 | 5.21 | 12 | 2.583 | 0 | 8/17 (47.1%) | 0 | True | True |
| turn-2 | 3027 | 184.2 | 10.005 | 7.83 | 4 | 3.0 | 1184 | 8/8 (100.0%) | 0 | True | True |
| turn-3 | 4857 | 194.56 | 9.503 | 9.52 | 2 | 6.0 | 3008 | 10/10 (100.0%) | 0 | True | True |
| turn-4 | 6687 | 207.57 | 8.936 | 9.93 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 0 | True | True |
| turn-5 | 8517 | 214.83 | 8.662 | 10.25 | 2 | 6.0 | 6656 | 10/10 (100.0%) | 0 | True | True |
| turn-6 | 10347 | 219.25 | 8.515 | 10.33 | 2 | 6.0 | 8480 | 10/10 (100.0%) | 0 | True | True |
| turn-7 | 12177 | 222.72 | 8.265 | 10.39 | 2 | 6.0 | 10336 | 10/10 (100.0%) | 0 | True | True |
| turn-8 | 14007 | 222.39 | 8.31 | 10.21 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 0 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1197 prompt tokens, cached 0 (0%), TTFT 8.195 s, prefill 146.05 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-2: 3027 prompt tokens, cached 1184 (39%), TTFT 10.005 s, prefill 184.2 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-3: 4857 prompt tokens, cached 3008 (62%), TTFT 9.503 s, prefill 194.56 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-4: 6687 prompt tokens, cached 4832 (72%), TTFT 8.936 s, prefill 207.57 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-5: 8517 prompt tokens, cached 6656 (78%), TTFT 8.662 s, prefill 214.83 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-6: 10347 prompt tokens, cached 8480 (82%), TTFT 8.515 s, prefill 219.25 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-7: 12177 prompt tokens, cached 10336 (85%), TTFT 8.265 s, prefill 222.72 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-8: 14007 prompt tokens, cached 12160 (87%), TTFT 8.31 s, prefill 222.39 tok/s, disk KV read-back 0 tokens, spill pages 0
draft acceptance 76/85 (89.4%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
