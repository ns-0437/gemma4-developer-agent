"""Prepare the REPAIRED disabled six-run final validation: submitted v3 versus frozen ON.

Identical to final_validation_v1 except that it is generated AFTER the control-node
identity repair, so its control gate canonicalizes each arm's own sandbox workspace
root before comparing. Verified on the real environment by the CPU-only control replay
(navin03/gemma4-control-replay v1, 2026-10-07): all six control arms reproduced.

Candidate selection, not a development experiment. Reaches three protected hold-out tasks
only through the manifest-gated final-validation entry point in make_compare_notebook; the
development guard is untouched and still rejects every protected task.

Never pushes, never arms, exposes nothing. A hold-out task counts as exposed only when its
evaluation actually starts, which the generated notebook records in pilot/EXPOSURE.json.

    python scripts/make_final_validation_notebook.py
"""
import hashlib
import json
import sys
from pathlib import Path

import make_compare_notebook as M

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/final_validation_v2'
OUT_EXP = EXP
SOURCE = EXP / 'candidate_V3'
FREEZE = ROOT / 'experiments/ab_v3_vs_short/task_freeze.json'
FREEZE_SHA256 = hashlib.sha256(FREEZE.read_bytes()).hexdigest()
MANIFEST = EXP / 'VALIDATION_MANIFEST.json'
IMAGE = ('gcr.io/kaggle-private-byod/python@sha256:'
         '37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461')

TASKS = ['fastapi_15280', 'requests_7427', 'rich_3894']
ORDER = [('fastapi_15280', 'V3'), ('fastapi_15280', 'ON'),
         ('requests_7427', 'ON'), ('requests_7427', 'V3'),
         ('rich_3894', 'V3'), ('rich_3894', 'ON')]

EXPOSURE_ANCHOR = '            started = time.perf_counter()\n            err = None'
EXPOSURE_CODE = """            _exp_path = RESULTS / 'EXPOSURE.json'
            if _exp_path.exists():
                # Corrupt or inconsistent evidence must FAIL, never be silently replaced.
                _exp = json.loads(_exp_path.read_text())
                assert _exp.get('freeze_sha256') == FREEZE_SHA256, (
                    'EXPOSURE.json records a different freeze; refusing to continue')
                assert isinstance(_exp.get('events'), list), (
                    'EXPOSURE.json events are malformed; refusing to continue')
            else:
                _exp = {'freeze_sha256': FREEZE_SHA256,
                        'timestamp_meaning': 'dispatch-start intent, recorded immediately before '
                                             'the evaluator call. It is NOT proof the agent '
                                             'received or began the task.',
                        'events': []}
            _exp['events'].append({'task': tid, 'candidate': cand,
                                   'event': 'dispatch_start_intent',
                                   'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
            _exp['tasks_exposed'] = sorted({e['task'] for e in _exp['events']})
            # Atomic replace: an interruption cannot truncate or erase earlier events.
            _exp_tmp = _exp_path.with_name('EXPOSURE.json.tmp')
            _exp_tmp.write_text(json.dumps(_exp, indent=2))
            _exp_tmp.replace(_exp_path)
            print('DISPATCH-START INTENT recorded:', tid, cand,
                  '| tasks with a dispatch intent so far:', _exp['tasks_exposed'])
            started = time.perf_counter()
            err = None"""

CAND_CHECK = """
for key, folder in CAND_DIRS.items():
    got = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in folder.rglob('*') if p.is_file()}
    assert got == EXPECTED_FILES[key], 'Candidate file drift: ' + key
"""

COMPILER_CHECK = """
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
"""

MD = """# FINAL VALIDATION, disabled - submitted v3 versus frozen ON

Candidate selection, not a development experiment. Two complete packages are compared as
submitted and as frozen: v3 is the archive actually submitted (ref 56636116, scored 0.06),
ON is the frozen thinking package. EACH KEEPS ITS OWN sampling.yaml, so this measures
package performance, not thinking in isolation. v3 reserves 8192 completion tokens with
thinking off; ON reserves 4096 with a 1024 thinking budget.

Three PROTECTED HELD-OUT tasks, one per repository, chosen only by smallest
sha256(instance_id) within each repo from the freeze's protected_holdout list. No task
content, reference patch or grading expectation was inspected to choose them.

A task counts as EXPOSED only when its evaluation actually starts, recorded per task in
pilot/EXPOSURE.json as a dispatch-start intent immediately before the evaluator call, which is
not proof the agent received the task. Generating this notebook exposes nothing; the ledger is
written atomically and is only initialised when absent, so an interruption cannot erase earlier
events and corrupt evidence fails rather than being replaced. The freeze stays byte-identical and consumption is recorded separately. Any
candidate revision based on these results retires these three tasks from future hold-out
claims. Saved control evidence is reused for instrument validation only; its answer content
is never used to revise a candidate.

Generated after the control-identity repair: the gate canonicalizes each arm's own
sandbox workspace root, verified on the real environment by the CPU-only control replay
where all six arms reproduced.

Order: v3 runs first on two tasks and ON on one. That is an IMBALANCE. It is not evidence
that the incumbent is favoured, and no claim is made about which candidate it helps; with
three tasks perfect counterbalance is impossible.

Controls, provenance, cleanup and all six planned rows are preserved; ungraded, failed and
missing runs stay visible. Three selected tasks cannot establish statistical superiority or
predict a public score.
"""


