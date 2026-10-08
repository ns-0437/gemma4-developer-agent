"""Read-only identity checks for the final-validation V3/ON packet.

Parses and compiles notebook cells without executing them. No model, network,
notebook regeneration or filesystem writes are involved.
"""
import ast
import base64
import hashlib
import json

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
