"""Summarize archived and current option-21 evidence without inference."""
import json
import re
import statistics as st
from pathlib import Path
BASE = Path(__file__).resolve().parent
CURRENT = BASE / 'attempt-3'
OLD = BASE.parent / 'option21-chunk-context-20261113-raw/clean-run'
TARGET = BASE.parent / 'option21-postmerge-20261118.md'

def load(path):
    return json.loads(path.read_text())

def bounds(values):
    return f'{st.median(values):.2f} ({min(values):.2f}-{max(values):.2f})' if values else '-'

def swapouts(path):
    return int(re.search(r'Swapouts:\s+(\d+)', load(path)['vm_stat']['stdout'])[1])

def main():
    old = [r for r in load(OLD / 'results.json')['rows'] if r['chunk'] == 2048 and r['clean'] and r['semantic_correct']]
    current = load(CURRENT / 'rows.json') if (CURRENT / 'rows.json').exists() else []
    complete = (CURRENT / 'complete.json').exists()
    fields = [('prefill_tok_s', 'cold'), ('decode_tok_s', 'cold'), ('sse_ttft_seconds', 'cold'), ('decode_tok_s', 'reuse'), ('sse_ttft_seconds', 'reuse'), ('wall_seconds', 'cold'), ('wall_seconds', 'reuse')]
    lines = ['# Option 21 postmerge performance comparison', '', f'Status: {"complete" if complete else "partial"}. Historical November 13 measurements compared with November 18 after merge `13bfb096`.', '', 'Qwen3.8-Flash-Next Q2_0 target, BF16 DFlash2 and state, INT8 KV; 10.8 GiB limit, 131,072 server context, 2,048-token chunks, one active request and 3 GiB persistent cache quota. Thinking off; temperature 1.0, top_p 0.95; 512 output tokens. Same pinned ORCHID recall/counting prompt, filler, early context salt and request parameters. Cold means zero prefix reuse with warm model/OS caches. Each current pass starts with its own empty cache. Production cache is preserved.', '', 'Historical comparison, not a matched causal A/B of the merge. The baseline predates intervening local changes, had interruptions, and checks only a 400-character output excerpt. Current trials save and validate full outputs. The current runtime uses a 1,170 MiB KV hot-cache floor versus the historical 780 MiB floor; expert residency and cache/prepared model identities also differ. Automatic verification and unseeded sampling can produce different generations.', '', 'Values are medians (observed minimum-maximum), not confidence intervals. Actual prompts include 12 chat-template tokens. Baseline 32K cold has one valid sample; its failed ORCHID-only generation remains excluded.', '', '| Content / filled tokens | Build | Cold PP tok/s | Cold TPS | Cold TTFT s | Cached TPS | Cached TTFT s | Cold wall s | Cached wall s | Valid cold/cache |', '|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    summary = []
    for size in (8192, 32768, 65536, 102400):
        groups = {}
        for label, data, size_key in [('Before', old, 'context'), ('After', current, 'size')]:
            rows = [r for r in data if r[size_key] == size and r['clean'] and r.get('full_output_correct', r.get('semantic_correct'))]
            groups[label] = rows
            cells = [bounds([r[key] for r in rows if r['mode'] == mode and r[key] is not None]) for key, mode in fields]
            counts = [sum(r['mode'] == mode for r in rows) for mode in ('cold', 'reuse')]
            lines.append(f'| {size:,} / {size+12:,} | {label} | ' + ' | '.join(cells) + f' | {counts[0]}/{counts[1]} |')
        entry = dict(size=size, before={}, after={}, percent_change={})
        for key, mode in fields:
            name = mode + '_' + key
            for label in ('Before', 'After'):
                vals = [r[key] for r in groups[label] if r['mode'] == mode and r[key] is not None]
                entry[label.lower()][name] = st.median(vals) if vals else None
            a, b = entry['before'][name], entry['after'][name]
            entry['percent_change'][name] = (b/a-1)*100 if a and b else None
        summary.append(entry)
    lines += ['', '## Current-run validity and resource conditions', '', '| Pass / content | Mode | Output tokens | Cache tokens | Correct / clean | Thermals | Swap-out pages | KV spilled-page delta |', '|---|---|---:|---:|---|---|---:|---:|']
    for row in current:
        name = row['name']
        directory = CURRENT / f"pass-{row['repeat']}"
        delta = swapouts(directory / (name + '-system-after.json')) - swapouts(directory / (name + '-system-before.json'))
        lines.append(f"| {row['repeat']} / {row['size']:,} | {row['mode']} | {row['completion_tokens']} | {row['cached_tokens']} | {row['full_output_correct']} / {row['clean']} | {','.join(row['thermal_states_during'])} | {delta} | {row['spill_whole_pages_delta']} |")
    lines += ['', 'Swap-out pages are system-wide deltas during each request, with the page size saved in vm_stat. Existing swap usage does not establish new swapping. KV spill counters and OS swap are distinct; this report makes no RAM-only full-context claim.', '', 'The first restart smoke used a 363-token prompt below the runtime persistence threshold of 2,048 tokens and was rejected. Attempt 2 returned only ORCHID with a 96-token cap and a request for 1,000 integers. Both failures are retained. Attempt 3 uses the established 30-integer smoke with a 4K prefix, validates executable code and persistent reuse across restart, then restores the original timed workload.', '', 'Evidence: [contract](option21-postmerge-20261118-raw/attempt-3/contract.json), [raw rows](option21-postmerge-20261118-raw/attempt-3/rows.json), [model source manifest](option21-postmerge-20261118-raw/model-manifest.json), [frozen binary SHA256](option21-postmerge-20261118-raw/attempt-3/binary-sha256.json), full request JSON/SSE/output and system snapshots alongside each trial. Runtime server logs and two-second resource monitors are under `build/validation/option21-postmerge-20261118-attempt-3/`. Production restoration is recorded in `attempt-3/production-restored.json`. No build occurred during inference.']
    TARGET.write_text('\n'.join(lines) + '\n')
    (BASE / 'comparison.json').write_text(json.dumps(dict(complete=complete, comparisons=summary), indent=2) + '\n')
    print(TARGET)
    print(json.dumps(summary, indent=2))
if __name__ == '__main__':
    main()
