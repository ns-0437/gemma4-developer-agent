"""Prepare an unmeasured verification-only derivative of S_shellread."""
import base64
import hashlib
import json
from pathlib import Path
import make_pilot_notebook as P
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT/'experiments/shellread_v1/candidate_S_shellread'
OUT = ROOT/'experiments/verification_v1'
OLD = '3. **Reproduce once.** Write one assertion-based script and run it. One reproduction is enough: once it fails the way the issue describes, stop reproducing and start fixing.'
NEW = '''3. **Reproduce and define success.** Separate requirements explicitly stated in the issue or repository documentation from your assumptions. Write a small assertion-based check for the requested behavior and one relevant existing behavior to preserve. Keep assertions enabled and let failures exit nonzero: never catch AssertionError merely to print a message, and never count printed success as a test result. Run the same checks before and after the edit; preserve their expected results instead of changing them to fit your patch. If the requested behavior already passes, investigate that discrepancy rather than claiming a repair. For ambiguous behavior, inspect local documentation and neighboring tests; label unsupported assumptions rather than inventing requirements.'''
def main():
    assert P.bundle(SOURCE)[1]=='8e3f9286ce0f2399c32dfa452e129a12fd48cdd657b88ea6c76d3c48c36956ae'
    dest=OUT/'candidate_V'
    for p in SOURCE.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(SOURCE);data=p.read_bytes()
        if rel.as_posix()=='prompts/system.md':
            text=data.decode();assert text.count(OLD)==1;data=text.replace(OLD,NEW,1).encode()
        q=dest/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
    encoded,sha=P.bundle(dest)
    (OUT/'V.zip').write_bytes(base64.b64decode(encoded))
    (OUT/'PREPARED.json').write_text(json.dumps({'sha256':sha,'baseline':'S_shellread','changed_files':['prompts/system.md'],'measured':False,'dispatch':False},indent=2))
    print(sha)
if __name__=='__main__':main()
