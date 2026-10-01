"""Generate notebooks/validate/ — a CPU-ONLY notebook that decides which tasks are trustworthy to
evaluate on. No model, no GPU, no agent.

For every task it runs, in a fresh sandbox each time:
  1. IMPORT PROBE   - does `import <pkg>` resolve to the task checkout (incl. src/ layouts)?
                      Also probes the fixture plugins the repo's tests need (e.g. pytest_httpbin).
  2. NEGATIVE CTRL  - test_patch only, no fix  -> target tests MUST FAIL (the bug is real & detected)
  3. POSITIVE CTRL  - reference patch + test_patch -> target tests MUST PASS (the task is winnable)

A task is USABLE only if the import resolves to the checkout AND negative fails AND positive passes.
Infrastructure failures (collection errors, missing fixtures, sandbox setup errors) are recorded in
their own category, never silently folded into "hard task".

Usage:
  python scripts/make_validation_notebook.py
  python -m kaggle kernels push -p notebooks/validate
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "validate"
KERNEL_ID = "navin03/gemma4-swe-agent-validate"

# The 14 paired candidates from the eval notebook, plus the smoke task that exposed the problem.
DEFAULT_TASKS = [
    "fastapi_11194", "fastapi_14246", "fastapi_14361", "fastapi_14482", "fastapi_14794",
    "fastapi_15588", "rich_2725", "rich_3105", "rich_3471", "rich_3676", "rich_3934",
    "requests_6589", "requests_7309", "httpx_3672",
]

MD = """# Task validation — CPU only, no model, no GPU

Decides which tasks are trustworthy to measure an agent on, before any GPU time is spent.

Per task, each in a fresh sandbox:

| Step | Requirement |
| --- | --- |
| Import probe | `import <pkg>` resolves **inside the task checkout** (handles `src/` layouts) |
| Negative control | `test_patch` only, no fix → target tests **fail** |
| Positive control | reference `patch` + `test_patch` → target tests **pass** |

`USABLE` requires all three. Anything else is reported with its reason; infrastructure failures
(collection errors, missing fixture plugins, sandbox setup errors) are a separate category from
"agent-hard". Nothing is dropped silently.

