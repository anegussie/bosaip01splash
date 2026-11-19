"""Recovered November 5 option-19 request and correctness harness.

Recovered from session 01a1ad99-024b-7041-9ecd-f1d839ee4792.
The timed request construction and SSE timing start are retained verbatim.
"""
from pathlib import Path
import json
import subprocess
import sys
import time
import urllib.request
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from dev.benchmarks import dflash2_tuning as bench, bonsai_coding
PYTHON = ROOT / '.venv/bin/python'
OUT = Path(__file__).resolve().parent
ALIAS = 'qwen3.6-35b-a3b-iq3-xxs-splash'
URL = 'http://127.0.0.1:1236'
record = {}
def save():
    bench.save(OUT / 'run.json', record)
def status():
    return bench.request(URL)

def healthy(s):
    assert s['ready'] and s['metal']['healthy']
    assert not s['active_requests'] and not s['transport']['pending'] and not s['transport']['frontend_waiting']
    assert s['requests']['failed'] == 0

def payload(text, salt, maximum=384, reasoning='none', code=True):
    messages=[]
    if code:
        messages.append({'role':'system','content':'Return only the requested Python function. Use no imports or commentary.'})
    messages.append({'role':'user','content':text})
    return {'model':ALIAS,'messages':messages,'temperature':0,'seed':42,
        'reasoning_effort':reasoning,'max_tokens':maximum,'cache_salt':OUT.name+':'+salt}

def infer(p, stream):
    if not stream:
        return bench.request(URL,'/v1/chat/completions',p), None
    q={**p,'stream':True,'stream_options':{'include_usage':True}}
    started=time.monotonic(); first_token=None; first_content=None
    content=''; reasoning=''; usage={}; timings={}; done=False; finish=None; events=[]
    req=urllib.request.Request(URL+'/v1/chat/completions',json.dumps(q).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=1200) as response:
        for raw in response:
            line=raw.decode().strip()
            if not line.startswith('data: '):continue
            if line[6:]=='[DONE]':done=True;continue
            event=json.loads(line[6:]);events.append(event)
            usage=event.get('usage') or usage;timings=event.get('timings') or timings
            for choice in event.get('choices',[]):
                delta=choice.get('delta',{}); text=delta.get('content') or ''
                thought=delta.get('reasoning_content') or delta.get('reasoning') or ''
                if (text or thought) and first_token is None:first_token=time.monotonic()-started
                if text and first_content is None:first_content=time.monotonic()-started
                content+=text;reasoning+=thought;finish=choice.get('finish_reason') or finish
    assert done and first_content is not None and usage and timings, 'incomplete SSE response'
    result={'choices':[{'index':0,'message':{'role':'assistant','content':content,'reasoning_content':reasoning},'finish_reason':finish}],
        'usage':usage,'timings':timings}
    return result, {'events':events,'done':done,'first_token_seconds':first_token,'first_content_seconds':first_content}

