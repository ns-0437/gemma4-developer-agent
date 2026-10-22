"""Prepare the disabled four-run V5 baseline measurement. Never pushes or arms.

One arm: the exact submitted V5 agent (`527acc54...`, byte-identical to frozen ON), with
V5's own packaged eval_config budgets substituted into the config cell: max_time_minutes 5,
max_turns 60, max_tool_calls 100, timeout_seconds 60.

Four development tasks, one run each, declared order rich_3278, rich_3535, rich_3675,
rich_3942. Purpose: describe V5's verified-solve rate and elapsed time on development tasks
under V5's own budgets, which has never been measured. Hold-out tasks are untouched.

This runs the V5 agent and budgets in the PUBLIC DEVELOPMENT HARNESS. It is not
private-grader-equivalent execution; see the runtime deviations recorded in
experiments/v5_budget_v1/PLAN.md.
"""
import hashlib
import json
import sys
from pathlib import Path
import make_compare_notebook as M
from generation_guard import require_unlaunched

IMAGE = ('gcr.io/kaggle-private-byod/python@sha256:'
         '37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461')

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/v5_budget_v1'
OUT_EXP = ROOT / 'experiments/v5_budget_v1'      # this follow-up's own records
SOURCE = ROOT / 'experiments/v5_budget_v1/candidate_V5'
TASKS = ['rich_3278', 'rich_3535', 'rich_3675', 'rich_3942']
ORDER = [('rich_3278','V5'), ('rich_3535','V5'),
         ('rich_3675','V5'), ('rich_3942','V5')]

CAND_CHECK = '''
for key, folder in CAND_DIRS.items():
    got = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in folder.rglob('*') if p.is_file()}
    assert got == EXPECTED_FILES[key], 'Candidate file drift: ' + key
'''

COMPILER_CHECK = '''
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
              'matches': version == '0.2.13' and found == EXPECTED_COMPILER_FILES}
    (RESULTS / 'compiler_identity.json').write_text(json.dumps(record, indent=2))
    assert record['matches'], 'Runtime compiler drift: refuse model startup'
verify_runtime_compiler()
'''

SWEGEMMA_CHECK = '''
def verify_runtime_swegemma(root=None, version=None):
    """Locate the IMPORTED swegemma, verify 0.2.11 and its per-file hashes, or refuse.

    Runs before any sandbox is created. The observed identity and every mismatch detail are
    persisted first, so a refusal leaves durable evidence rather than only an exception.
    """
    import importlib.metadata as metadata
    if root is None:
        import swegemma
        root = Path(swegemma.__file__).parent
    if version is None:
        try:
            version = metadata.version('swegemma')
        except Exception as exc:
            version = 'metadata unavailable: ' + type(exc).__name__
    found = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*.py')}
    missing = sorted(set(EXPECTED_SWEGEMMA_FILES) - set(found))
    extra = sorted(set(found) - set(EXPECTED_SWEGEMMA_FILES))
    changed = sorted(k for k in set(found) & set(EXPECTED_SWEGEMMA_FILES)
                     if found[k] != EXPECTED_SWEGEMMA_FILES[k])
    record = {'version': version, 'package_path': str(root), 'n_modules': len(found),
              'missing': missing, 'extra': extra, 'changed': changed,
              'version_ok': version == '0.2.11',
              'hashes_ok': found == EXPECTED_SWEGEMMA_FILES,
              'python_files': found}
    record['matches'] = record['version_ok'] and record['hashes_ok']
    (RESULTS / 'swegemma_identity.json').write_text(json.dumps(record, indent=2))
    print('swegemma identity:', record['version'], '| modules', record['n_modules'],
          '| matches', record['matches'])
    assert record['matches'], (
        'Runtime swegemma drift: refuse control execution. version_ok=%s hashes_ok=%s '
        'missing=%s extra=%s changed=%s' % (record['version_ok'], record['hashes_ok'],
                                            missing[:4], extra[:4], changed[:4]))
verify_runtime_swegemma()
'''

DECLARED_MODEL_SRC = """
def declared_model(agent_dir):
    import yaml as _yaml

    class _L(_yaml.SafeLoader):
        pass

    _L.add_multi_constructor('', lambda l, suffix, node: getattr(node, 'value', None))
    found = set()
    for q in sorted(Path(agent_dir).rglob('*.yaml')) + sorted(Path(agent_dir).rglob('*.yml')):
        doc = _yaml.load(q.read_text(encoding='utf-8'), Loader=_L) or {}
        if isinstance(doc, dict) and isinstance(doc.get('model'), str):
            name = doc['model'].strip()
            if not name:
                raise AssertionError('blank model string declared in ' + q.name)
            found.add(name)
    if not found:
        raise AssertionError('no model declared in the candidate configuration')
    if len(found) > 1:
        raise AssertionError('ambiguous model declaration: ' + repr(sorted(found)))
    return found.pop()
"""


