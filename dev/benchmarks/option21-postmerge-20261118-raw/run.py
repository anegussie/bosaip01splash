"""Serial postmerge characterization using the archived option-21 workload."""
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent
ROOT = ARTIFACTS.parents[2]
OUT = ARTIFACTS / 'attempt-3'
OUT.mkdir(exist_ok=True)
WORK = ROOT / 'build/validation/option21-postmerge-20261118-attempt-3'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

r = load('archived', ROOT / 'dev/benchmarks/option21-chunk-context-20261113-raw/run.py')
v = load('restoration', ROOT / 'dev/benchmarks/option21-gdn-staging-20261113-raw/validate.py')
v.OUT = OUT
v.WORK = WORK
h = r.h
save = r.save


def probe(client, directory, name, prompt, budget, cached):
    directory.mkdir(parents=True, exist_ok=True)
    original = urllib.request.urlopen
    parts = []
    reasoning = []
    class Capture:
        def __init__(self, response):
            self.response = response
        def __enter__(self):
            self.response.__enter__()
            self.stream = (directory / (name + '-sse.txt')).open('wb')
            return self
        def __exit__(self, *args):
            self.stream.close()
            return self.response.__exit__(*args)
        def __iter__(self):
            for raw in self.response:
                self.stream.write(raw)
                self.stream.flush()
                if raw.startswith(b'data:') and raw.strip() != b'data: [DONE]':
                    event = json.loads(raw[5:])
                    for choice in event.get('choices', []):
                        delta = choice.get('delta') or {}
                        parts.append(delta.get('content') or '')
                        reasoning.append(delta.get('reasoning_content') or '')
                yield raw
    def capture(request, *args, **kwargs):
        response = original(request, *args, **kwargs)
        if hasattr(request, 'full_url') and request.full_url.endswith('/v1/chat/completions'):
            save(directory / (name + '-request.json'), json.loads(request.data))
            return Capture(response)
        return response
    urllib.request.urlopen = capture
    try:
        row = r.probe(client, directory, name, prompt, budget, cached)
    finally:
        urllib.request.urlopen = original
        (directory / (name + '-output.txt')).write_text(''.join(parts))
    text = ''.join(parts)
    nums = [int(n) for n in re.findall(r'\d+', text)]
    full_correct = row['correct'] if name.startswith('code-') else h.smoke_gate_ok(text) and all(n == i for i, n in enumerate(nums[:-1], 1))
    row['full_output_correct'] = full_correct
    row['reasoning_disabled'] = not any(reasoning) and not row['usage'].get('completion_tokens_details', {}).get('reasoning_tokens', 0)
    save(directory / (name + '.json'), row)
    assert full_correct and row['reasoning_disabled'], 'full output or reasoning gate failed'
    return row


def cmd(original, directory, binary):
    command = r.command_for(original, chunk=2048, cache=directory / 'cache', binary=binary)
    for i, arg in enumerate(command):
        if arg == '--serve-record':
            command[i + 1] = str(directory / 'serve.json')
            break
        if arg.startswith('--serve-record='):
            command[i] = '--serve-record=' + str(directory / 'serve.json')
            break
    return command


def main():
    assert not (OUT / 'production-before.json').exists(), 'do not overwrite evidence'
    WORK.mkdir(parents=True, exist_ok=True)
    before = r.quiet(h.Client('http://127.0.0.1:1235', r.MODEL))
    assert before['instance']['model'] == r.MODEL
    save(OUT / 'production-before.json', before)
    original = shlex.split(subprocess.check_output(['ps', '-p', str(before['instance']['pid']), '-ww', '-o', 'command='], text=True).strip())
    save(OUT / 'restore-command.json', original)
    binaries = WORK / 'binaries'
    binaries.mkdir()
    hashes = {}
    for name in ('splash', 'splash.metallib', 'host-step.metallib'):
        source = ROOT / 'build' / name
        hashes[name] = r.sha(source)
        shutil.copy2(source, binaries / name)
        assert r.sha(binaries / name) == r.sha(source) == hashes[name]
    save(OUT / 'binary-sha256.json', hashes)
    save(OUT / 'contract.json', dict(model=r.MODEL, commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), source_build=before.get('identity'), sizes=r.SIZES, output_budget=512, chunk=2048, server_context=131072, passes=2, comparison='Historical November 13 valid 2048 rows; not a matched causal A/B.', cache='Fresh independent benchmark cache each pass; production cache preserved', thinking=False))
    stopped = False
    rows = []
    try:
        native = subprocess.check_output(['pgrep', '-P', str(before['instance']['pid'])], text=True).split()
        r.quiet(h.Client('http://127.0.0.1:1235', r.MODEL))
        os.kill(before['instance']['pid'], signal.SIGINT)
        stopped = True
        deadline = time.monotonic() + 120
        while any(subprocess.run(['ps', '-p', pid, '-o', 'pid='], capture_output=True).stdout.strip() for pid in native):
            assert time.monotonic() < deadline, 'native shutdown timeout'
            time.sleep(1)
        timed_tail = h.SMOKE_TAIL
        h.SMOKE_TAIL = '\nReturn the secret code, then list the integers from 1 through 30 in order. No explanation.'
        smoke = WORK / 'smoke'
        with r.serving(cmd(original, smoke, binaries / 'splash'), smoke) as client:
            prompt, _ = h.build_prompt(client, 'pre-4096', 'postmerge-smoke')
            probe(client, OUT / 'smoke', 'smoke-cold', prompt, 96, False)
            probe(client, OUT / 'smoke', 'smoke-reuse', prompt, 96, True)
            code, _ = h.build_prompt(client, 'code-3', '')
            probe(client, OUT / 'smoke', 'code-3', code, 192, False)
        with r.serving(cmd(original, smoke, binaries / 'splash'), WORK / 'smoke-restart') as client:
            probe(client, OUT / 'smoke-restart', 'smoke-persistent', prompt, 96, True)
        save(OUT / 'smoke-passed.json', dict(passed=True, time=time.time()))
        h.SMOKE_TAIL = timed_tail
        print('SMOKE PASSED: cold, cache reuse, code execution, persisted cache restart', flush=True)
        for repeat in (1, 2):
            directory = WORK / f'pass-{repeat}'
            with r.serving(cmd(original, directory, binaries / 'splash'), directory) as client:
                for size in r.SIZES:
                    prompt, actual = h.build_prompt(client, f'pre-{size}', f'chunk-context-{size}')
                    assert actual == size
                    for mode in ('cold', 'reuse'):
                        row = probe(client, OUT / f'pass-{repeat}', f'pre-{size}-{mode}', prompt, 512, mode == 'reuse')
                        row.update(repeat=repeat, size=size, mode=mode)
                        rows.append(row)
                        save(OUT / 'rows.json', rows)
        save(OUT / 'complete.json', dict(passed=True, rows=len(rows)))
    finally:
        if stopped:
            v.restore(original, before)

if __name__ == '__main__':
    main()
