"""Offline compiler/transport and real subprocess assertion-exit checks."""
import asyncio,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
sys.path.insert(0,str(ROOT/'experiments/shellread_v1/compiler_0_2_12/src'))
from test_shellread_candidate import compile_one
from check_temperature_transport import inspect_agent
from prepare_verification_candidate import OLD,NEW
def main():
    base=ROOT/'experiments/shellread_v1/candidate_S_shellread'; new=ROOT/'experiments/verification_v1/candidate_V'
    files={p.relative_to(base) for p in base.rglob('*') if p.is_file()}
    assert files=={p.relative_to(new) for p in new.rglob('*') if p.is_file()}
    for rel in files:
        a,b=(base/rel).read_bytes(),(new/rel).read_bytes()
        assert b==(a.decode().replace(OLD,NEW,1).encode() if rel.as_posix()=='prompts/system.md' else a)
    a,b=compile_one(base),compile_one(new)
    assert a.generate_content_config==b.generate_content_config
    ta,tb=asyncio.run(inspect_agent(a)),asyncio.run(inspect_agent(b))
    assert ta['client_parameters']==tb['client_parameters']
    for snippet,expected in [('assert 1 == 2',1),('assert 2 == 2',0),('try:\n assert 1 == 2\nexcept AssertionError:\n print("Test failed!")',0)]:
        result=subprocess.run([sys.executable,'-c',snippet],capture_output=True)
        assert result.returncode==expected
    report={'official_compile':'passed','transport_equal':True,'assertion_exit_checks':'passed','performance':'unmeasured','model_invoked':False}
    (ROOT/'experiments/verification_v1/CHECKS.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
if __name__=='__main__':main()
