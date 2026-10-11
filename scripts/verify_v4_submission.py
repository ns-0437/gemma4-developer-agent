"""Verify V4 submission provenance offline, without executing notebook code."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
from verify_final_validation_packet import strict_json

ROOT = Path(__file__).resolve().parent.parent
PIN = '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(root=ROOT):
    root = Path(root)
    record = strict_json((root / 'releases/v4_submission_record.json').read_text())
    require(record['submission_ref'] == 57064155 and record['kernel_version'] == 4,
            'submission identity mismatch')
    require(record['sha256'] == PIN, 'record digest mismatch')
    archive = (root / 'releases/v4_thinking_on_submission.zip').read_bytes()
    require(hashlib.sha256(archive).hexdigest() == PIN, 'release archive mismatch')
    for name in ('experiments/thinking_v2/ON.zip',
                 'reference/submission_v4_2026-10-11/submission.zip'):
        require((root / name).read_bytes() == archive, 'archive copy mismatch: ' + name)
    source = root / 'releases/v4_thinking_on'
    files = {p.relative_to(source).as_posix(): p.read_bytes()
             for p in source.rglob('*') if p.is_file()}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        require(len(z.namelist()) == len(set(z.namelist())), 'duplicate archive entries')
        require(set(files) == set(z.namelist()), 'release file set mismatch')
        require(all(files[n] == z.read(n) for n in files), 'release source mismatch')
    folder = root / 'notebooks/submit_v4_thinking_on'
    raw = (folder / 'submit.ipynb').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == record['notebook_sha256'], 'notebook hash mismatch')
    payloads = []
    for cell in strict_json(raw)['cells']:
        if cell['cell_type'] != 'code':
            continue
        for node in ast.parse(''.join(cell['source'])).body:
            if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'payload' for t in node.targets):
                call = node.value
                require(isinstance(call, ast.Call) and ast.unparse(call.func) == 'base64.b64decode',
                        'unexpected payload expression')
                payloads.append(base64.b64decode(ast.literal_eval(call.args[0]), validate=True))
    require(payloads == [archive], 'embedded payload mismatch')
    meta = strict_json((folder / 'kernel-metadata.json').read_text())
    require(meta['id'] == record['kernel'] == 'navin03/gemma4-swe-agent-submit', 'kernel mismatch')
    require(meta['enable_gpu'] is False and meta['enable_tpu'] is False
            and meta['enable_internet'] is False and meta['is_private'] is True,
            'packaging execution settings mismatch')
    require(meta['code_file'] == 'submit.ipynb' and meta['language'] == 'python'
            and meta['kernel_type'] == 'notebook', 'packaging entry point mismatch')
    require(meta['competition_sources'] == ['gemma-4-developer-agent']
            and all(meta[key] == [] for key in ('dataset_sources', 'kernel_sources', 'model_sources')),
            'packaging input sources mismatch')
    return {'verified': True, 'submission_ref': record['submission_ref'], 'sha256': PIN,
            'files': len(files), 'live_status_checked': False}


if __name__ == '__main__':
    print(json.dumps(verify(), sort_keys=True))
