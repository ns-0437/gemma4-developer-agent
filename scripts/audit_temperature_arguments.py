"""Offline audit of recorded arguments, not reconstruction of raw model output."""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    raw = ROOT / 'reference/temperature_run_2026-10-01'
    manifest = json.loads((ROOT / 'reference/temperature_review/raw_sha256.json').read_text())
    def hashes():
        return {p.relative_to(raw).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in raw.rglob('*') if p.is_file()}
    assert hashes() == manifest
    tree = ast.parse((ROOT / 'scripts/official_check.py').read_text())
    signatures = {n.name: {a.arg for a in n.args.args} for n in tree.body
                  if isinstance(n, ast.FunctionDef)}
    rows = []
    for p in sorted((raw / 'pilot').glob('*/traces/*.json')):
        findings = []
        count = Counter()
        for step in json.loads(p.read_text())['steps']:
            for call in step.get('tool_calls', []):
                name, args = call['function_name'], call.get('arguments', {})
                count[name] += 1
                if name not in signatures or not isinstance(args, dict):
                    continue
                extra = sorted(set(args) - signatures[name])
                if not extra:
                    continue
                obs = step.get('observation', {}).get('content', '')
                try:
                    observation = json.loads(obs)
                except (ValueError, TypeError):
                    observation = {}
                findings.append({'step': step['step_id'], 'tool': name,
                    'extra_keys': extra, 'arguments': args,
                    'observation_status': observation.get('status'),
                    'observation_error': observation.get('error'),
                    'observation_content_sha256': hashlib.sha256(str(observation.get('content', '')).encode()).hexdigest()})
        rows.append({'run': p.parent.parent.name, 'calls': dict(count),
                     'unknown_argument_calls': len(findings), 'findings': findings})
    out = ROOT / 'reference/temperature_review/argument_audit.json'
    out.write_text(json.dumps({'boundary': 'Recorded parsed calls; signatures from local official_check.py; no claim about original model bytes',
                              'rows': rows}, indent=2), encoding='utf-8')
    assert hashes() == manifest
    for row in rows:
        reads = [f for f in row['findings'] if f['tool'] == 'read_file']
        print(row['run'], 'unknown argument calls', row['unknown_argument_calls'],
              'read_file with extra keys', len(reads),
              'of which status ok', sum(f['observation_status'] == 'ok' for f in reads))

if __name__ == '__main__':
    main()
