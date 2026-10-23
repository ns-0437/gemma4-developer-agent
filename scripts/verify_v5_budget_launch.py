"""Verify the launched V5 GPU baseline offline, including its exact arming diff."""
import ast
import hashlib
import json
from pathlib import Path
from verify_final_validation_packet import strict_json, require

ROOT = Path(__file__).resolve().parent.parent
DISABLED = '70f9d5d98baa44ae77396013cc036bbec6a6a3599f43a9cd55a54dee1bc10989'
ARMED = '066b5fb71f8d432826fe251b69a88a54dbf7725ce756427f2e8bdb1eb4f1fdc9'
METADATA = '454a39b7a8716140a38ff54181b435e8d9521dd78ca6e83c22f3797a79dad9d1'
CANDIDATE = '527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33'
ORDER = [[t,'V5'] for t in ('rich_3278','rich_3535','rich_3675','rich_3942')]
BUDGET = dict(max_time_minutes=5.0,max_turns=60,max_tool_calls=100,timeout_seconds=60)


def verify_artifacts(raw, disabled, metadata, prepared, launch):
    digest=lambda b:hashlib.sha256(b).hexdigest()
    require(digest(disabled)==DISABLED==prepared['notebook_sha256']==launch['disabled_notebook_sha256'],
            'disabled baseline mismatch')
    require(disabled.count(b'DISPATCH_CONFIRM = False')==1, 'ambiguous dispatch flag')
    expected=disabled.replace(b'DISPATCH_CONFIRM = False',b'DISPATCH_CONFIRM = True',1)
    require(raw==expected and digest(raw)==ARMED==launch['armed_notebook_sha256'], 'armed notebook mismatch')
    require(digest(metadata)==METADATA==prepared['metadata_sha256']==launch['metadata_sha256'], 'metadata mismatch')
    require(launch['kernel']=='navin03/gemma4-v5-budget-v2' and type(launch['kernel_version']) is int
            and launch['kernel_version']==1, 'launch identity mismatch')
    require(type(launch['push_attempts']) is int and launch['push_attempts']==1,'push receipt mismatch')
    require(launch['order']==ORDER and launch['budgets']==BUDGET, 'launch plan mismatch')
    require(launch['candidate']=={'key':'V5','sha256':CANDIDATE},'launch candidate mismatch')
    meta=strict_json(metadata)
    require(meta['id']==launch['kernel'] and meta['code_file']=='v5_budget_v2.ipynb','kernel metadata identity')
    require(meta['enable_gpu'] is True and meta['enable_tpu'] is False and meta['enable_internet'] is False
            and meta['is_private'] is True,'execution settings mismatch')
    for index,cell in enumerate(strict_json(raw)['cells']):
        if cell['cell_type']=='code': compile(''.join(cell['source']),f'<cell {index}>','exec')
    return {'verified':True,'armed':True,'kernel':launch['kernel'],'version':1,'armed_sha256':ARMED}


def verify(root=ROOT):
    root=Path(root); exp=root/'experiments/v5_budget_v2/gpu_baseline'; nb=root/'notebooks/v5_budget_v2'
    return verify_artifacts((nb/'v5_budget_v2.ipynb').read_bytes(),
                            (exp/'v5_budget_v2_disabled.ipynb').read_bytes(),
                            (nb/'kernel-metadata.json').read_bytes(),
                            strict_json((exp/'NOTEBOOK_PREPARED.json').read_bytes()),
                            strict_json((exp/'LAUNCH_RECORD.json').read_bytes()))


if __name__=='__main__':
    try: print(json.dumps(verify(),indent=2))
    except (OSError,ValueError,KeyError,SyntaxError) as exc: raise SystemExit('CHECK FAILED: '+str(exc))
