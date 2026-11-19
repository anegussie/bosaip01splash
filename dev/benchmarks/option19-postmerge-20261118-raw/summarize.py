"""Summarize option-19 archived and postmerge real-serving evidence."""
import json
import re
import statistics as st
from pathlib import Path
BASE=Path(__file__).resolve().parent
OUT=BASE/'attempt-2'
TARGET=BASE.parent/'option19-postmerge-20261118.md'
OLD=BASE.parent/'qwen36-option19-10g-evaluation-20261105.json'

def load(p):return json.loads(p.read_text())
def bounds(values):return f'{st.mean(values):.2f} ({min(values):.2f}-{max(values):.2f})' if values else '-'
def swapouts(text):return int(re.search(r'Swapouts:\s+(\d+)',text)[1])

def main():
    rows=load(OUT/'rows.json') if (OUT/'rows.json').exists() else []
    baseline=load(OLD)
    old=[r for r in baseline['measurements'] if r['memory_gib']==10 and r['requested_chunk']==512]
    complete=(OUT/'complete.json').exists()
    checks=load(OUT/'final-verification.json') if (OUT/'final-verification.json').exists() else {}
    summary=[]
    for depth in [4096,32768,57344]:
        group={'depth':depth,'before':{},'after':{},'percent_change':{}}
        for mode in ['cold','cached']:
            b=next(r for r in old if r['depth']==depth and r['mode']==mode)
            current=[r for r in rows if r['depth']==depth and r['mode']==mode and r['correct']]
            group['filled_prompt']=b['prompt_tokens']
            group['before'][mode]=dict(trials=b['trials'],pp=b['pp_tokens_per_second'],tps=b['decode_tokens_per_second'],ttft=b['ttft_seconds'],wall=b['elapsed_seconds'])
            group['after'][mode]=dict(trials=len(current),pp=st.mean(r['response']['timings']['prompt_per_second'] for r in current) if current else None,tps=st.mean(r['response']['timings']['predicted_per_second'] for r in current) if current else None,ttft=st.mean(r['ttft_seconds'] for r in current) if current else None,wall=st.mean(r['seconds'] for r in current) if current else None)
            group['percent_change'][mode]={k:(group['after'][mode][k]/group['before'][mode][k]-1)*100 if group['after'][mode][k] is not None else None for k in ['pp','tps','ttft','wall']}
        summary.append(group)
    (BASE/'comparison.json').write_text(json.dumps(dict(complete=complete,comparisons=summary),indent=2)+'\n')
    good=sum(bool(r['correct']) for r in rows)
    lines=['# Option 19 postmerge performance comparison','',f'Status: {"complete" if complete else "partial"}. {good}/{len(rows)} timed executable coding checks passed. Three independent current launches each run a cold/cache pair at 4K, 32K and 57K.','',
    'Historical control: November 5 selected 10 GiB / requested 512 profile only. Current characterization: November 18 following the Splash 1.7.0 merge. Same M5 / 16 GiB host, Qwen3.6-35B-A3B UD-IQ3_XXS with DFlash2, INT8 KV, BF16 state, 81,920 configured context, automatic expert memory, one active request, verify-rows auto, vision enabled and isolated 2 GiB persistent caches. No production cache is cleared.', '',
    'The original workload and helper were recovered from session 01a1ad99-024b-7041-9ecd-f1d839ee4792 because the old build/validation runner was gone. Timed requests retain the exact system instruction, repository-note filler, task text, 384-token cap, temperature 0, seed 42 and reasoning none. Cache salts differ to isolate each launch. Filled prompt lengths are asserted equal to the historical values: 4,013 / 32,689 / 57,259. Cold means zero prefix reuse with model/OS caches warm. Cached repeats use the identical prompt and reuse all but the suffix. SSE first-content latency starts before the HTTP request, matching the historical helper.', '',
    'Arithmetic means and observed ranges are shown, matching the baseline aggregation. These are short executable coding outputs, not sustained generation, broad coding quality, concurrency or full 80K filled-context tests. Different tasks are used at 4K (stable_unique) versus 32K/57K (chunked). Automatic verification can change generated output even with a fixed seed.', '',
    '| Filled prompt | Build | Cold PP tok/s | Cold decode TPS | Cached decode TPS | Cold TTFT s | Cached TTFT s | Cold wall s | Cached wall s | Valid cold/cache |',
    '|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for group in summary:
        depth=group['depth'];before={r['mode']:r for r in old if r['depth']==depth}
        def old_cell(mode,key):
            r=before[mode]
            samples={'pp':'pp_samples_tokens_per_second','tps':'decode_samples_tokens_per_second','ttft':'ttft_samples_seconds'}.get(key)
            if samples:return bounds(r[samples])
            return f"{r['elapsed_seconds']:.2f} ({r['elapsed_min_seconds']:.2f}-{r['elapsed_max_seconds']:.2f})"
        def new_cell(mode,key):
            data=[r for r in rows if r['depth']==depth and r['mode']==mode and r['correct']]
            return bounds([r['response']['timings']['prompt_per_second' if key=='pp' else 'predicted_per_second'] if key in ['pp','tps'] else r['ttft_seconds' if key=='ttft' else 'seconds'] for r in data])
        fields=[('cold','pp'),('cold','tps'),('cached','tps'),('cold','ttft'),('cached','ttft'),('cold','wall'),('cached','wall')]
        for label,func in [('Before',old_cell),('After',new_cell)]:
            counts=group[label.lower()]
            lines.append(f"| {group['filled_prompt']:,} | {label} | "+' | '.join(func(mode,key) for mode,key in fields)+f" | {counts['cold']['trials']}/{counts['cached']['trials']} |")
    if complete:
        lines[4:4]=['Observed arithmetic-mean prefill improved 4.1-16.6%, cold decode 9.6-42.2%, and cached decode 11.4-26.8%. Cold first-token latency decreased 3.9-14.1%. These are historical cross-run observations.', '', 'At 32K, cached completion wall time increased 17.7% (1.195 to 1.406 seconds), even though TPS increased, because the valid generated function grew from 48 to 70 tokens. At 57K cached output grew from 48 to 51 tokens; 4K remained 66 tokens and 57K cold remained 48. Throughput, first-token latency and whole-response time therefore answer different questions.', '']
    lines+=['','## Per-trial correctness and resources','','| Pass / filled prompt | Mode | Output tokens | Cached tokens | Prefill tok/s (cached: suffix) | Decode TPS | TTFT s | Wall s | Correct | Thermals | OS swap-out pages | KV disk demotions | Expert slots after |','|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|']
    swap_total=0
    for r in rows:
        t=r['response']['timings'];u=r['response']['usage'];swap=swapouts(r['vm_stat_after'])-swapouts(r['vm_stat_before']);swap_total+=swap
        demotions=r['after']['disk']['kv_demotions']-r['before']['disk']['kv_demotions']
        lines.append(f"| {r['repeat']} / {u['prompt_tokens']:,} | {r['mode']} | {u['completion_tokens']} | {t['cache_n']} | {t['prompt_per_second']:.2f} | {t['predicted_per_second']:.2f} | {r['ttft_seconds']:.3f} | {r['seconds']:.3f} | {r['correct']} | {' / '.join(r['thermal'])} | {swap} | {demotions} | {r['after']['streamed_experts']['slots']} |")
    lines+=['',f'Current timed requests recorded {swap_total:,} new system-wide swap-out pages. Full vm_stat snapshots retain the page size; existing swap usage and fresh swap-outs are separate. KV disk demotions can persist idle prefixes and do not prove active-request KV spill. Resource monitors retain active-request state, disk traffic, expert residency, memory pressure and thermals. This target did not report a per-request KV mode, so no residency claim is inferred from that absent field. No RAM-only execution claim is made.', '',
    'Each timed pair starts after two nominal thermal readings five seconds apart, matching the old runner. The immediate cached request can inherit warmer thermals from cold prefill; per-trial endpoints and two-second monitor samples are retained. Memory pressure and background system conditions can differ across dates.', '',
    'This is a historical comparison, not a matched causal A/B of the merge. Build identities, automatic expert-cache sizing and recurrent-state allocations differ. The historical runtime was src-6a06f0d6c0d0ed50806c8908cc3c19b1629f79495f59de3a349c4fb0937b951d; the current build and frozen artifact hashes are in the contract and binary manifest. Historical expert slots were 3,186; current before/after counts are retained per request.', '',
    'The initial startup-only attempt was rejected because its harness expected /status.prefill_chunk_tokens to report the requested 512. The merged runtime reports effective warmup geometry of 2,048 rows on this target. RuntimeArenas.hpp already fixed this grouped geometry in the old profile; requested 512 is retained in the command. Attempt 2 checks both independently and preserves the failed attempt without timed data.', '',
    'Smoke checks before each launch matrix cover exact output, cold/cache reuse, forced tool calls, tool-result continuation, SSE, and executable code. The first pass also validates persistent 4K coding-prefix reuse across a clean restart before subsequent passes. Failed smoke checks block dependent workloads.', '',
    'Evidence: [contract](option19-postmerge-20261118-raw/attempt-2/contract.json), [full timed rows](option19-postmerge-20261118-raw/attempt-2/rows.json), [binary hashes](option19-postmerge-20261118-raw/attempt-2/binary-sha256.json), [model source manifest](option19-postmerge-20261118-raw/attempt-2/model-manifest.json), [historical summary](qwen36-option19-10g-evaluation-20261105.json). Requests, full responses, SSE events, before/after status and vm_stat snapshots are saved alongside each trial. No builds occur during inference.']
    if checks:
        assert checks['production_ready'] and checks['preexisting_edits_preserved']
        lines+=['','All 18 timed requests and 21 per-launch smoke checks passed, plus persisted-prefix restart reuse. The original option 21 service was restored with the same command arguments, model/build identity, production cache, logging and telemetry. Frozen and live binary hashes were unchanged. The four unrelated modified files are preserved. [Final verification](option19-postmerge-20261118-raw/attempt-2/final-verification.json). Runtime logs and resource monitors: [saved evidence](option19-postmerge-20261118-raw/attempt-2/runtime/).']
    TARGET.write_text('\n'.join(lines)+'\n')
    print(TARGET)
    print('complete',complete,'requests',len(rows),'swap-out pages',swap_total)

if __name__=='__main__':main()
