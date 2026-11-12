import importlib.util
import json
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('harness', OUT / 'harness.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
MODEL = 'ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0'
client = h.Client('http://127.0.0.1:1235', MODEL)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')

def system_snapshot():
    results = {}
    for command in [['sysctl', 'vm.swapusage'], ['vm_stat'], ['pmset', '-g', 'therm'],
                    ['git', 'rev-parse', 'HEAD'], ['git', 'status', '--short'],
                    ['shasum', '-a', '256', 'build/splash', 'build/splash.metallib',
                     'build/host-step.metallib', 'startllamacpp.sh']]:
        result = subprocess.run(command, text=True, capture_output=True)
        results[' '.join(command)] = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    return results

status = client.status()
assert status['ready']
assert status['instance']['model'] == MODEL, status['instance']
save('status-before.json', status)
save('system-before.json', system_snapshot())
rows = []
save('profile.json', h.profile_of_record(status))
print('Option 21 verified:', status['instance'], flush=True)
try:
    # The first full trial starts with a cold/reuse smoke pair. Its correctness
    # and cache gates must pass before the dependent 4K and coding probes run.
    for trial in (1, 2):
        for row in h.run_trial(client, OUT / 'serving', trial, ['full'], None):
            rows.append(dict(row, trial=trial, group='serving'))
        save('results.json', dict(complete=False, rows=rows))
    for trial in (1, 2):
        for row in h.run_trial(client, OUT / 'prefill', trial, ['prefill'], None,
                               prefill_sizes=[8192, 16384]):
            rows.append(dict(row, trial=trial, group='prefill'))
        save('results.json', dict(complete=False, rows=rows))
    assert all(r['correct'] and r['clean'] for r in rows), 'Inspect failed or contended probes'
    save('results.json', dict(complete=True, model=MODEL, rows=rows))
    print('COMPLETE:', len(rows), 'clean, correct probes', flush=True)
finally:
    save('system-after.json', system_snapshot())
    save('status-after.json', client.status())
