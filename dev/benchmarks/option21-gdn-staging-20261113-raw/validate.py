"""Serial GPU correctness and profiling; always restore the captured service."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

ARTIFACTS=Path(__file__).resolve().parent
ROOT=ARTIFACTS.parents[2]
OUT=ARTIFACTS/'attempt-2'
OUT.mkdir(exist_ok=True)
WORK=ROOT/'build/validation/option21-gdn-staging-20261113'
BASE=WORK/'baseline'
CAND=WORK/'candidate'
spec=importlib.util.spec_from_file_location('serving_helpers',ROOT/'dev/benchmarks/option21-chunk-context-20261113-raw/run.py')
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=str)+'\n')


def run(name,command,timeout=600):
    save(name+'-command.json',command)
    save(name+'-system-before.json',r.system())
    with (OUT/(name+'.log')).open('w') as stream:
        result=subprocess.run([str(x) for x in command],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    save(name+'-system-after.json',r.system())
    save(name+'-exit.json',dict(exit_code=result.returncode))
    assert result.returncode==0, f'{name} failed; see {OUT/(name+".log")}'
    print('PASS',name,flush=True)


def restore(command,before):
    command[0]=str(ROOT/'.venv/bin/python')
    alias='qwen3.8-flash-next-q2-0-dflash2-bf16-splash'
    logdir=Path.home()/'.local/state/llama-server'
    log=logdir/(alias+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    env={**os.environ,'PYTHONPATH':str(ROOT),'SPLASH_TELEMETRY_PATH':str(log)+'.jsonl'}
    with log.open('w') as stream:
        stream.write(f'Launcher: model={r.MODEL} server_context={before["maximum_context_tokens"]} reasoning=none kv=int8 state=bf16 prefill_chunk=2048 cache_disk=3G cache_mode=persistent\n')
        stream.flush()
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    save('restored-process.json',dict(pid=process.pid,command=command,log=str(log)))
    after=r.wait_ready(r.h.Client('http://127.0.0.1:1235',r.MODEL),process)
    assert after['identity']==before['identity']
    assert after['maximum_context_tokens']==before['maximum_context_tokens']
    assert after['prefill_chunk_tokens']==before['prefill_chunk_tokens']
    save('production-restored.json',after)
    for name in ['splash-latest.log',alias+'-latest.log']:
        temp=logdir/(name+'.kernel-validation-'+str(os.getpid()))
        temp.symlink_to(log)
        temp.replace(logdir/name)
    monitors=[]
    for line in subprocess.check_output(['ps','-axo','pid,command'],text=True).splitlines()[1:]:
        fields=line.strip().split(None,1)
        if len(fields)==2 and str(Path.home()/'monitorsplash.sh') in fields[1] and '--record' in fields[1]:monitors.append(int(fields[0]))
    if not monitors:
        with (WORK/'restored-monitor.log').open('w') as stream:
            monitor=subprocess.Popen(['bash',str(Path.home()/'monitorsplash.sh'),'--record','2'],cwd=ROOT,
                env={**env,'LLAMA_HOST':'127.0.0.1','LLAMA_PORT':'1235','SPLASH_MONITOR_OWNER_PID':str(process.pid),'SPLASH_MONITOR_TTY':''},
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        monitors=[monitor.pid]
    save('restored-logging.json',dict(log=str(log),monitor_pids=monitors))
    print('PRODUCTION RESTORED: original binary, context, chunk, identity and logging',flush=True)


def main():
    assert not (OUT/'gpu-validation-start.json').exists(), 'Do not overwrite a validation attempt'
    for root in [BASE,CAND]:
        assert (root/'splash').exists() and (root/'splash.metallib').exists() and (root/'host-step.metallib').exists()
    assert r.sha(BASE/'splash')==r.sha(CAND/'splash')
    save('candidate-sha256.json',{name:r.sha(CAND/name) for name in ['splash','splash.metallib','host-step.metallib']})
    save('gpu-validation-start.json',dict(started=time.time()))
    before=r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
    save('production-before.json',before)
    command=shlex.split(subprocess.check_output(['ps','-p',str(before['instance']['pid']),'-ww','-o','command='],text=True).strip())
    save('restore-command.json',command)
    stopped=False
    try:
        native=subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
        r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
        os.kill(before['instance']['pid'],signal.SIGINT)
        stopped=True
        deadline=time.monotonic()+120
        while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic()<deadline
            time.sleep(1)
        print('Production stopped; running GPU gates',flush=True)
        test=WORK/'gdn-compare'
        run('gdn-baseline-reference',[test,BASE/'splash.metallib'])
        run('gdn-candidate-reference',[test,CAND/'splash.metallib'])
        run('gdn-cross-library',[test,BASE/'splash.metallib','--compare',CAND/'splash.metallib'])
        run('attention-current-profile',[BASE/'engine-tests/attention-sweep',BASE/'splash.metallib',
            '--shapes','fn','--histories','8192,32768,102400','--lanes','1','--phases','prefill','--repeat','3',
            '--qsa','indexer','--qsa-top-blocks','1024'])
        run('moe-q20-smoke',[BASE/'engine-tests/gguf-moe-benchmark',BASE/'splash.metallib','flash-next','1'])
        run('moe-mixed-shared-smoke',[BASE/'engine-tests/gguf-moe-benchmark',BASE/'splash.metallib',
            'flash-next','1','q20','q20','q3k','q20','q20'])
        model_root=ROOT/'install/models/.resolved/974a9097bfe4bac04bb2a2e140d198f4cfdfced31d44091318906778ad109439'
        run('actual-model-profile',[BASE/'engine-tests/decode-profile',BASE/'splash.metallib',model_root,
            '--prompt-tokens','8192','--cycles','1','--max-lanes','1','--prefill-chunk-tokens','2048',
            '--state-format','bf16','--kv-format','int8','--expert-memory','2G','--ple-memory','64M'],timeout=1200)
        save('gpu-validation-complete.json',dict(complete=True,finished=time.time()))
    finally:
        if stopped:restore(command,before)


if __name__=='__main__':main()
