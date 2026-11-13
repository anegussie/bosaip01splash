"""Restore captured serving command with normal logs/monitor, without rebuilding."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

spec=importlib.util.spec_from_file_location('chunk_run',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def main():
    results=json.loads((r.OUT/'results.json').read_text())
    assert results['complete'] and len(results['rows'])==32
    client=r.h.Client('http://127.0.0.1:1235',r.MODEL)
    before=r.quiet(client)
    expected=json.loads((r.OUT/'production-before.json').read_text())
    assert before['identity']==expected['identity']
    for name,digest in json.loads((r.OUT/'binary-sha256.json').read_text()).items():
        assert r.sha(r.ROOT/'build'/name)==digest, 'production artifact changed'
    command=json.loads((r.OUT/'finish-restore-command.json').read_text())
    command[0]=str(r.ROOT/'.venv/bin/python')
    logdir=Path.home()/'.local/state/llama-server'
    alias='qwen3.8-flash-next-q2-0-dflash2-bf16-splash'
    logfile=logdir/(alias+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    assert not logfile.exists()
    native=subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
    os.kill(before['instance']['pid'],signal.SIGINT)
    deadline=time.monotonic()+120
    while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
        assert time.monotonic()<deadline
        time.sleep(1)
    env={**os.environ,'PYTHONPATH':str(r.ROOT),'SPLASH_TELEMETRY_PATH':str(logfile)+'.jsonl'}
    with logfile.open('w') as stream:
        stream.write('['+datetime.datetime.now().astimezone().isoformat()+'] Restored original option 21 command after chunk/context benchmark; no rebuild.\n')
        stream.write(f'Launcher: model={r.MODEL} alias={alias} binary={r.ROOT / "build/splash"} server_context=131072 reasoning=none kv=int8 state=bf16 prefill_chunk=2048 cache_disk=3G cache_mode=persistent\n')
        stream.flush()
        process=subprocess.Popen(command,cwd=r.ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    # Record recovery information before waiting for readiness.
    r.save(r.OUT/'normal-logging-process.json',dict(pid=process.pid,command=command,log=str(logfile),telemetry=str(logfile)+'.jsonl'))
    after=r.wait_ready(client,process)
    assert after['identity']==expected['identity']
    for key in ('maximum_context_tokens','prefill_chunk_tokens'):
        assert after[key]==expected[key]
    r.save(r.OUT/'production-restored.json',after)
    for name in ('splash-latest.log',alias+'-latest.log'):
        link=logdir/name
        temp=logdir/(name+'.benchmark-restore-'+str(os.getpid()))
        temp.symlink_to(logfile)
        temp.replace(link)
    monitor_env={**env,'LLAMA_HOST':'127.0.0.1','LLAMA_PORT':'1235','LLAMA_LOG_DIR':str(logdir),
                 'SPLASH_MONITOR_OWNER_PID':str(process.pid),'SPLASH_MONITOR_TTY':''}
    existing=[]
    for line in subprocess.check_output(['ps','-axo','pid,command'],text=True).splitlines()[1:]:
        fields=line.strip().split(None,1)
        if len(fields)==2 and str(Path.home()/'monitorsplash.sh') in fields[1] and '--record' in fields[1]:
            existing.append(int(fields[0]))
    monitor=None
    if existing:
        monitor_pid=existing[0]
    else:
        with (r.WORK/'production-monitor-restored.log').open('w') as stream:
            monitor=subprocess.Popen(['bash',str(Path.home()/'monitorsplash.sh'),'--record','2'],cwd=r.ROOT,env=monitor_env,
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        monitor_pid=monitor.pid
    time.sleep(5)
    if monitor is not None:
        assert monitor.poll() is None, 'performance monitor exited'
    os.kill(monitor_pid,0)
    telemetry=Path(str(logfile)+'.jsonl')
    assert telemetry.exists() and telemetry.stat().st_size>0
    r.save(r.OUT/'normal-logging-restored.json',dict(server_pid=process.pid,monitor_pid=monitor_pid,monitor_reused=bool(existing),
        log=str(logfile),telemetry=str(telemetry),identity=after['identity']))
    print('Original option 21 restored with unchanged build/profile, live log, JSONL telemetry and performance monitoring.',flush=True)
    print('Log:',logfile,flush=True)


if __name__=='__main__':
    main()