def measure(key,p,stream=False,task=None,expected=None):
    before=status();healthy(before)
    bench.save(OUT/(key+'-request.json'),{**p,**({'stream':True,'stream_options':{'include_usage':True}} if stream else {})})
    bench.save(OUT/(key+'-before.json'),before)
    swap_before=bench.swap(); vm_before=subprocess.check_output(['vm_stat'],text=True)
    started=time.monotonic();reply,events=infer(p,stream);elapsed=time.monotonic()-started
    after=status()
    row={'key':key,'seconds':elapsed,'response':reply,'before':before,'after':after,
        'swap_before':swap_before,'swap_after':bench.swap(),'vm_stat_before':vm_before,
        'vm_stat_after':subprocess.check_output(['vm_stat'],text=True),
        'thermal':[before['thermal_state'],after['thermal_state']],
        'memory_pressure':[before['memory_pressure'],after['memory_pressure']],
        'metrics_delta':{k:after['metrics'][k]-before['metrics'][k] for k in bench.METRICS}}
    bench.save(OUT/(key+'-response.json'),reply)
    bench.save(OUT/(key+'-after.json'),after)
    if events:
        bench.save(OUT/(key+'-sse.json'),events)
        row['ttft_seconds']=events['first_content_seconds']
        row['first_token_seconds']=events['first_token_seconds']
    bench.save(OUT/(key+'.json'),row)
    healthy(after)
    assert after['instance']['id']==record['before']['instance']['id']
    assert after['requests']['submitted']-before['requests']['submitted']==1
    assert after['requests']['completed']-before['requests']['completed']==1
    text=reply['choices'][0]['message'].get('content') or ''
    if expected is not None:assert text.strip()==expected, 'exact output mismatch: '+key
    if task:
        check=subprocess.run([str(PYTHON),str(ROOT/'dev/benchmarks/bonsai_coding.py'),'--check',task],
            input=text,capture_output=True,text=True,timeout=3)
        row.update(correct=check.returncode==0,check_error=check.stderr[-1200:])
        bench.save(OUT/(key+'.json'),row)
        assert row['correct'], 'coding correctness failed: '+key
    else:row['correct']=True
    print(json.dumps({'key':key,'correct':row['correct'],'seconds':round(elapsed,3),
        'prompt':reply['usage']['prompt_tokens'],'generated':reply['usage']['completion_tokens'],
        'cache_n':reply['timings']['cache_n'],'pp':reply['timings']['prompt_per_second'],
        'tps':reply['timings']['predicted_per_second'],'ttft':row.get('ttft_seconds'),
        'thermal':row['thermal'],'pressure':row['memory_pressure']}),flush=True)
    return row

def cool():
    started=time.monotonic(); stable=0
    while time.monotonic()-started < 300:
        s=status();healthy(s)
        stable=stable+1 if s['thermal_state']=='nominal' else 0
        if stable>=2:return time.monotonic()-started
        time.sleep(5)
    raise RuntimeError('could not reach nominal thermals before next pair')

def smoke():
    p=payload('Reply exactly READY_OK.','ready',32,code=False)
    record['smoke']['ready']=measure('smoke-ready',p,expected='READY_OK');save()
    p=payload(bench.context_text(URL,512)+'\nReply exactly CACHE_OK.','cache',32,code=False)
    for mode in ['cold','cached']:
        row=measure('smoke-cache-'+mode,p,expected='CACHE_OK')
        record['smoke'][mode]=row;save()
        assert row['response']['timings']['cache_n']==0 if mode=='cold' else row['response']['timings']['cache_n']>=row['response']['usage']['prompt_tokens']-64
    p=payload('Use add to calculate 17 plus 25.','tool',128,code=False)
    p.update(tools=[{'type':'function','function':{'name':'add','description':'Add two integers.',
        'parameters':{'type':'object','properties':{'a':{'type':'integer'},'b':{'type':'integer'}},'required':['a','b'],'additionalProperties':False}}}],
        tool_choice={'type':'function','function':{'name':'add'}})
    row=measure('smoke-tool',p);record['smoke']['tool']=row;save()
    calls=row['response']['choices'][0]['message']['tool_calls']
    assert len(calls)==1 and calls[0]['function']['name']=='add' and json.loads(calls[0]['function']['arguments'])=={'a':17,'b':25}
    p['messages'].extend([{'role':'assistant','content':None,'tool_calls':calls},{'role':'tool','tool_call_id':calls[0]['id'],'content':'42'}])
    p['tool_choice']='none'
    row=measure('smoke-tool-result',p);record['smoke']['tool_result']=row;save()
    assert '42' in row['response']['choices'][0]['message']['content']
    row=measure('smoke-stream',payload('Reply exactly STREAM_OK.','stream',32,code=False),stream=True,expected='STREAM_OK')
    record['smoke']['stream']=row;save()
    record['smoke_passed']=True;save();print('ALL SMOKE MODES PASSED',flush=True)
