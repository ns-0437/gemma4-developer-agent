"""Generate notebooks/provenance/ — a narrow CPU-only run that answers ONE question:

  do the AGENT's commands and the GRADING run both import the task checkout?

Scope is deliberately two tasks: `requests_7309` (the disputed case: its probe showed an installed copy
yet its gold patch passed) and `rich_3471` (a task whose provenance looked clean, as a comparison).

Design fixes for the confound in the 2026-09-27 run, where the control sandbox re-ran the editable
install BETWEEN recording `__file__` and running pytest, so the two measurements described different
environment states:
  * the control path performs NO installs and NO mutation of any kind;
  * install diagnostics run in their own throwaway sandbox and are reported separately;
  * provenance is recorded under the AGENT's execution settings (plain `python3`, as `run_command` uses);
  * provenance is ALSO recorded inside the pytest process itself, by a plugin living outside the repo,
    so the grading run reports the package it actually loaded;
  * full test identities, failure messages and the raw JUnit XML are preserved.

Usage:
  python scripts/make_provenance_notebook.py
  python -m kaggle kernels push -p notebooks/provenance
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "provenance"
KERNEL_ID = "navin03/gemma4-swe-agent-provenance"
TASKS = ["requests_7309", "rich_3471"]

MD = """# Provenance check — CPU only, two tasks

One question: **do the agent's commands and the grading run both import the task checkout?**

`requests_7309` is the disputed case — its probe reported `/usr/local/lib/python3.12/dist-packages/requests`
yet its gold patch made the tests pass. `rich_3471` is the comparison.

The 2026-09-27 run had a confound: the control sandbox re-ran the editable install *between* recording
`__file__` and running pytest, so the probe and the grading described different environment states. Here
the control path performs **no installs and no mutation**; install diagnostics get their own sandbox.

Provenance is captured twice per control:
1. **agent settings** — plain `python3` via the same shell path `run_command` uses;
2. **inside pytest** — a plugin on `PYTHONPATH=/tmp` (outside the repo) records `sys.executable`,
   `sys.path` and the loaded package's `__file__`/`__path__` at `pytest_configure`.

