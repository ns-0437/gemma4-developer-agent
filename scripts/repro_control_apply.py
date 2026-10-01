"""Reproduce the control-stage patch failure on CPU with REAL subprocess and git execution.

Version 1 of the comparison kernel aborted at the control re-validation assertion: all eight
test-patch applications and all four reference-patch applications returned 128, every pytest run
returned 0 (so no baseline could fail), and no agent ran. The custom `_apply` helper preserved only
the exit code, so 128 alone cannot establish the mechanism.

This script runs the REAL `swegemma.sandbox.SubprocessManager` against a REAL git repository and a
REAL patch, with no fakes and no stubbed results. For every command it records the command string,
exit code, stdout, stderr and the working directory, and it checks whether the patch file exists,
with its size and SHA-256, BEFORE any application is attempted.

Two paths are compared:

  BROKEN   what the launched notebook did: write the patch with a shell `python3 -c` one-liner
           using a literal absolute /tmp path, then `cd /workspace && git apply <that path>`;
  HARNESS  what the successful screening run did: write to a host temp file, `mgr.copy_to` it into
           the sandbox, then call `swegemma.harness.verification.apply_patch_in_container`.

Usage:
    .venv\\Scripts\\python.exe scripts/repro_control_apply.py [--out DIR]

Writes a JSON evidence file. Runs nothing on Kaggle and touches no candidate or notebook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in ("reference/harness_src/src_swegemma",
           "reference/harness_src/src_adk_eval_core",
           "reference/harness_src/src_adk_submission"):
    sys.path.insert(0, str(ROOT / _p))

# WINDOWS-ONLY ACCOMMODATION. SubprocessManager.exec rewrites /tmp and /workspace with re.sub,
# passing the real directory as the REPLACEMENT TEMPLATE. On Linux (Kaggle) a path contains no
# backslashes and this is harmless. On Windows a path like C:\Users\... makes re parse \U as a bad
# escape, and the call raises before any command runs. Escaping backslashes in the replacement
# changes nothing about which commands are produced; it only lets this reproduction run here.
import re as _re  # noqa: E402

_orig_sub = _re.sub
BACKSLASH = chr(92)


def _safe_sub(pattern, repl, string, *a, **k):
    if isinstance(repl, str):
        repl = repl.replace(BACKSLASH, BACKSLASH * 2)
    return _orig_sub(pattern, repl, string, *a, **k)


_re.sub = _safe_sub

from swegemma.sandbox import SubprocessManager  # noqa: E402
from swegemma.harness.verification import apply_patch_in_container  # noqa: E402

EVIDENCE = []


def record(stage, command, res=None, **extra):
    row = {"stage": stage, "command": command}
    if res is not None:
        row.update({
            "exit_code": getattr(res, "exit_code", None),
            "status": getattr(res, "status", None),
            "stdout": (getattr(res, "stdout", "") or "")[-2000:],
            "stderr": (getattr(res, "stderr", "") or "")[-2000:],
        })
    row.update(extra)
    EVIDENCE.append(row)
    ec = row.get("exit_code")
    print(f"  [{stage}] rc={ec} :: {command[:110]}")
    for k in ("stderr", "note"):
        v = row.get(k)
        if v:
            print(f"        {k}: {str(v).strip()[:300]}")
    return row


def file_probe(mgr, sid, path, label):
    """Existence, size and sha256 of a path AS THE SANDBOX SHELL SEES IT."""
    probe = (
        "python3 -c \"import hashlib,os,sys;"
        "p=sys.argv[1];"
        "print('exists=%s' % os.path.exists(p));"
        "print('size=%d' % (os.path.getsize(p) if os.path.exists(p) else -1));"
        "print('sha256=%s' % (hashlib.sha256(open(p,'rb').read()).hexdigest() if os.path.exists(p) else ''))"
        "\" " + path)
    res = mgr.exec(sid, probe)
    return record(f"probe:{label}", probe, res, probed_path=path)


def make_repo(tmp: Path):
    """A real git repository with one tracked source file and one tracked test file."""
    ws = tmp / "repo"
    (ws / "pkg").mkdir(parents=True)
    (ws / "tests").mkdir()
    (ws / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "pkg" / "mod.py").write_text("def strip(s):\n    return s\n", encoding="utf-8")
    (ws / "tests" / "test_mod.py").write_text(
        "from pkg.mod import strip\n\n\ndef test_ok():\n    assert strip('x') == 'x'\n",
        encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"]):
        subprocess.run(cmd, cwd=ws, env=env, check=True, capture_output=True)
    return ws


TEST_PATCH = """diff --git a/tests/test_mod.py b/tests/test_mod.py
--- a/tests/test_mod.py
+++ b/tests/test_mod.py
@@ -1,5 +1,9 @@
 from pkg.mod import strip


 def test_ok():
     assert strip('x') == 'x'
