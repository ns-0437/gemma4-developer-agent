"""Read-only identity checks for the final-validation V3/ON packet.

Parses and compiles notebook cells without executing them. No model, network,
notebook regeneration or filesystem writes are involved.
"""
import ast
import argparse
import base64
import hashlib
import json
from pathlib import Path

ORDER = [('fastapi_15280', 'V3'), ('fastapi_15280', 'ON'),
         ('requests_7427', 'ON'), ('requests_7427', 'V3'),
         ('rich_3894', 'V3'), ('rich_3894', 'ON')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_packet(raw, prepared, *, armed=False, baseline=None):
    disabled = baseline if armed else raw
    require(disabled is not None, '--armed requires a preserved disabled baseline')
    require(hashlib.sha256(disabled).hexdigest() == prepared['notebook_sha256'],
            'disabled notebook hash mismatch')
    require(disabled.count(b'DISPATCH_CONFIRM = False') == 1,
            'expected exactly one disabled dispatch flag')
    require(b'DISPATCH_CONFIRM = True' not in disabled, 'baseline contains an armed flag')
    expected = disabled.replace(b'DISPATCH_CONFIRM = False',
                                b'DISPATCH_CONFIRM = True', 1) if armed else disabled
    require(raw == expected, 'unexpected change beyond the dispatch flag')
    require(set(prepared['candidates']) == {'V3', 'ON'}, 'expected V3 and ON candidate pins')
    assignments = {}
    for index, cell in enumerate(json.loads(raw)['cells']):
        if cell['cell_type'] != 'code':
            continue
        source = cell['source']
        tree = ast.parse(''.join(source) if isinstance(source, list) else source)
        compile(tree, f'<packet cell {index}>', 'exec')
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or target.id not in {
                        'ORDER', 'TASK_IDS', 'BUNDLES', 'DISPATCH_CONFIRM'}:
                    continue
                require(target.id not in assignments, 'duplicate assignment: ' + target.id)
                if target.id == 'BUNDLES':
                    require(isinstance(node.value, ast.Dict), 'BUNDLES must be a literal dict')
                    labels = [ast.literal_eval(key) for key in node.value.keys]
                    require(len(labels) == len(set(labels)), 'duplicate candidate label')
                assignments[target.id] = ast.literal_eval(node.value)
    require(set(assignments) == {'ORDER', 'TASK_IDS', 'BUNDLES', 'DISPATCH_CONFIRM'},
            'packet is missing identity assignments')
    require(assignments['DISPATCH_CONFIRM'] is armed, 'dispatch value does not match requested state')
    bundles = assignments['BUNDLES']
    require(set(bundles) == set(prepared['candidates']), 'embedded candidate labels differ from pins')
    for label, pin in prepared['candidates'].items():
        bundle = bundles[label]
        require(isinstance(bundle, dict) and set(bundle) == {'b64', 'sha256'},
                'invalid bundle fields for ' + label)
        require(bundle['sha256'] == pin, 'declared package hash mismatch for ' + label)
        try:
            payload = base64.b64decode(bundle['b64'], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError('invalid base64 payload for ' + label) from exc
        require(hashlib.sha256(payload).hexdigest() == pin,
                'decoded package hash mismatch for ' + label)
    require(assignments['ORDER'] == ORDER, 'embedded run order changed')
    require(assignments['TASK_IDS'] == prepared['tasks'], 'embedded task list changed')
    require([list(pair) for pair in ORDER] == prepared['order'], 'prepared run order changed')
    return {'verified': True, 'armed': armed, 'candidates': sorted(bundles), 'runs': len(ORDER)}


def verify_directory(root, *, armed=False, baseline=None):
    """Cross-check the notebook, metadata, manifest, source packages and freeze."""
    root = Path(root).resolve(strict=True)
    experiment = root / 'experiments/final_validation_v2'
    notebook = root / 'notebooks/final_validation_v2/final_validation_v2.ipynb'
    prepared = json.loads((experiment / 'NOTEBOOK_PREPARED.json').read_text(encoding='utf-8'))
    result = verify_packet(notebook.read_bytes(), prepared, armed=armed,
                           baseline=Path(baseline).read_bytes() if baseline else None)
    metadata_raw = notebook.with_name('kernel-metadata.json').read_bytes()
    require(hashlib.sha256(metadata_raw).hexdigest() == prepared['metadata_sha256'],
            'metadata hash mismatch')
    metadata = json.loads(metadata_raw)
    require(metadata['id'] == 'navin03/gemma4-final-validation-v2', 'unexpected kernel identity')
    require(metadata['enable_gpu'] is True and metadata['enable_tpu'] is False,
            'unexpected accelerator flags')
    require(metadata['is_private'] is True and metadata['enable_internet'] is False,
            'unexpected privacy or internet settings')
    require(metadata['machine_shape'] == 'NvidiaL4', 'unexpected machine shape')
    require(metadata['docker_image'] == prepared['docker_image'], 'image pin mismatch')
    manifest = json.loads((experiment / 'VALIDATION_MANIFEST.json').read_text(encoding='utf-8'))
    require(manifest['purpose'] == 'final_validation', 'unexpected manifest purpose')
    require(manifest['tasks'] == prepared['tasks'], 'manifest task selection mismatch')
    require(manifest['order'] == prepared['order'], 'manifest run order mismatch')
    require(manifest['freeze_sha256'] == prepared['freeze_sha256'], 'manifest freeze mismatch')
    require(set(manifest['packages']) == set(prepared['candidates']), 'manifest package labels mismatch')
    freeze = root / 'experiments/ab_v3_vs_short/task_freeze.json'
    require(hashlib.sha256(freeze.read_bytes()).hexdigest() == prepared['freeze_sha256'],
            'holdout freeze hash mismatch')
    for label, package in manifest['packages'].items():
        require(package['sha256'] == prepared['candidates'][label],
                'manifest package hash mismatch for ' + label)
        source = (root / package['source']).resolve()
        require(source.is_relative_to(root), 'package source escapes repository: ' + label)
        require(hashlib.sha256(source.read_bytes()).hexdigest() == package['sha256'],
                'source package hash mismatch for ' + label)
    result.update(kernel=metadata['id'], source_packages_verified=len(manifest['packages']),
                  freeze_sha256=prepared['freeze_sha256'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--armed', action='store_true')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.armed != bool(args.baseline):
        parser.error('--armed and --baseline must be supplied together')
    try:
        result = verify_directory(args.root, armed=args.armed, baseline=args.baseline)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
        parser.exit(1, f'PACKET VERIFICATION FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
