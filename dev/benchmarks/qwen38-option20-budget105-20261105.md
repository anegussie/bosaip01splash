# Option 20: exact 10.5 GiB budget and residency check

## Option 20 engine budget, November 5, 2026

The 16 GiB Air preset now defaults to **10.5 GiB**, exactly 11,274,289,152 bytes, an increase of 536,870,912 bytes. Both repository and installed home launchers match. The live service uses 2,048-token prefill, 131,072 served context, one active request, automatic expert memory, INT8 KV and BF16 state. Explicit caps are preserved; other presets retain 10G. All 38 launcher tests passed, with shell syntax, Ruff and whitespace checks passing.

**The requested increase does not eliminate near-131K SSD spill.** The original estimate used the KV allocation bound as a spill threshold. With SSD caching enabled, resident admission also reserves spill index runway and the larger of hot-cache or staging memory. At 10.5 GiB its actual resident budget is 1,701,448,804 bytes, about 128,416 tokens before output projection. The 130,733-token live request selected `kv_mode: "spill"` at admission; its converted-from-resident counter remained zero. This is not solely a host-pressure fallback. Host growth was also blocked during the request, with zero reported host headroom.

| Memory setting | Before | Installed |
|---|---:|---:|
| Engine cap, GiB | 10 | 10.5 |
| KV allocation token bound | 114,681 | 155,641 |
| Resident-admission tokens before output projection | 87,904 | 128,416 |
| Expert store GiB, including staging | 1.945969 | 1.945969 |
| N-gram row cache, MiB | 63.999981 | 63.999981 |

The allocation-bound status field rose to 155,641 tokens, but it describes capacity without the additional SSD-tier admission reserves. It does not prove that a request will use resident mode. Earlier tables labeling 114,681 as the spill threshold need this correction.

For 131,072 tokens plus seven speculative rows, the present page geometry needs 1,736,865,792 resident bytes. Holding the other planner terms fixed needs another 35,416,988 bytes (33.78 MiB, about 0.033 GiB) beyond 10.5 GiB to pass that admission comparison. This is arithmetic, not a validated configuration or a guarantee against host-pressure conversion. The installed cap remains exactly the requested 10.5 GiB.

The 26.82 GiB n-gram table remains SSD-backed, with its existing approximately 64 MiB row cache. Expert store capacity remains 1.945969 GiB including staging. The persistent prefix cache retains its 16 GiB SSD quota. Engine cap is not total process RSS, and these tests do not establish absence of OS swap or other disk I/O. No other-Mac or DGX Spark performance estimate is increased from this change.

### Serving checks

Temperature zero, seed 42, reasoning disabled. The long repeated-filler prompt places ORCHID at the beginning and AMBER at the end and asks for the initial code and count to 30. This verifies early-context recall; it is not a representative codebase or an exactly filled-131,072 workload. Resource warmups are recorded separately. Timings characterize these conditions and are not a controlled speedup comparison.

| Request | Prompt | Cached | Prefill tok/s | Decode tok/s | SSE TTFT s | Correct | Observed KV mode |
|---|---:|---:|---:|---:|---:|---|---|
| installed-resource-warmup | 16 | 0 | 12.58 | 2.31 | 1.281 | None | warmup |
| smoke-cold | 4,019 | 0 | 402.40 | 12.53 | 9.993 | True | resident |
| smoke-reuse | 4,019 | 4,000 | 12.93 | 12.29 | 1.475 | True | resident |
| near131k-cold | 130,733 | 0 | 274.80 | 11.19 | 475.896 | True | spill (sampled) |
| final-installed-resource-warmup | 16 | 0 | 12.51 | 2.30 | 1.284 | None | warmup |
| final-persisted-smoke | 4,019 | 4,000 | 13.29 | 12.27 | 1.463 | True | resident |

The residency assertion correctly failed on `spill`, so the controller restored the previous profile before a separate final install retained the requested 10.5 GiB cap. The final persisted smoke request passed correctness and read cached prefix data from SSD. No near-131K resident-mode success is claimed.

Build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Native binary SHA-256: `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` (unchanged). Installed launcher SHA-256: `cec6b278137425f4bdb58e25cad51258fa6acae65951533f0e5768eaa1414327`. Final service instance: `7148717b890413844fffc20b`.

Raw evidence: `build/validation/option20-budget105-20261105` (launcher backups, logs, initial/final status, SSE events, payloads, request results, long-request active-mode samples and failed residency check). Packaged rows: [qwen38-option20-budget105-20261105.json](qwen38-option20-budget105-20261105.json).
