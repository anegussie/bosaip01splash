"""Summarize saved chunk/context results without inference."""
import json
from pathlib import Path
import re
import statistics

BASE = Path(__file__).resolve().parent
OUT = BASE / 'clean-run'
TARGET = BASE.parent / 'option21-chunk-context-20261113.md'


def bounds(values, digits=2):
    values = [v for v in values if v is not None]
    if not values:
        return '-'
    return f'{statistics.median(values):.{digits}f} ({min(values):.{digits}f}–{max(values):.{digits}f})'


def swapouts(system):
    return int(re.search(r'Swapouts:\s+(\d+)', system['vm_stat']['stdout'])[1])


def main():
    data = json.loads((OUT / 'results.json').read_text())
    contract = json.loads((OUT / 'contract.json').read_text())
    lines = ['# Option 21: 2,048 vs 1,024 prefill chunks across context sizes', '',
        f"Status: {'complete' if data['complete'] else 'partial; do not treat as a final ranking'}.", '',
        'Same frozen executable and Metal libraries; Q2_0 target and BF16 DFlash2, INT8 KV, BF16 state,',
        '10.8 GiB cap, 131,072 server context, one active request, automatic verification.',
        'The tested indexer profile is `top_k=4096` (780 MiB hot-cache floor); this is separate from the prefill chunk size.',
        'Thinking disabled. Temperature 1.0, top_p 0.95; each counting request has a 512-token budget.',
        'A/B/B/A order; each arm has a new isolated 3 GiB persistent cache.',
        'Cold means no reused prefix, with model/OS caches warmed. Reuse repeats the identical prompt.', '',
        f"Branch: `{contract['branch']}`; repository HEAD: `{contract['commit']}`.",
        'The checkout was dirty; the executable hash and reported build ID identify the tested runtime.', '',
        'Each value is the median followed by the observed range of valid requests only.',
        'Valid cold/cached sample counts are shown; failed generations remain in the raw results and validity table.',
        'These are not statistical confidence intervals. Actual filled prompts include chat-template tokens.', '',
        '| Content tokens | Chunk | Filled prompt | Cold PP tok/s | Cold decode TPS | Cold TTFT s | Cached decode TPS | Cached TTFT s | Valid cold/cached |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    if contract.get('resume_note'):
        lines[3:3] = ['**Protocol interruption:** ' + contract['resume_note'], '']
    if data['complete']:
        passed=sum(bool(r['clean'] and r['semantic_correct']) for r in data['rows'])
        lines[3:3] = [
            f"**Outcome:** {passed}/{len(data['rows'])} timed trials passed the semantic gate. "
            'The failed 32K cold 2,048-chunk generation returned only ORCHID; it is retained and excluded from speed aggregates.', '',
            'Observed medians: 1,024-token chunks increased cached decode TPS by 12.8–23.6% and reduced cold PP by 22.7–33.0%. '
            'Keep 2,048 chunks as the general profile; 1,024 is an option for workloads dominated by cached-prefix generation. '
            'These are conditional observations from an interrupted, small synthetic-workload comparison, not a universal speedup.', '',
            'Both profiles retained 128K server capacity. The 100K requests used KV spill, and some trials recorded macOS swap-outs. '
            'This does not establish RAM-only execution at 128K.', '']
    groups = []
    for size in contract['contexts']:
        for chunk in (2048, 1024):
            cold = [r for r in data['rows'] if r['context']==size and r['chunk']==chunk and r['mode']=='cold' and r['clean'] and r['semantic_correct']]
            reuse = [r for r in data['rows'] if r['context']==size and r['chunk']==chunk and r['mode']=='reuse' and r['clean'] and r['semantic_correct']]
            groups.append(dict(context=size,chunk=chunk,cold=cold,reuse=reuse))
            if not cold:
                continue
            lines.append(f"| {size:,} | {chunk} | {cold[0]['prompt_tokens']:,} | " + ' | '.join([
                bounds([r['prefill_tok_s'] for r in cold]), bounds([r['decode_tok_s'] for r in cold]),
                bounds([r['sse_ttft_seconds'] for r in cold]), bounds([r['decode_tok_s'] for r in reuse]),
                bounds([r['sse_ttft_seconds'] for r in reuse])]) + f' | {len(cold)}/{len(reuse)} |')
    lines += ['', '## End-to-end request time', '',
        'Wall seconds include prefill and generation, with the same 512-token output budget.',
        'They exclude the preceding idle/thermal wait. Actual generated token counts are retained in the raw rows.', '',
        '| Content tokens | Chunk | Cold wall seconds | Cached wall seconds |',
        '|---:|---:|---:|---:|']
    for group in groups:
        if group['cold']:
            lines.append(f"| {group['context']:,} | {group['chunk']} | " +
                bounds([r['wall_seconds'] for r in group['cold']]) + ' | ' +
                bounds([r['wall_seconds'] for r in group['reuse']]) + ' |')
    if data['complete']:
        lines += ['', '## Assumed workflow: 70% of elapsed time in prompt processing', '',
            'This is a model using the measured medians, not a measured end-to-end user workflow.',
            'Assume 70% of the 2,048-chunk inference time is fresh prompt processing and 30% is decode.',
            'For the same work, the estimated 1,024-chunk time ratio is',
            '`0.70 * (PP_2048 / PP_1024) + 0.30 * (cached_TPS_2048 / cached_TPS_1024)`.',
            'Using cached decode gives the smaller chunk its favorable observed decode regime.',
            'The assumption concerns time, not token or request counts. Queueing, tools and other work are excluded.', '',
            '| Content tokens | Estimated extra elapsed time with 1,024 chunks |',
            '|---:|---:|']
        for size in contract['contexts']:
            pair={g['chunk']:g for g in groups if g['context']==size}
            pp=lambda c:statistics.median(r['prefill_tok_s'] for r in pair[c]['cold'])
            tg=lambda c:statistics.median(r['decode_tok_s'] for r in pair[c]['reuse'])
            ratio=0.7*pp(2048)/pp(1024)+0.3*tg(2048)/tg(1024)
            lines.append(f'| {size:,} | +{(ratio-1)*100:.1f}% |')
    lines += ['', '## Conditions and validity', '',
        '| Arm | Timed requests | Correct/clean | Expert slots observed | Thermals during requests | Memory pressure | Swap-out pages | Spilled requests | KV spilled-page delta |',
        '|---|---:|---|---|---|---|---:|---:|---:|']
    for arm in contract['order']:
        rows=[r for r in data['rows'] if r['arm']==arm]
        if not rows:
            continue
        swaps=0
        for r in rows:
            directory=OUT/arm
            before=json.loads((directory/(r['name']+'-system-before.json')).read_text())
            after=json.loads((directory/(r['name']+'-system-after.json')).read_text())
            swaps+=swapouts(after)-swapouts(before)
        slots=sorted({r[s]['streamed_experts']['slots'] for r in rows for s in ('status_before','status_after')})
        thermals=sorted({x for r in rows for x in r['thermal_states_during']})
        pressure=sorted({r[s]['memory_pressure'] for r in rows for s in ('status_before','status_after')})
        spill=sum(r['status_after']['kv_spill']['pages']['spilled']-r['status_before']['kv_spill']['pages']['spilled'] for r in rows)
        spilled_requests=sum(r['status_after']['kv_spill']['requests']['spill']-r['status_before']['kv_spill']['requests']['spill'] for r in rows)
        lines.append(f"| {arm} | {len(rows)} | {all(r['clean'] and r['semantic_correct'] for r in rows)} | {slots} | {thermals} | {pressure} | {swaps} | {spilled_requests} | {spill} |")
    lines += ['', '## Limits and evidence', '',
        'The primary context workload is synthetic recall/counting. Executable Python correctness is checked',
        'in the short smoke gates; these results do not establish representative coding throughput.',
        'Counting correctness checks the saved output excerpt (up to 400 characters), including the secret',
        'and ordered integers; a final partial integer is ignored. It does not validate every generated token.',
        'Automatic verification can produce different outputs even with matching request settings.',
        'Full request metrics, before/after status, system snapshots, server logs and a two-second',
        'memory/thermal/expert-residency monitor are saved beside this runner.',
        'Smoke gates cover both chunk sizes, cold and cached requests, executable code and restart restore.',
        'An earlier attempt was rejected at 32K after it reused a 4K prefix from the 8K prompt.',
        'It is excluded here. Context-specific early salts and a cross-context cold smoke gate fixed it;',
        '[the failure record is retained](option21-chunk-context-20261113-raw/FAILURE.md).',
        'Production restoration is recorded in `production-restored.json`.', '',
        'Normal log links, JSONL telemetry and the performance monitor were restored without rebuilding;',
        'see `normal-logging-restored.json` for their paths and process identifiers.', '',
        '[Raw evidence](option21-chunk-context-20261113-raw/clean-run/).']
    TARGET.write_text('\n'.join(lines)+'\n')
    print(TARGET)


if __name__ == '__main__':
    main()
