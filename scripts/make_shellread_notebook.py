"""Prepare a disabled four-run diagnostic. Never pushes or arms."""
import hashlib
import json
import sys
from pathlib import Path
import make_compare_notebook as M

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/shellread_v1'
SOURCE = ROOT / 'experiments/concise_workflow_v1/candidate_S'
TASKS = ['rich_3675', 'rich_3942']
ORDER = [('rich_3675','S'), ('rich_3675','S_shellread'),
         ('rich_3942','S_shellread'), ('rich_3942','S')]

def specialize(P):
    P.CANDIDATES = {'S': SOURCE, 'S_shellread': EXP / 'candidate_S_shellread'}
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
    compiler = EXP / 'compiler_0_2_12/src/adk_submission'
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
    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["S"]')
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.', 'both candidates request thinking disabled.')

def main(arm=False):
    nb = ROOT/'notebooks/shellread/shellread.ipynb'
    baseline = EXP/'shellread_disabled.ipynb'
    if arm:
        raw = nb.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == '71ddec6ae5a66fadf037a27a1701ee2dd7870563dc93f11e4c10edff89afa768'
        baseline.write_bytes(raw)
    expected = {'S': '8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07',
                'S_shellread': '8e3f9286ce0f2399c32dfa452e129a12fd48cdd657b88ea6c76d3c48c36956ae'}
    for key, folder in [('S',SOURCE), ('S_shellread',EXP/'candidate_S_shellread')]:
        assert M.P.bundle(folder)[1] == expected[key], 'Candidate drift'
    M.TASKS = TASKS
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = 'S_shellread', EXP, 'candidate_S_shellread'
    M.OUT_NAME, M.NB_FILENAME = 'shellread', 'shellread.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-swe-agent-shellread', 'gemma4-swe-agent-shellread'
    M.CFG_LABEL, M.ORDER_EXPR = 'shellread diagnostic:', 'ORDER = ' + repr(ORDER)
    M.RUN_COUNT_PHRASE = 'the four runs will NOT'
    M.ARM_FOR_LAUNCH = arm
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 150, 25
    M.CUSTOMIZE_CELLS = specialize
    M.MD = '''# Coder read-interface diagnostic — disabled

Two selected Rich development tasks, S versus S_shellread, four planned runs.
Only the coder read interface changes; sampling, analyzer and editing tools stay fixed.
Runtime compiler source identity is checked before server startup. Controls and
provenance must pass. This subprocess environment is not private-grader equivalence.
All rows, including ungraded/missing outcomes, remain visible. Fewer malformed
reads is a mechanism observation, not a solve or a leaderboard prediction.
No follow-on experiment or submission. Session cap admits work, not a hard kill.
'''
    M.main()
    raw = (ROOT/'notebooks/shellread/shellread.ipynb').read_bytes()
    if arm:
        assert raw == baseline.read_bytes().replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1)
    record = {'notebook_sha256':hashlib.sha256(raw).hexdigest(), 'candidates':expected,
              'order':ORDER, 'dispatch':arm, 'compiler_version':'0.2.12',
              'compiler_wheel_sha256':'077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10'}
    (EXP/('ARMED.json' if arm else 'NOTEBOOK_PREPARED.json')).write_text(json.dumps(record,indent=2))

if __name__ == '__main__':
    main(arm='--arm' in sys.argv)
