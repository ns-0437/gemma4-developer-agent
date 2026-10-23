"""Exercise repaired GPU packet with simulated services only; no launch."""
import ast
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path
import test_v5_control_replay_notebook as C
from verify_v5_budget_launch import verify as verify_launch

ROOT=Path(__file__).resolve().parent.parent
NB=ROOT/'notebooks/v5_budget_v2/v5_budget_v2.ipynb'


def main():
    raw=NB.read_bytes()
    verify_launch()
    exp=ROOT/'experiments/v5_budget_v2/gpu_baseline'
    disabled=(exp/'v5_budget_v2_disabled.ipynb').read_bytes()
    assert b'validate_single_declared_model' not in raw
    original=json.loads((ROOT/'experiments/v5_budget_v1/v5_budget_disabled.ipynb').read_text())
    current=json.loads(disabled)
    differences=[i for i,(a,b) in enumerate(zip(original['cells'],current['cells'])) if ''.join(a['source'])!=''.join(b['source'])]
    assert len(original['cells'])==len(current['cells']) and differences==[7], differences
    assert original['metadata']==current['metadata']
    C.H.NB=NB
    for enabled in (False,True):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                ns=C.H.run_cells(Path(tmp),dispatch=enabled,server_healthy=True,hook=C.hook())
            counts=C.H.counts()
            assert len(ns['CONTROL_RECHECK'])==8
            assert all(a['agrees_with_saved'] and a['cleanup_ok'] for a in ns['CONTROL_RECHECK'])
            assert ns['ORDER']==[(t,'V5') for t in ['rich_3278','rich_3535','rich_3675','rich_3942']]
            assert ns['BUDGET']==dict(max_time_minutes=5.0,max_tool_calls=100,max_turns=60,timeout_seconds=60)
            assert len(ns['rows']) == 4, 'planned result rows must survive disabled dispatch'
            if enabled:
                assert [(r['task'],r['candidate']) for r in ns['RUNS']]==ns['ORDER']
            else:
                assert all(not r['attempted'] for r in ns['rows'])
            assert counts['evaluations']==(4 if enabled else 0),counts
            assert counts['server_started']==(1 if enabled else 0),counts
            assert counts['server_stopped']==(1 if enabled else 0),counts
            print('PASS: simulated dispatch',enabled,counts)
    for fault, kwargs, reason in [('compiler_version',{},'Runtime compiler drift'),
                                  (None,{'control_leak':True},'control sandbox cleanup failed')]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    C.H.run_cells(Path(tmp),dispatch=True,server_healthy=True,hook=C.hook(fault),**kwargs)
            except AssertionError as exc:
                assert reason in str(exc), str(exc)
            else:
                raise AssertionError('launch refusal did not fire')
            counts=C.H.counts()
            assert counts['evaluations']==counts['server_created']==0,counts
    assert NB.read_bytes()==raw, 'test rewrote launched notebook'
    print('PASS: repaired GPU baseline; one candidate-validation cell changed, original experiment preserved')


if __name__=='__main__':main()