def specialize(P):
    P.CFG += '\n' + 'FREEZE_SHA256 = ' + repr(FREEZE_SHA256) + '\n'
    P.CANDIDATES = {'V3': SOURCE, 'ON': EXP / 'candidate_ON'}
    expected = {}
    for key, folder in P.CANDIDATES.items():
        expected[key] = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in folder.rglob('*') if p.is_file()}
    marker = '\na = (CAND_DIRS["A"] / "configs" / "sampling.yaml").read_bytes()'
    assert P.CANDS.count(marker) == 1
    P.CANDS = P.CANDS.split(marker)[0] + '\nEXPECTED_FILES = ' + repr(expected) + CAND_CHECK

    compiler = ROOT / 'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'
    hashes = {p.relative_to(compiler).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in compiler.rglob('*.py')}
    P.CANDS += '\nEXPECTED_COMPILER_FILES = ' + repr(hashes) + COMPILER_CHECK

    assert P.RUN.count(EXPOSURE_ANCHOR) == 1, 'exposure anchor missing; refusing to generate'
    P.RUN = P.RUN.replace(EXPOSURE_ANCHOR, EXPOSURE_CODE, 1)

    # The template's scope caveat was written for a four-task rich-only diagnostic. Both of its
    # sentences are false here: this packet spans three repositories, and "generalises to rich at
    # best" is wrong once fastapi and requests are included.
    stale = 'Four tasks from ONE repository (Textualize/rich) are a narrow diagnostic, not a general'
    stale2 = 'ranking: any result here generalises to rich at best, and cannot say which candidate is'
    assert stale in P.REPORT and stale2 in P.REPORT, 'scope caveat text moved; refusing to generate'
    P.REPORT = P.REPORT.replace(
        stale,
        'Three hold-out tasks, one each from fastapi, requests and rich, are a narrow diagnostic,'
        ' not a general')
    P.REPORT = P.REPORT.replace(
        stale2,
        'ranking: one task per repository cannot support a per-repository or overall claim, and'
        ' cannot say which candidate is')
    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["V3"]')
    P.SERVER = P.SERVER.replace("# vLLM with the grader's serving settings.",
                                '# vLLM with the public harness serving configuration; private parity unverified.')
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.',
                                'Each package keeps its own sampling.yaml exactly as submitted or frozen.')


def main():
    expected = {'V3': 'b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b',
                'ON': '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'}
    for key, folder in [('V3', SOURCE), ('ON', EXP / 'candidate_ON')]:
        assert M.P.bundle(folder)[1] == expected[key], 'Candidate drift: ' + key

    M.VALIDATION_MANIFEST = str(MANIFEST)
    M.TASKS = TASKS
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = 'ON', EXP, 'candidate_ON'
    M.OUT_NAME, M.NB_FILENAME = 'final_validation_v2', 'final_validation_v2.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-final-validation-v2', 'gemma4-final-validation-v2'
    M.CFG_LABEL, M.ORDER_EXPR = 'final validation:', 'ORDER = ' + repr(ORDER)
    M.RUN_COUNT_PHRASE = 'the six runs will NOT'
    M.ARM_FOR_LAUNCH = False
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 240, 25
    M.CUSTOMIZE_CELLS = specialize
    M.MD = MD
    M.main()

    nb_path = ROOT / 'notebooks/final_validation_v2/final_validation_v2.ipynb'
    raw = nb_path.read_bytes()
    assert raw.count(b'DISPATCH_CONFIRM = False') == 1
    assert b'DISPATCH_CONFIRM = True' not in raw
    assert b'DISPATCH-START INTENT recorded' in raw, 'exposure recording missing'

    meta_path = ROOT / 'notebooks/final_validation_v2/kernel-metadata.json'
    meta = json.loads(meta_path.read_text())
    meta['docker_image'] = IMAGE
    meta_path.write_text(json.dumps(meta, indent=2) + '\n')

    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    nb = json.loads(raw)
    embedded = chr(10).join(''.join(c['source']) for c in nb['cells'])
    import re as _re
    got_order = _re.search(r'ORDER = (\[[^\]]*\])', embedded).group(1)
    assert eval(got_order) == [tuple(x) for x in ORDER], 'embedded ORDER != generator ORDER'
    assert [list(x) for x in ORDER] == [list(x) for x in man['order']], 'ORDER != manifest order'
    for key, pin in man['packages'].items():
        assert pin['sha256'] == expected[key], 'manifest package hash != intended frozen hash'
        assert pin['sha256'] in embedded, 'notebook does not embed the manifest hash for ' + key
    for t in man['tasks']:
        assert t in embedded, 'notebook does not embed manifest task ' + t
    print('embedded-vs-manifest cross-check: ORDER, package hashes and tasks all agree')

    record = {'notebook_sha256': hashlib.sha256(raw).hexdigest(),
              'metadata_sha256': hashlib.sha256(meta_path.read_bytes()).hexdigest(),
              'candidates': expected, 'order': ORDER, 'tasks': TASKS,
              'dispatch': False, 'compiler_version': '0.2.12',
              'compiler_wheel_sha256': '077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10',
              'docker_image': IMAGE,
              'freeze_sha256': FREEZE_SHA256,
              'validation_manifest': str(MANIFEST.relative_to(ROOT)),
              'holdout_tasks_exposed_if_executed': TASKS,
              'exposure_recorded_at': 'dispatch-start intent immediately before the evaluator call, per task, appended atomically to pilot/EXPOSURE.json; not proof the agent received the task',
              'exposed_so_far': []}
    (OUT_EXP / 'NOTEBOOK_PREPARED.json').write_text(json.dumps(record, indent=2) + '\n')
    print('prepared (disabled):', meta['id'])
    print('notebook sha256:', record['notebook_sha256'])
    print('metadata sha256:', record['metadata_sha256'])


if __name__ == '__main__':
    assert len(sys.argv) == 1, 'Preparation only; arming requires a reviewed launch step'
    main()