Motivation: in the 2026-09-26 smoke run the agent read `total_length = len(o)` from
`src/requests/utils.py` but its reproduction printed `super_len('🚀') = 4` — the executed package was
not the checkout. Comparisons run on top of that would measure reactions to a broken environment.
"""

CFG = '''# ============================ CONFIG ============================
TASK_IDS = __TASKS__
RUN_NEGATIVE = True      # test_patch only -> must FAIL
RUN_POSITIVE = True      # reference patch -> must PASS
TIMEOUT_SECONDS = 600    # per pytest invocation
# ================================================================
import json, os, sys, time
from pathlib import Path
print(f"{len(TASK_IDS)} task(s) to validate (CPU only, no model will be loaded)")
'''

INSTALL = '''# Wheelhouse install (same wheels as the grader). CPU only — vLLM is installed but never started.
import glob, importlib, os, subprocess, sys
from pathlib import Path

os.environ.update({"LITELLM_LOCAL_MODEL_COST_MAP": "True", "TRANSFORMERS_NO_TF": "1",
                   "OTEL_SDK_DISABLED": "true", "VLLM_NO_USAGE_STATS": "1"})
WHEELHOUSE_DIR = Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse")
for pat in ("/usr/local/lib/python*/dist-packages/*cutlass*.pth", "/usr/local/lib/python*/site-packages/*cutlass*.pth"):
    for pth in glob.glob(pat):
        try:
            os.unlink(pth)
        except OSError:
            pass
tmp_whl = Path("/tmp/wheelhouse"); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob("*.whl"):
    if "cutlass" in w.name.lower():
        continue
    name = w.name.replace("cu128", "+cu128") if ("cu128" in w.name and "+" not in w.name) else w.name
    if not (tmp_whl / name).exists():
        os.symlink(w, tmp_whl / name)
wheels = sorted(str(w) for w in tmp_whl.glob("*.whl"))
print(f"installing {len(wheels)} wheels...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--force-reinstall", *wheels], check=True)
importlib.invalidate_caches()
import importlib.metadata as md
for p in ("swegemma", "adk-submission", "adk-eval-core", "google-adk"):
    print(f"  {p:16s} {md.version(p)}")
'''

SETUP = '''# Harness objects. No ModelRegistry entries are needed: no agent runs in this notebook.
import asyncio, concurrent.futures, json, re, time, traceback
from pathlib import Path
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.models import load_tasks
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import (
    extract_snapshot, install_editable_package, install_test_dependencies,
    setup_baseline_commit, setup_container_wheels, setup_git_exclude, setup_workspace_test_config,
)
from swegemma.harness.verification import verify_task

DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
WORKING_DIR = Path("/kaggle/working"); WORKING_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = WORKING_DIR / "validation"; RESULTS.mkdir(parents=True, exist_ok=True)
TASKS_PATH = DATA_DIR / "tasks.jsonl"
ALL = {t.instance_id: t for t in load_tasks(TASKS_PATH)}
missing = [t for t in TASK_IDS if t not in ALL]
assert not missing, f"unknown task ids: {missing}"

def run_sync(fn):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(fn())).result()
    return asyncio.run(fn())

def make_config(results_dir):
    return EvalConfig(
        tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots", results_dir=results_dir,
        submission_dir=WORKING_DIR, models=ModelRegistry(), sandbox="subprocess",
        graph_dir=str(DATA_DIR / "graphs"), embeddings_dir=str(DATA_DIR / "embeddings"),
        timeout_seconds=TIMEOUT_SECONDS, display_mode="quiet")

PKG = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich",
       "psf/requests": "requests", "encode/httpx": "httpx"}
def snapshot_for(t):
    return DATA_DIR / "snapshots" / f"{t.instance_id}.tgz"
def target_tests(t):
    return re.findall(r"^\\+\\+\\+ b/(\\S+)", t.test_patch or "", re.M)
print("ready:", len(TASK_IDS), "tasks")
'''

PROBE = '''# STEP 1 — import probe. Fresh sandbox, full harness setup, then ask Python where the package is.
async def probe(task):
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    info = {"instance_id": task.instance_id, "repo": task.repo}
    try:
        cfg = make_config(RESULTS / "probe")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        info["repair_log"] = await repair_editable_install(mgr, sid)
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "baseline")

        pkg = PKG.get(task.repo, task.repo.split("/")[-1])
        r = await sandbox_exec(mgr, sid, f'cd /workspace && python3 -c "import {pkg}, sys; '
                                         f'print({pkg}.__file__); print(sys.executable)"')
        out = (r.stdout or "").strip().splitlines()
        info["pkg_file"] = out[0] if out else ""
        info["python"] = out[1] if len(out) > 1 else ""
        info["import_error"] = (r.stderr or "")[:300] if r.exit_code != 0 else ""
        # The checkout is what matters: /workspace/<pkg> or /workspace/src/<pkg>.
        info["import_in_checkout"] = info["pkg_file"].startswith("/workspace/")
        r2 = await sandbox_exec(mgr, sid, "cd /workspace && ls src 2>/dev/null | head -5")
        info["src_layout"] = bool((r2.stdout or "").strip())
        # Fixture plugins the repo's own tests rely on.
        for plug in ("pytest_httpbin", "pytest_asyncio", "trio", "anyio"):
            rp = await sandbox_exec(mgr, sid, f'python3 -c "import {plug}; print({plug}.__file__)" 2>&1 | tail -1')
            info[f"has_{plug}"] = "Error" not in (rp.stdout or "") and rp.exit_code == 0
        # Does the graded test file even collect?
        tf = target_tests(task)
        if tf:
            rc = await sandbox_exec(mgr, sid,
                f"cd /workspace && python3 -m pytest {tf[0]} --collect-only -q 2>&1 | tail -6")
            info["collect_tail"] = (rc.stdout or "").strip()[-400:]
            info["collect_errors"] = "error" in (rc.stdout or "").lower()
    except Exception as e:
        info["probe_exception"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        await sandbox_stop(mgr, sid)
    return info

probes = []
for tid in TASK_IDS:
    t = ALL[tid]
    p = run_sync(lambda t=t: probe(t))
    probes.append(p)
    flag = "OK " if p.get("import_in_checkout") else "BAD"
    print(f"[{flag}] {tid:16s} {p.get('pkg_file','')[:70]}"
          f"{'  src/' if p.get('src_layout') else ''}"
          f"{'  COLLECT-ERR' if p.get('collect_errors') else ''}", flush=True)
(RESULTS / "probes.json").write_text(json.dumps(probes, indent=2), encoding="utf-8")
bad = [p["instance_id"] for p in probes if not p.get("import_in_checkout")]
print(f"\\nimports NOT resolving to the checkout: {bad or 'none'}")
'''

CONTROLS = r'''# STEPS 2 & 3 — controls. Each runs in its OWN fresh sandbox and probes import provenance
# INSIDE that same sandbox, because a clean probe elsewhere proves nothing about this one.
import os, tempfile, uuid
import xml.etree.ElementTree as ET
from swegemma.harness.verification import apply_patch_in_container

NEW_TEST_RE = re.compile(r"^\+\s*(?:async\s+)?def\s+(test_\w+)", re.M)
def new_tests(t):
    return sorted(set(NEW_TEST_RE.findall(t.test_patch or "")))

async def apply_text_patch(mgr, sid, text):
    """Apply a unified diff with the harness's own 4-pass applier."""
    if not (text or "").strip():
        return 0, "no patch"
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
        host = Path(f.name)
    try:
        await asyncio.to_thread(mgr.copy_to, sid, host, "/tmp/")
        code, out, err = await asyncio.to_thread(apply_patch_in_container, mgr, sid, f"/tmp/{host.name}")
        return code, (err or out or "")[:300]
    finally:
        os.unlink(host)

