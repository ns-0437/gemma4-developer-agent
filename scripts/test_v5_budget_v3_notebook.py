"""Exercise the disabled v3 (raised-timeout) GPU packet with simulated services only. No launch.

v3 has not been pushed, so there is no armed/launch record to verify yet (unlike
test_v5_budget_v2_notebook.py, which checks an already-launched kernel). This checks the
disabled packet only: exact single-line diff against the launched v2 packet, dispatch disabled,
candidate/order/budget unchanged, and the same simulated-lifecycle and refusal behaviour.
"""
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path
import test_v5_control_replay_notebook as C

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / 'notebooks/v5_budget_v3/v5_budget_v3.ipynb'
EXP = ROOT / 'experiments/v5_budget_v3/gpu_baseline'
NOTEBOOK_SHA = '8e5cea46bfdaa449281402a8f541558d42cac2141937cb6eaf35df99deaf21c3'
METADATA_SHA = '06d908c0a7e4d79fa1cd7329c580b18b9cb0111e5d17e869552c0bb7e518696b'


def main():
    raw = NB.read_bytes()
    digest = lambda b: hashlib.sha256(b).hexdigest()
    assert digest(raw) == NOTEBOOK_SHA, 'v3 notebook hash drift'
    assert digest((ROOT / 'notebooks/v5_budget_v3/kernel-metadata.json').read_bytes()) == METADATA_SHA
    assert b'validate_single_declared_model' not in raw
    assert raw.count(b'DISPATCH_CONFIRM = False') == 1 and b'DISPATCH_CONFIRM = True' not in raw

    prepared = json.loads((EXP / 'NOTEBOOK_PREPARED.json').read_text())
    assert prepared['notebook_sha256'] == NOTEBOOK_SHA
    assert prepared['startup_timeout_s'] == 1800
    assert prepared['order'] == [[t, 'V5'] for t in
                                 ('rich_3278', 'rich_3535', 'rich_3675', 'rich_3942')]
    assert prepared['budget'] == dict(max_time_minutes=5.0, max_tool_calls=100, max_turns=60,
                                      timeout_seconds=60)
    assert prepared['candidates'] == {'V5': '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'}

    # Exactly the startup_timeout line differs from the launched v2 packet; everything else,
    # including the dispatch flag's surrounding comment and every other cell, is unchanged.
    v2 = json.loads((ROOT / 'notebooks/v5_budget_v2/v5_budget_v2.ipynb').read_text(encoding='utf-8'))
    v3 = json.loads(raw)
    c2 = [''.join(c['source']) for c in v2['cells']]
    c3 = [''.join(c['source']) for c in v3['cells']]
    assert len(c2) == len(c3) == 13
    differences = [i for i in range(13) if c2[i] != c3[i]]
    # cell 1 differs only because v2 is ARMED (DISPATCH_CONFIRM True) and v3 is disabled;
    # cell 10 carries the one intended change.
    assert differences == [1, 10], differences
    assert 'startup_timeout=60 * 20)' in c2[10] and 'startup_timeout=1800)' in c3[10]
    assert c2[10].replace('startup_timeout=60 * 20)', 'startup_timeout=1800)') == c3[10]
    assert v2['metadata'] == v3['metadata']

    C.H.NB = NB
    for enabled in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                ns = C.H.run_cells(Path(tmp), dispatch=enabled, server_healthy=True, hook=C.hook())
            counts = C.H.counts()
            assert len(ns['CONTROL_RECHECK']) == 8
            assert all(a['agrees_with_saved'] and a['cleanup_ok'] for a in ns['CONTROL_RECHECK'])
            assert ns['ORDER'] == [(t, 'V5') for t in
                                   ('rich_3278', 'rich_3535', 'rich_3675', 'rich_3942')]
            assert len(ns['rows']) == 4
            if enabled:
                assert [(r['task'], r['candidate']) for r in ns['RUNS']] == ns['ORDER']
            else:
                assert all(not r['attempted'] for r in ns['rows'])
            assert counts['evaluations'] == (4 if enabled else 0), counts
            assert counts['server_started'] == (1 if enabled else 0), counts
            assert counts['server_stopped'] == (1 if enabled else 0), counts
            print('PASS: simulated dispatch', enabled, counts)

    for fault, kwargs, reason in [('compiler_version', {}, 'Runtime compiler drift'),
                                  (None, {'control_leak': True}, 'control sandbox cleanup failed')]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    C.H.run_cells(Path(tmp), dispatch=True, server_healthy=True,
                                 hook=C.hook(fault), **kwargs)
            except AssertionError as exc:
                assert reason in str(exc), str(exc)
            else:
                raise AssertionError('launch refusal did not fire')
            counts = C.H.counts()
            assert counts['evaluations'] == counts['server_created'] == 0, counts

    assert NB.read_bytes() == raw, 'test rewrote the disabled packet'
    print('PASS: v3 GPU baseline disabled; only startup_timeout changed (1200s -> 1800s), '
          'candidate/order/budget unchanged, not launched')


if __name__ == '__main__':
    main()
