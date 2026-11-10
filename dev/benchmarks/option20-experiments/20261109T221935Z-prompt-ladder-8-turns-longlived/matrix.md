# Option 20 ladder matrix

cache state: longlived | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1188 | 141.07 | 8.421 | 6.06 | 11 | 2.818 | 0 | 21/28 (75.0%) | 0 | True | True |
| turn-2 | 3018 | 179.48 | 10.401 | 6.67 | 9 | 2.444 | 1152 | 10/13 (76.9%) | 0 | True | True |
| turn-3 | 4848 | 190.42 | 9.663 | 10.09 | 2 | 6.0 | 3008 | 10/10 (100.0%) | 0 | True | True |
| turn-4 | 6678 | 202.73 | 9.105 | 9.76 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 0 | True | True |
| turn-5 | 8508 | 218.24 | 8.486 | 8.58 | 2 | 6.0 | 6656 | 10/14 (71.4%) | 0 | True | True |
| turn-6 | 10338 | 216.72 | 8.573 | 8.12 | 2 | 6.0 | 8480 | 10/14 (71.4%) | 0 | True | True |
| turn-7 | 12168 | 219.58 | 8.488 | 10.32 | 2 | 6.0 | 10304 | 10/10 (100.0%) | 0 | True | True |
| turn-8 | 13998 | 220.64 | 8.333 | 10.14 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 0 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1188 prompt tokens, cached 0 (0%), TTFT 8.421 s, prefill 141.07 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-2: 3018 prompt tokens, cached 1152 (38%), TTFT 10.401 s, prefill 179.48 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-3: 4848 prompt tokens, cached 3008 (62%), TTFT 9.663 s, prefill 190.42 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-4: 6678 prompt tokens, cached 4832 (72%), TTFT 9.105 s, prefill 202.73 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-5: 8508 prompt tokens, cached 6656 (78%), TTFT 8.486 s, prefill 218.24 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-6: 10338 prompt tokens, cached 8480 (82%), TTFT 8.573 s, prefill 216.72 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-7: 12168 prompt tokens, cached 10304 (85%), TTFT 8.488 s, prefill 219.58 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-8: 13998 prompt tokens, cached 12160 (87%), TTFT 8.333 s, prefill 220.64 tok/s, disk KV read-back 0 tokens, spill pages 0
draft acceptance 91/109 (83.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1188 | 141.07 | 8.421 | 6.06 | 11 | 2.818 | 0 | 21/28 (75.0%) | 0 | True | True |
| turn-2 | 3018 | 179.48 | 10.401 | 6.67 | 9 | 2.444 | 1152 | 10/13 (76.9%) | 0 | True | True |
| turn-3 | 4848 | 190.42 | 9.663 | 10.09 | 2 | 6.0 | 3008 | 10/10 (100.0%) | 0 | True | True |
| turn-4 | 6678 | 202.73 | 9.105 | 9.76 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 0 | True | True |
| turn-5 | 8508 | 218.24 | 8.486 | 8.58 | 2 | 6.0 | 6656 | 10/14 (71.4%) | 0 | True | True |
| turn-6 | 10338 | 216.72 | 8.573 | 8.12 | 2 | 6.0 | 8480 | 10/14 (71.4%) | 0 | True | True |
| turn-7 | 12168 | 219.58 | 8.488 | 10.32 | 2 | 6.0 | 10304 | 10/10 (100.0%) | 0 | True | True |
| turn-8 | 13998 | 220.64 | 8.333 | 10.14 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 0 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1188 prompt tokens, cached 0 (0%), TTFT 8.421 s, prefill 141.07 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-2: 3018 prompt tokens, cached 1152 (38%), TTFT 10.401 s, prefill 179.48 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-3: 4848 prompt tokens, cached 3008 (62%), TTFT 9.663 s, prefill 190.42 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-4: 6678 prompt tokens, cached 4832 (72%), TTFT 9.105 s, prefill 202.73 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-5: 8508 prompt tokens, cached 6656 (78%), TTFT 8.486 s, prefill 218.24 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-6: 10338 prompt tokens, cached 8480 (82%), TTFT 8.573 s, prefill 216.72 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-7: 12168 prompt tokens, cached 10304 (85%), TTFT 8.488 s, prefill 219.58 tok/s, disk KV read-back 0 tokens, spill pages 0
- turn-8: 13998 prompt tokens, cached 12160 (87%), TTFT 8.333 s, prefill 220.64 tok/s, disk KV read-back 0 tokens, spill pages 0
draft acceptance 91/109 (83.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 0
disk KV read-back tokens during probes: 0
thermal states: fair