Full test identities, failure messages and raw JUnit XML are preserved for review.
"""

CFG = r'''# ============================ CONFIG ============================
TASK_IDS = __TASKS__
TIMEOUT_SECONDS = 900
# The Docker image the real grader uses preinstalls the PEP 517 build backends
# (Dockerfile.sandbox: setuptools wheel poetry-core hatchling flit-core pdm-backend editables).
# The subprocess sandbox venv does not have them, so install_editable_package silently fails and the
# checkout never reaches sys.path. REPAIR installs those backends from the competition's own /wheels
# and re-runs the editable install, bringing this sandbox CLOSER to the grader. Applied identically to
# every control. Set False to reproduce the broken baseline.
REPAIR_EDITABLE_INSTALL = True
# ================================================================
import json, os, re, sys, tempfile, uuid
from pathlib import Path
print("provenance run (CPU only, no model):", TASK_IDS)
'''

INSTALL = r'''# Wheelhouse install (same wheels as the grader). CPU only.
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
print("installing", len(wheels), "wheels...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--force-reinstall", *wheels], check=True)
importlib.invalidate_caches()
print("done")
'''

SETUP = r'''# Harness objects + the pytest provenance plugin (kept OUTSIDE the repository).
import asyncio, concurrent.futures, json, re, tempfile, uuid, os
from pathlib import Path
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.models import load_tasks
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import (
    extract_snapshot, install_editable_package, install_test_dependencies,
    setup_baseline_commit, setup_container_wheels, setup_git_exclude, setup_workspace_test_config,
)
from swegemma.harness.verification import apply_patch_in_container

DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
WORKING_DIR = Path("/kaggle/working"); WORKING_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = WORKING_DIR / "provenance"; RESULTS.mkdir(parents=True, exist_ok=True)
TASKS_PATH = DATA_DIR / "tasks.jsonl"
ALL = {t.instance_id: t for t in load_tasks(TASKS_PATH)}
PKG = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich",
       "psf/requests": "requests", "encode/httpx": "httpx"}

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

def snapshot_for(t):
    return DATA_DIR / "snapshots" / (t.instance_id + ".tgz")
def target_tests(t):
    return re.findall(r"^\+\+\+ b/(\S+)", t.test_patch or "", re.M)

# Plugin source. Built without triple quotes so it can live inside this generated cell.
PLUGIN_SRC = "\n".join([
    "import json, os, sys",
    "def pytest_configure(config):",
    "    info = {'sys_executable': sys.executable, 'cwd': os.getcwd(),",
    "            'sys_path_head': sys.path[:12], 'prefix': sys.prefix,",
    "            'base_prefix': getattr(sys, 'base_prefix', None),",
    "            'PYTHONPATH': os.environ.get('PYTHONPATH', ''),",
    "            'safepath': os.environ.get('PYTHONSAFEPATH', '')}",
    "    for pkg in [p for p in os.environ.get('PROV_PKGS', '').split(',') if p]:",
    "        try:",
    "            m = __import__(pkg)",
    "            info[pkg + '__file__'] = getattr(m, '__file__', None)",
    "            info[pkg + '__path__'] = list(getattr(m, '__path__', []) or [])",
    "        except Exception as e:",
    "            info[pkg + '__file__'] = 'IMPORT_ERROR: ' + repr(e)",
    "    with open(os.environ.get('PROV_OUT', '/tmp/prov.json'), 'w') as f:",
    "        json.dump(info, f, indent=2)",
    "",
])

async def put_text(mgr, sid, text, name):
    with tempfile.NamedTemporaryFile("w", suffix="_" + name, delete=False, encoding="utf-8") as f:
        f.write(text)
        host = Path(f.name)
    try:
        await asyncio.to_thread(mgr.copy_to, sid, host, "/tmp/")
        return "/tmp/" + host.name
    finally:
        os.unlink(host)

async def apply_text_patch(mgr, sid, text):
    if not (text or "").strip():
        return 0, "no patch"
    p = await put_text(mgr, sid, text if text.endswith("\n") else text + "\n", "p.patch")
    code, out, err = await asyncio.to_thread(apply_patch_in_container, mgr, sid, p)
    return code, (err or out or "")[:300]

BACKENDS = ["setuptools", "wheel", "editables", "flit_core", "hatchling", "poetry_core", "pdm_backend"]

async def repair_editable_install(mgr, sid):
    """Give the sandbox venv the build backends the grader's Docker image already has, then redo the
    editable install. Returns the log so the repair is auditable, never silent."""
    log = {}
    r = await sandbox_exec(mgr, sid, "ls /wheels/*.whl 2>/dev/null | wc -l")
    log["wheels_present_sandbox"] = (r.stdout or "").strip()
    # The sandbox stages only a subset of /wheels (41 of 124), and `editables` is not in it. pip aborts
    # the whole command when one name is unresolvable, so install each backend separately and also point
    # at the competition's full wheel directory, which the subprocess sandbox can read directly.
    comp_wheels = str(DATA_DIR / "wheels")
    r = await sandbox_exec(mgr, sid, "ls " + comp_wheels + "/*.whl 2>/dev/null | wc -l")
    log["wheels_present_competition"] = (r.stdout or "").strip()
    per = {}
    for b in BACKENDS:
        rb = await sandbox_exec(mgr, sid, "python3 -m pip install --no-index --find-links=/wheels "
                                          "--find-links=" + comp_wheels + " --no-build-isolation " + b +
                                          " 2>&1 | tail -2")
        per[b] = (rb.stdout or "").strip()[-140:]
    log["backends_install"] = per
    rv = await sandbox_exec(mgr, sid, 'python3 -c "import poetry.core, hatchling, editables; print(\'backends ok\')" 2>&1 | tail -1')
    log["backends_importable"] = (rv.stdout or "").strip()[:160]
    r = await sandbox_exec(mgr, sid, "cd /workspace && python3 -m pip install --no-index "
                                     "--find-links=/wheels --no-build-isolation --no-deps -e . 2>&1 | tail -3")
    log["editable_install"] = (r.stdout or "").strip()[-300:]
    r = await sandbox_exec(mgr, sid, "find / -maxdepth 9 -name '__editable__*' -o -maxdepth 9 -name '*.egg-link' "
                                     "2>/dev/null | head -4")
    log["editable_artifacts"] = (r.stdout or "").strip()[:300]
    return log

async def base_setup(mgr, sid, task, cfg, baseline_name):
    await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
    await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
    await asyncio.to_thread(setup_git_exclude, mgr, sid)
    await asyncio.to_thread(install_editable_package, mgr, sid)
    await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
    repair_log = None
    if REPAIR_EDITABLE_INSTALL:
        repair_log = await repair_editable_install(mgr, sid)
    await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
    await asyncio.to_thread(setup_baseline_commit, mgr, sid, baseline_name)
    return repair_log
print("ready | REPAIR_EDITABLE_INSTALL =", REPAIR_EDITABLE_INSTALL)
'''

CONTROL = r'''# Controls: NO installs, NO mutation anywhere in this path.
import xml.etree.ElementTree as ET

def parse_junit_full(xml_text):
    """Preserve full test identities and failure messages."""
    out = {"parsed": False, "cases": []}
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        out["parse_error"] = repr(e)[:200]
        return out
    out["parsed"] = True
    for tc in root.iter("testcase"):
        rec = {"classname": tc.get("classname", ""), "name": tc.get("name", ""),
               "time": tc.get("time", ""), "outcome": "passed"}
        for child in tc:
            if child.tag in ("failure", "error", "skipped"):
                rec["outcome"] = {"failure": "failed", "error": "errored",
                                  "skipped": "skipped"}[child.tag]
                rec["message"] = (child.get("message") or "")[:400]
                rec["detail"] = (child.text or "")[:800]
        out["cases"].append(rec)
    return out

async def agent_style_provenance(mgr, sid, pkg):
    """Exactly how the agent would see it: plain python3 through run_command, cwd=/workspace."""
    code = ("import sys, " + pkg + " as _m; "
            "print(sys.executable); print(_m.__file__); print(list(getattr(_m,'__path__',[]))); "
            "print(sys.prefix); print(sys.path[:8])")
    r = await sandbox_exec(mgr, sid, 'cd /workspace && python3 -c "' + code + '"')
    lines = (r.stdout or "").strip().splitlines()
    got = {"raw": (r.stdout or "")[:600], "stderr": (r.stderr or "")[:300], "exit": r.exit_code}
    if r.exit_code == 0 and len(lines) >= 2:
        got["sys_executable"] = lines[0]
        got["pkg_file"] = lines[1]
        got["pkg_path"] = lines[2] if len(lines) > 2 else ""
        got["prefix"] = lines[3] if len(lines) > 3 else ""
    rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
    got["workspace_real"] = (rw.stdout or "").strip()
    return got

async def control(task, patch_text, tag):
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    pkg = PKG.get(task.repo, task.repo.split("/")[-1])
    info = {"tag": tag, "task": task.instance_id, "pkg": pkg}
    try:
        cfg = make_config(RESULTS / tag)
        info["repair_log"] = await base_setup(mgr, sid, task, cfg, "eval_baseline")

        # (1) provenance under the AGENT's settings, before anything else touches the sandbox
        info["agent_provenance"] = await agent_style_provenance(mgr, sid, pkg)

        plugin_path = await put_text(mgr, sid, PLUGIN_SRC, "prov_plugin.py")
        # the plugin must be importable by name from OUTSIDE the repo
        await sandbox_exec(mgr, sid, "mkdir -p /tmp/provplug && cp " + plugin_path + " /tmp/provplug/prov_plugin.py")

        code, msg = await apply_text_patch(mgr, sid, patch_text)
        info["patch_applied"] = (code == 0); info["patch_msg"] = msg

        tfiles = target_tests(task)
        if tfiles:
            q = " ".join(tfiles)
            await sandbox_exec(mgr, sid, "cd /workspace && git checkout HEAD -- " + q + " 2>/dev/null || true")
            await sandbox_exec(mgr, sid, "cd /workspace && git clean -f -- " + q + " 2>/dev/null || true")
        tcode, tmsg = await apply_text_patch(mgr, sid, task.test_patch)
        info["test_patch_applied"] = (tcode == 0); info["test_patch_msg"] = tmsg

        junit = "/tmp/_j_" + uuid.uuid4().hex[:8] + ".xml"
        provout = "/tmp/_prov_" + uuid.uuid4().hex[:8] + ".json"
        q = " ".join(tfiles) if tfiles else "."
        # the harness's exact command, plus the out-of-repo provenance plugin
        cmd = ("cd /workspace && PYTHONPATH=/tmp/provplug PROV_PKGS=" + pkg + " PROV_OUT=" + provout +
               " PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest " + q +
               " -p prov_plugin --junitxml=" + junit +
               " -p no:anyio -o timeout=0 -o python_classes=\"Test* *Test\" -q")
        r = await sandbox_exec(mgr, sid, cmd)
        info["pytest_exit"] = r.exit_code
        info["pytest_tail"] = (r.stdout or "")[-1500:]

        rp = await sandbox_exec(mgr, sid, "cat " + provout + " 2>/dev/null || true")
        try:
            info["pytest_provenance"] = json.loads(rp.stdout or "{}")
        except Exception:
            info["pytest_provenance"] = {"raw": (rp.stdout or "")[:400]}

        rx = await sandbox_exec(mgr, sid, "cat " + junit + " 2>/dev/null || true")
        info["junit_raw"] = (rx.stdout or "")[:20000]
        info["junit"] = parse_junit_full(rx.stdout or "")
    except Exception as e:
        info["exception"] = (type(e).__name__ + ": " + str(e))[:300]
    finally:
        await sandbox_stop(mgr, sid)
    return info

results = {}
for tid in TASK_IDS:
    t = ALL[tid]
    results[tid] = {
        "negative": run_sync(lambda t=t: control(t, "", "negative_" + tid)),
        "positive": run_sync(lambda t=t: control(t, t.patch or "", "positive_" + tid)),
    }
    (RESULTS / "controls_full.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for phase in ("negative", "positive"):
        c = results[tid][phase]
        ap = c.get("agent_provenance", {}); pp = c.get("pytest_provenance", {})
        print("%-14s %-9s agent=%s" % (tid, phase, (ap.get("pkg_file") or "?")[:64]))
        print("%-14s %-9s pytest=%s" % ("", "", (pp.get(c["pkg"] + "__file__") or "?")[:64]))
        print("%-14s %-9s exit=%s cases=%d" % ("", "", c.get("pytest_exit"),
                                               len(c.get("junit", {}).get("cases", []))), flush=True)
'''

DIAG = r'''# Install diagnostics — SEPARATE throwaway sandbox, never the control path.
async def diagnostics(task):
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    pkg = PKG.get(task.repo, task.repo.split("/")[-1])
    d = {"task": task.instance_id, "pkg": pkg}
    try:
        cfg = make_config(RESULTS / "diag")
        d["repair_log"] = await base_setup(mgr, sid, task, cfg, "diag_baseline")
        for key, cmd in [
            ("pip_version", "python3 -m pip --version 2>&1 | tail -2"),
            ("which_python", "cd /workspace && which -a python3 | head -3"),
            ("layout", "cd /workspace && ls -d src 2>/dev/null; ls -d " + pkg + " 2>/dev/null"),
            ("pth_files", "find / -maxdepth 8 -name '*.pth' -newer /etc/hostname 2>/dev/null | head -5"),
            ("editable_finder", "find / -maxdepth 8 -name '__editable__*' 2>/dev/null | head -5"),
            ("egg_info", "cd /workspace && ls -d *.egg-info src/*.egg-info 2>/dev/null"),
            ("other_copies", "find / -maxdepth 8 -name " + pkg + " -type d -not -path '/proc/*' 2>/dev/null | head -6"),
            ("editable_rerun", "cd /workspace && python3 -m pip install --no-index --find-links=/wheels "
                               "--no-build-isolation --no-deps -e . 2>&1 | tail -4"),
            ("after_rerun_import", "cd /workspace && python3 -c \"import " + pkg + " as m; print(m.__file__)\" 2>&1 | tail -1"),
        ]:
            r = await sandbox_exec(mgr, sid, cmd)
            d[key] = (r.stdout or r.stderr or "").strip()[:400]
    except Exception as e:
        d["exception"] = (type(e).__name__ + ": " + str(e))[:300]
    finally:
        await sandbox_stop(mgr, sid)
    return d

diags = {tid: run_sync(lambda t=ALL[tid]: diagnostics(t)) for tid in TASK_IDS}
(RESULTS / "diagnostics.json").write_text(json.dumps(diags, indent=2), encoding="utf-8")
for tid, d in diags.items():
    print("=" * 62); print(tid, "(" + d["pkg"] + ")")
    for k in ("pip_version", "which_python", "layout", "egg_info", "editable_finder",
              "other_copies", "editable_rerun", "after_rerun_import"):
        print("  %-20s %s" % (k, (d.get(k, "") or "").replace("\n", " | ")[:150]))
'''

REPORT = r'''# Verdict: do the agent's commands AND grading both import the checkout?
import json
from pathlib import Path

def under_checkout(path, ws_real):
    if not path:
        return False
    return path.startswith("/workspace/") or (ws_real and path.startswith(ws_real))

print("%-14s %-9s %-7s %-7s %s" % ("task", "phase", "agent", "pytest", "exit"))
summary = {}
for tid, phases in results.items():
    rec = {}
    for phase, c in phases.items():
        pkg = c["pkg"]
        ap = c.get("agent_provenance", {}) or {}
        pp = c.get("pytest_provenance", {}) or {}
        ws = ap.get("workspace_real", "")
        a_file = ap.get("pkg_file", "")
        p_file = pp.get(pkg + "__file__", "")
        a_ok = under_checkout(a_file, ws)
        p_ok = under_checkout(p_file, ws)
        rec[phase] = {"agent_ok": a_ok, "pytest_ok": p_ok, "agent_file": a_file,
                      "pytest_file": p_file, "exit": c.get("pytest_exit"),
                      "sys_exe_agent": ap.get("sys_executable", ""),
                      "sys_exe_pytest": pp.get("sys_executable", "")}
        print("%-14s %-9s %-7s %-7s %s" % (tid, phase, a_ok, p_ok, c.get("pytest_exit")))
    summary[tid] = rec

print("")
print("DETAIL")
for tid, phases in results.items():
    print("")
    print("=" * 66)
    print(tid)
    for phase, c in phases.items():
        pkg = c["pkg"]
        ap = c.get("agent_provenance", {}) or {}
        pp = c.get("pytest_provenance", {}) or {}
        print("  [%s] workspace_real = %s" % (phase, ap.get("workspace_real", "?")))
        print("      agent  : exe=%s" % (ap.get("sys_executable", "?"),))
        print("               file=%s" % (ap.get("pkg_file", "?"),))
        print("      pytest : exe=%s" % (pp.get("sys_executable", "?"),))
        print("               file=%s" % (pp.get(pkg + "__file__", "?"),))
        print("               safepath=%r PYTHONPATH=%r" % (pp.get("safepath", ""), pp.get("PYTHONPATH", "")))
        j = c.get("junit", {})
        cases = j.get("cases", [])
        bad = [x for x in cases if x["outcome"] in ("failed", "errored")]
        rl = c.get("repair_log") or {}
        if rl:
            print("      repair: backends_importable=%s" % ((rl.get("backends_importable") or "?")[:60],))
            print("              editable=%s" % ((rl.get("editable_install") or "").replace(chr(10), " ")[-90:],))
            print("              artifacts=%s" % ((rl.get("editable_artifacts") or "none")[:90],))
        print("      pytest_exit=%s cases=%d failed/errored=%d" % (c.get("pytest_exit"), len(cases), len(bad)))
        for x in bad[:6]:
            print("        %-8s %s::%s" % (x["outcome"], x["classname"], x["name"]))
            if x.get("message"):
                print("                 %s" % (x["message"][:150].replace("\n", " "),))

print("")
print("DECISION GATE")
for tid, rec in summary.items():
    both = all(rec[p]["agent_ok"] and rec[p]["pytest_ok"] for p in rec)
    agent_only_bad = all(rec[p]["pytest_ok"] for p in rec) and not all(rec[p]["agent_ok"] for p in rec)
    if both:
        print("  %-14s PASS - agent commands and grading both import the checkout" % tid)
    elif agent_only_bad:
        print("  %-14s FAIL - grading is fine but the AGENT imports an installed copy" % tid)
        print("  %-14s        (this is exactly the smoke-run failure; a repro would lie to the agent)" % "")
    else:
        print("  %-14s FAIL - grading does not import the checkout" % tid)

(RESULTS / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("")
print("saved: provenance/controls_full.json, diagnostics.json, summary.json (raw JUnit XML included)")
print("NOTE: no install or mutation occurred in the control path; diagnostics ran in their own sandbox.")
'''


def main() -> None:
    cells = [("markdown", MD), ("code", CFG.replace("__TASKS__", json.dumps(TASKS))),
             ("code", INSTALL), ("code", SETUP), ("code", CONTROL), ("code", DIAG), ("code", REPORT)]
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
    (OUT / "provenance.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-provenance", "code_file": "provenance.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": [],
    }, indent=2), encoding="utf-8")
    print("wrote", OUT, "tasks:", TASKS)


if __name__ == "__main__":
    main()
