# Option 20: 10.8 GiB engine budget

## Option 20 10.8 GiB engine budget, November 5, 2026

Both repository and installed home launchers now default to **10.8G** for the 16 GiB/131K/automatic-expert/single-request/16G-persistent-cache preset. The server parser rounds this down to **11,596,411,699 whole bytes**, and the live hard budget matches without clamping. Explicit caps, including 10G and 10.5G, remain supported. Other presets retain their previous defaults. All 38 launcher tests passed, along with shell syntax, Ruff and whitespace checks.

The real-launcher restart retained 2,048-token prefill, 131,072 served context, INT8 KV, BF16 state and the same IQ3_XXS model, DFlash2 draft and native binary. The n-gram table remains SSD-backed with its approximately 64 MiB row cache. The expert-store cap remains 1.945969 GiB including staging, and the persistent prefix-cache quota remains 16 GiB on SSD.

| Setting | Previous | Installed |
|---|---:|---:|
| Engine budget, GiB | 10.5 | 10.8 |
| KV allocation token bound | 155,641 | 180,217 |
| Resident-admission bytes after SSD-tier reserves | 1,701,448,804 | 2,023,571,351 |
| Resident-admission tokens before output projection | 128,416 | 152,736 |
| Expert store GiB including staging | 1.945969 | 1.945969 |
| N-gram row cache MiB, approximately | 64 | 64 |

The **130,733-token persisted replay stayed in resident KV mode**. It reused 130,720 prefix tokens, passed initial-code recall and count-to-30 correctness, and completed streaming. The request counters increased by one resident admission, zero spill admissions and zero resident-to-spill conversions. Prefix restoration still reads SSD data; active KV residency does not eliminate expert, n-gram or persistent-cache disk I/O.

### All serving checks

Temperature zero, seed 42, reasoning disabled, 160-token output cap for correctness probes. The long prompt places ORCHID at the start and AMBER at the end, then asks for the initial code and count to 30. The resource-restoration warmup uses an 8-token cap. This is a repeated-filler functional validation, not a codebase benchmark, cold near-131K run or exactly filled-131,072 test.

| Request | Prompt | Cached | Prefill tok/s | Decode tok/s | SSE TTFT s | Correct | Observed KV |
|---|---:|---:|---:|---:|---:|---|---|
| installed-resource-warmup | 16 | 0 | 12.31 | 2.34 | 1.303 | warmup | warmup |
| smoke-cold | 4,019 | 0 | 398.60 | 12.60 | 10.088 | True | resident |
| smoke-reuse | 4,019 | 4,000 | 13.13 | 12.49 | 1.453 | True | resident |
| near131k-persisted-replay | 130,733 | 130,720 | 9.25 | 11.43 | 2.288 | True | resident |

The long replay restored prefix data from disk (1,802,272,768 bytes read). Its queue-to-start latency was 727.7 ms, so it fails the timing harness's under-100-ms benchmark filter. It passed the functional validation: correct output, complete SSE, one request, no foreign-request samples or counter mismatch, and zero additional Metal/capacity failures. These timings are descriptive; no speedup is claimed.

The planner now has sufficient resident-admission budget for the served context. Host pressure can still force spill, and neither absence of OS swap nor cold full-context residency is established. No host applications were closed and no governor safeguards were changed. No other-device performance estimates are increased.

Build: `src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d`. Native binary SHA-256: `e355f85c8cb6a92f304e97c490f2c0bad113a5a1a8ef81b2c44432c734471691` (unchanged). Installed launcher SHA-256: `7405e6d2ff13cd7be668fd584ea869821aa00712c397694a638c5d026b2d4415`.

Raw evidence: `build/validation/option20-budget108-20261105`. [Packaged results](qwen38-option20-budget108-20261105.json).
