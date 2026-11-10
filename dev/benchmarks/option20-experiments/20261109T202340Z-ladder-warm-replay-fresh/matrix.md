# Option 20 ladder matrix

cache state: fresh | thermal gate: none | build: src-882891f890315dd4690df62d5f5cd80d5f701b31d32d975102cdb3dc9611392a

## trial1
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1188 | 14.28 | 2.52 | 5.36 | 17 | 1.824 | 1152 | 15/20 (75.0%) | 36 | True | True |
| turn-2 | 3018 | 11.3 | 0.885 | 6.52 | 4 | 3.0 | 3008 | 8/12 (66.7%) | 58 | True | True |
| turn-3 | 4848 | 10.78 | 1.484 | 10.35 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 57 | True | True |
| turn-4 | 6678 | 11.5 | 1.913 | 9.95 | 2 | 6.0 | 6656 | 10/10 (100.0%) | 57 | True | True |
| turn-5 | 8508 | 12.18 | 2.299 | 10.39 | 2 | 6.0 | 8480 | 10/10 (100.0%) | 57 | True | True |
| turn-6 | 10338 | 12.8 | 2.657 | 8.49 | 2 | 6.0 | 10304 | 10/14 (71.4%) | 57 | True | True |
| turn-7 | 12168 | 10.62 | 0.753 | 10.24 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 58 | True | True |
| turn-8 | 13998 | 10.67 | 1.312 | 10.23 | 2 | 6.0 | 13984 | 10/10 (100.0%) | 57 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1188 prompt tokens, cached 1152 (97%), TTFT 2.52 s, prefill 14.28 tok/s, disk KV read-back 1152 tokens, spill pages 36
- turn-2: 3018 prompt tokens, cached 3008 (100%), TTFT 0.885 s, prefill 11.3 tok/s, disk KV read-back 1856 tokens, spill pages 58
- turn-3: 4848 prompt tokens, cached 4832 (100%), TTFT 1.484 s, prefill 10.78 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-4: 6678 prompt tokens, cached 6656 (100%), TTFT 1.913 s, prefill 11.5 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-5: 8508 prompt tokens, cached 8480 (100%), TTFT 2.299 s, prefill 12.18 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-6: 10338 prompt tokens, cached 10304 (100%), TTFT 2.657 s, prefill 12.8 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-7: 12168 prompt tokens, cached 12160 (100%), TTFT 0.753 s, prefill 10.62 tok/s, disk KV read-back 1856 tokens, spill pages 58
- turn-8: 13998 prompt tokens, cached 13984 (100%), TTFT 1.312 s, prefill 10.67 tok/s, disk KV read-back 1824 tokens, spill pages 57
draft acceptance 83/96 (86.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 437
disk KV read-back tokens during probes: 13984
thermal states: fair

## pooled
| Probe | Prompt | Prefill tok/s | TTFT (s) | Decode tok/s | Cycles | Tok/cycle | Cached | Draft acc | Spill pages | Correct | Clean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| turn-1 | 1188 | 14.28 | 2.52 | 5.36 | 17 | 1.824 | 1152 | 15/20 (75.0%) | 36 | True | True |
| turn-2 | 3018 | 11.3 | 0.885 | 6.52 | 4 | 3.0 | 3008 | 8/12 (66.7%) | 58 | True | True |
| turn-3 | 4848 | 10.78 | 1.484 | 10.35 | 2 | 6.0 | 4832 | 10/10 (100.0%) | 57 | True | True |
| turn-4 | 6678 | 11.5 | 1.913 | 9.95 | 2 | 6.0 | 6656 | 10/10 (100.0%) | 57 | True | True |
| turn-5 | 8508 | 12.18 | 2.299 | 10.39 | 2 | 6.0 | 8480 | 10/10 (100.0%) | 57 | True | True |
| turn-6 | 10338 | 12.8 | 2.657 | 8.49 | 2 | 6.0 | 10304 | 10/14 (71.4%) | 57 | True | True |
| turn-7 | 12168 | 10.62 | 0.753 | 10.24 | 2 | 6.0 | 12160 | 10/10 (100.0%) | 58 | True | True |
| turn-8 | 13998 | 10.67 | 1.312 | 10.23 | 2 | 6.0 | 13984 | 10/10 (100.0%) | 57 | True | True |

Turn ladder (each turn re-sends the whole conversation):
- turn-1: 1188 prompt tokens, cached 1152 (97%), TTFT 2.52 s, prefill 14.28 tok/s, disk KV read-back 1152 tokens, spill pages 36
- turn-2: 3018 prompt tokens, cached 3008 (100%), TTFT 0.885 s, prefill 11.3 tok/s, disk KV read-back 1856 tokens, spill pages 58
- turn-3: 4848 prompt tokens, cached 4832 (100%), TTFT 1.484 s, prefill 10.78 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-4: 6678 prompt tokens, cached 6656 (100%), TTFT 1.913 s, prefill 11.5 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-5: 8508 prompt tokens, cached 8480 (100%), TTFT 2.299 s, prefill 12.18 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-6: 10338 prompt tokens, cached 10304 (100%), TTFT 2.657 s, prefill 12.8 tok/s, disk KV read-back 1824 tokens, spill pages 57
- turn-7: 12168 prompt tokens, cached 12160 (100%), TTFT 0.753 s, prefill 10.62 tok/s, disk KV read-back 1856 tokens, spill pages 58
- turn-8: 13998 prompt tokens, cached 13984 (100%), TTFT 1.312 s, prefill 10.67 tok/s, disk KV read-back 1824 tokens, spill pages 57
draft acceptance 83/96 (86.5%)
probes marked clean: 8/8
spill whole-page restores during probes: 437
disk KV read-back tokens during probes: 13984
thermal states: fair
