"""Verify V5 submission provenance offline, without executing notebook code."""
import ast
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
from verify_final_validation_packet import strict_json

ROOT = Path(__file__).resolve().parent.parent
PIN = 'ca7ebe43b7f1c33715d9657a133e38514e89aa49d7faa7808d0a6711cfad4d21'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(root=ROOT):
    root = Path(root)
    record = strict_json((root / 'releases/v5_submission_record.json').read_text())
    require(record['submission_ref'] == 57378663 and record['kernel_version'] == 5,
            'submission identity mismatch')
    require(record['sha256'] == PIN, 'record digest mismatch')
    archive = (root / 'releases/v5_bounded_on_submission.zip').read_bytes()
    require(hashlib.sha256(archive).hexdigest() == PIN, 'release archive mismatch')
    for name in ('reference/submission_v5_2026-10-19/submission.zip',):
        require((root / name).read_bytes() == archive, 'archive copy mismatch: ' + name)
    source = root / 'releases/v5_bounded_on'
    files = {p.relative_to(source).as_posix(): p.read_bytes()
             for p in source.rglob('*') if p.is_file()}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        require(len(z.namelist()) == len(set(z.namelist())), 'duplicate archive entries')
        require(set(files) == set(z.namelist()), 'release file set mismatch')
        require(all(files[n] == z.read(n) for n in files), 'release source mismatch')
    base = (root / 'releases/v4_thinking_on_submission.zip').read_bytes()
    require(hashlib.sha256(base).hexdigest() == record['base_sha256'] ==
            '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33', 'base archive mismatch')
    with zipfile.ZipFile(io.BytesIO(base)) as old:
        require(set(files) == set(old.namelist()) | {'eval_config.yaml'}, 'unexpected V5 additions')
        require(all(files[n] == old.read(n) for n in old.namelist()), 'V4 agent changed')
    require(record['evaluation'] == {'timeout_seconds': 60, 'max_tool_calls': 100,
                                    'max_time_minutes': 5, 'max_turns': 60}, 'budget receipt mismatch')
    folder = root / 'notebooks/submit_v5'
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'SUBMISSION VERIFICATION FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
