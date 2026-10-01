"""Generate notebooks/replay/ — a CPU-ONLY replay of requests_7309 with four patch arms.

No model, no GPU, no agent. It answers two questions left open by pilot v1:

  1. Did candidate A actually have a correct source fix, or only a plausible-looking one?
     -> arm `A_source_only` applies A's diff with the tests/ blocks stripped.
  2. Why did the grader's verification patch fail to apply after A's run?
     -> every reset/apply command is logged with its return code, and the target test file is
        hashed before and after the reset. Reset errors are NOT suppressed (the harness runs them
        with `2>/dev/null || true`, which hides exactly this).

Arms, each in its own fresh sandbox:
  baseline          no patch                      -> target tests must FAIL
  reference         the task's own reference fix  -> target tests must PASS
  A_original        A's saved diff, unmodified    -> reproduce the pilot failure
  A_source_only     A's diff minus tests/ blocks  -> the real question

Usage:
  python scripts/make_replay_notebook.py
  python -m kaggle kernels push -p notebooks/replay
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "replay"
KERNEL_ID = "navin03/gemma4-swe-agent-replay"
TASK = "requests_7309"
A_PATCH = ROOT / "reference/pilot_v1_results/pilot/A__requests_7309/patches/requests_7309.patch"


def split_blocks(raw: str):
    blocks, cur = [], []
    for line in raw.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if cur:
                blocks.append("".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("".join(cur))
    return blocks


def target_of(block: str) -> str:
    for l in block.splitlines():
        if l.startswith("+++ b/"):
            return l[6:].strip()
    return ""


MD = """# CPU replay of `requests_7309` — four patch arms, no model

Pilot v1 left two questions open. This answers both without another GPU run.

1. **Did candidate A have a correct fix?** Its run was never graded, because it also edited the test
   file. Arm `A_source_only` applies the same diff with the `tests/` blocks stripped.
2. **Why did the grader's verification patch fail to apply?** Every reset and apply command is logged
   with its return code, and the target test file is hashed before and after the reset. The harness
   runs those resets with `2>/dev/null || true`, which would hide the answer.

| arm | patch applied | expectation |
| --- | --- | --- |
| `baseline` | none | target tests **fail** |
| `reference` | the task's own reference fix | target tests **pass** |
| `A_original` | A's saved diff, unmodified | reproduces the pilot failure |
| `A_source_only` | A's diff minus `tests/` blocks | **the real question** |

