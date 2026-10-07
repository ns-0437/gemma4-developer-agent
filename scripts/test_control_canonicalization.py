"""Focused tests for sandbox-root canonicalization in the control comparison.

Runs against the CPU-only control replay notebook, which carries the control cells and no model
startup. The fixture varies the observed sandbox root independently of the saved one by default, so
a regression to root-sensitive identities cannot pass unnoticed.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
os.environ['NB_TARGET'] = 'control_replay'
import test_pilot_notebook as H  # noqa: E402

COMPILER = ROOT / 'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'
TASKS = ['fastapi_15280', 'requests_7427', 'rich_3894']


def hook(conflicting_roots=False):
    def edit(i, cell, ns):
        if 'verify_runtime_compiler()' in cell:
            ns['COMPILER_FIXTURE'] = COMPILER
            cell = cell.replace('verify_runtime_compiler()',
                                "verify_runtime_compiler(COMPILER_FIXTURE, '0.2.12')")
        if conflicting_roots and 'CONTROL_STOP_REASON = None' in cell:
            for arm in ns['CONTROL_EVIDENCE']['requests_7427'].values():
                arm['grading_import'] = '/tmp/conflicting/workspace/requests/__init__.py'
        return cell
    return edit


def run(tmp, **fixture):
    conflicting_roots = fixture.pop('ambiguous_root', False)
    H.CONTROL_FIXTURE.update(fixture) if hasattr(H, 'CONTROL_FIXTURE') else None
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        ns = H.run_cells(Path(tmp), dispatch=False, server_healthy=True,
                         hook=hook(conflicting_roots=conflicting_roots))
    return ns, log.getvalue()


def expect_control_failure(label, mutate_xml=None, detail_key=None, diagnostic=None, **fixture):
    """Require the intended gate refusal and inspect its persisted evidence."""
    with tempfile.TemporaryDirectory() as tmp:
        saved = dict(H.CONTROL_RAW_XML)
        saved_fixture = dict(H.CONTROL_FIXTURE)
        if mutate_xml:
            for k in list(H.CONTROL_RAW_XML):
                H.CONTROL_RAW_XML[k] = mutate_xml(k, H.CONTROL_RAW_XML[k])
            assert H.CONTROL_RAW_XML != saved, 'fault did not change any fixture XML'
        work = Path(tmp) / 'w'
        try:
            run(work, **fixture)
        except AssertionError as exc:
            assert 'controls do not reproduce' in str(exc), 'unrelated assertion: ' + str(exc)
            records = json.loads((work / 'working/pilot/control_recheck.json').read_text())
            failed = [record for record in records if not record['agrees_with_saved']]
            assert failed, 'no persisted rejected arm'
            if detail_key:
                assert any(record['node_comparison'].get(detail_key) for record in failed), detail_key
            if diagnostic:
                assert any(diagnostic(record['canonicalization']) for record in failed), label
            assert H.counts()['server_created'] == H.counts()['evaluations'] == 0
            print('  PASS  %s\n          -> %s' % (label, str(exc).splitlines()[0][:130]))
            return
        finally:
            H.CONTROL_RAW_XML.clear()
            H.CONTROL_RAW_XML.update(saved)
            H.CONTROL_FIXTURE.clear()
            H.CONTROL_FIXTURE.update(saved_fixture)
    raise AssertionError('control gate did NOT refuse: ' + label)


def _helpers():
    """Load the canonicalization helpers straight out of the notebook fragment."""
    import ast
    import compare_cells as C
    tree = ast.parse(C.CONTROL_REVALIDATION)
    want = {'_canon_path', '_canon_re', 'canonicalize_nodes', 'canonicalize_targets',
            '_workspace_root_from_evidence'}
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
    assign = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, 'id', '') in ('WORKSPACE_TOKEN', '_EMPTY_DETAIL')
                      for t in n.targets)]
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=assign + keep, type_ignores=[])),
                 '<fragment>', 'exec'), ns)
    return ns


def group_0():
    print('0. canonicalizer unit behaviour')
    ns = _helpers()
    cn, ct, cp = ns['canonicalize_nodes'], ns['canonicalize_targets'], ns['_canon_path']
    R = '/tmp/swegemma_sandbox_aaa_bbb/workspace'
    a = {'t::x[%s/f.py]' % R: 'passed', 't::x[<WS>/f.py]': 'passed'}
    b = {'t::x[<WS>/f.py]': 'passed', 't::x[%s/f.py]' % R: 'passed'}
    c = {'t::x[%s/f.py]' % R: 'passed', 't::x[<WS>/f.py]': 'failed'}
    for label, nodes in (('substituted first', a), ('literal <WS> first', b),
                         ('differing outcomes', c)):
        assert cn(nodes, R)[2], 'many-to-one mapping accepted (%s)' % label
    print('  PASS  many-to-one mapping rejected in both orders and with equal outcomes')

    assert cp('t::x[%s/f.py]' % R, R) == 't::x[<WS>/f.py]'
    assert cp('t::x[%s_backup/f.py]' % R, R) == 't::x[%s_backup/f.py]' % R, 'sibling path mangled'
    assert cp('t::x[%s]' % R, R) == 't::x[<WS>]'
    assert cp('tests.test_workspace::test_workspace_thing', R) ==         'tests.test_workspace::test_workspace_thing', 'classname or test name altered'
    assert cp('t::x[workspace-param]', R) == 't::x[workspace-param]', 'non-path parameter altered'
    assert ct(['t::x[%s/f.py]' % R, 't::x[%s_backup/f.py]' % R], R) ==         ['t::x[<WS>/f.py]', 't::x[%s_backup/f.py]' % R], 'targets normalized differently'
    print('  PASS  boundaries respected; siblings, classnames, test names and params preserved')
    print('  PASS  nodes and targets use the same normalization')

    root, err = ns['_workspace_root_from_evidence']('/a/workspace/x', '/b/workspace/y')
    assert root is None and 'ambiguous' in err, 'conflicting roots not refused'
    print('  PASS  conflicting recorded roots refused at the helper level')


def _flip_one_outcome(key, xml):
    """Turn exactly one passing testcase into a failing one, keeping its identity byte-identical."""
    if key[0] != 'requests_7427':
        return xml
    i = xml.find('<testcase ')
    while i >= 0:
        end = xml.find('/>', i)
        nxt = xml.find('<testcase ', i + 1)
        if 0 < end < (nxt if nxt > 0 else len(xml)):
            head = xml[i:end]
            return xml[:i] + head + '><failure message="flipped"/></testcase>' + xml[end + 2:]
        i = nxt
    return xml


def _add_ws_collision(key, xml):
    """Add a node whose identity is already the canonical token, colliding with a real path."""
    if key[0] != 'requests_7427':
        return xml
    document = ET.fromstring(xml)
    root = H.CONTROL_SAVED_ROOT[key]
    for suite in document.iter('testsuite'):
        for case in list(suite):
            if case.tag == 'testcase' and root in case.get('name', ''):
                alias = ET.Element('testcase', {
                    'classname': case.get('classname', ''),
                    'name': case.get('name').replace(root, '<WS>'),
                })
                suite.append(alias)
                return ET.tostring(document, encoding='unicode')
    raise AssertionError('no workspace parameter available for collision fixture')


def main():
    group_0()
    print('1. all six controls reproduce after canonicalization, with roots varying')
    assert H.CONTROL_OBSERVED_ROOT, 'fixture did not mint observed roots'
    diff = [k for k in H.CONTROL_SAVED_ROOT
            if H.CONTROL_OBSERVED_ROOT.get(k) != H.CONTROL_SAVED_ROOT[k]]
    assert len(diff) == len(H.CONTROL_SAVED_ROOT), 'fixture reused the saved root somewhere'
    print('  PASS  fixture varies the observed sandbox root on all %d arms' % len(diff))

    with tempfile.TemporaryDirectory() as tmp:
        ns, out = run(Path(tmp) / 'ok')
        rechecks = ns['CONTROL_RECHECK']
        assert len(rechecks) == 6, 'expected six control arms, got %d' % len(rechecks)
        bad = [(c['task'], c['arm']) for c in rechecks if not c['agrees_with_saved']]
        assert not bad, 'these arms still disagree: %s' % (bad,)
        req = [c for c in rechecks if c['task'] == 'requests_7427']
        assert len(req) == 2 and all(c['agrees_with_saved'] for c in req)
        assert all(c['canonicalization']['applied'] for c in req), 'canonicalization not applied'
        for c in rechecks:
            canon = c['canonicalization']
            if canon['applied']:
                assert canon['saved_root'] != canon['observed_root'], 'roots were equal'
                assert not canon['expected_collisions'] and not canon['observed_collisions']
        print('  PASS  both requests_7427 arms match after canonicalization')
        print('  PASS  all 6 arms agree; mappings and diagnostics recorded per arm')
        applied = [(c['task'], c['arm']) for c in rechecks if c['canonicalization']['applied']]
        print('        canonicalization applied on: %s' % (applied,))

    print('2. real differences must still fail')
    expect_control_failure(
        'different RELATIVE path inside the same root stays different',
        mutate_xml=lambda k, x: x.replace('/workspace/tests/test_utils.py',
                                          '/workspace/tests/other_utils.py'))
    expect_control_failure(
        'non-path parameter changed stays different',
        mutate_xml=lambda k, x: x.replace('[StringIO-Test]', '[StringIO-Changed]'))
    expect_control_failure(
        'a CHANGED OUTCOME with identity preserved fails',
        mutate_xml=_flip_one_outcome, detail_key='changed')
    expect_control_failure(
        'conflicting recorded workspace roots are refused',
        ambiguous_root=True,
        diagnostic=lambda c: 'ambiguous workspace root' in (c.get('refused') or ''))
    expect_control_failure(
        'nonzero workspace probe with plausible stdout is refused',
        workspace_probe_rc=3,
        diagnostic=lambda c: 'workspace probe exited' in (c.get('refused') or ''))
    expect_control_failure(
        'many-to-one identity mapping (literal <WS> colliding) is refused',
        mutate_xml=_add_ws_collision,
        diagnostic=lambda c: bool(c.get('observed_collisions')))

    print('3. all six controls remain required before model startup')
    text = json.loads((ROOT / 'notebooks/control_replay/control_replay.ipynb')
                      .read_text(encoding='utf-8'))
    blob = '\n'.join(''.join(c['source']) for c in text['cells'])
    assert '_expected_arms = 2 * len(SELECTED)' in blob, 'arm-count requirement removed'
    assert 'do not start the model' in blob, 'startup refusal text removed'
    assert 'agrees_with_saved' in blob
    print('  PASS  arm-count requirement and startup refusal still present')
    print('\nPASS: canonicalization fixes requests_7427 without weakening any other check.')


if __name__ == '__main__':
    main()
