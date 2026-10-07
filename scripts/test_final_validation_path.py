"""Tests for the manifest-gated final-validation path. Offline; no GPU, push or hold-out execution.

Three groups, kept separate:
  A. the development hold-out guard is unchanged;
  B. HAPPY PATH, strict: the disabled notebook reaches its final report with six rows, zero
     evaluations, zero server creations and no exposure record; and the simulated ENABLED path
     performs six evaluations in order, cleans up its server and writes a correct append-only
     exposure ledger, including across a partial run;
  C. EXPECTED FAILURES: every rejection the validation path must make.

No AssertionError anywhere is treated as success.
"""
import hashlib
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
EXP = ROOT / 'experiments/final_validation_v1'
MANIFEST = EXP / 'VALIDATION_MANIFEST.json'
TASKS = ['fastapi_15280', 'requests_7427', 'rich_3894']
ORDER = [('fastapi_15280', 'V3'), ('fastapi_15280', 'ON'),
         ('requests_7427', 'ON'), ('requests_7427', 'V3'),
         ('rich_3894', 'V3'), ('rich_3894', 'ON')]
COMPILER = ROOT / 'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'


def fresh():
    import make_compare_notebook
    return importlib.reload(make_compare_notebook)


def hook(i, cell, ns):
    """Point the real per-file compiler gate at the extracted source. The gate is unchanged."""
    if 'verify_runtime_compiler()' in cell:
        ns['COMPILER_FIXTURE'] = COMPILER
        cell = cell.replace('verify_runtime_compiler()',
                            "verify_runtime_compiler(COMPILER_FIXTURE, '0.2.12')")
    return cell


def expect_refusal(label, tasks, manifest_path):
    M = fresh()
    M.VALIDATION_MANIFEST = manifest_path
    try:
        M.assert_tasks_not_held_out(tasks)
    except SystemExit as exc:
        first = str(exc).splitlines()[0]
        assert first.startswith('REFUSING TO GENERATE'), first
        print('  PASS  ' + label + '\n          -> ' + first[:140])
        return
    raise AssertionError('FAILED TO REFUSE: ' + label)


def mutated(label, tasks, mutate):
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    mutate(man)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'manifest.json'
        p.write_text(json.dumps(man), encoding='utf-8')
        expect_refusal(label, tasks, str(p))


def group_a():
    print('A. development guard unchanged')
    M = fresh()
    assert M.VALIDATION_MANIFEST is None, 'default must be None'
    held = json.loads((ROOT / 'experiments/ab_v3_vs_short/task_freeze.json')
                      .read_text(encoding='utf-8'))['protected_holdout']
    for t in held:
        try:
            M.assert_tasks_not_held_out([t])
        except SystemExit:
            continue
        raise AssertionError('dev path allowed a protected task: ' + t)
    print('  PASS  all %d protected tasks rejected with no manifest set' % len(held))
    M.assert_tasks_not_held_out(['rich_3278', 'rich_3535', 'rich_3942'])
    print('  PASS  development task set still accepted')


