"""Prepare a disabled four-run diagnostic. Never pushes or arms."""
import hashlib
import json
import sys
from pathlib import Path
import make_compare_notebook as M

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/thinking_v2'
SOURCE = ROOT / 'experiments/thinking_v2/candidate_OFF'
TASKS = ['rich_3675', 'rich_3278']
ORDER = [('rich_3675','OFF'), ('rich_3675','ON'),
         ('rich_3278','ON'), ('rich_3278','OFF')]

def specialize(P):
    P.CANDIDATES = {'OFF': SOURCE, 'ON': EXP / 'candidate_ON'}
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
    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["OFF"]')
    P.SERVER = P.SERVER.replace("# vLLM with the grader's serving settings.", '# vLLM with the public harness serving configuration; private parity unverified.')
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.', 'OFF disables thinking; ON requests a 1024-token thinking budget.')

def main():
    expected = {'OFF': '640fadab5b5b638a7e8a31abb26fcecb6b2e139929d77cdb6691f2d832ca2ec1',
                'ON': '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'}
    for key, folder in [('OFF',SOURCE), ('ON',EXP/'candidate_ON')]:
        assert M.P.bundle(folder)[1] == expected[key], 'Candidate drift'
    M.TASKS = TASKS
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = 'ON', EXP, 'candidate_ON'
    M.OUT_NAME, M.NB_FILENAME = 'thinking_v2', 'thinking_v2.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-swe-agent-thinking-v2', 'gemma4-swe-agent-thinking-v2'
    M.CFG_LABEL, M.ORDER_EXPR = 'thinking_v2 diagnostic:', 'ORDER = ' + repr(ORDER)
    M.RUN_COUNT_PHRASE = 'the four runs will NOT'
    M.ARM_FOR_LAUNCH = False
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 150, 25
    M.CUSTOMIZE_CELLS = specialize
    M.MD = """# Matched thinking OFF/ON diagnostic - disabled

Frozen S derivatives: both reserve 4096 total completion tokens. OFF is a new
baseline, not the submitted agent. ON requests thinking enabled with budget 1024.
Only sampling.yaml differs; prompts/tools/analyzer are identical. Two selected Rich
development tasks, four runs; heldout excluded. No leaderboard extrapolation.
32768 context minus 4096 completion permits at most 28672 prompt tokens; neither
compaction nor a thinking budget guarantees the next request fits or reserves
final-tool-call space. Compaction 20480 is equal across arms and differs from the
public harness default None; private grader configuration is unknown.
Forwarding is offline-verified; host enforcement is unverified. Inspect recorded
thought/reasoning evidence if present; absence is unknown, not proof of disabled
thinking. Total completion tokens do not prove a thinking budget is enforced.
All ungraded, truncated, failed and missing runs stay visible. Session cap is an
admission limit, not a hard kill. No follow-on launch or competition submission.
"""
    M.main()
    raw = (ROOT/'notebooks/thinking_v2/thinking_v2.ipynb').read_bytes()
    assert raw.count(b'DISPATCH_CONFIRM = False') == 1
    assert b'DISPATCH_CONFIRM = True' not in raw
    record = {'notebook_sha256':hashlib.sha256(raw).hexdigest(), 'candidates':expected,
              'order':ORDER, 'dispatch':False, 'compiler_version':'0.2.12',
              'compiler_wheel_sha256':'077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10'}
    (EXP/'NOTEBOOK_PREPARED.json').write_text(json.dumps(record,indent=2))

if __name__ == '__main__':
    assert len(sys.argv) == 1, 'Preparation only; arming requires a reviewed launch step'
    main()