def specialize(P):
    P.CANDIDATES = {'V5': SOURCE}
    # V5's own eval_config budgets, substituted into the config cell literal.
    old_budget = ('BUDGET = dict(max_time_minutes=10.0, max_tool_calls=100, '
                  'max_turns=60, timeout_seconds=300)')
    new_budget = ('BUDGET = dict(max_time_minutes=5.0, max_tool_calls=100, '
                  'max_turns=60, timeout_seconds=60)')
    assert P.CFG.count(old_budget) == 1, 'budget literal anchor missing; refusing to generate'
    P.CFG = P.CFG.replace(old_budget, new_budget, 1)
    expected = {}
    for key, folder in P.CANDIDATES.items():
        expected[key] = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in folder.rglob('*') if p.is_file()}
    marker = '\na = (CAND_DIRS["A"] / "configs" / "sampling.yaml").read_bytes()'
    assert P.CANDS.count(marker) == 1
    # Pinned dependency identities, re-verified against their recorded manifests before use.
    import json as _json
    compiler = ROOT / 'experiments/v5_budget_v2/compiler_0_2_13/src/adk_submission'
    _pin = _json.loads((ROOT / 'experiments/v5_budget_v2/compiler_0_2_13_hashes.json')
                       .read_text(encoding='utf-8'))
    hashes = {q.relative_to(compiler).as_posix(): hashlib.sha256(q.read_bytes()).hexdigest()
              for q in compiler.rglob('*.py')}
    assert hashes == _pin['python_files'], '0.2.13 source drift against recorded hashes'
    swegemma_src = ROOT / 'experiments/v5_budget_v2/swegemma_0_2_11/src/swegemma'
    _sg_pin = _json.loads((ROOT / 'experiments/v5_budget_v2/swegemma_0_2_11_hashes.json')
                          .read_text(encoding='utf-8'))
    sg_hashes = {q.relative_to(swegemma_src).as_posix(): hashlib.sha256(q.read_bytes()).hexdigest()
                 for q in swegemma_src.rglob('*.py')}
    assert sg_hashes == _sg_pin['python_files'], 'swegemma 0.2.11 source drift against manifest'

    body = P.CANDS.split(marker)[0]

    # Remove the obsolete import and its call from GENERATED EXECUTABLE CODE: swegemma 0.2.11
    # no longer ships swegemma/models/discovery.py, so this import failed at runtime.
    dead_import = ('from swegemma.models.discovery import '
                   'validate_single_declared_model' + chr(10))
    assert body.count(dead_import) == 1, 'obsolete import anchor missing; refusing to generate'
    body = body.replace(dead_import, '', 1)
    assert body.count('validate_single_declared_model(d)') == 1, 'call anchor missing'
    body = body.replace('validate_single_declared_model(d)', 'declared_model(d)', 1)
    assert 'validate_single_declared_model' not in body, 'obsolete symbol still referenced'

    # Gates and the model helper are PREPENDED: everything later in this cell imports
    # adk_submission and swegemma, so verifying after those imports would verify too late.
    prelude = ('# ---- dependency identity gates, before any dependent code ----' + chr(10)
               + 'import hashlib, json' + chr(10) + 'from pathlib import Path' + chr(10)
               + chr(10) + 'EXPECTED_COMPILER_FILES = ' + repr(hashes) + COMPILER_CHECK
               + chr(10) + 'EXPECTED_SWEGEMMA_FILES = ' + repr(sg_hashes) + SWEGEMMA_CHECK
               + DECLARED_MODEL_SRC + '# ---- end gates ----' + chr(10))

    P.CANDS = prelude + body + chr(10) + 'EXPECTED_FILES = ' + repr(expected) + CAND_CHECK
    assert P.CANDS.index('verify_runtime_compiler()') < P.CANDS.index('build_submission_limits')
    assert P.CANDS.index('verify_runtime_swegemma()') < P.CANDS.index('declared_model(d)')
    assert 'validate_single_declared_model' not in P.CANDS

    P.SERVER = P.SERVER.replace('CAND_DIRS["A"]', 'CAND_DIRS["V5"]')
    P.SERVER = P.SERVER.replace("# vLLM with the grader's serving settings.", '# vLLM with the public harness serving configuration; private parity unverified.')
    P.SERVER = P.SERVER.replace("for cand in ('A','B'):", 'for cand in CAND_DIRS:')
    P.SERVER = P.SERVER.replace('which is what makes A and B differ.', 'Single arm: the exact V5 agent under V5 budgets.')

