"""Prepare S versus S_temp, disabled; reuse control/dispatch/report cells. Never push."""
import base64
import hashlib
import json
import sys
from pathlib import Path
import make_compare_notebook as M

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments' / 'temperature_v1'
SOURCE = ROOT / 'experiments' / 'concise_workflow_v1' / 'candidate_S'
EXPECTED_S = '8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07'
TASKS = ['rich_3278', 'rich_3535', 'rich_3675', 'rich_3942']
ORDER = [(t, c) for i, t in enumerate(TASKS)
         for c in (('S', 'S_temp') if i % 2 == 0 else ('S_temp', 'S'))]

ISOLATION = '''
a_root, b_root = CAND_DIRS['S'], CAND_DIRS['S_temp']
files = {p.relative_to(a_root).as_posix() for p in a_root.rglob('*') if p.is_file()}
assert files == {p.relative_to(b_root).as_posix() for p in b_root.rglob('*') if p.is_file()}
changed = []
for rel in sorted(files):
    a, b = (a_root / rel).read_bytes(), (b_root / rel).read_bytes()
    if a != b:
        changed.append(rel)
    if rel == 'configs/sampling.yaml':
        assert a.count(b'temperature: 0.2') == 1
        assert b == a.replace(b'temperature: 0.2', b'temperature: 0.7', 1)
    else:
        assert a == b, rel
assert changed == ['configs/sampling.yaml'], changed
print('S vs S_temp: shared coder/analyzer temperature 0.2 -> 0.7 only; configured seed unchanged')
'''


def prepare_candidate():
    EXP.mkdir(parents=True, exist_ok=True)
    _, source_sha = M.P.bundle(SOURCE)
    assert source_sha == EXPECTED_S, 'Frozen S drift'
    target = EXP / 'candidate_S_temp'
    expected_files = {p.relative_to(SOURCE) for p in SOURCE.rglob('*') if p.is_file()}
    if target.exists():
        assert {p.relative_to(target) for p in target.rglob('*') if p.is_file()} <= expected_files
    for rel in sorted(expected_files):
        data = (SOURCE / rel).read_bytes()
        if rel.as_posix() == 'configs/sampling.yaml':
            assert data.count(b'temperature: 0.2') == 1
            data = data.replace(b'temperature: 0.2', b'temperature: 0.7', 1)
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for key, folder in [('S', SOURCE), ('S_temp', target)]:
        encoded, sha = M.P.bundle(folder)
        (EXP / f'{key}.zip').write_bytes(base64.b64decode(encoded))
        print(key, sha)
    return target


def specialize(P):
    P.CANDIDATES = {'S': SOURCE, 'S_temp': EXP / 'candidate_S_temp'}
    marker = '\na = (CAND_DIRS["A"] / "configs" / "sampling.yaml").read_bytes()'
    assert P.CANDS.count(marker) == 1
    P.CANDS = P.CANDS.split(marker)[0] + ISOLATION
    assert 'CAND_DIRS["A"]' in P.SERVER
    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["S"]')
    assert "for cand in ('A','B'):" in P.SERVER
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.',
                               'thinking is disabled for both candidates; temperature differs.')


def main(arm=False):
    nb = ROOT / 'notebooks/temperature/temperature.ipynb'
    baseline = EXP / 'temperature_disabled.ipynb'
    if arm:
        raw = nb.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == 'd17f234a34b1c44d8f85461c7563504cf5a5977a3836acf12122081f6a7e5ef7'
        baseline.write_bytes(raw)
    prepare_candidate()
    M.TASKS = TASKS
    M.SECOND_KEY = 'S_temp'
    M.SECOND_EXP = EXP
    M.SECOND_DIR_NAME = 'candidate_S_temp'
    M.OUT_NAME = 'temperature'
    M.NB_FILENAME = 'temperature.ipynb'
    M.KERNEL_ID = M.KERNEL_TITLE = 'navin03/gemma4-swe-agent-temperature'
    M.KERNEL_TITLE = 'gemma4-swe-agent-temperature'
    M.CFG_LABEL = 'S vs S_temp temperature-only config:'
    M.ORDER_EXPR = 'ORDER = ' + repr(ORDER)
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 300, 25
    M.ARM_FOR_LAUNCH = arm
    M.CUSTOMIZE_CELLS = specialize
    M.MD = '''# S versus S_temp: temperature-only diagnostic

Four selected Rich development tasks, eight contemporaneous runs, alternating order.
S is frozen; S_temp changes shared coder/analyzer temperature 0.2 to 0.7 only.
Prompts, tools, model, configured seed 42, penalties and budgets are unchanged.
The seed remains in YAML; this does not prove it reaches the inference server.
Both candidates have thinking disabled. This is a repaired subprocess environment,
not a claim of private-grader equivalence or filesystem isolation.

Main outcomes: verified solves, graded-unsolved, ungraded, not attempted (all four
planned tasks per candidate). Reliability: nonempty valid source patch and grading.
Diagnostic: repetition, rejected calls, distinct calls and time. Less repetition
alone cannot promote S_temp. No population or leaderboard extrapolation.

The session cap admits new work; it is not a hard termination timer. Dispatch is
disabled. No automatic follow-up experiment or competition submission is included.
'''
    M.main()
    nb = ROOT / 'notebooks/temperature/temperature.ipynb'
    source = '\n'.join(''.join(c['source']) for c in json.loads(nb.read_bytes())['cells'])
    assert source.count('DISPATCH_CONFIRM = ' + str(arm)) == 1
    assert 'DISPATCH_CONFIRM = ' + str(not arm) not in source
    if arm:
        expected = baseline.read_bytes().replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1)
        assert nb.read_bytes() == expected, 'Arming changed more than the flag'
    manifest = {'notebook_sha256': hashlib.sha256(nb.read_bytes()).hexdigest(),
                'order': ORDER, 'dispatch': arm, 'candidates': {}}
    for key in ('S', 'S_temp'):
        manifest['candidates'][key] = hashlib.sha256((EXP / f'{key}.zip').read_bytes()).hexdigest()
    (EXP / ('ARMED.json' if arm else 'PREPARED.json')).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main(arm='--arm' in sys.argv)
