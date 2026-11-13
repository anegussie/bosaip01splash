"""Matched option-21 chunk/context ABBA; reuses the established serving probes."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
OUT = OUT / 'clean-run'
OUT.mkdir(exist_ok=True)
WORK = ROOT / 'build/validation/option21-chunk-context-20261113-clean'
MODEL = 'ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0'
SIZES = (8192, 32768, 65536, 102400)
spec = importlib.util.spec_from_file_location('existing_probe', ROOT / 'dev/benchmarks/option20_serving_matrix.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
# Enough counting work to measure sustained decode rather than an eight-token probe.
h.SMOKE_TAIL = '\nReturn the secret code, then list the integers from 1 through 1000 in order. No explanation.'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def system():
    out = {}
    for command in (['vm_stat'], ['sysctl', 'vm.swapusage'], ['pmset', '-g', 'therm']):
        p = subprocess.run(command, text=True, capture_output=True)
        out[' '.join(command)] = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        assert p.returncode == 0, out
    return out


def wait_ready(client, process, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert process.poll() is None, f'server exited {process.returncode}'
        try:
            s = client.status()
            if s.get('ready'):
                return s
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('readiness timeout')


def quiet(client):
    s = client.status()
    assert not s['active_requests'] and s['http']['requests']['active'] <= 1, 'foreign request active'
    return s


def command_for(command, *, chunk, cache, binary):
    command = list(command)
    replacements = {'--port': '1236', '--binary': str(binary), '--prefill-chunk-tokens': str(chunk),
                    '--cache-dir': str(cache), '--default-reasoning-effort': 'none'}
    for flag, value in replacements.items():
        for i, arg in enumerate(command):
            if arg == flag:
                command[i + 1] = value
                break
            if arg.startswith(flag + '='):
                command[i] = flag + '=' + value
                break
        else:
            command.extend([flag, value])
    command[0] = str(ROOT / '.venv/bin/python')
    return command


@contextlib.contextmanager
def serving(command, directory):
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / 'command.json', command)
    with (directory / 'server.log').open('w') as log:
        p = subprocess.Popen(command, cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT)}, stdout=log, stderr=subprocess.STDOUT)
        client = h.Client('http://127.0.0.1:1236', MODEL)
        stop = threading.Event()
        def monitor():
            with (directory / 'monitor.jsonl').open('w') as stream:
                while not stop.wait(2):
                    try:
                        s = client.status()
                        stream.write(json.dumps(dict(time=time.time(), state=h.scalar_state(s),
                            experts=s.get('streamed_experts'), requests=s.get('requests'))) + '\n')
                        stream.flush()
                    except OSError:
                        pass
        thread = threading.Thread(target=monitor, daemon=True)
        try:
            ready = wait_ready(client, p)
            save(directory / 'ready.json', ready)
            thread.start()
            yield client
        finally:
            stop.set()
            if thread.is_alive():
                thread.join(15)
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:
                    code = p.wait(60)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    p.wait(30)
                    raise RuntimeError('benchmark server required termination')
                assert code == 0, f'benchmark server exit {code}'


def probe(client, directory, name, prompt, budget, cached=None):
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / (name + '-system-before.json'), system())
    row = h.run_probe(client, directory, name, prompt, budget, directory.name, 'nominal')
    save(directory / (name + '-system-after.json'), system())
    if not name.startswith('code-'):
        numbers = [int(n) for n in re.findall(r'\d+', row['text'])]
        # The response excerpt is capped at 400 characters; ignore only a final partial integer.
        row['semantic_correct'] = h.smoke_gate_ok(row['text']) and all(n == i for i, n in enumerate(numbers[:-1], 1))
    else:
        row['semantic_correct'] = row['correct']
    save(directory / (name + '.json'), row)
    assert row['clean'] and row['correct'] and row['semantic_correct'], f'{name}: correctness/contention gate'
    assert row['status_after']['transport']['restarts'] == 0, 'runtime restarted'
    if cached is False:
        assert row['cached_tokens'] == 0, 'cold prefix unexpectedly reused'
    if cached is True:
        assert row['cached_tokens'] >= row['content_tokens_pinned'] - 128, 'cache round-trip failed'
    return row


def main():
    assert not (OUT / 'contract.json').exists(), 'Do not overwrite evidence'
    WORK.mkdir(parents=True, exist_ok=True)
    before = quiet(h.Client('http://127.0.0.1:1235', MODEL))
    assert before['instance']['model'] == MODEL
    save(OUT / 'production-before.json', before)
    command = shlex.split(subprocess.check_output(['ps', '-p', str(before['instance']['pid']), '-ww', '-o', 'command='], text=True).strip())
    save(OUT / 'restore-command.json', command)
    binary_dir = WORK / 'binaries'
    binary_dir.mkdir()
    binary_manifest = {}
    for name in ('splash', 'splash.metallib', 'host-step.metallib'):
        src = ROOT / 'build' / name
        digest = sha(src)
        shutil.copy2(src, binary_dir / name)
        assert sha(src) == sha(binary_dir / name) == digest, 'artifact changed while snapshotting'
        binary_manifest[name] = digest
    save(OUT / 'binary-sha256.json', binary_manifest)
    save(OUT / 'contract.json', dict(model=MODEL, contexts=SIZES, order=['A1-2048','B1-1024','B2-1024','A2-2048'],
        output_budget=512, thinking=False, temperature=1.0, top_p=0.95, server_context=131072,
        max_memory=11596411699, prefix_quota=3221225472, active_requests=1,
        workloads='ORCHID recall plus ordered counting; executable code-3 smoke, not a representative coding benchmark',
        cold_definition='zero reused prefix; model and OS caches warmed',
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=subprocess.check_output(['git','status','--short'],text=True).splitlines()))
    rows = []
    stopped = False
    try:
        quiet(h.Client('http://127.0.0.1:1235', MODEL))
        native = subprocess.check_output(['pgrep','-P',str(before['instance']['pid'])],text=True).split()
        os.kill(before['instance']['pid'], signal.SIGINT)
        stopped = True
        deadline = time.monotonic() + 120
        while any(subprocess.run(['ps','-p',pid,'-o','pid='],capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic() < deadline, 'production native process did not exit'
            time.sleep(1)
        print('Production stopped cleanly; testing both smoke/restart gates', flush=True)
        prompts = {}
        for chunk in (2048, 1024):
            with tempfile.TemporaryDirectory(prefix=f'prefix-smoke-{chunk}-',dir=WORK) as cache:
                cmd = command_for(command, chunk=chunk, cache=cache, binary=binary_dir/'splash')
                with serving(cmd, OUT/f'smoke-{chunk}') as client:
                    s=client.status()
                    assert s['prefill_chunk_tokens']==chunk and s['maximum_context_tokens']==131072
                    assert s['identity']['cache']['build_id']==before['identity']['cache']['build_id']
                    prompt,_=h.build_prompt(client,'pre-8192','chunk-smoke')
                    probe(client,OUT/f'smoke-{chunk}','pre-smoke-cold',prompt,512,False)
                    probe(client,OUT/f'smoke-{chunk}','pre-smoke-reuse',prompt,512,True)
                    probe(client,OUT/f'smoke-{chunk}','code-3',h.CODE_TASKS['code-3'][0],192,False)
                    cross,_=h.build_prompt(client,'pre-32768','chunk-smoke-32768')
                    probe(client,OUT/f'smoke-{chunk}','pre-cross-context-cold',cross,512,False)
                    for size in SIZES:
                        prompts[size]=h.build_prompt(client,f'pre-{size}',f'chunk-context-{size}')[0]
                with serving(cmd, OUT/f'smoke-{chunk}-restart') as client:
                    probe(client,OUT/f'smoke-{chunk}-restart','pre-smoke-restored',prompt,512,True)
            print(f'SMOKE PASS chunk={chunk}: cold/reuse, executable code and restart restore',flush=True)
        for label,chunk in [('A1-2048',2048),('B1-1024',1024),('B2-1024',1024),('A2-2048',2048)]:
            directory=OUT/label
            with tempfile.TemporaryDirectory(prefix=f'prefix-{label}-',dir=WORK) as cache:
                cmd=command_for(command,chunk=chunk,cache=cache,binary=binary_dir/'splash')
                with serving(cmd,directory) as client:
                    ready=client.status()
                    assert ready['prefill_chunk_tokens']==chunk and ready['maximum_context_tokens']==131072
                    assert ready['identity']['kv']==before['identity']['kv']
                    assert ready['identity']['cache']['build_id']==before['identity']['cache']['build_id']
                    warm,_=h.build_prompt(client,'smoke',f'warm-{label}')
                    probe(client,directory,'warmup',warm,96,False)
                    for size in SIZES:
                        for mode in ('cold','reuse'):
                            row=probe(client,directory,f'pre-{size}-{mode}',prompts[size],512,mode=='reuse')
                            row.update(arm=label,chunk=chunk,context=size,mode=mode)
                            rows.append(row)
                            save(OUT/'results.json',dict(complete=False,rows=rows))
            print(f'ARM COMPLETE {label}',flush=True)
        save(OUT/'results.json',dict(complete=True,rows=rows))
    finally:
        if stopped:
            command[0]=str(ROOT/'.venv/bin/python')
            logpath=WORK/'production-restored-live.log'
            with logpath.open('ab') as log:
                p=subprocess.Popen(command,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            save(OUT/'restored-process.json',dict(pid=p.pid,command=command,log=str(logpath)))
            restored=wait_ready(h.Client('http://127.0.0.1:1235',MODEL),p)
            save(OUT/'production-restored.json',restored)
            assert restored['identity']==before['identity']
            assert restored['prefill_chunk_tokens']==before['prefill_chunk_tokens']
            assert restored['maximum_context_tokens']==before['maximum_context_tokens']
            print('PRODUCTION RESTORED: matching build/model/context/chunk/cache',flush=True)


if __name__ == '__main__':
    main()
