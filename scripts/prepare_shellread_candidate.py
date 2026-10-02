"""Build an offline, unlaunched S derivative avoiding read_file optional arguments."""
import base64
import hashlib
import json
from pathlib import Path
import make_pilot_notebook as P

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/shellread_v1'
SOURCE = ROOT / 'experiments/concise_workflow_v1/candidate_S'

def main():
    encoded, sha = P.bundle(SOURCE)
    assert sha == '8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07'
    target = EXP / 'candidate_S_shellread'
    changes = []
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(SOURCE)
        data = p.read_bytes()
        new = data
        if rel.as_posix() == 'agent.yaml':
            assert data.count(b'  - read_file\n') == 1
            new = data.replace(b'  - read_file\n', b'', 1)
        elif rel.as_posix() == 'prompts/system.md':
            old = b'then read the matching ranges with `read_file`.'
            replacement = b'then read matching ranges through `run_command`, for example `sed -n \'100,160p\' path/to/file.py`. Check that the returned text contains the intended definition; use `git grep -n` to find its current line number when it does not.'
            assert data.count(old) == 1
            new = data.replace(old, replacement, 1)
            old = b'Output is cut at 5,000 characters and `read_file` returns at most 150 lines. Read focused ranges; pipe long output through `head`.'
            assert new.count(old) == 1
            new = new.replace(old, b'Output is cut at 5,000 characters. Read focused ranges with `sed -n`; pipe long search output through `head`.', 1)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new)
        if new != data:
            changes.append(rel.as_posix())
    assert changes == ['agent.yaml', 'prompts/system.md'], changes
    output, digest = P.bundle(target)
    (EXP / 'S_shellread.zip').write_bytes(base64.b64decode(output))
    report = {'baseline_sha256': sha, 'candidate_sha256': digest,
              'changed_files': changes, 'dispatch': False,
              'claim': 'Unmeasured read-interface intervention; no score improvement established.'}
    (EXP / 'PREPARED.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
