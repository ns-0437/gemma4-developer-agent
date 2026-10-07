"""Prepare a disabled four-run diagnostic. Never pushes or arms."""
import hashlib
import json
import sys
from pathlib import Path
import make_compare_notebook as M

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/verification_v1'
SOURCE = ROOT / 'experiments/shellread_v1/candidate_S_shellread'
TASKS = ['rich_3675', 'rich_3942']
ORDER = [('rich_3675','S_shellread'), ('rich_3675','V'),
         ('rich_3942','V'), ('rich_3942','S_shellread')]

def specialize(P):
    P.CANDIDATES = {'S_shellread': SOURCE, 'V': EXP / 'candidate_V'}
    expected = {}
    for key, folder in P.CANDIDATES.items():
        expected[key] = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in folder.rglob('*') if p.is_file()}
    marker = '\na = (CAND_DIRS["A"] / "configs" / "sampling.yaml").read_bytes()'
    assert P.CANDS.count(marker) == 1
    P.CANDS = P.CANDS.split(marker)[0] + '\nEXPECTED_FILES = ' + repr(expected) + '''
for key, folder in CAND_DIRS.items():
    got = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in folder.rglob('*') if p.is_file()}
    assert got == EXPECTED_FILES[key], 'Candidate file drift: ' + key
'''
    compiler = ROOT / 'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'
    hashes = {p.relative_to(compiler).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in compiler.rglob('*.py')}
    P.CANDS += '\nEXPECTED_COMPILER_FILES = ' + repr(hashes) + '''
def verify_runtime_compiler(root=None, version=None):
    import importlib.metadata as metadata
    if root is None:
        import adk_submission
        root = Path(adk_submission.__file__).parent
    if version is None:
        version = metadata.version('adk-submission')
    found = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*.py')}
    record = {'version': version, 'python_files': found,
              'matches': version == '0.2.12' and found == EXPECTED_COMPILER_FILES}
    (RESULTS / 'compiler_identity.json').write_text(json.dumps(record, indent=2))
    assert record['matches'], 'Runtime compiler drift: refuse model startup'
verify_runtime_compiler()
'''
    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["S_shellread"]')
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.', 'both candidates request thinking disabled.')

def main(arm=False):
    nb = ROOT/'notebooks/verification/verification.ipynb'
    baseline = EXP/'verification_disabled.ipynb'
    if arm:
        raw = nb.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == json.loads((EXP/'NOTEBOOK_PREPARED.json').read_text())['notebook_sha256']
        assert raw.count(b'DISPATCH_CONFIRM = False') == 1
        baseline.write_bytes(raw)
    expected = {'S_shellread': '8e3f9286ce0f2399c32dfa452e129a12fd48cdd657b88ea6c76d3c48c36956ae',
                'V': '315ba92750d38550a7e1880da2dfa80db8944a166d8be04a3e748db68450d804'}
    for key, folder in [('S_shellread',SOURCE), ('V',EXP/'candidate_V')]:
        assert M.P.bundle(folder)[1] == expected[key], 'Candidate drift'
    M.TASKS = TASKS
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = 'V', EXP, 'candidate_V'
    M.OUT_NAME, M.NB_FILENAME = 'verification', 'verification.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-swe-agent-verification', 'gemma4-swe-agent-verification'
    M.CFG_LABEL, M.ORDER_EXPR = 'verification diagnostic:', 'ORDER = ' + repr(ORDER)
    M.RUN_COUNT_PHRASE = 'the four runs will NOT'
    M.ARM_FOR_LAUNCH = arm
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 150, 25
    M.CUSTOMIZE_CELLS = specialize
    M.MD = '''# Verification discipline diagnostic — disabled

Two selected Rich development tasks, S_shellread versus V, four planned runs.
Only reproduction instructions change; sampling, analyzer and tools stay fixed.
Runtime compiler source identity is checked before server startup. Controls and
provenance must pass. This subprocess environment is not private-grader equivalence.
All rows, including ungraded/missing outcomes, remain visible. Better verification
behaviour alone is not a solve or a leaderboard prediction.
No follow-on experiment or submission. Session cap admits work, not a hard kill.
'''
    M.main()
    raw = (ROOT/'notebooks/verification/verification.ipynb').read_bytes()
    if arm:
        assert raw == baseline.read_bytes().replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1)
    record = {'notebook_sha256':hashlib.sha256(raw).hexdigest(), 'candidates':expected,
              'order':ORDER, 'dispatch':arm, 'compiler_version':'0.2.12',
              'compiler_wheel_sha256':'077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10'}
    (EXP/('ARMED.json' if arm else 'NOTEBOOK_PREPARED.json')).write_text(json.dumps(record,indent=2))

if __name__ == '__main__':
    main(arm='--arm' in sys.argv)
