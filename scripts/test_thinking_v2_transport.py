"""Official compilation/client capture of frozen OFF/ON. No HTTP/model calls."""
import hashlib
import json
from pathlib import Path
import sys
import check_thinking_transport as C

ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/thinking_v2'

def main():
    C._bootstrap('0.2.12'); location=C._check_compiler('0.2.12')
    import official_check as O
    from google.adk.models.lite_llm import LiteLlm
    record=json.loads((EXP/'CANDIDATES.json').read_text())
    reports={}
    for name in ['OFF','ON']:
        folder=EXP/f'candidate_{name}'
        found={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
        assert found==record['candidates'][name]['files']
        O.validate_directory(folder,O.LIMITS)
        models=O.ModelRegistry()
        models.register('gemma-4-31b-it-qat-w4a16-ct',LiteLlm(model='openai/gemma-4-31b-it-qat-w4a16-ct',api_base='http://127.0.0.1:9/v1',api_key='EMPTY'))
        a=O.compile_submission(submission_dir=folder,tool_registry=O.TOOLS,model_registry=models,limits=O.LIMITS,generation_constraints=O.GEN)
        agents=[a]+[t.agent for t in a.tools if getattr(t,'agent',None) is not None]
        assert len(agents)==2
        reports[name]={x.name:C._capture(x) for x in agents}
    for key in reports['OFF']:
        a,b=reports['OFF'][key],reports['ON'][key]
        assert a['instruction_sha256']==b['instruction_sha256']
        off,on=a['client_parameters'],b['client_parameters']
        assert off['seed']==on['seed']==42
        assert off['max_completion_tokens']==on['max_completion_tokens']==4096
        assert off['extra_body']=={'chat_template_kwargs':{'enable_thinking':False}}
        assert on['extra_body']=={'chat_template_kwargs':{'enable_thinking':True},'thinking_token_budget':1024}
        assert {k:v for k,v in off.items() if k!='extra_body'}=={k:v for k,v in on.items() if k!='extra_body'}
    base=C.FROZEN_S
    for name in ['OFF','ON']:
        folder=EXP/f'candidate_{name}'
        assert {p.relative_to(base) for p in base.rglob('*') if p.is_file()}=={p.relative_to(folder) for p in folder.rglob('*') if p.is_file()}
        for p in base.rglob('*'):
            if p.is_file() and p.relative_to(base).as_posix()!='configs/sampling.yaml':assert p.read_bytes()==(folder/p.relative_to(base)).read_bytes()
    (EXP/'MATCHED_TRANSPORT.json').write_text(json.dumps({'compiler_source':location,'variants':reports,'provider_HTTP':False,'server_enforcement':'unverified','prompt_ceiling_if_32768_context':32768-4096},indent=2))
    print('PASS: official 0.2.12, exact file isolation, coder/analyzer client parameters, seed, output cap and thinking fields. Server enforcement unverified.')

if __name__=='__main__': main()
