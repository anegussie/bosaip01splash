"""Finish independent remaining contexts while retaining the failed 32K control observation."""
import importlib.util
import json
import os
import shlex
import signal
import subprocess
import tempfile
import time

from pathlib import Path

spec = importlib.util.spec_from_file_location('chunk_run', Path(__file__).with_name('run.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def main():
    data=json.loads((r.OUT/'results.json').read_text())
    assert not data['complete'] and len(data['rows'])==26
    assert all(x['clean'] and x['semantic_correct'] for x in data['rows'])
    contract=json.loads((r.OUT/'contract.json').read_text())
    contract['order'].append('A2-2048-resume')
    contract['resume_note'] += ' A2-2048 timed 32K cold returned only ORCHID (4 output tokens) and failed semantic correctness. That failed observation is retained, excluded from throughput aggregates, and not retried as a timed cold trial. Production restored. The final five independent requests run in a fresh A2-2048-resume process; an untimed one-token 32K prefill establishes the prefix before the original cached trial. These interruptions limit attribution.'
    failed=json.loads((r.OUT/'A2-2048/pre-32768-cold.json').read_text())
    failed.update(arm='A2-2048',chunk=2048,context=32768,mode='cold',valid_for_timing=False,failure='Model stopped after ORCHID and omitted the requested counting sequence')
    data['rows'].append(failed)
    r.save(r.OUT/'results.json',data)
    r.save(r.OUT/'contract.json',contract)
    binary=r.WORK/'binaries/splash'
    manifest=json.loads((r.OUT/'binary-sha256.json').read_text())
    for name,digest in manifest.items():
        assert r.sha(binary.parent/name)==r.sha(r.ROOT/'build'/name)==digest
    before=r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
    original=json.loads((r.OUT/'production-before.json').read_text())
    assert before['identity']==original['identity']
    r.save(r.OUT/'production-finish-before.json',before)
    command=shlex.split(subprocess.check_output(['ps','-p',str(before['instance']['pid']),'-ww','-o','command='],text=True).strip())
    r.save(r.OUT/'finish-restore-command.json',command)
    stopped=False
    rows=data['rows']
    try:
        r.quiet(r.h.Client('http://127.0.0.1:1235',r.MODEL))
        native=subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
        os.kill(before['instance']['pid'],signal.SIGINT)
        stopped=True
        deadline=time.monotonic()+120
        while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic()<deadline
            time.sleep(1)
        for label,chunk in [('A2-2048-resume',2048)]:
            directory=r.OUT/label
            assert not directory.exists(), 'Do not overwrite an attempted arm'
            with tempfile.TemporaryDirectory(prefix=f'prefix-{label}-',dir=r.WORK) as cache:
                cmd=r.command_for(command,chunk=chunk,cache=cache,binary=binary)
                with r.serving(cmd,directory) as client:
                    ready=client.status()
                    assert ready['identity']['kv']==before['identity']['kv']
                    assert ready['identity']['cache']['build_id']==before['identity']['cache']['build_id']
                    assert ready['prefill_chunk_tokens']==chunk and ready['maximum_context_tokens']==131072
                    tail=r.h.SMOKE_TAIL
                    r.h.SMOKE_TAIL='\nReturn the secret code, then list the integers from 1 through 30 in order. No explanation.'
                    warm,_=r.h.build_prompt(client,'smoke',f'warm-{label}')
                    r.h.SMOKE_TAIL=tail
                    r.probe(client,directory,'warmup',warm,96,False)
                    print('FOCUSED WARMUP PASS',label,flush=True)
                    preload,_=r.h.build_prompt(client,'pre-32768','chunk-context-32768')
                    loaded=r.h.run_probe(client,directory,'pre-32768-preload',preload,1,'untimed-cache-preload','nominal')
                    assert loaded['clean'] and loaded['cached_tokens']==0 and loaded['complete_sse']
                    print('UNTIMED 32K CACHE PRELOAD PASS',flush=True)
                    for size in (32768,65536,102400):
                        prompt,_=r.h.build_prompt(client,f'pre-{size}',f'chunk-context-{size}')
                        for mode in (('reuse',) if size==32768 else ('cold','reuse')):
                            row=r.probe(client,directory,f'pre-{size}-{mode}',prompt,512,mode=='reuse')
                            row.update(arm=label,chunk=chunk,context=size,mode=mode)
                            rows.append(row)
                            r.save(r.OUT/'results.json',dict(complete=False,rows=rows))
            print('ARM COMPLETE',label,flush=True)
        r.save(r.OUT/'results.json',dict(complete=True,rows=rows))
    finally:
        if stopped:
            command[0]=str(r.ROOT/'.venv/bin/python')
            logpath=r.WORK/'production-restored-final-live.log'
            with logpath.open('ab') as log:
                process=subprocess.Popen(command,cwd=r.ROOT,env={**os.environ,'PYTHONPATH':str(r.ROOT)},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            r.save(r.OUT/'restored-process.json',dict(pid=process.pid,command=command,log=str(logpath)))
            after=r.wait_ready(r.h.Client('http://127.0.0.1:1235',r.MODEL),process)
            r.save(r.OUT/'production-restored.json',after)
            assert after['identity']==before['identity']
            assert after['maximum_context_tokens']==before['maximum_context_tokens']
            assert after['prefill_chunk_tokens']==before['prefill_chunk_tokens']
            print('PRODUCTION RESTORED: matching build/model/context/chunk/cache',flush=True)


if __name__=='__main__':
    main()
