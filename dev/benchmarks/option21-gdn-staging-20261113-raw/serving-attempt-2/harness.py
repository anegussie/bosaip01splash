"""Matched 8K serving check; change only the Metal library, restore production."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('validation',HERE/'validate.py')
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
r=v.r
OUT=HERE/'serving-attempt-2'
# The baseline sometimes answered only ORCHID to the previous recall/count task.
# Give both arms the full output sequence to copy and retain the strict gate.
r.h.SMOKE_TAIL='\nCopy the following line exactly. Include every integer and no explanation:\nORCHID '+', '.join(map(str,range(1,301)))


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=str)+'\n')


def main():
    assert (HERE/'attempt-2/gpu-validation-complete.json').exists(), 'GPU gates must pass first'
    OUT.mkdir(exist_ok=True)
    assert not (OUT/'contract.json').exists(), 'Do not overwrite a serving attempt'
    before=r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
    command=shlex.split(subprocess.check_output(['ps','-p',str(before['instance']['pid']),'-ww','-o','command='],text=True).strip())
    save('contract.json',dict(model=r.MODEL,context=before['maximum_context_tokens'],chunk=2048,
        max_memory=11596411699,kv='int8',state='bf16',smoke_prompt=2048,timed_prompt=8192,
        output_budget=128,order=['A1','B1','B2','A2'],A='FP32 staging',B='BF16 staging',
        workload='explicit ORCHID and integer-sequence copying, executable Python smoke',
        temperature=1.0,top_p=0.95,
        cold='zero reused prefix, warmed model and filesystem caches',
        executable_sha256=r.sha(v.BASE/'splash'),baseline_library_sha256=r.sha(v.BASE/'splash.metallib'),
        candidate_library_sha256=r.sha(v.CAND/'splash.metallib')))
    save('production-before.json',before)
    stopped=False
    rows=[]
    try:
        native=subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
        r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
        os.kill(before['instance']['pid'],signal.SIGINT)
        stopped=True
        deadline=time.monotonic()+120
        while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic()<deadline
            time.sleep(1)
        for arm,binary in [('A',v.BASE/'splash'),('B',v.CAND/'splash')]:
            with tempfile.TemporaryDirectory(prefix='gdn-smoke-'+arm+'-',dir=v.WORK) as cache:
                cmd=r.command_for(command,chunk=2048,cache=cache,binary=binary)
                directory=OUT/('smoke-'+arm)
                with r.serving(cmd,directory) as client:
                    assert client.status()['maximum_context_tokens']==102400
                    prompt,_=r.h.build_prompt(client,'pre-2048','gdn-smoke')
                    r.probe(client,directory,'pre-cold',prompt,96,False)
                    r.probe(client,directory,'pre-reuse',prompt,96,True)
                    r.probe(client,directory,'code-3',r.h.CODE_TASKS['code-3'][0],192,False)
                    timed,_=r.h.build_prompt(client,'pre-8192','gdn-staging-timed')
                with r.serving(cmd,OUT/('smoke-'+arm+'-restart')) as client:
                    r.probe(client,OUT/('smoke-'+arm+'-restart'),'pre-restored',prompt,96,True)
            print('SMOKE PASS',arm,flush=True)
        for label in ['A1','B1','B2','A2']:
            binary=(v.BASE if label.startswith('A') else v.CAND)/'splash'
            with tempfile.TemporaryDirectory(prefix='gdn-'+label+'-',dir=v.WORK) as cache:
                cmd=r.command_for(command,chunk=2048,cache=cache,binary=binary)
                directory=OUT/label
                with r.serving(cmd,directory) as client:
                    # Identical warmup precedes every measured cold/reuse pair.
                    r.probe(client,directory,'pre-warm',prompt,64,False)
                    for name,cached in [('pre-cold',False),('pre-reuse',True)]:
                        row=r.probe(client,directory,name,timed,128,cached)
                        row['arm']=label
                        rows.append(row)
                        save('rows.json',rows)
            print('TIMED PASS',label,flush=True)
        save('complete.json',dict(passed=True,requests=len(rows)))
    finally:
        if stopped:v.restore(command,before)


if __name__=='__main__':main()
