"""Execute generated cells with fake model/sandboxes, real compiler hash checks."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
os.environ['NB_TARGET'] = 'shellread'
import test_pilot_notebook as H
from make_shellread_notebook import ORDER
ROOT = Path(__file__).resolve().parent.parent
COMPILER = ROOT/'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'

def hook(fault=None):
    def edit(i, cell, ns):
        if 'verify_runtime_compiler()' in cell:
            ns['COMPILER_FIXTURE'] = COMPILER
            version = '0.2.11' if fault == 'compiler' else '0.2.12'
            cell = cell.replace('verify_runtime_compiler()', f'verify_runtime_compiler(COMPILER_FIXTURE, {version!r})')
            if fault == 'source':
                cell = cell.replace('verify_runtime_compiler(COMPILER_FIXTURE,', "EXPECTED_COMPILER_FILES['schema.py'] = 'wrong'\nverify_runtime_compiler(COMPILER_FIXTURE,",1)
            if fault == 'candidate':
                cell = cell.replace('for key, folder in CAND_DIRS.items():', "(CAND_DIRS['S_shellread']/'agent.yaml').write_text('drift')\nfor key, folder in CAND_DIRS.items():",1)
        if fault == 'control':
            cell = cell.replace("'pytest_exit': 1", "'pytest_exit': 0",1)
        return cell
    return edit

def main():
    nb=ROOT/'notebooks/shellread/shellread.ipynb'; raw=nb.read_bytes()
    prepared=json.loads((ROOT/'experiments/shellread_v1/NOTEBOOK_PREPARED.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==prepared['notebook_sha256']
    assert b'DISPATCH_CONFIRM = False' in raw and b'DISPATCH_CONFIRM = True' not in raw
    log=io.StringIO()
    with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(log):
        tmp=Path(temp)
        for armed in [False,True]:
            ns=H.run_cells(tmp/str(armed),dispatch=armed,server_healthy=True,hook=hook())
            assert len(ns['rows'])==4
            assert H.counts()['evaluations']==(4 if armed else 0)
            assert H.counts()['server_started']==H.counts()['server_stopped']==int(armed)
            if armed:
                assert [(r['task'],r['candidate']) for r in ns['RUNS']]==ORDER
            else:
                assert all(not r['attempted'] for r in ns['rows'])
        for fault in ['compiler','source','candidate','control','provenance']:
            options={'grading_import_in_checkout':False} if fault=='provenance' else {}
            try:
                H.run_cells(tmp/fault,dispatch=True,server_healthy=True,hook=hook(fault),**options)
            except (AssertionError,RuntimeError,SystemExit):
                assert H.counts()['server_created']==H.counts()['evaluations']==0
            else:
                raise AssertionError('Failed to block: '+fault)
    assert nb.read_bytes()==raw
    (ROOT/'experiments/shellread_v1/EXECUTION_CHECKS.log').write_text(log.getvalue(),encoding='utf8')
    print('PASS: disabled, four-run order, lifecycle, compiler version/source drift, candidate drift, controls, provenance; simulated dependencies.')

if __name__=='__main__':
    main()
