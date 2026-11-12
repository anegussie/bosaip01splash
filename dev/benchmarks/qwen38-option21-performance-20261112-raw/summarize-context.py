import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text())

def span(rows, key, digits=2):
    values = [r[key] for r in rows]
    return f'{min(values):.{digits}f}–{max(values):.{digits}f}'

original = read(ROOT / 'results.json')['rows']
lines = ['# Option 21 performance including 64K', '',
         'Two trials per context, on the same live Q2_0 + BF16 DFlash2 server.',
         'Output budget: 96 tokens; thinking disabled, temperature 1.0, top_p 0.95.',
         'Prompt counts include 12 chat-template tokens. Cold means zero reused prefix tokens,',
         'with the model and operating-system caches already warm. Prefix reuse uses the identical prompt.', '',
         '| Filled prompt tokens | Cold PP tok/s | Cold TPS | Cold TTFT s | Cached TPS | Cached TTFT s |',
         '|---:|---:|---:|---:|---:|---:|']

for content, cold, reuse in [
    (351, [r for r in original if r['name']=='smoke-cold'], [r for r in original if r['name']=='smoke-reuse']),
    (4019, [r for r in original if r['name']=='4k-cold'], [r for r in original if r['name']=='4k-reuse']),
    *[(size, [r for r in read(ROOT / directory / 'results.json')['rows'] if r['name'].endswith('-cold')],
             [r for r in read(ROOT / directory / 'results.json')['rows'] if r['name'].endswith('-reuse')])
      for size,directory in [(8192,'context8192'),(16384,'context16384'),(65536,'context64k')]]
]:
    lines.append(f"| {cold[0]['prompt_tokens']:,} | {span(cold,'prefill_tok_s')} | {span(cold,'decode_tok_s')} | {span(cold,'sse_ttft_seconds',3)} | {span(reuse,'decode_tok_s')} | {span(reuse,'sse_ttft_seconds',3)} |")

lines += ['', 'TPS measures decode only; PP measures fresh prompt processing. Ranges contain both observations.',
          '0.35K/4K results are from the original run. 8K/16K results here replace the',
          'original eight-token probes with 96-token output-budget reruns. All requests',
          'finish naturally or at that budget; actual output counts are in raw records.', '',
          '## Added runs: validation and conditions', '']
for directory in ['context64k','context8192','context16384']:
    out = ROOT / directory
    result = read(out / 'results.json')
    rows = result['rows']
    assert result['complete'] and all(r['clean'] and r['correct'] and r['semantic_correct'] for r in rows)
    before, after = [read(out / f'system-{s}.json') for s in ['before','after']]
    swapouts = [int(re.search(r'Swapouts:\s+(\d+)',s['vm_stat']['stdout'])[1]) for s in [before,after]]
    swapins = [int(re.search(r'Swapins:\s+(\d+)',s['vm_stat']['stdout'])[1]) for s in [before,after]]
    thermal = sorted(set(v for r in rows for v in r['thermal_states_during']))
    pressure = sorted(set(r[k] for r in rows for k in ['memory_pressure_before','memory_pressure_after']))
    lines += [f'### {directory}', '',
              f"Four clean requests; ORCHID recall/counting and full-prefix cache gates passed.",
              f"Actual output tokens: {[r['completion_tokens'] for r in rows]}.",
              f"Thermal states: {thermal}; memory pressure: {pressure}.",
              f"Peak Metal allocation: {max(r['metal_peak_bytes_during'] for r in rows)/2**30:.3f} GiB.",
              f"System swap-out delta: {swapouts[1]-swapouts[0]} pages; swap-in delta: {swapins[1]-swapins[0]} pages.",
              'Before: ' + before['sysctl vm.swapusage']['stdout'].strip(),
              'After: ' + after['sysctl vm.swapusage']['stdout'].strip(),
              f"KV spilled-page delta: {sum(r['delta']['spill_pages'] for r in rows)}; whole-page restore delta: {sum(r['spill_whole_pages_delta'] for r in rows)}.", '']
lines += ['## Configuration and evidence', '',
          'Apple M5, 8 GPU cores, 16 GiB RAM; 10.8 GiB cap, 2,048-token chunks,',
          'INT8 KV, BF16 state, automatic verification width, one active request.',
          'Configured context remains 114,681 tokens after the launcher fallback.',
          'Largest context actually filled: 65,548 tokens. No full-capacity claim.',
          'Persistent cache quota is subject to available disk space; see per-run status snapshots.',
          'This is a current-condition measurement; thermal/cache state differs across time.', '',
          'Each context directory contains request metrics, responses, correctness checks,',
          'sampled conditions, profile/build identity, status and system snapshots.',
          '`64k.log`, `8192.log` and `16384.log` preserve progress and completion.',
          '`run64k.py` and `run-context.py` reproduce the added runs.',
          'The original report, raw results and build hashes remain beside this file.']
(ROOT / 'CONTEXT-REPORT.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines[:18]))
