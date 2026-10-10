"""Verify the pinned final-validation packet and execute its cells with fake services.

No Kaggle requests or real model execution. Use --armed --baseline PATH only
after an authorized launch step; the baseline must match NOTEBOOK_PREPARED.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

os.environ['NB_TARGET'] = 'final_validation_v2'
import test_pilot_notebook as H
from verify_final_validation_packet import ORDER, verify_packet

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / 'experiments/final_validation_v2'
NB = ROOT / 'notebooks/final_validation_v2/final_validation_v2.ipynb'
COMPILER = ROOT / 'experiments/shellread_v1/compiler_0_2_12/src/adk_submission'


def hook(fault=None):
    def edit(index, cell, namespace):
        if fault == 'task' and 'EXPECTED_TASK_HASHES = ' in cell:
            namespace['ALL_BY_ID']['fastapi_15280'].problem_statement += ' drift'
        if 'verify_runtime_compiler()' in cell:
            namespace['COMPILER_FIXTURE'] = COMPILER
            version = '0.2.11' if fault == 'compiler' else '0.2.12'
            cell = cell.replace('verify_runtime_compiler()',
                                f'verify_runtime_compiler(COMPILER_FIXTURE, {version!r})')
            if fault == 'candidate':
                anchor = 'for key, folder in CAND_DIRS.items():'
                assert anchor in cell
                cell = cell.replace(anchor,
                                    "(CAND_DIRS['ON']/'agent.yaml').write_text('drift')\n" + anchor, 1)
        if fault == 'control' and 'CONTROL_STOP_REASON = None' in cell:
            namespace['CONTROL_EVIDENCE']['fastapi_15280']['negative']['pytest_exit'] = 0
        return cell
    return edit


def verify_ledger_refusal(tmp, freeze_sha256):
    """Corrupt evidence must survive refusal, with no evaluation and no server leak."""
    cases = [
        ('invalid_json', '{broken', json.JSONDecodeError, 'Expecting property name'),
        ('wrong_freeze', json.dumps({'freeze_sha256': '0' * 64, 'events': []}),
         AssertionError, 'different freeze'),
        ('invalid_events', json.dumps({'freeze_sha256': freeze_sha256, 'events': {}}),
         AssertionError, 'events are malformed'),
    ]
    for label, content, error_type, message in cases:
        work = tmp / label
        ledger = work / 'working/pilot/EXPOSURE.json'
        ledger.parent.mkdir(parents=True)
        ledger.write_text(content, encoding='utf-8')
        original = ledger.read_bytes()
        try:
            H.run_cells(work, dispatch=True, server_healthy=True, hook=hook())
        except error_type as exc:
            assert message in str(exc), (label, str(exc))
        else:
            raise AssertionError('Failed to refuse corrupt ledger: ' + label)
        assert ledger.read_bytes() == original, 'corrupt evidence was overwritten: ' + label
        assert H.counts()['evaluations'] == 0, label
        assert H.counts()['server_started'] == H.counts()['server_stopped'] == 1, label
        assert not ledger.with_name('EXPOSURE.json.tmp').exists(), label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--armed', action='store_true')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    raw = NB.read_bytes()
    prepared = json.loads((EXP / 'NOTEBOOK_PREPARED.json').read_text())
    verify_packet(raw, prepared, armed=args.armed,
                  baseline=args.baseline.read_bytes() if args.baseline else None)
    metadata = NB.with_name('kernel-metadata.json').read_bytes()
    assert hashlib.sha256(metadata).hexdigest() == prepared['metadata_sha256']
    meta = json.loads(metadata)
    assert meta['enable_gpu'] is True and meta['enable_internet'] is False
    assert meta['docker_image'] == prepared['docker_image']
    assert hashlib.sha256((ROOT / 'experiments/ab_v3_vs_short/task_freeze.json').read_bytes()).hexdigest() == prepared['freeze_sha256']

    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        for dispatch in (False, True):
            work = Path(tmp) / str(dispatch)
            ns = H.run_cells(work, dispatch=dispatch, server_healthy=True, hook=hook())
            counts = H.counts()
            assert len(ns['rows']) == 6
            assert counts['evaluations'] == (6 if dispatch else 0)
            assert counts['server_started'] == counts['server_stopped'] == int(dispatch)
            ledger = work / 'working/pilot/EXPOSURE.json'
            if dispatch:
                assert [(row['task'], row['candidate']) for row in ns['RUNS']] == ORDER
                events = json.loads(ledger.read_text())['events']
                assert [(event['task'], event['candidate']) for event in events] == ORDER
                assert all(event['event'] == 'dispatch_start_intent' for event in events)
            else:
                assert all(not row['attempted'] for row in ns['rows'])
                assert not ledger.exists()
        for fault, message in [('task', 'task content changed'),
                               ('compiler', 'Runtime compiler drift'),
                               ('candidate', 'Candidate file drift'),
                               ('control', 'controls do not reproduce')]:
            try:
                H.run_cells(Path(tmp) / fault, dispatch=True, server_healthy=True, hook=hook(fault))
            except AssertionError as exc:
                assert message in str(exc), (fault, str(exc))
                assert H.counts()['server_created'] == H.counts()['evaluations'] == 0
            else:
                raise AssertionError('Failed to refuse ' + fault)
        verify_ledger_refusal(Path(tmp), prepared['freeze_sha256'])
    assert NB.read_bytes() == raw, 'test modified the packet'
    assert NB.with_name('kernel-metadata.json').read_bytes() == metadata
    print('PASS: packet identity, six-run order, disabled/enabled lifecycle, ledger preservation and server cleanup on refusal, compiler/candidate/control refusal; simulated services only.')


if __name__ == '__main__':
    main()