async def provenance(mgr, sid, pkg):
    """Establish HOW the package resolves in THIS sandbox, with evidence."""
    p = {}
    r = await sandbox_exec(mgr, sid, 'cd /workspace && python3 -c "import ' + pkg + '; print(' + pkg + '.__file__)"')
    lines = (r.stdout or "").strip().splitlines()
    p["pkg_file"] = lines[-1] if (r.exit_code == 0 and lines) else ""
    p["import_error"] = (r.stderr or "")[:200] if r.exit_code != 0 else ""
    rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
    ws = (rw.stdout or "").strip()
    p["workspace_real"] = ws
    p["in_checkout"] = bool(p["pkg_file"]) and (p["pkg_file"].startswith("/workspace/")
                                                or (ws and p["pkg_file"].startswith(ws)))
    r = await sandbox_exec(mgr, sid, "python3 -m pip --version 2>&1 | tail -1")
    p["pip"] = (r.stdout or "").strip()[:120]
    p["pip_available"] = (r.exit_code == 0) and ("no module named pip" not in p["pip"].lower())
    r = await sandbox_exec(mgr, sid, 'find / -maxdepth 8 -name "' + pkg + '" -type d '
                                     '-not -path "/workspace/*" -not -path "/proc/*" 2>/dev/null | head -4')
    p["other_copies"] = [x for x in (r.stdout or "").strip().splitlines() if x]
    return p

def parse_junit(xml_text, wanted):
    """Per-test outcome from the harness's own JUnit XML: <failure> is not <error>."""
    out = {"failed": [], "errored": [], "passed": [], "skipped": [], "parsed": False}
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    out["parsed"] = True
    for tc in root.iter("testcase"):
        kinds = {c.tag for c in tc}
        bucket = ("errored" if "error" in kinds else "failed" if "failure" in kinds
                  else "skipped" if "skipped" in kinds else "passed")
        out[bucket].append(tc.get("name", ""))
    for k in ("failed", "errored", "passed", "skipped"):
        out["target_" + k] = [n for n in out[k] if any(n.split("[")[0] == w for w in (wanted or []))]
    return out


BACKENDS = ["setuptools", "wheel", "editables", "flit_core", "hatchling", "poetry_core", "pdm_backend"]

async def repair_editable_install(mgr, sid):
    """Give the sandbox venv the PEP 517 backends the grader's Docker image already has, then redo the
    editable install. Without this the checkout never reaches sys.path and every verdict is void."""
    log = {}
    comp_wheels = str(DATA_DIR / "wheels")
    per = {}
    for b in BACKENDS:
        rb = await sandbox_exec(mgr, sid, "python3 -m pip install --no-index --find-links=/wheels "
                                          "--find-links=" + comp_wheels + " --no-build-isolation " + b +
                                          " 2>&1 | tail -1")
        per[b] = (rb.stdout or "").strip()[-100:]
    log["backends"] = per
    r = await sandbox_exec(mgr, sid, "cd /workspace && python3 -m pip install --no-index "
                                     "--find-links=/wheels --find-links=" + comp_wheels +
                                     " --no-build-isolation --no-deps -e . 2>&1 | tail -2")
    log["editable_install"] = (r.stdout or "").strip()[-200:]
    return log

