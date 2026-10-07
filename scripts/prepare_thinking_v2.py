"""Prepare frozen S derivatives. No inference, arming, or external action."""
import base64
import hashlib
import json
from pathlib import Path
import make_pilot_notebook as P

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/thinking_v2'
SOURCE = ROOT/'experiments/concise_workflow_v1/candidate_S'
SOURCE_SHA = '8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07'


def main():
    assert P.bundle(SOURCE)[1] == SOURCE_SHA
    records = {}
    for name in ('OFF','ON'):
        folder = EXP/f'candidate_{name}'
        for p in SOURCE.rglob('*'):
            if not p.is_file(): continue
            rel = p.relative_to(SOURCE); data = p.read_bytes()
            if rel.as_posix() == 'configs/sampling.yaml':
                assert data.count(b'max_output_tokens: 8192') == 1
                data = data.replace(b'max_output_tokens: 8192',b'max_output_tokens: 4096')
                if name == 'ON':
                    data = data.replace(b'thinking_budget: 4096',b'thinking_budget: 1024')
                    data = data.replace(b'include_thoughts: false',b'include_thoughts: true')
            dst = folder/rel
            if dst.exists(): assert dst.read_bytes() == data, f'Refuse candidate overwrite: {dst}'
            dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
        encoded,sha=P.bundle(folder)
        zipped=EXP/f'{name}.zip'; data=base64.b64decode(encoded)
        if zipped.exists(): assert zipped.read_bytes()==data
        zipped.write_bytes(data)
        records[name]={'sha256':sha,'files':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()}}
    (EXP/'CANDIDATES.json').write_text(json.dumps({'source_S_sha256':SOURCE_SHA,'candidates':records,'dispatch':False,'measured':False},indent=2))
    print({k:v['sha256'] for k,v in records.items()})

if __name__=='__main__': main()
