"""Create a CPU-only diagnostic from the working comparison's setup/control cells.

Never regenerates or modifies the comparison notebook. No model attachment or inference cells.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'notebooks' / 'control_preflight'

VERIFY = '''import hashlib, json
from pathlib import Path
DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WORKING_DIR = Path('/kaggle/working')
RESULTS = WORKING_DIR / 'pilot'
RESULTS.mkdir(parents=True, exist_ok=True)
assert DATA_DIR.exists(), 'competition data not mounted'
print('CPU-only control preflight: no model attached or started')
'''

DIAGNOSTIC = r'''
# Execute the frozen v1 patch writer and applier with real subprocess commands.
# Separate sandbox: its mutations cannot affect the revalidation arms.
import base64, shlex, traceback
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import extract_snapshot, setup_baseline_commit
from swegemma.config import EvalConfig
from adk_submission import ModelRegistry

async def diagnose_original():
    task = SELECTED[0]
    mgr = SubprocessManager(timeout_seconds=120)
    sid = None
    records = []
    out = RESULTS / 'original_patch_diagnostic.json'
    def save():
        out.write_text(json.dumps(records, indent=2, default=str), encoding='utf-8')
    async def command(label, cmd):
        r = await sandbox_exec(mgr, sid, cmd)
        records.append(dict(label=label, command=cmd, rc=r.exit_code,
                            stdout=r.stdout, stderr=r.stderr))
        save()
        return r
    try:
        sid = await sandbox_start(mgr)
        await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, 'diagnostic baseline')
        await command('environment', 'cd /workspace && pwd -P && command -v python3 && git status --short')
        # Exact strings from launched v1, injected by the generator; patch data supplied at runtime.
        diff = task.test_patch
        label = 'testpatch'
        b64 = base64.b64encode(diff.encode('utf-8')).decode('ascii')
        write_cmd = eval(ORIGINAL_WRITE_EXPR, {}, dict(label=label, b64=b64))
        apply_cmd = eval(ORIGINAL_APPLY_EXPR, {}, dict(label=label, b64=b64))
        await command('original_write', write_cmd)
        await command('file_probe', 'ls -l /tmp/testpatch.patch; wc -c /tmp/testpatch.patch; sha256sum /tmp/testpatch.patch')
        await command('original_apply', apply_cmd)
        await command('after_apply', 'cd /workspace && git diff --stat && git status --short')
    except BaseException:
        records.append(dict(exception=traceback.format_exc()))
    finally:
        if sid is not None:
            try:
                await sandbox_stop(mgr, sid)
            except BaseException:
                records.append(dict(teardown_error=traceback.format_exc()))
        save()
    for rec in records:
        print(rec.get('label', 'exception'), rec.get('rc'), str(rec.get('stderr', rec.get('exception', '')))[:500])

run_sync(diagnose_original)
'''


def main():
    source = ROOT / 'notebooks/compare/compare.ipynb'
    frozen = ROOT / 'releases/compare_v1_launched/compare.ipynb'
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == '532d3f7e6be6bd4fcf7035b0d4af741820f40fa553c00025ca3c3156f781f15b'
    launched = json.loads(frozen.read_text(encoding='utf-8'))
    old = next(''.join(c['source']) for c in launched['cells'] if 'async def _revalidate_control' in ''.join(c['source']))
    fn = next(n for n in ast.walk(ast.parse(old)) if isinstance(n, ast.AsyncFunctionDef) and n.name == '_apply')
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'sandbox_exec']
    expressions = [ast.unparse(n.args[2]) for n in calls]
    assert len(expressions) == 2
    diagnostic = 'ORIGINAL_WRITE_EXPR = ' + repr(expressions[0]) + '\nORIGINAL_APPLY_EXPR = ' + repr(expressions[1]) + '\n' + DIAGNOSTIC
    nb = json.loads(source.read_text(encoding='utf-8'))
    # Keep setup, task invariance, repair, controls. Exclude candidate bundles and all model cells.
    cells = []
    for index in (1, 2, 3, 4, 5, 6, 8, 9):
        cell = copy.deepcopy(nb['cells'][index])
        text = ''.join(cell['source'])
        if index == 1:
            text = text.replace('DISPATCH_CONFIRM = True', 'DISPATCH_CONFIRM = False')
        if index == 3:
            text = VERIFY
        if index == 9:
            # Record commands in the actual setup/control path, including helper-internal calls.
            text = INSTRUMENT + '\n' + diagnostic + '\n' + text
        ast.parse(text)
        cell.update(source=text.splitlines(keepends=True), execution_count=None, outputs=[])
        cells.append(cell)
    nb['cells'] = [dict(cell_type='markdown', metadata={}, source=['# CPU patch-path diagnosis and four-task control revalidation\nNo model, no GPU, no agent performance measurement.'])] + cells
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / 'control_preflight.ipynb'
    dest.write_text(json.dumps(nb, indent=1), encoding='utf-8')
    meta = json.loads((source.parent / 'kernel-metadata.json').read_text())
    meta.update(id='navin03/gemma4-control-preflight', title='gemma4-control-preflight',
                code_file=dest.name, enable_gpu=False, enable_tpu=False, model_sources=[])
    meta.pop('machine_shape', None)
    (OUT / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    (OUT / 'source_hashes.json').write_text(json.dumps(dict(
        working_compare=hashlib.sha256(source.read_bytes()).hexdigest(),
        frozen_compare=hashlib.sha256(frozen.read_bytes()).hexdigest(),
        preflight=hashlib.sha256(dest.read_bytes()).hexdigest()), indent=2))
    print(dest, hashlib.sha256(dest.read_bytes()).hexdigest())


INSTRUMENT = r'''
from swegemma.sandbox import SubprocessManager
_original_exec = SubprocessManager.exec
_audit_path = RESULTS / 'sandbox_commands.jsonl'
def _audited_exec(self, sandbox_id, command, *, timeout=None):
    record = dict(sandbox=str(sandbox_id), command=command)
    try:
        result = _original_exec(self, sandbox_id, command, timeout=timeout)
        record.update(rc=result.exit_code, stdout=result.stdout, stderr=result.stderr)
        return result
    except BaseException as exc:
        record['exception'] = repr(exc)
        raise
    finally:
        with _audit_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, default=str) + '\n')
SubprocessManager.exec = _audited_exec
'''

if __name__ == '__main__':
    main()
