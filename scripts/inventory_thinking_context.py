"""Offline token inventory; never infer a launch configuration from current code."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'experiments/thinking_v2/CONTEXT_INVENTORY.json'
SESSIONS = [
    ('pilot_v1_results', 'pilot', None),
    ('compare_run2', 'compare', None),
    ('ab_s_run_2026-10-01', 'ab_s', '86d1c83bb203a1000c205d8913df59abcf83f86c584e66eb2ceba1e3e5a5a649'),
    ('stage1_run_2026-09-30', 'stage1', '775d88dfe3b91ee8b4d5b30cffdd9f2957556b1f045f2b87a1a6b4e3aacd3158'),
    ('temperature_run_2026-10-01', 'temperature', 'ff22c79682ec29e90c795bc61cde205e2f2ddf3cce1aa52c1ee4d9c08bcb5f26'),
    ('shellread_run_2026-10-02', 'shellread', '5722594505e407387a00567e39d78ddd00570384a32893f5c6223664de72f6a3'),
    ('verification_run_2026-10-03', 'verification', '7ea8397683c47beaeb9302036a18546deb8ed642dcc4c900f61eba4b0c754919'),
]


def numbers(value, key):
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key and type(v) in (int, float):
                yield v
            else:
                yield from numbers(v, key)
    elif isinstance(value, list):
        for v in value:
            yield from numbers(v, key)


def main():
    rows = []
    for directory, name, pin in SESSIONS:
        notebook = ROOT / f'notebooks/{name}/{name}.ipynb'
        raw = notebook.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if pin:
            assert sha == pin, 'Launched notebook drift: ' + name
        code = '\n'.join(''.join(c.get('source', [])) for c in json.loads(raw)['cells'])
        thresholds = sorted(set(map(int, re.findall(r'token_threshold\s*=\s*(\d+)', code))))
        for trace in sorted((ROOT / 'reference' / directory).rglob('trace_*.json')):
            data = trace.read_bytes()
            steps = json.loads(data)['steps']
            prompts = list(numbers(steps, 'prompt_tokens'))
            completions = list(numbers(steps, 'completion_tokens'))
            rows.append({
                'trace': trace.relative_to(ROOT).as_posix(),
                'sha256': hashlib.sha256(data).hexdigest(),
                'peak_recorded_prompt_tokens': max(prompts, default=None),
                'peak_recorded_completion_tokens': max(completions, default=None),
                'notebook': notebook.relative_to(ROOT).as_posix(),
                'notebook_sha256': sha,
                'matches_launch_pin': bool(pin),
                'configured_threshold': thresholds[0] if pin and len(thresholds) == 1 else None,
                'current_file_thresholds_not_launch_evidence': thresholds if not pin else [],
            })
    result = {
        'scope': 'Explicit seven-session inventory; not every trace on disk.',
        'excluded': ['smoke_run_2026-09-26: earlier smoke experiment',
                     'CPU controls/replays: no model usage', 'duplicate copies and synthetic fixtures'],
        'limitations': ['Successful recorded usage omits rejected request input sizes.',
                        'Threshold is a configured trigger, not a hard context bound.',
                        'Pilot/compare current notebooks are not pinned to these launches here; thresholds remain unknown.',
                        'Completion usage does not isolate reasoning or establish thinking-budget enforcement.'],
        'trace_count': len(rows),
        'above_20480_descriptive_only': sum((r['peak_recorded_prompt_tokens'] or 0) > 20480 for r in rows),
        'rows': rows,
    }
    OUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(f"{len(rows)} traces inventoried; {result['above_20480_descriptive_only']} above 20480 (not a pooled compaction test).")


if __name__ == '__main__':
    main()