+
+
+def test_new_behaviour():
+    assert strip('  x  ') == 'x'
"""


def run_broken_path(mgr, sid, patch_text):
    """Exactly what the launched notebook's _apply did, with everything recorded."""
    print("\n--- BROKEN PATH (as launched) ---")
    import base64
    b64 = base64.b64encode(patch_text.encode("utf-8")).decode("ascii")
    write_cmd = ("python3 -c \"import base64,sys,pathlib;"
                 "pathlib.Path('/tmp/testpatch.patch').write_bytes(base64.b64decode(sys.argv[1]))\" "
                 + b64)
    # The launched notebook DISCARDED this result. Here it is recorded.
    res = mgr.exec(sid, write_cmd)
    record("broken:write", write_cmd[:160] + " <b64 truncated>", res,
           note="the launched notebook never checked this exit code")
    file_probe(mgr, sid, "/tmp/testpatch.patch", "broken-after-write")
    apply_cmd = ("cd /workspace && git apply --verbose /tmp/testpatch.patch"
                 " || git apply -3 /tmp/testpatch.patch")
    res2 = mgr.exec(sid, apply_cmd)
    return record("broken:apply", apply_cmd, res2)


def run_harness_path(mgr, sid, patch_text, tmp: Path):
    """What the successful screening run did: copy_to + apply_patch_in_container."""
    print("\n--- HARNESS PATH (as the screening run) ---")
    host = tmp / "ref_test.patch"
    host.write_text(patch_text if patch_text.endswith("\n") else patch_text + "\n",
                    encoding="utf-8")
    record("harness:host-file", str(host), None,
           size=host.stat().st_size,
           sha256=hashlib.sha256(host.read_bytes()).hexdigest())
    try:
        mgr.copy_to(sid, host, "/tmp/")
        in_sandbox = "/tmp/" + host.name
        record("harness:copy_to", f"copy_to({host.name} -> /tmp/)", None, note="ok",
               sandbox_path=in_sandbox)
    except Exception as exc:
        record("harness:copy_to", "copy_to", None, note=f"FAILED {type(exc).__name__}: {exc}")
        return None
    file_probe(mgr, sid, in_sandbox, "harness-after-copy")
    code, out, err = apply_patch_in_container(mgr, sid, in_sandbox)
    row = {"stage": "harness:apply", "command": f"apply_patch_in_container(..., {in_sandbox})",
           "exit_code": code, "stdout": (out or "")[-2000:], "stderr": (err or "")[-2000:]}
    EVIDENCE.append(row)
    print(f"  [harness:apply] rc={code} :: apply_patch_in_container")
    if err:
        print(f"        stderr: {err.strip()[:300]}")
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "reference" / "control_apply_repro")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="repro_apply_"))
    try:
        ws = make_repo(tmp)
        print(f"real git repo: {ws}")
        mgr = SubprocessManager(timeout_seconds=120)
        sid = mgr.start() if hasattr(mgr, "start") else None
        if sid is None:
            from swegemma.sandbox import sandbox_start
            import asyncio
            sid = asyncio.run(sandbox_start(mgr))
        print(f"sandbox id: {sid}")

        record("env:where-am-i", "pwd -P && echo --- && ls -a", mgr.exec(sid, "pwd -P && echo --- && ls -a"))
        record("env:workspace", "cd /workspace && pwd -P", mgr.exec(sid, "cd /workspace && pwd -P"),
               note="does the literal absolute path /workspace exist for a raw shell command?")
        record("env:tmp", "ls -d /tmp && echo TMPDIR=$TMPDIR && echo HOME=$HOME",
               mgr.exec(sid, "ls -d /tmp && echo TMPDIR=$TMPDIR && echo HOME=$HOME"))
        record("env:python3", "command -v python3 || echo NO_PYTHON3",
               mgr.exec(sid, "command -v python3 || echo NO_PYTHON3"))
        record("env:git", "command -v git && git --version", mgr.exec(sid, "command -v git && git --version"))

        # put the repo where the sandbox can see it, mirroring the real workspace layout
        try:
            mgr.copy_to(sid, ws, "/")
            record("setup:copy-repo", "copy_to(repo -> /)", None, note="ok")
        except Exception as exc:
            record("setup:copy-repo", "copy_to(repo -> /)", None,
                   note=f"FAILED {type(exc).__name__}: {exc}")
        record("setup:git-status", "cd /workspace && git status --short || echo NOT_A_REPO",
               mgr.exec(sid, "cd /workspace && git status --short || echo NOT_A_REPO"))

        broken = run_broken_path(mgr, sid, TEST_PATCH)
        harness = run_harness_path(mgr, sid, TEST_PATCH, tmp)

        print("\n=== VERDICT ===")
        if broken and broken.get("exit_code") not in (0,):
            print(f"  BROKEN path exit code: {broken.get('exit_code')}")
        if harness:
            print(f"  HARNESS path exit code: {harness.get('exit_code')}")
        out = a.out / "repro_evidence.json"
        out.write_text(json.dumps({"evidence": EVIDENCE, "sandbox_id": str(sid),
                                   "repo": str(ws)}, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {out}")
        try:
            from swegemma.sandbox import sandbox_stop
            import asyncio
            asyncio.run(sandbox_stop(mgr, sid))
        except Exception:
            pass
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