`baseline` and `reference` are controls: if they do not behave as expected, the environment is wrong
and nothing else in the run means anything. Infrastructure failures are reported separately from
incorrect patches. Reference fixes and verification tests never reach an agent — no agent runs here.
"""

CFG = r'''# ============================ CONFIG ============================
TASK_ID = "__TASK__"
TIMEOUT_SECONDS = 900
# A's saved patch from pilot v1, and the same diff with tests/ blocks removed.
A_ORIGINAL_B64 = "__A_ORIG__"
A_SOURCE_ONLY_B64 = "__A_SRC__"
# ================================================================
import base64, json, hashlib, os, re, tempfile, uuid
from pathlib import Path
A_ORIGINAL = base64.b64decode(A_ORIGINAL_B64).decode("utf-8")
A_SOURCE_ONLY = base64.b64decode(A_SOURCE_ONLY_B64).decode("utf-8")
print("task:", TASK_ID)
print("A original diff targets :", re.findall(r"^\+\+\+ b/(\S+)", A_ORIGINAL, re.M))
print("A source-only targets   :", re.findall(r"^\+\+\+ b/(\S+)", A_SOURCE_ONLY, re.M))
assert not any(t.startswith("tests/") for t in re.findall(r"^\+\+\+ b/(\S+)", A_SOURCE_ONLY, re.M))
'''

INSTALL = r'''# Wheelhouse install. Exit status checked.
import glob, importlib, os, subprocess, sys
from pathlib import Path
os.environ.update({"LITELLM_LOCAL_MODEL_COST_MAP": "True", "TRANSFORMERS_NO_TF": "1",
                   "OTEL_SDK_DISABLED": "true", "VLLM_NO_USAGE_STATS": "1"})
WH = Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse")
for pat in ("/usr/local/lib/python*/dist-packages/*cutlass*.pth",
            "/usr/local/lib/python*/site-packages/*cutlass*.pth"):
    for pth in glob.glob(pat):
        try:
            os.unlink(pth)
        except OSError:
            pass
tmp = Path("/tmp/wheelhouse"); tmp.mkdir(parents=True, exist_ok=True)
for w in WH.glob("*.whl"):
    if "cutlass" in w.name.lower():
        continue
    n = w.name.replace("cu128", "+cu128") if ("cu128" in w.name and "+" not in w.name) else w.name
    if not (tmp / n).exists():
        os.symlink(w, tmp / n)
wheels = sorted(str(w) for w in tmp.glob("*.whl"))
proc = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps",
                       "--force-reinstall", *wheels], capture_output=True, text=True)
if proc.returncode != 0:
    print(proc.stdout[-1500:]); print(proc.stderr[-1500:])
    raise SystemExit(f"wheelhouse install failed rc={proc.returncode}")
importlib.invalidate_caches()
print("wheelhouse installed:", len(wheels))
'''

SETUP = r'''# Harness objects and the environment repair (evaluation support only).
import asyncio, concurrent.futures
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.models import load_tasks
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import (
    extract_snapshot, install_editable_package, install_test_dependencies,
    setup_baseline_commit, setup_container_wheels, setup_git_exclude, setup_workspace_test_config)
from swegemma.harness.verification import apply_patch_in_container

DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
WORKING = Path("/kaggle/working"); WORKING.mkdir(parents=True, exist_ok=True)
RESULTS = WORKING / "replay"; RESULTS.mkdir(parents=True, exist_ok=True)
TASKS_PATH = DATA_DIR / "tasks.jsonl"
TASK = {t.instance_id: t for t in load_tasks(TASKS_PATH)}[TASK_ID]
PKG = {"psf/requests": "requests", "Textualize/rich": "rich",
       "fastapi/fastapi": "fastapi", "encode/httpx": "httpx"}[TASK.repo]
TEST_FILES = re.findall(r"^\+\+\+ b/(\S+)", TASK.test_patch or "", re.M)
print("repo:", TASK.repo, "| package:", PKG, "| verification test files:", TEST_FILES)

BACKENDS = ["setuptools", "wheel", "editables", "flit_core", "poetry_core", "pdm_backend"]
COMP_WHEELS = str(DATA_DIR / "wheels")

def run_sync(fn):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(fn())).result()
    return asyncio.run(fn())

def repair(mgr, sid, log):
    for b in BACKENDS:
        r = mgr.exec(sid, "python3 -m pip install --no-index --find-links=/wheels "
                          "--find-links=" + COMP_WHEELS + " --no-build-isolation " + b)
        log.append({"cmd": "pip install " + b, "rc": r.exit_code})
    r = mgr.exec(sid, "cd /workspace && python3 -m pip install --no-index --find-links=/wheels "
                      "--find-links=" + COMP_WHEELS + " --no-build-isolation --no-deps -e .")
    log.append({"cmd": "pip install -e .", "rc": r.exit_code, "tail": (r.stdout or "")[-200:]})
    if r.exit_code != 0:
        raise RuntimeError("editable install failed rc=" + str(r.exit_code))

async def put(mgr, sid, text, name):
    with tempfile.NamedTemporaryFile("w", suffix="_" + name, delete=False, encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        host = Path(f.name)
    try:
        await asyncio.to_thread(mgr.copy_to, sid, host, "/tmp/")
        return "/tmp/" + host.name
    finally:
        os.unlink(host)
print("ready")
'''

ARMS = r'''# One fresh sandbox per arm. Official grading semantics, with every command logged.
import xml.etree.ElementTree as ET

def parse_junit(xml_text):
    out = {"parsed": False, "cases": []}
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        out["parse_error"] = repr(e)[:160]; return out
    out["parsed"] = True
    for tc in root.iter("testcase"):
        rec = {"name": tc.get("name", ""), "classname": tc.get("classname", ""), "outcome": "passed"}
        for c in tc:
            if c.tag in ("failure", "error", "skipped"):
                rec["outcome"] = {"failure": "failed", "error": "errored", "skipped": "skipped"}[c.tag]
                rec["message"] = (c.get("message") or "")[:300]
        out["cases"].append(rec)
    return out

async def arm(name, patch_text):
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    R = {"arm": name, "commands": [], "infrastructure_error": None}
    try:
        cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots",
                         results_dir=RESULTS / name, submission_dir=WORKING,
                         models=ModelRegistry(), sandbox="subprocess",
                         timeout_seconds=TIMEOUT_SECONDS, display_mode="quiet")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, DATA_DIR / "snapshots" / (TASK_ID + ".tgz"))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, TASK.repo, config=cfg)
        repair(mgr, sid, R["commands"])
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=TASK.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "eval_baseline")

        # import provenance in THIS grading environment, under the flags pytest will use
        rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
        ws = (rw.stdout or "").strip()
        rp = await sandbox_exec(mgr, sid, "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 "
                                          'python3 -s -c "import ' + PKG + ' as m; print(m.__file__)"')
        R["grading_import"] = (rp.stdout or "").strip().splitlines()[-1] if rp.exit_code == 0 else ""
        R["import_in_checkout"] = bool(R["grading_import"]) and R["grading_import"].startswith(ws)

        async def sh(label, cmd):
            r = await sandbox_exec(mgr, sid, cmd)
            R["commands"].append({"label": label, "cmd": cmd[:150], "rc": r.exit_code,
                                  "out": (r.stdout or "")[-400:], "err": (r.stderr or "")[-400:]})
            return r

        async def hash_of(path):
            r = await sandbox_exec(mgr, sid, "cd /workspace && sha256sum " + path + " 2>&1 || true")
            return (r.stdout or "").strip().split()[0][:16]

        # 1. candidate patch
        if patch_text.strip():
            p = await put(mgr, sid, patch_text, "cand.patch")
            code, out, err = await asyncio.to_thread(apply_patch_in_container, mgr, sid, p)
            R["candidate_apply_rc"] = code
            R["candidate_apply_err"] = (err or out or "")[-500:]
            if code != 0:
                R["infrastructure_error"] = None  # a patch that will not apply is a RESULT, not infra
        else:
            R["candidate_apply_rc"] = 0

        # 2. reset verification test files - errors NOT suppressed, hashes recorded
        for tf in TEST_FILES:
            R.setdefault("test_file_hashes", {})[tf] = {"before_reset": await hash_of(tf)}
            await sh("checkout " + tf, "cd /workspace && git checkout HEAD -- " + tf)
            await sh("clean " + tf, "cd /workspace && git clean -f -- " + tf)
            R["test_file_hashes"][tf]["after_reset"] = await hash_of(tf)
        rpr = await sh("pristine hash", "cd /workspace && git show HEAD:" + TEST_FILES[0] +
                       " | sha256sum") if TEST_FILES else None
        if rpr is not None:
            R["pristine_hash"] = (rpr.stdout or "").strip().split()[0][:16]

        # 3. verification patch
        tp = await put(mgr, sid, TASK.test_patch, "test.patch")
        code, out, err = await asyncio.to_thread(apply_patch_in_container, mgr, sid, tp)
        R["test_patch_apply_rc"] = code
        R["test_patch_apply_err"] = (err or out or "")[-700:]

        # 4. official pytest invocation
        junit = "/tmp/_j_" + uuid.uuid4().hex[:8] + ".xml"
        q = " ".join(TEST_FILES) if TEST_FILES else "."
        r = await sh("pytest", "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest "
                     + q + " --junitxml=" + junit + " -p no:anyio -o timeout=0 "
                     '-o python_classes="Test* *Test" -q')
        R["pytest_exit"] = r.exit_code
        R["pytest_tail"] = (r.stdout or "")[-900:]
        rx = await sandbox_exec(mgr, sid, "cat " + junit + " 2>/dev/null || true")
        R["junit"] = parse_junit(rx.stdout or "")
        R["resolved"] = (r.exit_code == 0)
    except Exception as e:
        R["infrastructure_error"] = (type(e).__name__ + ": " + str(e))[:400]
    finally:
        await sandbox_stop(mgr, sid)
    return R

ARM_SPECS = [("baseline", ""), ("reference", TASK.patch or ""),
             ("A_original", A_ORIGINAL), ("A_source_only", A_SOURCE_ONLY)]
REPLAY = []
for nm, pt in ARM_SPECS:
    print("\n===== arm:", nm, flush=True)
    res = run_sync(lambda nm=nm, pt=pt: arm(nm, pt))
    REPLAY.append(res)
    (RESULTS / "replay.json").write_text(json.dumps(REPLAY, indent=2), encoding="utf-8")
    print("  infra_error :", res.get("infrastructure_error"))
    print("  import ok   :", res.get("import_in_checkout"), res.get("grading_import", "")[-60:])
    print("  cand apply  :", res.get("candidate_apply_rc"))
    print("  test_patch  :", res.get("test_patch_apply_rc"))
    print("  pytest exit :", res.get("pytest_exit"))
'''

REPORT = r'''# Verdict per arm, with controls checked first.
UNAVAILABLE = "unavailable"
by = {r["arm"]: r for r in REPLAY}

print("%-14s %-6s %-6s %-7s %-7s %s" % ("arm", "infra", "apply", "tpatch", "pytest", "verdict"))
for r in REPLAY:
    infra = "YES" if r.get("infrastructure_error") else "no"
    if r.get("infrastructure_error"):
        v = "INFRASTRUCTURE FAILURE"
    elif r.get("import_in_checkout") is False:
        v = "INFRASTRUCTURE FAILURE (import not in checkout)"
    elif r.get("candidate_apply_rc") not in (0, None):
        v = "patch did not apply (a result, not infra)"
    elif r.get("test_patch_apply_rc") not in (0, None):
        v = "verification patch did not apply -> NOT GRADED"
    elif r.get("pytest_exit") == 0:
        v = "tests PASS"
    else:
        v = "tests FAIL"
    print("%-14s %-6s %-6s %-7s %-7s %s" % (r["arm"], infra, r.get("candidate_apply_rc"),
                                            r.get("test_patch_apply_rc"), r.get("pytest_exit"), v))

print("")
base, ref = by.get("baseline", {}), by.get("reference", {})
controls_ok = (base.get("pytest_exit") not in (0, None)) and (ref.get("pytest_exit") == 0)
print("CONTROLS:", "valid (baseline fails, reference passes)" if controls_ok
      else "INVALID - interpret nothing below until this is fixed")

so = by.get("A_source_only", {})
print("")
print("Q1  Did candidate A have a correct source fix?")
if not controls_ok:
    print("    unanswerable: controls invalid")
elif so.get("infrastructure_error") or so.get("import_in_checkout") is False:
    print("    unanswerable:", so.get("infrastructure_error") or "import not in checkout")
elif so.get("pytest_exit") == 0:
    print("    YES - with the tests/ blocks stripped, A's source change passes the graded tests.")
    print("    The test edits alone cost a solved task.")
else:
    print("    NO - A's source change fails the graded tests on its own.")
    failed = [c["name"] for c in (so.get("junit", {}) or {}).get("cases", [])
              if c["outcome"] in ("failed", "errored")]
    print("    failing/erroring nodes:", failed[:6] or UNAVAILABLE)
    print("    The test edits were a symptom of a wrong fix, not the only problem.")

orig = by.get("A_original", {})
print("")
print("Q2  Why did the verification patch fail to apply after A's run?")
print("    A_original test_patch rc:", orig.get("test_patch_apply_rc"))
h = (orig.get("test_file_hashes") or {})
for tf, hv in h.items():
    print("    %s  before_reset=%s  after_reset=%s  pristine=%s" %
          (tf, hv.get("before_reset"), hv.get("after_reset"), orig.get("pristine_hash", UNAVAILABLE)))
    if hv.get("after_reset") and orig.get("pristine_hash"):
        same = hv["after_reset"] == orig["pristine_hash"]
        print("    reset restored the pristine file:", same)
        if not same:
            print("    -> the reset did NOT restore it; the harness suppresses these errors with")
            print("       `2>/dev/null || true`, which is why the pilot could not show this.")
for c in (orig.get("commands") or []):
    if str(c.get("label", "")).startswith(("checkout", "clean")) and c.get("rc") not in (0, None):
        print("    nonzero reset command:", c["label"], "rc=", c["rc"], c["err"][:160])
print("")
print("    A_original verification-patch error:")
print("   ", (orig.get("test_patch_apply_err") or UNAVAILABLE)[:400].replace(chr(10), " | "))

(WORKING / "replay_summary.json").write_text(json.dumps(
    {"controls_valid": controls_ok,
     "arms": {r["arm"]: {k: r.get(k) for k in
                         ("pytest_exit", "resolved", "candidate_apply_rc", "test_patch_apply_rc",
                          "import_in_checkout", "infrastructure_error", "test_file_hashes",
                          "pristine_hash")} for r in REPLAY}}, indent=2), encoding="utf-8")
print("")
print("saved replay_summary.json and replay/replay.json")
print("No model ran. This measures patches and grading mechanics, not agent quality.")
'''


def main() -> None:
    raw = A_PATCH.read_text(encoding="utf-8")
    blocks = split_blocks(raw)
    src_only = "".join(b for b in blocks if not target_of(b).startswith("tests/"))
    assert src_only.strip() and "tests/" not in [target_of(b) for b in split_blocks(src_only)]
    enc = lambda t: base64.b64encode(t.encode("utf-8")).decode("ascii")

    cells = [("markdown", MD),
             ("code", CFG.replace("__TASK__", TASK)
                         .replace("__A_ORIG__", enc(raw)).replace("__A_SRC__", enc(src_only))),
             ("code", INSTALL), ("code", SETUP), ("code", ARMS), ("code", REPORT)]
    nb = {"cells": [{"cell_type": t, "metadata": {}, "source": s.splitlines(keepends=True)}
                    | ({"execution_count": None, "outputs": []} if t == "code" else {})
                    for t, s in cells],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 4}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "replay.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-replay", "code_file": "replay.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": [],
    }, indent=2), encoding="utf-8")
    print("wrote", OUT, "| arms: baseline, reference, A_original, A_source_only")


if __name__ == "__main__":
    main()
