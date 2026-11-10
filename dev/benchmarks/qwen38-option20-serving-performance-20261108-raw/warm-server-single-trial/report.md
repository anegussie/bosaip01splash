# Option 20 live performance run, November 8 2026

Profile under test: `bash /Users/mymac/startllamacpp.sh --direct 20`, already serving on
`127.0.0.1:1235` (PID 92460). `/status` confirms the option-20 preset exactly:
`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:IQ3_XXS`, 131,072 context, 2,048 prefill
chunks, INT8 KV, governor limit 11,596,411,699 bytes (10.8 GiB cap, the validated 16 GiB
Air preset), persistent option-20 prefix cache.

Machine: Apple M5 MacBook Air, 8 GPU cores, 16 GiB unified memory. No restart, no cache
flush, no other server process; every probe waited for `active_requests = 0` and ran
uncontended. Thinking was disabled per request (`enable_thinking: false`) so decode
measures generation, matching earlier option-20 reports.

## Conditions at run time

- `memory_pressure = warning`, `thermal_state = fair` for the whole run (not the
  `nominal` thermal state of the November 6 reference runs).
- `growth_allowed = false` on every probe; host spare 2.01-2.11 GB against a 2 GiB reserve.
- Metal allocation steady at 8.498 GiB peak across all seven probes; governor
  `denied_reservations` rose 2,131 to 5,026 during the run.
- Zero `capacity_failures` and zero `metal_failures`. All seven SSE streams completed.

## Results

| Probe | Prompt tokens | Prefill tok/s | SSE TTFT (s) | Decode tok/s | Cached tokens | Draft accepted |
|---|---:|---:|---:|---:|---:|---:|
| smoke-cold | 385 | 87.04 | 4.426 | 12.54 | 0 | 83/83 |
| smoke-reuse | 385 | 15.23 | 2.178 | 12.42 | 352 | 83/84 |
| 4k-cold | 4,067 | 312.15 | 13.040 | 11.55 | 0 | 81/86 |
| 4k-reuse | 4,067 | 13.99 | 2.511 | 11.19 | 4,032 | 81/91 |
| code-1 | 47 | 18.94 | 2.487 | 9.17 | 0 | 96/113 |
| code-2 | 40 | 16.92 | 2.368 | 9.66 | 0 | 87/106 |
| code-3 | 38 | 17.06 | 2.231 | 10.07 | 0 | 104/109 |

- Coding decode mean 9.63 tok/s (range 9.17-10.07), against the November 6 reference of
  10.04 tok/s (10.00-10.11) and the documented Air band of 8.81-8.92.
- 4,067-token cold prefill 312 tok/s against the November 6 reference of 406-408 tok/s at
  the same 10.8G cap and 2,048 chunks; the reuse TTFT is 2.511 s against 1.52-1.59 s.
  Both gaps line up with `warning` pressure plus `fair` thermal and a zero host headroom
  at preflight, not with a configuration change.
- Prefix cache reuse works: 4,032 of 4,067 tokens came back from cache (32-token block
  aligned) and reuse TTFT fell from 13.04 s to 2.511 s.
- Draft acceptance 615/672 (91.5%) across the probes.

## Notes

- Prompt token counts land slightly above the 351 / 4,019 targets because the count is
  measured after the chat template adds its own tokens.
- Raw per-probe records: `smoke-cold.json`, `smoke-reuse.json`, `4k-cold.json`,
  `4k-reuse.json`, `code-1..3.json`, aggregated in `matrix-results.json`.
- Runner: `run_option20_perf.py` (idle gating, 0.5 s `/status` sampling, 5 s cooldowns).