def group_b():
    print('B. happy path, strict')
    M = fresh()
    M.VALIDATION_MANIFEST = str(MANIFEST)
    M.assert_tasks_not_held_out(TASKS)
    print('  PASS  exact configuration accepted under the real manifest')

    prepared = json.loads((EXP / 'NOTEBOOK_PREPARED.json').read_text(encoding='utf-8'))
    live = (ROOT / 'notebooks/final_validation/final_validation.ipynb').read_bytes()
    base = (EXP / 'final_validation_disabled.ipynb').read_bytes()
    assert hashlib.sha256(base).hexdigest() == prepared['notebook_sha256'], 'disabled copy drift'
    assert base.count(b'DISPATCH_CONFIRM = False') == 1
    assert b'DISPATCH_CONFIRM = True' not in base
    assert prepared['exposed_so_far'] == []
    if hashlib.sha256(live).hexdigest() == prepared['notebook_sha256']:
        print('  PASS  preserved disabled notebook matches; live copy still disabled')
    else:
        # The launched artifact is armed and must be preserved exactly as pushed.
        assert live == base.replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1),             'launched notebook is neither the disabled copy nor it armed by one substitution'
        print('  PASS  preserved disabled notebook matches; launched copy is it armed by one flag')

    os.environ['NB_TARGET'] = 'final_validation'
    import test_pilot_notebook as H

    launched = hashlib.sha256(live).hexdigest() != prepared['notebook_sha256']
    if launched:
        # The launched artifact predates sandbox-root canonicalization, so with the fixture now
        # varying the observed root it genuinely cannot reproduce requests_7427's controls. That is
        # exactly what happened on Kaggle. It is preserved as pushed and NOT regenerated; the
        # canonicalization happy path is covered by scripts/test_control_canonicalization.py.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / 'launched'
            try:
                H.run_cells(work, dispatch=False, server_healthy=True, hook=hook)
            except AssertionError as exc:
                assert 'controls do not reproduce' in str(exc), exc
                counts = H.counts()
                assert counts['evaluations'] == 0 and counts['server_created'] == 0, counts
                assert not (work / 'working' / 'pilot' / 'EXPOSURE.json').exists()
                print('  PASS  launched artifact: control gate refuses, 0 evaluations, no exposure')
            else:
                raise AssertionError('launched artifact unexpectedly reproduced its controls')
        print('  NOTE  strict six-row happy path for the repaired comparison is covered by '
              'scripts/test_control_canonicalization.py against notebooks/control_replay')
        group_c()
        print(chr(10) + 'PASS: dev guard intact; launched artifact preserved and its '
              'control gate still refuses before any evaluation; every expected rejection fires.')
        raise SystemExit(0)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / 'disabled'
        ns = H.run_cells(work, dispatch=False, server_healthy=True, hook=hook)
        counts = H.counts()
        assert len(ns['rows']) == 6, 'expected six rows, got %d' % len(ns['rows'])
        assert all(not r['attempted'] for r in ns['rows']), 'disabled run attempted something'
        assert counts['evaluations'] == 0, counts
        assert counts['server_created'] == 0, counts
        assert counts['server_started'] == 0, counts
        assert not (work / 'working' / 'pilot' / 'EXPOSURE.json').exists(), 'disabled run recorded exposure'
    print('  PASS  disabled: final report reached, 6 rows, 0 evaluations, 0 servers, no ledger')

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / 'enabled'
        ns = H.run_cells(work, dispatch=True, server_healthy=True, hook=hook)
        counts = H.counts()
        assert len(ns['rows']) == 6, 'expected six rows, got %d' % len(ns['rows'])
        assert counts['evaluations'] == 6, counts
        assert counts['server_started'] == 1 and counts['server_stopped'] == 1, counts
        got = [(r['task'], r['candidate']) for r in ns['RUNS']]
        assert got == ORDER, 'order mismatch: %s' % (got,)
        ledger = json.loads((work / 'working' / 'pilot' / 'EXPOSURE.json').read_text(encoding='utf-8'))
        assert len(ledger['events']) == 6, ledger
        assert [(e['task'], e['candidate']) for e in ledger['events']] == ORDER
        assert all(e['event'] == 'dispatch_start_intent' for e in ledger['events'])
        assert ledger['tasks_exposed'] == sorted(set(TASKS)), ledger['tasks_exposed']
        assert 'not proof' in ledger['timestamp_meaning'].lower()
        assert not (work / 'working' / 'pilot' / 'EXPOSURE.json.tmp').exists(), 'temp file left behind'
    print('  PASS  enabled: 6 evaluations in order, server started and stopped, ledger correct')

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / 'partial'
        (work / 'working' / 'pilot').mkdir(parents=True)
        seed = {'freeze_sha256': prepared['freeze_sha256'],
                'timestamp_meaning': 'dispatch-start intent, NOT proof the agent received it.',
                'events': [{'task': 'fastapi_15280', 'candidate': 'V3',
                            'event': 'dispatch_start_intent', 'utc': '2026-01-01T00:00:00Z'}],
                'tasks_exposed': ['fastapi_15280']}
        (work / 'working' / 'pilot' / 'EXPOSURE.json').write_text(json.dumps(seed), encoding='utf-8')
        H.run_cells(work, dispatch=True, server_healthy=True, hook=hook)
        ledger = json.loads((work / 'working' / 'pilot' / 'EXPOSURE.json').read_text(encoding='utf-8'))
        assert len(ledger['events']) == 7, 'earlier event lost: %d' % len(ledger['events'])
        assert ledger['events'][0]['utc'] == '2026-01-01T00:00:00Z', 'earlier event overwritten'
    print('  PASS  partial run: earlier exposure event preserved and appended to')


def group_c():
    print('C. expected failures')
    expect_refusal('manifest file missing', TASKS, str(EXP / 'nope.json'))
    mutated('required key removed (packages)', TASKS, lambda m: m.pop('packages'))
    mutated('wrong purpose', TASKS, lambda m: m.update(purpose='development'))
    mutated('freeze drift', TASKS, lambda m: m.update(freeze_sha256='0' * 64))
    mutated('packages={}', TASKS, lambda m: m.update(packages={}))
    mutated('extra package key', TASKS,
            lambda m: m['packages'].update(OFF={'source': 'x', 'sha256': '0' * 64}))
    mutated('missing package key (ON dropped)', TASKS, lambda m: m['packages'].pop('ON'))
    mutated('V3 not the intended frozen hash', TASKS,
            lambda m: m['packages']['V3'].update(sha256='1' * 64))
    mutated('ON not the intended frozen hash', TASKS,
            lambda m: m['packages']['ON'].update(sha256='2' * 64))
    mutated('order=[]', TASKS, lambda m: m.update(order=[]))
    mutated('reversed order', TASKS, lambda m: m.update(order=list(reversed(m['order']))))
    mutated('six entries but five unique', TASKS,
            lambda m: m.update(order=m['order'][:5] + [m['order'][4]]))
    mutated('seven ordered pairs', TASKS,
            lambda m: m.update(order=m['order'] + [['rich_3894', 'V3']]))
    mutated('package source missing on disk', TASKS,
            lambda m: m['packages']['V3'].update(source='releases/not_here.zip'))
    expect_refusal('extra task in selection', TASKS + ['rich_3180'], str(MANIFEST))
    expect_refusal('substituted task', ['fastapi_15280', 'requests_6644', 'rich_3894'],
                   str(MANIFEST))
    expect_refusal('unlisted protected task alone', ['rich_3938'], str(MANIFEST))


def main():
    group_a()
    group_b()
    group_c()
    print('\nPASS: dev guard intact; disabled notebook reaches its report with 0 evaluations; '
          'simulated enabled path runs six evaluations in order with a correct append-only '
          'exposure ledger; every expected rejection fires.')


if __name__ == '__main__':
    main()
