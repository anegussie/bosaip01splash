"""Sequential option-19 characterization, with guaranteed production restore."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import threading
import time

ARTIFACTS = Path(__file__).resolve().parent
ROOT = ARTIFACTS.parents[2]
OUT = ARTIFACTS / 'attempt-2'
WORK = ROOT / 'build/validation/option19-postmerge-20261118-attempt-2'
MODEL = 'unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS'
MODEL_ROOT = ROOT / 'install/models/.resolved/f2cc941e42a5753efdc2e0b057d9ef2c5e5bb79bf5a7323a5bc2d4bba61fece1'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

h=load('historical_helpers',ARTIFACTS/'historical_helpers.py')
r=load('restoration_helpers',ROOT/'dev/benchmarks/option21-chunk-context-20261113-raw/run.py')
v=load('restore_production',ROOT/'dev/benchmarks/option21-gdn-staging-20261113-raw/validate.py')
v.OUT=OUT
v.WORK=WORK
save=r.save


def command(directory):
    return [str(ROOT/'.venv/bin/python'),'-u','-P','-m','server.server',str(MODEL_ROOT),'--model',MODEL,
            '--binary',str(WORK/'binaries/splash'),'--port','1236','--serve-record',str(directory/'serve.json'),
            '--max-context','81920','--max-memory','10737418240','--expert-memory','auto',
            '--prefill-chunk-tokens','512','--max-active-requests','1','--resource-wait-timeout','60',
            '--kv-format','int8','--state-format','bf16','--max-cache-disk','2147483648',
            '--persistent-cache','--cache-dir',str(directory/'cache'),'--default-reasoning-effort','none',
            '--served-model-name',h.ALIAS,'--max-image-pixels','1048576']


@contextlib.contextmanager
def serving(directory,cache_directory=None):
    directory.mkdir(parents=True,exist_ok=True)
    args=command(cache_directory or directory)
    save(directory/'command.json',args)
    stop=threading.Event()
    def monitor():
        with (directory/'monitor.jsonl').open('w') as stream:
            while not stop.wait(2):
                try:
                    s=h.status()
                    fields=['thermal_state','memory_pressure','system_pressure','active_requests','streamed_experts','disk','kv','metal','requests','transport']
                    stream.write(json.dumps(dict(time=time.time(),**{k:s.get(k) for k in fields}))+'\n')
                    stream.flush()
                except OSError:pass
    with (directory/'server.log').open('w') as log:
        p=subprocess.Popen(args,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},stdout=log,stderr=subprocess.STDOUT)
        thread=threading.Thread(target=monitor,daemon=True)
        try:
            ready=r.wait_ready(r.h.Client(h.URL,MODEL),p)
            save(directory/'ready.json',ready)
            h.healthy(ready)
            assert ready['instance']['model']==MODEL and ready['maximum_context_tokens']==81920
            assert ready['prefill_chunk_tokens']==2048 and ready['identity']['kv']['format']=='int8', (ready['prefill_chunk_tokens'], ready['identity']['kv'])
            assert ready['memory_plan']['model']['state_format']=='bf16' and ready['verify_rows']=='auto'
            assert ready['memory_governor']['limit_bytes']==10737418240
            assert ready['disk']['persistent'] and ready['disk']['limit_bytes']==2147483648
            assert ready['identity']['cache']['build_id']==h.record['build_id']
            h.record['before']=ready
            save(directory/'ready.json',ready)
            thread.start()
            yield
        finally:
            stop.set()
            if thread.is_alive():thread.join(10)
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:p.wait(45)
                except subprocess.TimeoutExpired:
                    p.terminate();p.wait(15)
                    raise RuntimeError('benchmark server required termination')
            assert p.returncode==0, f'server exit {p.returncode}'


def timed(directory,repeat):
    h.OUT=directory
    directory.mkdir(parents=True,exist_ok=True)
    rows=[]
    for depth,task,expected in [(4096,'stable_unique',4013),(32768,'chunked',32689),(57344,'chunked',57259)]:
        cooldown=h.cool()
        payload=h.payload(h.bench.context_text(h.URL,depth)+'\nTask: '+h.bonsai_coding.TASKS[task][0],f'pass-{repeat}:{depth}')
        for mode in ['cold','cached']:
            key=f'{depth}-{mode}'
            row=h.measure(key,payload,stream=True,task=task)
            response=row['response']; prompt=response['usage']['prompt_tokens'];cached=response['timings']['cache_n']
            assert prompt==expected, f'filled prompt drift {prompt} != {expected}'
            assert cached==0 if mode=='cold' else cached>=prompt-64
            assert not response['choices'][0]['message']['reasoning_content'], 'reasoning unexpectedly enabled'
            assert row['after']['transport']['restarts']==0
            row.update(depth=depth,repeat=repeat,mode=mode,task=task,cooldown_seconds=cooldown)
            rows.append(row)
            save(directory/(key+'.json'),row)
            global_rows.append(row)
            save(OUT/'rows.json',global_rows)
    return rows


global_rows=[]
def main():
    assert not OUT.exists(),'do not overwrite evidence'
    OUT.mkdir(parents=True)
    WORK.mkdir(parents=True,exist_ok=True)
    original_client=r.h.Client('http://127.0.0.1:1235',r.MODEL)
    before=r.quiet(original_client)
    save(OUT/'production-before.json',before)
    original=shlex.split(subprocess.check_output(['ps','-p',str(before['instance']['pid']),'-ww','-o','command='],text=True).strip())
    save(OUT/'restore-command.json',original)
    binary_dir=WORK/'binaries';binary_dir.mkdir()
    hashes={}
    for name in ['splash','splash.metallib','host-step.metallib']:
        source=ROOT/'build'/name;hashes[name]=r.sha(source)
        shutil.copy2(source,binary_dir/name)
        assert r.sha(binary_dir/name)==r.sha(source)==hashes[name]
    save(OUT/'binary-sha256.json',hashes)
    save(OUT/'model-manifest.json',json.loads((MODEL_ROOT/'model.json').read_text()))
    identity=json.loads((ROOT/'build/engine/build-identity.json').read_text())
    h.record=dict(smoke={},smoke_passed=False,build_id=identity['build_id'])
    save(OUT/'contract.json',dict(model=MODEL,build=identity,head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),profile=command(WORK/'pass-1'),trials=3,filled_prompts=[4013,32689,57259],sampling=dict(temperature=0,seed=42,reasoning_effort='none',max_tokens=384),baseline='qwen36-option19-10g-evaluation-20261105.json, 10G/512 only',comparison='historical, not causal merge A/B',timing='SSE TTFT from before HTTP request, matching recovered historical helper'))
    dirty=['dev/benchmarks/test_bonsai_launcher.py','install/assembly.py','install/hub.py','install/models.py']
    save(OUT/'preservation.json',{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in dirty})
    stopped=False
    try:
        native=subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
        r.quiet(original_client)
        os.kill(before['instance']['pid'],signal.SIGINT);stopped=True
        deadline=time.monotonic()+120
        while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic()<deadline,'native shutdown timeout'
            time.sleep(1)
        for repeat in [1,2,3]:
            directory=WORK/f'pass-{repeat}'
            evidence=OUT/f'pass-{repeat}';evidence.mkdir()
            with serving(directory):
                h.OUT=evidence
                h.record['smoke']={};h.record['smoke_passed']=False
                h.smoke()
                assert h.record['smoke_passed']
                # Untimed executable coding check before the timed matrix.
                payload=h.payload(h.bonsai_coding.TASKS['stable_unique'][0],'coding-smoke')
                h.measure('smoke-code',payload,stream=True,task='stable_unique')
                timed(evidence,repeat)
            if repeat==1:
                with serving(WORK/'restart-smoke',directory):
                    h.OUT=OUT/'restart-smoke';h.OUT.mkdir()
                    task='stable_unique';depth=4096
                    # Same cache salt and messages as pass 1, independent of evidence directory.
                    payload=h.payload(h.bench.context_text(h.URL,depth)+'\nTask: '+h.bonsai_coding.TASKS[task][0],'pass-1:4096')
                    payload['cache_salt']='pass-1:pass-1:4096'
                    row=h.measure('persisted-coding',payload,stream=True,task=task)
                    assert row['response']['timings']['cache_n']>=row['response']['usage']['prompt_tokens']-64
                    save(OUT/'restart-passed.json',dict(passed=True))
        save(OUT/'complete.json',dict(passed=True,requests=len(global_rows)))
    finally:
        if stopped:v.restore(original,before)

if __name__=='__main__':main()
