"""Prepare a DISABLED, CPU-only replay of the six final-validation controls.

Purpose: re-run only the control arms for fastapi_15280, requests_7427 and rich_3894 under the
same pinned image and the same wheel-install and compiler-identity checks, to see whether the
sandbox-root canonicalization makes all six reproduce on the real environment.

It contains NO model startup and NO candidate evaluation: the server, run-loop and result cells are
removed after generation and their absence is asserted. The launched final-validation notebook and
every raw artifact are untouched.

    python scripts/make_control_replay_notebook.py
"""
import hashlib
import json
import sys
from pathlib import Path

import make_compare_notebook as M
import make_final_validation_notebook as FV

ROOT = Path(__file__).resolve().parent.parent
OUT_NB_DIR = ROOT / 'notebooks/control_replay'
OUT_EXP = ROOT / 'experiments/control_replay_v1'
# Cell sources that must not survive into a CPU-only control replay.
# Cells that would start a model or evaluate a candidate. The config cell is KEPT with
# DISPATCH_CONFIRM = False: it carries task ids and budgets, and with no run loop the
# flag cannot dispatch anything, while its presence keeps the disabled-state check honest.
FORBIDDEN = ('Evaluator(',)
# Cells removed by ROLE, identified by their own leading comment, so a token rename
# cannot silently leave a model server or a result packet behind.
DROP_MARKERS = ('# vLLM with the public harness serving configuration',
                '# Result packet:')


def main() -> None:
    assert len(sys.argv) == 1, 'Preparation only'

    M.VALIDATION_MANIFEST = str(FV.MANIFEST)
    M.TASKS = FV.TASKS
    M.SECOND_KEY, M.SECOND_EXP, M.SECOND_DIR_NAME = 'ON', FV.EXP, 'candidate_ON'
    M.OUT_NAME, M.NB_FILENAME = 'control_replay', 'control_replay.ipynb'
    M.KERNEL_ID, M.KERNEL_TITLE = 'navin03/gemma4-control-replay', 'gemma4-control-replay'
    M.CFG_LABEL, M.ORDER_EXPR = 'control replay:', 'ORDER = ' + repr(FV.ORDER)
    M.RUN_COUNT_PHRASE = 'the six runs will NOT'
    M.ARM_FOR_LAUNCH = False
    M.SESSION_CAP_MIN, M.RUN_RESERVE_MIN = 60, 10
    M.CUSTOMIZE_CELLS = FV.specialize
    M.MD = """# CPU-ONLY CONTROL REPLAY, disabled

Re-runs ONLY the six control arms for fastapi_15280, requests_7427 and rich_3894, under the same
pinned image and the same wheel-install and compiler-identity checks as the final validation.

**No model startup and no candidate evaluation.** The server, run-loop and result cells are removed
at generation time and their absence is asserted. Nothing here can expose a hold-out task to an
agent: no agent runs. The candidate packages are still embedded and hash-checked, because the
compiler-identity gate reads them, but they are never executed against a task.

Purpose: establish whether the sandbox-root canonicalization makes all six controls reproduce on the
real environment. The previous final-validation attempt stopped at a control-identity mismatch before
candidate dispatch, on requests_7427, whose suite parametrises a test with the absolute workspace
path.
"""
    M.main()

    nb_path = OUT_NB_DIR / 'control_replay.ipynb'
    nb = json.loads(nb_path.read_text(encoding='utf-8'))
    before = len(nb['cells'])
    kept = []
    dropped = []
    for c in nb['cells']:
        src = ''.join(c['source'])
        marker = next((m for m in DROP_MARKERS if m in src), None)
        if marker:
            dropped.append(marker)
            continue
        if any(tok in src for tok in FORBIDDEN):
            dropped.append(next(t for t in FORBIDDEN if t in src))
            continue
        kept.append(c)
    nb['cells'] = kept
    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')

    raw = nb_path.read_bytes()
    text = '\n'.join(''.join(c['source']) for c in nb['cells'])
    # No server is STARTED and no candidate is evaluated. VLLM_* env vars in the install cell are
    # left alone: setting an environment variable cannot start a server.
    for tok in FORBIDDEN + ('submit_patch(', 'run_sync(_ev', 'vllm serve', 'vllm.entrypoints',
                            'serving configuration', 'Result packet', 'start_server'):
        assert tok not in text, 'forbidden construct survived: ' + tok
    assert text.count('DISPATCH_CONFIRM = False') == 1, 'config cell lost its disabled flag'
    assert 'DISPATCH_CONFIRM = True' not in text
    assert 'CONTROL_RECHECK' in text, 'control re-validation cell was dropped by mistake'
    assert 'verify_runtime_compiler' in text, 'compiler-identity gate was dropped'
    assert 'installing' in text and 'wheels' in text, 'wheelhouse install was dropped'
    assert 'canonicaliz' in text.lower(), 'canonicalization is not present in this notebook'

    meta_path = OUT_NB_DIR / 'kernel-metadata.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    meta.update({'docker_image': FV.IMAGE, 'enable_gpu': False, 'enable_tpu': False,
                 'enable_internet': False})
    meta.pop('machine_shape', None)
    meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')

    OUT_EXP.mkdir(parents=True, exist_ok=True)
    record = {'purpose': 'CPU-only replay of the six final-validation controls',
              'notebook_sha256': hashlib.sha256(raw).hexdigest(),
              'metadata_sha256': hashlib.sha256(meta_path.read_bytes()).hexdigest(),
              'cells_before': before, 'cells_after': len(kept),
              'dropped_for': sorted(set(dropped)),
              'tasks': FV.TASKS, 'docker_image': FV.IMAGE,
              'model_startup': False, 'candidate_evaluation': False, 'dispatch_flag': 'DISPATCH_CONFIRM = False retained in the config cell; no run loop exists',
              'freeze_sha256': FV.FREEZE_SHA256}
    (OUT_EXP / 'NOTEBOOK_PREPARED.json').write_text(json.dumps(record, indent=2) + '\n',
                                                    encoding='utf-8')
    print('prepared CPU-only control replay (disabled):', meta['id'])
    print('cells %d -> %d, dropped for: %s' % (before, len(kept), sorted(set(dropped))))
    print('notebook sha256:', record['notebook_sha256'])
    print('metadata sha256:', record['metadata_sha256'])


if __name__ == '__main__':
    main()
