"""Execute generated temperature notebook with existing simulated dependencies; no model."""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['NB_TARGET'] = 'temperature'
import test_pilot_notebook as H

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = [(t, c) for i, t in enumerate(['rich_3278', 'rich_3535', 'rich_3675', 'rich_3942'])
            for c in (('S', 'S_temp') if i % 2 == 0 else ('S_temp', 'S'))]


def main():
    notebook = ROOT / 'notebooks/temperature/temperature.ipynb'
    raw = notebook.read_bytes()
    manifest = json.loads((ROOT / 'experiments/temperature_v1/PREPARED.json').read_text())
    armed = '--armed' in sys.argv
    if armed:
        baseline = (ROOT / 'experiments/temperature_v1/temperature_disabled.ipynb').read_bytes()
        assert hashlib.sha256(baseline).hexdigest() == manifest['notebook_sha256']
        assert raw == baseline.replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1)
    else:
        assert hashlib.sha256(raw).hexdigest() == manifest['notebook_sha256']
    source = '\n'.join(''.join(c['source']) for c in json.loads(raw)['cells'])
    assert source.count('DISPATCH_CONFIRM = ' + str(armed)) == 1
    assert 'DISPATCH_CONFIRM = ' + str(not armed) not in source
    checks = 2
    log = io.StringIO()
    with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(log):
        tmp = Path(temp)
        ns = H.run_cells(tmp / 'disabled', dispatch=False)
        assert H.counts()['server_created'] == H.counts()['evaluations'] == 0
        assert len(ns['rows']) == 8 and all(not r['attempted'] for r in ns['rows'])
        checks += 2
        ns = H.run_cells(tmp / 'enabled', dispatch=True, server_healthy=True)
        assert [(r['task'], r['candidate']) for r in ns['RUNS']] == EXPECTED
        assert H.counts()['evaluations'] == 8
        assert H.counts()['server_started'] == H.counts()['server_stopped'] == 1
        assert len(ns['rows']) == 8 and not ns.get('STOP_REASON')
        assert set(ns['CAND_DIRS']) == {'S', 'S_temp'}
        assert ns['BUNDLES']['S']['sha256'] == manifest['candidates']['S']
        checks += 6
        def corrupt_control(i, cell, ns):
            return cell.replace("'pytest_exit': 1", "'pytest_exit': 0", 1)
        def corrupt_candidate(i, cell, ns):
            marker = '\na_root, b_root = '
            if marker in cell:
                cell = cell.replace(marker, "\n(CAND_DIRS['S_temp'] / 'prompts/system.md').write_text('drift')\n" + marker, 1)
            return cell
        for name, options in [('precondition', {'grading_import_in_checkout': False}),
                              ('control', {'hook': corrupt_control}),
                              ('candidate', {'hook': corrupt_candidate})]:
            try:
                H.run_cells(tmp / name, dispatch=True, server_healthy=True, **options)
            except (AssertionError, RuntimeError, SystemExit):
                assert H.counts()['server_created'] == H.counts()['evaluations'] == 0
            else:
                raise AssertionError(f'{name} did not stop dispatch')
            checks += 1
    assert notebook.read_bytes() == raw
    checks += 1
    (ROOT / 'experiments/temperature_v1/execution_checks.log').write_text(log.getvalue(), encoding='utf-8')
    print(f'{checks} focused checks passed; simulated dependencies, no model or real sandbox.')


if __name__ == '__main__':
    main()