async def control(task, patch_text, tag):
    """Container-B equivalent: setup -> provenance -> patch -> test_patch -> the harness's pytest."""
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    info = {"tag": tag}
    try:
        cfg = make_config(RESULTS / tag)
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        info["repair_log"] = await repair_editable_install(mgr, sid)
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "eval_baseline")

        info["provenance"] = await provenance(mgr, sid, PKG.get(task.repo, task.repo.split("/")[-1]))
        code, msg = await apply_text_patch(mgr, sid, patch_text)
        info["patch_applied"] = (code == 0)
        info["patch_msg"] = msg

        tfiles = target_tests(task)
        if tfiles:
            q = " ".join(tfiles)
            await sandbox_exec(mgr, sid, "cd /workspace && git checkout HEAD -- " + q + " 2>/dev/null || true")
            await sandbox_exec(mgr, sid, "cd /workspace && git clean -f -- " + q + " 2>/dev/null || true")
        tcode, tmsg = await apply_text_patch(mgr, sid, task.test_patch)
        info["test_patch_applied"] = (tcode == 0)
        info["test_patch_msg"] = tmsg

        junit = "/tmp/_v_" + uuid.uuid4().hex[:8] + ".xml"
        q = " ".join(tfiles) if tfiles else "."
        cmd = ("cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest " + q +
               " --junitxml=" + junit + " -p no:anyio -o timeout=0 -o python_classes=\"Test* *Test\" -q")
        r = await sandbox_exec(mgr, sid, cmd)
        info["pytest_exit"] = r.exit_code
        info["pytest_tail"] = (r.stdout or "")[-700:]
        rx = await sandbox_exec(mgr, sid, "cat " + junit + " 2>/dev/null || true")
        info["junit"] = parse_junit(rx.stdout or "", new_tests(task))
    except Exception as e:
        info["exception"] = (type(e).__name__ + ": " + str(e))[:300]
    finally:
        await sandbox_stop(mgr, sid)
    return info

