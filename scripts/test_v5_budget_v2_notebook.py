"""Exercise repaired GPU packet with simulated services only; no launch."""
import ast
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path
import test_v5_control_replay_notebook as C

ROOT=Path(__file__).resolve().parent.parent
NB=ROOT/'notebooks/v5_budget_v2/v5_budget_v2.ipynb'


def main():
    raw=NB.read_bytes(); prepared=json.loads((ROOT/'experiments/v5_budget_v2/gpu_baseline/NOTEBOOK_PREPARED.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==prepared['notebook_sha256']
    meta=(NB.parent/'kernel-metadata.json').read_bytes()
    assert hashlib.sha256(meta).hexdigest()==prepared['metadata_sha256']
    assert raw.count(b'DISPATCH_CONFIRM = False')==1 and b'DISPATCH_CONFIRM = True' not in raw
    assert b'validate_single_declared_model' not in raw
    assert prepared['compiler_version']=='0.2.13'
    original=json.loads((ROOT/'experiments/v5_budget_v1/v5_budget_disabled.ipynb').read_text())
    current=json.loads(raw)
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
            assert counts['evaluations']==(4 if enabled else 0),counts
            assert counts['server_started']==(1 if enabled else 0),counts
            assert counts['server_stopped']==(1 if enabled else 0),counts
            print('PASS: simulated dispatch',enabled,counts)
    print('PASS: repaired GPU baseline; one candidate-validation cell changed, original experiment preserved')


if __name__=='__main__':main()
