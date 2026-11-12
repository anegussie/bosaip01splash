import importlib.util
import json
import subprocess
import uuid
import sys
SIZE = int(sys.argv[1])
assert SIZE in (8192, 16384)
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / f'context{SIZE}'
OUT.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('harness', ROOT / 'harness.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
MODEL = 'ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0'
client = h.Client('http://127.0.0.1:1235', MODEL)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')

def snapshot():
    result = {}
    for cmd in [['sysctl', 'vm.swapusage'], ['vm_stat'], ['pmset', '-g', 'therm']]:
        p = subprocess.run(cmd, capture_output=True, text=True)
        result[' '.join(cmd)] = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    return result

status = client.status()
original = json.loads((ROOT / 'status-before.json').read_text())
assert status['ready'] and status['instance']['model'] == MODEL
assert status['instance']['id'] == original['instance']['id'], 'Server instance changed'
assert status['identity'] == original['identity'], 'Model/build identity changed'
assert status['maximum_context_tokens'] >= SIZE + 256
save('status-before.json', status)
save('system-before.json', snapshot())
save('profile.json', h.profile_of_record(status))
rows = []
try:
    for trial in (1, 2):
        trial_dir = OUT / f'trial{trial}'
        trial_dir.mkdir(exist_ok=True)
        prompt, tokens = h.build_prompt(client, f'pre-{SIZE}', uuid.uuid4().hex[:8])
        print(f'trial {trial}: {tokens} content tokens; max output 96; thinking disabled', flush=True)
        for kind in ('cold', 'reuse'):
            row = h.run_probe(client, trial_dir, f'pre-{SIZE}-{kind}', prompt,
                              96, f'{SIZE}-trial{trial}', None)
            row['semantic_correct'] = h.smoke_gate_ok(row['text'])
            row['trial'] = trial
            rows.append(row)
            save('results.json', dict(complete=False, model=MODEL, rows=rows))
            assert row['clean'] and row['correct'] and row['semantic_correct'], 'Request correctness/contention gate failed'
            if kind == 'cold':
                assert row['cached_tokens'] == 0, 'Cold request reused a prefix'
            else:
                assert row['cached_tokens'] >= tokens - 128, 'full-prefix cache reuse gate failed'
    save('results.json', dict(complete=True, model=MODEL, rows=rows))
    print(f'COMPLETE: {SIZE}: 4 clean requests; recall/counting and cache gates passed', flush=True)
finally:
    save('system-after.json', snapshot())
    save('status-after.json', client.status())