def main():
    require_unlaunched(OUT_EXP)
    expected = {'V5': '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'}
    for key, folder in [('V5', SOURCE)]:
        assert M.P.bundle(folder)[1] == expected[key], 'Candidate drift'
    M.TASKS = TASKS
    # The shared generator builds two candidate paths before CUSTOMIZE_CELLS runs; this
    # placeholder is discarded there, where P.CANDIDATES becomes the single V5 arm.
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = '_unused', EXP, 'candidate_V5'
    M.OUT_NAME, M.NB_FILENAME = 'v5_budget', 'v5_budget.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-v5-budget', 'gemma4-v5-budget'
    M.CFG_LABEL, M.ORDER_EXPR = 'v5 budget diagnostic:', 'ORDER = ' + repr(ORDER)
    M.RUN_COUNT_PHRASE = 'the four runs will NOT'
    M.ARM_FOR_LAUNCH = False
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 90, 20
    M.CUSTOMIZE_CELLS = specialize
    M.MD = """# V5 baseline measurement, four runs, one arm - disabled

The exact submitted V5 agent, byte-identical to the frozen ON candidate, run under V5's own
packaged eval_config budgets: max_time_minutes 5, max_turns 60, max_tool_calls 100,
timeout_seconds 60. The command timeout is V5's shipped value, not the development default
of 300.

One arm, so there is nothing to counterbalance. Four development tasks, one run each, in the
declared order rich_3278, rich_3535, rich_3675, rich_3942. Hold-out tasks are untouched.

Purpose: describe V5's verified-solve rate and elapsed time on development tasks under V5's
own budgets, which has never been measured. This is descriptive baseline evidence. It does not
supply a matched control for a later candidate comparison; any future candidate test should
run V5 contemporaneously in the same session.

The only package change from V4 was evaluation limits. V4 timed out; V5 scored 0.13. Limits
are the leading explanation for completion, but their effect on patch quality and score is not
isolated.

THIS IS THE V5 AGENT AND BUDGETS IN THE PUBLIC DEVELOPMENT HARNESS, not
private-grader-equivalent execution. Runtime deviations, including evaluation event compaction
at token_threshold 20480 which the private grader applies only if its own config sets it, are
listed in experiments/v5_budget_v1/PLAN.md. Report solves, graded failures, candidate no-patch
and time-budget failures, and environment failures separately; every attempted row stays
visible. Four tasks from one repository cannot predict the hidden set or a public score.
"""
    M.main()
    raw = (ROOT/'notebooks/v5_budget/v5_budget.ipynb').read_bytes()
    assert raw.count(b'DISPATCH_CONFIRM = False') == 1
    assert b'DISPATCH_CONFIRM = True' not in raw
    compiler_pin = json.loads((ROOT / 'experiments/v5_budget_v2/compiler_0_2_13_hashes.json')
                              .read_text(encoding='utf-8'))
    record = {'notebook_sha256':hashlib.sha256(raw).hexdigest(), 'candidates':expected,
              'order':ORDER, 'dispatch':False, 'compiler_version':compiler_pin['version'],
              'compiler_wheel_sha256':compiler_pin['wheel_sha256']}
    OUT_EXP.mkdir(parents=True, exist_ok=True)
    record['tasks'] = TASKS
    record['budget'] = dict(max_time_minutes=5.0, max_tool_calls=100, max_turns=60, timeout_seconds=60)
    record['purpose'] = 'descriptive V5 baseline; not a matched control for a later A/B'
    record['harness'] = 'public development harness, not private-grader-equivalent'
    record['docker_image'] = IMAGE
    meta_path = ROOT/'notebooks/v5_budget/kernel-metadata.json'
    meta = json.loads(meta_path.read_text())
    meta['docker_image'] = IMAGE
    meta_path.write_text(json.dumps(meta, indent=2) + chr(10))
    record['metadata_sha256'] = hashlib.sha256(meta_path.read_bytes()).hexdigest()
    (OUT_EXP/'NOTEBOOK_PREPARED.json').write_text(json.dumps(record,indent=2))
    print('prepared (disabled):', meta['id'])
    print('notebook sha256:', record['notebook_sha256'])
    print('metadata sha256:', record['metadata_sha256'])

if __name__ == '__main__':
    assert len(sys.argv) == 1, 'Preparation only; arming requires a reviewed launch step'
    main()
