"""Generate notebooks/evalset/ — CPU-only screening of a development / held-out task split.

No model, no GPU, no agent. This decides WHICH TASKS CAN BE MEASURED RELIABLY. It does not and
cannot measure agent wins, regressions or inference runtime: those need later model runs.

Sampling is fixed here, before any outcome is seen:
  * strata = repository x patch size (small <20 changed lines, medium <60, large otherwise)
  * order within a stratum = ascending sha256(instance_id), which is deterministic, reproducible
    and independent of difficulty, recency or any result
  * quotas are proportional to repository share, with a floor so the smaller repo is not crowded out
  * candidates are screened in that fixed order and the first ones that pass controls fill the quota
  * dev/held-out assignment alternates by the same order inside each stratum

Validity for a task (all required):
  * both the baseline and reference grading processes import the package from the checkout
  * the reference patch and the verification patch both apply (rc 0)
  * a non-empty set of test node ids FAILS at baseline and PASSES with the reference patch
  * the reference run has no failed or errored node
Disqualifiers: collection errors, empty collection, target nodes only skipped, missing dependencies.
Target nodes are derived by comparing baseline and reference node outcomes, not by regex over new
test names, so modified, parametrised and newly added tests are all covered.

Usage:
  python scripts/make_evalset_notebook.py
  python -m kaggle kernels push -p notebooks/evalset
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "evalset"
KERNEL_ID = "navin03/gemma4-swe-agent-evalset"

POLICY_SRC = (ROOT / "scripts" / "evalset_policy.py").read_text(encoding="utf-8")

MD = """# Development / held-out task screening — CPU only

**What this produces:** a frozen split of tasks whose controls behave correctly, so later agent
comparisons mean something. **What it does not produce:** any statement about agent quality. CPU
controls establish which tasks can be evaluated reliably; wins, regressions and inference runtime
require subsequent model runs.

Sampling is defined before any outcome is observed: strata are repository x patch size, order inside
a stratum is ascending `sha256(instance_id)`, and quotas are proportional to repository share with a
floor for the smallest repo. Candidates are screened in that fixed order.

A task is valid only if both grading processes import from the checkout, both patches apply, a
non-empty set of node ids fails at baseline and passes with the reference patch, and the reference
run has no failure or error. Target nodes come from comparing baseline and reference outcomes, so
modified, parametrised and newly added tests are all handled; no regex over test names is used.