rows = []
for tid in TASK_IDS:
    t = ALL[tid]
    wanted = new_tests(t)
    neg = run_sync(lambda t=t: control(t, "", "negative")) if RUN_NEGATIVE else {}
    pos = run_sync(lambda t=t: control(t, t.patch or "", "positive")) if RUN_POSITIVE else {}

    nprov, pprov = neg.get("provenance", {}), pos.get("provenance", {})
    njl, pjl = neg.get("junit", {}), pos.get("junit", {})
    imports_ok = bool(nprov.get("in_checkout")) and bool(pprov.get("in_checkout"))

    # Did the negative control fail because of the TARGET BUG, or because of infrastructure?
    n_failed = bool(njl.get("target_failed"))
    n_errored = bool(njl.get("target_errored"))
    n_passed = bool(njl.get("target_passed"))
    collected = bool(njl.get("parsed")) and bool(njl.get("failed") or njl.get("errored") or njl.get("passed"))

    if not imports_ok:
        verdict, why = "UNUSABLE", "import not in checkout (neg=" + str(nprov.get("pkg_file", "?")) + ")"
    elif neg.get("exception") or pos.get("exception"):
        verdict, why = "INFRA_FAILURE", str(neg.get("exception") or pos.get("exception"))
    elif not neg.get("test_patch_applied", False):
        verdict, why = "INFRA_FAILURE", "test_patch did not apply: " + str(neg.get("test_patch_msg", ""))
    elif not pos.get("patch_applied", False):
        verdict, why = "INFRA_FAILURE", "gold patch did not apply: " + str(pos.get("patch_msg", ""))
    elif not collected:
        verdict, why = "INFRA_FAILURE", "negative control produced no usable JUnit XML (tests never ran)"
    elif n_errored:
        verdict, why = "INFRA_FAILURE", "target tests ERROR at setup, not fail: " + str(njl.get("target_errored")[:3])
    elif n_passed and not n_failed:
        verdict, why = "UNUSABLE", "negative control PASSED the target tests — no fix needed"
    elif not n_failed:
        verdict, why = "INFRA_FAILURE", "target tests neither failed nor errored (not collected?)"
    elif pos.get("pytest_exit") != 0:
        gold_infra = bool(pjl.get("target_errored")) or not pjl.get("parsed")
        verdict = "INFRA_FAILURE" if gold_infra else "UNUSABLE"
        why = "gold patch did not make tests pass (exit " + str(pos.get("pytest_exit")) + ")"
    else:
        verdict, why = "USABLE", "target tests FAIL at baseline, PASS with gold; imports in checkout"

    rows.append(dict(task=tid, repo=t.repo, verdict=verdict, reason=why, new_tests=wanted,
        neg_pkg_file=nprov.get("pkg_file", ""), pos_pkg_file=pprov.get("pkg_file", ""),
        imports_in_checkout=imports_ok, pip_available=nprov.get("pip_available"),
        pip=nprov.get("pip", ""), editable_log=(nprov.get("editable_install_log") or "")[-200:],
        other_copies=nprov.get("other_copies", []),
        neg_exit=neg.get("pytest_exit"), pos_exit=pos.get("pytest_exit"),
        neg_target_failed=njl.get("target_failed"), neg_target_errored=njl.get("target_errored"),
        neg_target_passed=njl.get("target_passed"), pos_target_passed=pjl.get("target_passed"),
        pos_target_failed=pjl.get("target_failed"), pos_target_errored=pjl.get("target_errored"),
        gold_applied=pos.get("patch_applied"), test_patch_applied=neg.get("test_patch_applied"),
        neg_tail=(neg.get("pytest_tail") or "")[-300:], pos_tail=(pos.get("pytest_tail") or "")[-300:]))
    print("%-14s %-16s imports=%s neg_fail=%s neg_err=%s pos_exit=%s  %s" % (
        verdict, tid, imports_ok, n_failed, n_errored, pos.get("pytest_exit"), why[:70]), flush=True)
    (RESULTS / "controls.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
'''

REPORT = r'''# Per-task provenance, baseline failure reason, gold result, and exclusion reason.
import csv
from collections import Counter

flat = [{k: (";".join(map(str, v)) if isinstance(v, list) else v)
         for k, v in r.items() if not k.endswith("_tail")} for r in rows]
with (WORKING_DIR / "validation_results.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(flat[0]))
    w.writeheader()
    w.writerows(flat)

print("VERDICTS:", dict(Counter(r["verdict"] for r in rows)))

print("")
print("ENVIRONMENT EVIDENCE (captured inside each control sandbox):")
print("  pip available in sandbox:", set(r["pip_available"] for r in rows))
for r in rows[:3]:
    print("  %s: pip=%r" % (r["task"], r["pip"][:60]))
    print("      editable install log: %r" % (r["editable_log"][:160],))

bad_imports = [r for r in rows if not r["imports_in_checkout"]]
if bad_imports:
    print("")
    print("  IMPORTS NOT RESOLVING TO THE CHECKOUT:")
    for r in bad_imports:
        print("    %-16s neg=%s  pos=%s" % (r["task"], r["neg_pkg_file"], r["pos_pkg_file"]))
        print("        other copies on disk: %s" % (r["other_copies"],))

print("")
print("PER-TASK DETAIL")
for r in rows:
    print("")
    print("  %s [%s] %s" % (r["task"], r["verdict"], r["repo"]))
    print("    import (neg / pos): %s / %s" % (r["neg_pkg_file"] or "<none>", r["pos_pkg_file"] or "<none>"))
    print("    new tests: %s" % (r["new_tests"],))
    print("    baseline: exit=%s failed=%s errored=%s passed=%s" % (
        r["neg_exit"], r["neg_target_failed"], r["neg_target_errored"], r["neg_target_passed"]))
    print("    gold:     exit=%s applied=%s passed=%s failed=%s errored=%s" % (
        r["pos_exit"], r["gold_applied"], r["pos_target_passed"],
        r["pos_target_failed"], r["pos_target_errored"]))
    print("    reason:   %s" % (r["reason"],))

usable = [r["task"] for r in rows if r["verdict"] == "USABLE"]
print("")
print("USABLE (%d): %s" % (len(usable), usable))
for cat in ("UNUSABLE", "INFRA_FAILURE"):
    sub = [r for r in rows if r["verdict"] == cat]
    if sub:
        print("")
        print("%s - excluded, with reason (never dropped silently):" % cat)
        for r in sub:
            print("  %-16s %s" % (r["task"], r["reason"]))

print("")
print("usable per repo:", dict(Counter(r["repo"] for r in rows if r["verdict"] == "USABLE")))
print("USABLE validates the TASK and this sandbox, not the agent, and does not prove that")
print("the subprocess backend isolates the host filesystem.")
if len(usable) < 8:
    print("")
    print("WARNING: too few usable tasks for a meaningful paired comparison.")
    print("Repair the environment (imports / fixture plugins) before spending GPU time.")
'''


def main() -> None:
    cells = [("markdown", MD), ("code", CFG.replace("__TASKS__", json.dumps(DEFAULT_TASKS))),
             ("code", INSTALL), ("code", SETUP), ("code", PROBE), ("code", CONTROLS), ("code", REPORT)]
    nb = {
        "cells": [
            {"cell_type": t, "metadata": {}, "source": s.splitlines(keepends=True)}
            | ({"execution_count": None, "outputs": []} if t == "code" else {})
            for t, s in cells
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 4,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validate.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-validate", "code_file": "validate.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": [],
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(DEFAULT_TASKS)} tasks, CPU only)")


if __name__ == "__main__":
    main()
