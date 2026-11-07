# Flash-Next 150,000-token context spill validation, November 7, 2026

**Active KV stayed resident, but the complete no-spill requirement did not pass: macOS performed new swap-outs.**

Real HTTP serving at port 1235, IQ3_XXS, INT8 KV, BF16 state, DFlash2 verify-rows auto, one active request, 2,048-token prefill, 64 MiB PLE cache, automatic expert memory, 16 GiB persistent prefix-cache quota, and exactly 11,596,411,699 bytes (10.8 GiB) engine budget. Served context was 150,000. No rebuild or model change; identity matched the earlier running service. A short cold/reuse correctness/cache gate passed before the long test. The earlier 131K service stopped before the test started; a 150K server was then started and remains running.

The long input contained 148,967 tokens with a 1,024-token output cap (149,991 tokens including reservation). Each response generated 114 tokens, reaching 149,081 actual total tokens. A unique cache salt ensured zero prefix reuse in the cold run. Both runs recalled ORCHID from the start and counted 1 through 30 correctly. The cached repeat reused 148,960 input tokens. This validates a repeated-filler workload near 150K; exactly 150,000 actual tokens and arbitrary workloads were not tested.

| Request | Input tokens | Cached tokens | PP tok/s | Decode tok/s | TTFT seconds | KV mode | KV spill admissions/conversions/write bytes |
|---|---:|---:|---:|---:|---:|---|---|
| Cold |148,967|0|310.18|11.06|480.28|resident|0 /0 /0|
| Cached repeat |148,967|148,960|7 new tokens|8.94|0.76|resident|0 /0 /0|

Both requests completed correctly with zero failed requests, capacity failures or Metal failures. Every observed active sample was resident; spill moves and spilled bytes remained zero. These are descriptive timings, without a matched baseline or speedup claim.

System-wide swap-outs increased by 637.84 MiB during the cold run and 366.31 MiB during the cached repeat, totaling 1004.16 MiB. The 16,384-byte VM page size and cumulative `vm_stat` Swapouts counter establish new swap activity even though net swap use fell from 2234.88 to 1803.62 MiB as other pages were reclaimed. These counters cover the whole Mac and do not attribute writes to Splash alone.

Sampled Metal allocation peaked at 9.711 GiB. The engine hard budget stayed 10.8 GiB. Memory pressure was warning throughout; thermals ranged nominal to fair, and the final governor denied growth with zero host headroom. Thus active KV residency is verified for this run; operation without macOS swap is not. No other applications were closed or governor safeguards changed. Expert/PLE reads and persistent prefix-cache traffic continue independently of active KV spill.

Build ID: `src-d3ea0ffe96934b78c61585e3965e6ccc76fea994a2f23b6c26b62f10b004d0cd`. Hashes are saved in `artifact-sha256.json`. Raw requests, SSE events, status samples every two seconds, host samples, startup logs and final status: `build/validation/option20-context150k-spill-20261107`.

[Structured results](qwen38-option20-context150k-spill-20261107.json).