This is a repaired **public subprocess** environment. It is not the private grader and no parity is
claimed. The agent access boundary is documented in the manifest: prompt construction excludes
reference patches and verification data, but the subprocess backend is not filesystem isolation.
"""

CFG = r'''# ============================ CONFIG ============================
TARGET_DEV, TARGET_HOLDOUT = 12, 12      # goal; a shortfall is reported, never hidden
MAX_SCREEN = 40                          # bound on how many candidates we attempt
TIMEOUT_SECONDS = 1200
INCLUDE_HTTPX_IF_VALID = True            # httpx is screened only after the backend preflight
# ================================================================
import hashlib, json, os, re, tempfile, time, uuid
from pathlib import Path
T0 = time.time()
print("targets:", TARGET_DEV, "dev +", TARGET_HOLDOUT, "held-out | screen cap:", MAX_SCREEN)
'''

INSTALL = r'''import glob, importlib, os, subprocess, sys
from pathlib import Path
os.environ.update({"TRANSFORMERS_NO_TF": "1", "OTEL_SDK_DISABLED": "true", "VLLM_NO_USAGE_STATS": "1"})
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
    print(proc.stdout[-1200:]); print(proc.stderr[-1200:])
    raise SystemExit("wheelhouse install failed rc=%d" % proc.returncode)
importlib.invalidate_caches()
import importlib.metadata as md
VERSIONS = {}
for p in ("swegemma", "adk-submission", "adk-eval-core", "google-adk"):
    try:
        VERSIONS[p] = md.version(p)
    except Exception as e:
        VERSIONS[p] = "MISSING: " + repr(e)[:40]
print(json.dumps(VERSIONS))
'''

SAMPLE = r'''# Inventory, then the FIXED sampling plan. Recorded before any control is run.
import collections, hashlib, importlib.util, json, re, sys
from pathlib import Path
import base64 as _b64
POLICY_SRC = _b64.b64decode("__POLICY_B64__").decode("utf-8")
_pol = Path("/kaggle/working/evalset_policy.py")
_pol.write_text(POLICY_SRC, encoding="utf-8")
POLICY_SHA = hashlib.sha256(POLICY_SRC.encode()).hexdigest()
_spec = importlib.util.spec_from_file_location("evalset_policy", _pol)
P = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(P)
print("policy loaded, sha256:", POLICY_SHA[:16])
from swegemma.models import load_tasks
DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
WORKING = Path("/kaggle/working"); WORKING.mkdir(parents=True, exist_ok=True)
RESULTS = WORKING / "evalset"; RESULTS.mkdir(parents=True, exist_ok=True)
TASKS_PATH = DATA_DIR / "tasks.jsonl"
ALL = {t.instance_id: t for t in load_tasks(TASKS_PATH)}
PKG = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich",
       "psf/requests": "requests", "encode/httpx": "httpx"}

def patch_files(p):
    return re.findall(r"^\+\+\+ b/(\S+)", p or "", re.M)

def changed_lines(p):
    return sum(1 for l in (p or "").splitlines()
               if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))

def task_sha(t):
    return hashlib.sha256(json.dumps({k: getattr(t, k, None) for k in
        ("repo", "base_commit", "problem_statement", "hints_text", "patch", "test_patch")},
        sort_keys=True).encode()).hexdigest()

INVENTORY = []
for t in ALL.values():
    n = changed_lines(t.patch)
    INVENTORY.append({"id": t.instance_id, "repo": t.repo, "size": P.size_band(n),
                      "n_lines": n, "n_files": len(patch_files(t.patch)),
                      "scope": "single" if len(patch_files(t.patch)) == 1 else "multi",
                      "order_key": hashlib.sha256(t.instance_id.encode()).hexdigest(),
                      "task_sha256": task_sha(t)})
import collections
print("inventory by repo:", dict(collections.Counter(r["repo"] for r in INVENTORY)))
print("inventory by size:", dict(collections.Counter(r["size"] for r in INVENTORY)))

TOTAL = TARGET_DEV + TARGET_HOLDOUT
repo_counts = collections.Counter(r["repo"] for r in INVENTORY)
if not INCLUDE_HTTPX_IF_VALID:
    repo_counts.pop("encode/httpx", None)
QUOTA = P.repo_quota(dict(repo_counts), TOTAL)
print("repo quota (policy):", QUOTA)

# Round-robin interleave across (repo, size) strata. Sorting by repository and truncating - the
# previous approach - dropped every psf/requests candidate from the first 40.
CANDIDATES = P.screening_order(INVENTORY, QUOTA, MAX_SCREEN)
by_id = {r["id"]: r for r in INVENTORY}
for c in CANDIDATES:
    c["task_sha256"] = by_id[c["id"]]["task_sha256"]
SAMPLING_PLAN = {"strata": "repository x patch-size band (small<20, medium<60, large)",
                 "order_within_stratum": "ascending sha256(instance_id)",
                 "screening_order": "round-robin interleave across strata (no repository truncation)",
                 "quota": QUOTA, "targets": {"dev": TARGET_DEV, "holdout": TARGET_HOLDOUT},
                 "screen_cap": MAX_SCREEN, "defined_before_any_control_ran": True,
                 "policy_sha256": POLICY_SHA}
(RESULTS / "sampling_plan.json").write_text(json.dumps(
    {"plan": SAMPLING_PLAN, "candidates": CANDIDATES}, indent=2), encoding="utf-8")
print("candidates to screen:", len(CANDIDATES),
      dict(collections.Counter(c["repo"] for c in CANDIDATES)))
'''

HTTPX = r'''# Bounded preflight: can the httpx backend (hatchling) be installed offline at all?
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
import asyncio, concurrent.futures
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

async def _httpx_preflight():
    mgr = SubprocessManager(timeout_seconds=600)
    sid = await sandbox_start(mgr)
    out = {}
    try:
        r = await sandbox_exec(mgr, sid, "ls " + COMP_WHEELS + " | grep -i -E 'trove|hatch' || true")
        out["wheels_present"] = (r.stdout or "").strip() or "none"
        r = await sandbox_exec(mgr, sid, "python3 -m pip install --no-index --find-links=/wheels "
                                         "--find-links=" + COMP_WHEELS + " --no-build-isolation hatchling")
        out["with_deps_rc"] = r.exit_code
        out["with_deps_err"] = (r.stderr or "")[-250:]
        r = await sandbox_exec(mgr, sid, "python3 -m pip install --no-index --find-links=/wheels "
                                         "--find-links=" + COMP_WHEELS + " --no-deps hatchling hatch_vcs "
                                         "hatch_fancy_pypi_readme 2>&1 | tail -2")
        out["no_deps_out"] = (r.stdout or "").strip()[-250:]
        r = await sandbox_exec(mgr, sid, 'python3 -c "import hatchling; print(hatchling.__file__)"')
        out["importable_rc"] = r.exit_code
        out["importable"] = (r.stdout or "").strip()[-120:] or (r.stderr or "")[-120:]
    finally:
        await sandbox_stop(mgr, sid)
    return out

HTTPX_PREFLIGHT = run_sync(_httpx_preflight)
print(json.dumps(HTTPX_PREFLIGHT, indent=2))
HTTPX_USABLE = HTTPX_PREFLIGHT.get("importable_rc") == 0
print("hatchling importable after preflight:", HTTPX_USABLE)
if not HTTPX_USABLE:
    print("-> httpx tasks stay EXCLUDED; recorded as a dependency limitation, not a task defect.")
    CANDIDATES = [c for c in CANDIDATES if c["repo"] != "encode/httpx"]
'''

CONTROLS = r'''# Baseline and reference controls, fresh sandbox each, official verification semantics.
import xml.etree.ElementTree as ET
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.harness.container_setup import (
    extract_snapshot, install_editable_package, install_test_dependencies, setup_baseline_commit,
    setup_container_wheels, setup_git_exclude, setup_workspace_test_config)
from swegemma.harness.verification import apply_patch_in_container

BACKENDS = ["setuptools", "wheel", "editables", "flit_core", "poetry_core", "pdm_backend"]
if HTTPX_USABLE:
    BACKENDS.append("hatchling")

def _safe(fn):
    """Never let a hashing failure cost us the whole evidence record."""
    try:
        return fn()
    except Exception as e:
        return "unavailable: " + repr(e)[:80]

def snap_sha(task):
    p = DATA_DIR / "snapshots" / (task.instance_id + ".tgz")
    if not p.exists():
        return "unavailable"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def failure_details(xml_text):
    """Message and detail per non-passing node. A <failure> alone does not establish its cause,
    so the text is preserved for human inspection rather than trusted as proof."""
    out = {}
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for tc in root.iter("testcase"):
        nid = (tc.get("classname", "") + "::" + tc.get("name", "")).strip(":")
        for c in tc:
            if c.tag in ("failure", "error", "skipped"):
                out[nid] = {"kind": c.tag, "message": (c.get("message") or "")[:600],
                            "detail": (c.text or "")[:1500]}
    return out

def nodes(xml_text):
    out = {}
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None
    for tc in root.iter("testcase"):
        nid = (tc.get("classname", "") + "::" + tc.get("name", "")).strip(":")
        kinds = {c.tag for c in tc}
        out[nid] = ("errored" if "error" in kinds else "failed" if "failure" in kinds
                    else "skipped" if "skipped" in kinds else "passed")
    return out

async def put(mgr, sid, text, name):
    with tempfile.NamedTemporaryFile("w", suffix="_" + name, delete=False, encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n"); host = Path(f.name)
    try:
        await asyncio.to_thread(mgr.copy_to, sid, host, "/tmp/"); return "/tmp/" + host.name
    finally:
        os.unlink(host)

async def control(task, patch_text, tag, log):
    mgr = SubprocessManager(timeout_seconds=TIMEOUT_SECONDS)
    sid = await sandbox_start(mgr)
    R = {"tag": tag}
    try:
        cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots",
                         results_dir=RESULTS / "ctl", submission_dir=WORKING,
                         models=ModelRegistry(), sandbox="subprocess",
                         timeout_seconds=TIMEOUT_SECONDS, display_mode="quiet")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid,
                                DATA_DIR / "snapshots" / (task.instance_id + ".tgz"))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        for b in BACKENDS:
            r = mgr.exec(sid, "python3 -m pip install --no-index --find-links=/wheels "
                              "--find-links=" + COMP_WHEELS + " --no-build-isolation " + b)
            log.append({"cmd": "pip " + b, "rc": r.exit_code})
        r = mgr.exec(sid, "cd /workspace && python3 -m pip install --no-index --find-links=/wheels "
                          "--find-links=" + COMP_WHEELS + " --no-build-isolation --no-deps -e .")
        log.append({"cmd": "pip -e .", "rc": r.exit_code, "tail": (r.stdout or "")[-150:]})
        R["editable_rc"] = r.exit_code
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "eval_baseline")

        pkg = PKG[task.repo]
        rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
        ws = (rw.stdout or "").strip()
        rp = await sandbox_exec(mgr, sid, "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 "
                                          'python3 -s -c "import ' + pkg + ' as m; print(m.__file__)"')
        R["grading_import"] = (rp.stdout or "").strip().splitlines()[-1] if rp.exit_code == 0 else ""
        R["import_in_checkout"] = bool(R["grading_import"]) and R["grading_import"].startswith(ws)

        if patch_text.strip():
            code, o, e = await asyncio.to_thread(apply_patch_in_container, mgr, sid,
                                                 await put(mgr, sid, patch_text, "ref.patch"))
            R["patch_rc"] = code; R["patch_err"] = (e or o or "")[-300:]
        else:
            R["patch_rc"] = 0

        tfiles = re.findall(r"^\+\+\+ b/(\S+)", task.test_patch or "", re.M)
        for tf in tfiles:
            r = await sandbox_exec(mgr, sid, "cd /workspace && git checkout HEAD -- " + tf)
            log.append({"cmd": "checkout " + tf, "rc": r.exit_code})
            r = await sandbox_exec(mgr, sid, "cd /workspace && git clean -f -- " + tf)
            log.append({"cmd": "clean " + tf, "rc": r.exit_code})
        code, o, e = await asyncio.to_thread(apply_patch_in_container, mgr, sid,
                                             await put(mgr, sid, task.test_patch, "test.patch"))
        R["test_patch_rc"] = code; R["test_patch_err"] = (e or o or "")[-300:]

        junit = "/tmp/_j_" + uuid.uuid4().hex[:8] + ".xml"
        q = " ".join(tfiles) if tfiles else "."
        r = await sandbox_exec(mgr, sid, "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 "
                               "python3 -s -m pytest " + q + " --junitxml=" + junit +
                               ' -p no:anyio -o timeout=0 -o python_classes="Test* *Test" -q')
        R["pytest_exit"] = r.exit_code
        rx = await sandbox_exec(mgr, sid, "cat " + junit + " 2>/dev/null || true")
        raw_xml = rx.stdout or ""
        R["nodes"] = nodes(raw_xml)
        R["failure_details"] = failure_details(raw_xml)
        R["collection_error"] = ("error" in (r.stdout or "").lower()
                                 and "collecting" in (r.stdout or "").lower())
        R["raw_xml"] = raw_xml
        R["stdout"] = r.stdout or ""
        R["stderr"] = r.stderr or ""
        R["pytest_cmd"] = "PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest " + q
    except Exception as ex:
        import traceback as _tb
        R["exception"] = (type(ex).__name__ + ": " + str(ex))[:300]
        R["traceback"] = _tb.format_exc()[-2000:]
    finally:
        # Evidence is written even when the arm never reached pytest. A setup or patch exception is
        # exactly the case we most need to diagnose, and the earlier version skipped these writes.
        try:
            ev = RESULTS / "evidence" / task.instance_id / tag
            ev.mkdir(parents=True, exist_ok=True)
            reached = "raw_xml" in R
            if reached:
                (ev / "junit.xml").write_text(R["raw_xml"], encoding="utf-8")
            else:
                # Do NOT fabricate XML for a run that never happened.
                (ev / "NO_PYTEST_RUN.txt").write_text(
                    "pytest was never reached in this arm; no JUnit report exists." + chr(10)
                    + (R.get("exception") or "no exception recorded") + chr(10), encoding="utf-8")
            (ev / "stdout.txt").write_text(R.get("stdout", ""), encoding="utf-8")
            (ev / "stderr.txt").write_text(R.get("stderr", ""), encoding="utf-8")
            if R.get("traceback"):
                (ev / "traceback.txt").write_text(R["traceback"], encoding="utf-8")
            (ev / "arm.json").write_text(json.dumps({
                "task": task.instance_id, "arm": tag,
                "reached_pytest": reached,
                "pytest_exit": R.get("pytest_exit"), "pytest_cmd": R.get("pytest_cmd"),
                "nodes": R.get("nodes"), "failure_details": R.get("failure_details"),
                "import_in_checkout": R.get("import_in_checkout"),
                "grading_import": R.get("grading_import"),
                "patch_rc": R.get("patch_rc"), "patch_err": R.get("patch_err"),
                "test_patch_rc": R.get("test_patch_rc"), "test_patch_err": R.get("test_patch_err"),
                "editable_rc": R.get("editable_rc"), "collection_error": R.get("collection_error"),
                "exception": R.get("exception"), "traceback": R.get("traceback"),
                "task_sha256": _safe(lambda: task_sha(task)),
                "snapshot_sha256": _safe(lambda: snap_sha(task)),
                "environment_versions": VERSIONS, "policy_sha256": POLICY_SHA,
                "setup_commands": log,
            }, indent=2), encoding="utf-8")
            R["evidence_dir"] = str(ev)
        except Exception as write_err:
            R["evidence_write_error"] = repr(write_err)[:200]
        await sandbox_stop(mgr, sid)
    return R

RESULTS_FILE = RESULTS / "screen.json"
SCREEN = json.loads(RESULTS_FILE.read_text(encoding="utf-8")) if RESULTS_FILE.exists() else []
done = {s["id"] for s in SCREEN}
for cand in CANDIDATES:
    if cand["id"] in done:
        continue
    t = ALL[cand["id"]]
    log = []
    base = run_sync(lambda t=t: control(t, "", "baseline", log))
    ref = run_sync(lambda t=t: control(t, t.patch or "", "reference", log))
    valid, reasons, target = P.classify(base, ref)
    _unused_reasons = []
    rec = {"id": cand["id"], "repo": cand["repo"], "size": cand["size"],
           "task_sha256": cand["task_sha256"], "valid": valid,
           "exclusion_reasons": reasons,
           "target_nodes": target,                      # ALL ids; never truncated
           "n_target_nodes": len(target),
           "evidence_dirs": {"baseline": base.get("evidence_dir"),
                             "reference": ref.get("evidence_dir")},
           "baseline": {k: base.get(k) for k in
                        ("pytest_exit", "import_in_checkout", "grading_import", "patch_rc",
                         "test_patch_rc", "editable_rc", "collection_error")},
           "reference": {k: ref.get(k) for k in
                         ("pytest_exit", "import_in_checkout", "grading_import", "patch_rc",
                          "test_patch_rc", "editable_rc", "collection_error")},
           "commands": log}
    SCREEN.append(rec)
    RESULTS_FILE.write_text(json.dumps(SCREEN, indent=2), encoding="utf-8")
    print(("  VALID   " if rec["valid"] else "  EXCLUDE") + " %-16s %-16s targets=%-3d %s"
          % (rec["id"], rec["repo"].split("/")[-1], rec["n_target_nodes"],
             "; ".join(reasons)[:70]), flush=True)
    # Stop only when EVERY repository has met its quota (or run out of candidates). Stopping at a
    # global valid count let early repositories fill the set and starve the rest.
    valid_by_repo = collections.Counter(s["repo"] for s in SCREEN if s["valid"])
    remaining = collections.Counter(c["repo"] for c in CANDIDATES
                                    if c["id"] not in {s["id"] for s in SCREEN})
    if all(valid_by_repo[r] >= QUOTA[r] or remaining[r] == 0 for r in QUOTA):
        print("all repository quotas met or exhausted:", dict(valid_by_repo)); break
'''

REPORT = r'''# Freeze the split, then report manifest, exclusions and a GPU budget proposal.
import collections, csv
valid = [s for s in SCREEN if s["valid"]]
excluded = [s for s in SCREEN if not s["valid"]]

valid_rows = [{"id": s["id"], "repo": s["repo"], "size": s["size"]} for s in valid]
DEV, HOLD, SHORT = P.allocate(valid_rows, TARGET_DEV, TARGET_HOLDOUT,
                              studied=P.PREVIOUSLY_STUDIED, quota=QUOTA)
short = (SHORT["dev_short"], SHORT["holdout_short"])

print("screened:", len(SCREEN), "| valid:", len(valid), "| excluded:", len(excluded))
print("DEV     (%d): %s" % (len(DEV), DEV))
print("HELD-OUT(%d): %s" % (len(HOLD), HOLD))
for name, ids in (("dev", DEV), ("holdout", HOLD)):
    c = collections.Counter(ALL[i].repo.split("/")[-1] for i in ids)
    print("  %-8s by repo: %s" % (name, dict(c)))
print("  selected per repo:", SHORT["selected_per_repo"],
      "| quota respected:", SHORT["quota_respected"], "| unused valid:", SHORT["unused_valid"])
print("  held-out excludes previously studied:",
      not (set(HOLD) & P.PREVIOUSLY_STUDIED))
if any(x > 0 for x in short):
    print("SHORTFALL: dev short by %d, held-out short by %d - reported, not padded" % short)

print("")
print("EXCLUSIONS")
for s in excluded:
    print("  %-16s %-10s %s" % (s["id"], s["repo"].split("/")[-1], "; ".join(s["exclusion_reasons"])[:95]))

with (WORKING / "evalset_screen.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id", "repo", "size", "valid", "n_target_nodes",
                                      "exclusion_reasons", "task_sha256"])
    w.writeheader()
    for s in SCREEN:
        w.writerow({"id": s["id"], "repo": s["repo"], "size": s["size"], "valid": s["valid"],
                    "n_target_nodes": s["n_target_nodes"],
                    "exclusion_reasons": "; ".join(s["exclusion_reasons"]),
                    "task_sha256": s["task_sha256"]})

MANIFEST = {
    "produced": "task split for later agent comparison",
    "does_not_measure": ["agent wins", "regressions", "inference runtime",
                         "private-grader behaviour"],
    "sampling_plan": SAMPLING_PLAN,
    "environment": {"versions": VERSIONS,
                    "label": "repaired PUBLIC subprocess environment; NOT the private grader; no parity claimed",
                    "repair": "PEP517 backends installed per-package from /wheels and the competition "
                              "wheels dir, then an explicit editable install of /workspace",
                    "httpx_preflight": HTTPX_PREFLIGHT, "httpx_usable": HTTPX_USABLE},
    "access_boundary": ("The harness builds agent prompts from problem_statement and hints only; "
                        "reference patches and verification data are not placed in agent inputs. "
                        "The subprocess backend executes run_command on the host and is NOT a "
                        "filesystem isolation boundary, so traces must be audited for answer-key "
                        "access before any agent result is trusted."),
    "validity_rule": ("grading imports from checkout in BOTH controls; reference and verification "
                      "patches apply; a non-empty node set fails at baseline and passes with "
                      "reference; reference run has no failed/errored node"),
    "dev": DEV, "holdout": HOLD,
    "task_sha256": {s["id"]: s["task_sha256"] for s in SCREEN},
    "target_nodes": {s["id"]: s["target_nodes"] for s in valid},
    "evidence_dirs": {s["id"]: s.get("evidence_dirs") for s in SCREEN},
    "shortfall": SHORT,
    "previously_studied_barred_from_holdout": sorted(P.PREVIOUSLY_STUDIED),
    "policy_sha256": POLICY_SHA,
    "frozen_before_any_agent_comparison": True,
    "reproduce": ["python scripts/make_evalset_notebook.py",
                  "python -m kaggle kernels push -p notebooks/evalset"],
}
(WORKING / "evalset_manifest.json").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")

n = len(DEV)
print("")
print("PROPOSED GPU COMPARISON BUDGET (for approval; nothing is dispatched here)")
print("  scope      : development set only (%d tasks); held-out reserved for one preselected candidate" % n)
print("  arms       : 2 candidates x %d tasks = %d runs" % (n, 2 * n))
print("  per run    : <=10 min agent budget + setup + grading")
print("  observed   : pilot v1 measured 108-226 s agent loop and ~27 s grading on requests_7309")
print("  server     : one shared vLLM start, measured at 6.3 min in pilot v1")
print("  NOTE       : this is a planning estimate from two runs on one task, not a tail bound.")
print("               Run the arms in separate sessions if the admission limit is reached.")
print("")
print("saved evalset_manifest.json and evalset_screen.csv")
print("CPU controls establish which tasks can be measured. They are NOT agent performance.")
'''


def main() -> None:
    cells = [("markdown", MD), ("code", CFG), ("code", INSTALL), ("code", SAMPLE),
             ("code", HTTPX), ("code", CONTROLS), ("code", REPORT)]
    import base64 as _b
    pol_b64 = _b.b64encode(POLICY_SRC.encode("utf-8")).decode("ascii")
    cells = [(t, (src.replace("__POLICY_B64__", pol_b64) if t == "code" else src))
             for t, src in cells]
    nb = {"cells": [{"cell_type": t, "metadata": {}, "source": s.splitlines(keepends=True)}
                    | ({"execution_count": None, "outputs": []} if t == "code" else {})
                    for t, s in cells],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 4}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evalset.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-evalset", "code_file": "evalset.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": [],
    }, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
