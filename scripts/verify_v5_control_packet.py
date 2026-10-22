"""Read-only checks for the repaired CPU replay, without running notebook cells."""
import ast
import base64
import hashlib
import json
from pathlib import Path
from verify_final_validation_packet import strict_json, require

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = 'bedb8c0ab57eb5c5707aad8c1ff247987c8a30ecb2350995d675b56bb11cd9a9'
METADATA = '0c196e079b42502bc0e39567f44f3a9f8254908218ab84bc4fe6528521bac958'
CANDIDATE = '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'
FREEZE = '220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b'
TASKS = ['rich_3278','rich_3535','rich_3675','rich_3942']


def inspect_notebook(nb):
    assignments = {}; calls = {}; sources = []
    for index, cell in enumerate(nb['cells']):
        if cell['cell_type'] != 'code': continue
        source = ''.join(cell['source']); sources.append(source)
        tree = ast.parse(source); compile(tree, '<cell>', 'exec')
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = getattr(target, 'id', '')
                    if name in {'DISPATCH_CONFIRM','TASK_IDS','BUNDLES','BUDGET','CONTROL_RECHECK'}:
                        require(name not in assignments, 'duplicate assignment: ' + name)
                        assignments[name] = (index, node.value)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                name = ast.unparse(node.value.func)
                calls.setdefault(name, []).append((index,node.lineno))
    require(ast.literal_eval(assignments['DISPATCH_CONFIRM'][1]) is False, 'dispatch must be disabled')
    require(ast.literal_eval(assignments['TASK_IDS'][1]) == TASKS, 'development task list mismatch')
    budget = assignments['BUDGET'][1]
    require(isinstance(budget,ast.Call) and ast.unparse(budget.func)=='dict' and not budget.args,
            'unexpected budget expression')
    limits = {k.arg:ast.literal_eval(k.value) for k in budget.keywords}
    require(limits == dict(max_time_minutes=5.0,max_turns=60,max_tool_calls=100,timeout_seconds=60),
            'budget mismatch')
    bundles = ast.literal_eval(assignments['BUNDLES'][1])
    require(set(bundles)=={'V5'}, 'unexpected candidate set')
    payload = base64.b64decode(bundles['V5']['b64'],validate=True)
    require(hashlib.sha256(payload).hexdigest()==bundles['V5']['sha256']==CANDIDATE, 'candidate mismatch')
    for gate in ('verify_runtime_compiler','verify_runtime_swegemma'):
        require(len(calls.get(gate,[]))==1, 'missing or duplicate gate: ' + gate)
        require(calls[gate][0][0] < assignments['CONTROL_RECHECK'][0], 'gate must precede controls')
    source = '\n'.join(sources)
    for forbidden in ('validate_single_declared_model','Evaluator(', 'start_server', 'vllm serve', 'submit_patch('):
        require(forbidden not in source, 'unexpected executable construct: ' + forbidden)
    return {'candidate_sha256':CANDIDATE,'tasks':TASKS,'dispatch':False,'budget':limits}


def verify(root=ROOT):
    root=Path(root); folder=root/'notebooks/v5_control_replay'
    raw=(folder/'v5_control_replay.ipynb').read_bytes()
    meta_raw=(folder/'kernel-metadata.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==NOTEBOOK,'CPU notebook drift')
    require(hashlib.sha256(meta_raw).hexdigest()==METADATA,'CPU metadata drift')
    prepared=strict_json((root/'experiments/v5_budget_v2/NOTEBOOK_PREPARED.json').read_bytes())
    require(prepared['notebook_sha256']==NOTEBOOK and prepared['metadata_sha256']==METADATA,'prepared record drift')
    require(prepared['tasks']==TASKS and prepared['model_startup'] is False and prepared['candidate_evaluation'] is False,
            'prepared execution claims mismatch')
    require(prepared['dependency_set']=={'swegemma':'0.2.11','adk-submission':'0.2.13'},'dependency claim mismatch')
    freeze=(root/'experiments/ab_v3_vs_short/task_freeze.json').read_bytes()
    require(hashlib.sha256(freeze).hexdigest()==prepared['freeze_sha256']==FREEZE,'freeze drift')
    meta=strict_json(meta_raw)
    require(all(meta[k] is False for k in ('enable_gpu','enable_tpu','enable_internet')),'CPU execution settings')
    require(meta['is_private'] is True and 'machine_shape' not in meta,'CPU privacy or machine shape')
    return inspect_notebook(strict_json(raw))


if __name__=='__main__':
    try: print(json.dumps(verify(),indent=2))
    except (ValueError,KeyError,OSError,SyntaxError) as exc: raise SystemExit('CHECK FAILED: '+str(exc))
