"""Generate notebooks/pilot/ — the four-run A/B thinking pilot (2 tasks x 2 candidates).

A = releases/pilot_A  (frozen v2_reviewed, unchanged, enable_thinking=false)
B = releases/pilot_B  (same bytes except include_thoughts: true -> enable_thinking=true)

Fixes carried over from review of the previous generator:
  * cells are emitted in true dependency order; run_sync / ALL_BY_ID / TASK_IDS are defined in COMMON
    before REPAIR uses them (the old notebook raised NameError at the repair cell);
  * pip runs keep their exit status (no `| tail`), full output is retained, and a failed REQUIRED
    editable install aborts instead of being reported as success;
  * the monkeypatch is idempotent, so re-running the cell cannot wrap the wrapper;
  * preconditions cover EVERY selected task, and the same patched setup path is used;
  * phase timing separates setup / agent loop / grading instead of reusing duration_seconds;
  * diagnostics come from structured traces; missing data is reported as "unavailable", never 0.

Usage:
  python scripts/make_pilot_notebook.py
  (review, then push manually — this script never dispatches anything)
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "pilot"
KERNEL_ID = "navin03/gemma4-swe-agent-pilot"
TEXT_EXT = {".yaml", ".yml", ".md", ".txt", ".py", ".json"}
CANDIDATES = {"A": ROOT / "releases" / "pilot_A", "B": ROOT / "releases" / "pilot_B"}
PILOT_TASKS = ["requests_7309", "rich_3471"]
EVIDENCE = ROOT / "reference" / "provenance_run_2026-09-27_repaired" / "controls_full.json"


def bundle(src: Path) -> tuple[str, str]:
    buf = io.BytesIO()
    files = sorted((p for p in src.rglob("*") if p.is_file()),
                   key=lambda p: p.relative_to(src).as_posix())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            if p.suffix not in TEXT_EXT:
                raise SystemExit(f"non-text file {p}")
            info = zipfile.ZipInfo(p.relative_to(src).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    data = buf.getvalue()
    return base64.b64encode(data).decode("ascii"), hashlib.sha256(data).hexdigest()


# NOTE: CONTROL_EVIDENCE is substituted into Python source, so it must be a PYTHON literal.
# json.dumps emits true/false/null, which are NameErrors in Python. repr() is correct here.
def control_evidence() -> dict:
    """Summarise the saved repaired-control evidence for the pilot tasks."""
    if not EVIDENCE.exists():
        raise SystemExit(f"missing control evidence: {EVIDENCE}")
    raw = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    out = {}
    for tid, phases in raw.items():
        if tid not in PILOT_TASKS:
            continue
        rec = {}
        for phase, c in phases.items():
            pkg = c.get("pkg", "")
            ap = c.get("agent_provenance", {}) or {}
            pp = c.get("pytest_provenance", {}) or {}
            cases = (c.get("junit", {}) or {}).get("cases", [])
            rec[phase] = {
                "pytest_exit": c.get("pytest_exit"),
                "workspace_real": ap.get("workspace_real", ""),
                "agent_pkg_file": ap.get("pkg_file", ""),
                "pytest_pkg_file": pp.get(pkg + "__file__", ""),
                "n_cases": len(cases),
                "failed_nodes": [x.get("classname", "")+"::"+x["name"] for x in cases if x["outcome"] == "failed"],
                "passed_nodes": [x.get("classname", "")+"::"+x["name"] for x in cases if x["outcome"] == "passed"],
                "failed": [x["name"] for x in cases if x["outcome"] == "failed"],
                "errored": [x["name"] for x in cases if x["outcome"] == "errored"],
            }
        out[tid] = rec
    return out


MD = r'''# Thinking A/B pilot — four runs, two tasks

| candidate | source | effective difference |
| --- | --- | --- |
| **A** | frozen `releases/pilot_A` (= `v2_reviewed`, unchanged) | `enable_thinking: false` |
| **B** | `releases/pilot_B` | `enable_thinking: true` — **only** `include_thoughts` differs (one line; file length decreases by one byte) |

Everything else is byte-identical: prompts, tools, temperature, top_p, top_k, seed,
max_output_tokens, adapters (none), budgets.

Tasks: `requests_7309`, `rich_3471` — the two with directly measured repaired controls
(baseline fails, gold passes, agent **and** grading importing the checkout).

Four runs, order alternated per task (A→B, then B→A) to reduce systematic ordering bias; this does not eliminate shared-server effects. This pilot establishes that the experiment executes and produces
usable evidence. **It cannot establish which candidate is better** — two tasks is not a comparison.

`thinking_budget: 4096` is **not** forwarded to the server (verified: only
`extra_body.chat_template_kwargs.enable_thinking` is). Do not describe it as an enforced limit.
'''

CFG = r'''# ============================ CONFIG ============================
DISPATCH_CONFIRM = False     # guards model startup/dispatch; a Kaggle GPU session still consumes quota during setup
SESSION_CAP_MIN  = 150       # admission deadline; not a hard OS-process/session kill
RUN_RESERVE_MIN = 25         # refuse a new run when less than this planning allowance remains

# Identical for A and B. Not tuned per variant.
BUDGET = dict(max_time_minutes=10.0, max_tool_calls=100, max_turns=60, timeout_seconds=300)
# ================================================================
import json, os, sys, time
from pathlib import Path
T0 = time.perf_counter()
def elapsed_min():
    return (time.perf_counter() - T0) / 60.0
print("pilot config:", BUDGET, "| session cap", SESSION_CAP_MIN, "min")
if not DISPATCH_CONFIRM:
    print("DISPATCH_CONFIRM is False: setup and preconditions will run, the four runs will NOT.")
'''

INSTALL = r'''# Wheelhouse install. Exit status is checked, not piped away.
import glob, importlib, os, subprocess, sys
from pathlib import Path
os.environ.update({
    "LITELLM_LOCAL_MODEL_COST_MAP": "True", "TRANSFORMERS_NO_TF": "1",
    "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": "1",
    "VLLM_ENGINE_READY_TIMEOUT_S": "1200", "VLLM_NO_USAGE_STATS": "1",
    "OTEL_SDK_DISABLED": "true", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
})
WHEELHOUSE_DIR = Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse")
for pat in ("/usr/local/lib/python*/dist-packages/*cutlass*.pth",
            "/usr/local/lib/python*/site-packages/*cutlass*.pth"):
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
proc = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps",
                       "--force-reinstall", *wheels], capture_output=True, text=True)
if proc.returncode != 0:
    print(proc.stdout[-2000:]); print(proc.stderr[-2000:])
    raise SystemExit(f"wheelhouse install failed rc={proc.returncode}")
importlib.invalidate_caches()
import importlib.metadata as md
VERSIONS = {}
for p in ("swegemma", "adk-submission", "adk-eval-core", "google-adk", "vllm", "transformers", "litellm"):
    try:
        VERSIONS[p] = md.version(p)
    except Exception as e:
        VERSIONS[p] = "MISSING: " + repr(e)[:60]
print(json.dumps(VERSIONS, indent=2))
'''

VERIFY = r'''# Hardware / model identity.
import hashlib, json, torch
from pathlib import Path
DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
MODEL_PATH = Path("/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2")
WORKING_DIR = Path("/kaggle/working"); WORKING_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = WORKING_DIR / "pilot"; RESULTS.mkdir(parents=True, exist_ok=True)

N_GPU = torch.cuda.device_count() if torch.cuda.is_available() else 0
GPU_NAMES = [torch.cuda.get_device_name(i) for i in range(N_GPU)]
print("GPUs:", N_GPU, GPU_NAMES)
assert MODEL_PATH.exists(), "attach model gemma-4-31b-it-qat-w4a16-ct/2"
assert DATA_DIR.exists(), "attach the competition data"
_cfg_bytes = (MODEL_PATH / "config.json").read_bytes()
MODEL_CONFIG_SHA = hashlib.sha256(_cfg_bytes).hexdigest()
_cfg = json.loads(_cfg_bytes)
QUANT = _cfg.get("quantization_config") or _cfg.get("text_config", {}).get("quantization_config")
print("model revision dir:", MODEL_PATH.name, "| config sha256:", MODEL_CONFIG_SHA[:16])
print("architectures:", _cfg.get("architectures"))
print("quantization:", json.dumps(QUANT)[:200])
if N_GPU != 4:
    print(f"WARNING: {N_GPU} GPU(s); the grader uses 4x L4. Timings are not comparable.")
'''

COMMON = r'''# Shared helpers. Defined BEFORE any cell that uses them (the previous notebook referenced
# run_sync / TASK_IDS from the repair cell, which were only defined later -> NameError at runtime).
import asyncio, concurrent.futures, re
from swegemma.models import load_tasks

TASKS_PATH = DATA_DIR / "tasks.jsonl"
all_tasks = load_tasks(TASKS_PATH)
ALL_BY_ID = {t.instance_id: t for t in all_tasks}
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

def snapshot_for(t):
    return DATA_DIR / "snapshots" / (t.instance_id + ".tgz")

def target_tests(t):
    return re.findall(r"^\+\+\+ b/(\S+)", t.test_patch or "", re.M)

def pkg_of(t):
    return PKG.get(t.repo, t.repo.split("/")[-1])

def under(path, ws):
    from pathlib import PurePosixPath
    import posixpath
    if not path or not ws or not path.startswith('/') or not ws.startswith('/'):
        return False
    actual, root = PurePosixPath(posixpath.normpath(path)), PurePosixPath(posixpath.normpath(ws))
    return actual != root and actual.is_relative_to(root)

print("loaded", len(all_tasks), "tasks")
'''

TASKS = r'''# Task manifest + the saved control evidence these tasks were selected on.
TASK_IDS = __TASKS__
CONTROL_EVIDENCE = __EVIDENCE__
EXPECTED_TASK_HASHES = __TASK_HASHES__
import hashlib
def task_hash(t):
    return hashlib.sha256(json.dumps({k:getattr(t,k,None) for k in
        ('repo','base_commit','problem_statement','hints_text','patch','test_patch')},sort_keys=True).encode()).hexdigest()

missing = [t for t in TASK_IDS if t not in ALL_BY_ID]
assert not missing, f"unknown task ids: {missing}"
SELECTED = [ALL_BY_ID[t] for t in TASK_IDS]
for t in SELECTED:
    assert task_hash(t) == EXPECTED_TASK_HASHES.get(t.instance_id), f'{t.instance_id}: task content changed since local preparation; rerun controls'

print("PILOT TASKS and the evidence they were chosen on:")
for tid in TASK_IDS:
    ev = CONTROL_EVIDENCE.get(tid)
    print("\n ", tid, ALL_BY_ID[tid].repo)
    if not ev:
        raise AssertionError(f"{tid}: missing saved control evidence")
    for phase in ("negative", "positive"):
        e = ev.get(phase, {})
        print(f"    {phase:9s} exit={e.get('pytest_exit')} cases={e.get('n_cases')} "
              f"failed={len(e.get('failed', []))} errored={len(e.get('errored', []))}")
        print(f"              agent  import: {e.get('agent_pkg_file','')}")
        print(f"              pytest import: {e.get('pytest_pkg_file','')}")
    neg, pos = ev.get("negative", {}), ev.get("positive", {})
    failed = set(neg.get('failed_nodes', []))
    passed = set(pos.get('passed_nodes', []))
    ok = (neg.get('pytest_exit') == 1 and pos.get('pytest_exit') == 0
          and bool(failed) and failed <= passed
          and not neg.get('errored') and not pos.get('errored')
          and all(under(e.get(key, ''), e.get('workspace_real', ''))
                  for e in (neg,pos) for key in ('agent_pkg_file','pytest_pkg_file')))
    print(f"    baseline-fails / gold-passes / imports-in-checkout: {ok}")
    assert ok, f"{tid}: saved control evidence does not support using this task"
    if neg.get("failed"):
        print(f"    baseline failures: {neg['failed'][:4]}")
'''

LEAK = r'''# The agent prompt must contain no answer-key text beyond what the issue itself carries.
from swegemma.harness.agent_runner import build_agent_prompt
from dataclasses import replace

class _B:
    time_minutes, tool_calls, turns, cost_usd = (BUDGET["max_time_minutes"], BUDGET["max_tool_calls"],
                                                 BUDGET["max_turns"], None)
class _H:
    command_timeout_seconds, max_stdout_chars, max_file_lines, max_file_chars = (
        BUDGET["timeout_seconds"], 5000, 150, 10000)
class _C:
    budget, harness = _B(), _H()
    graph_dir, embeddings_dir = str(DATA_DIR / "graphs"), str(DATA_DIR / "embeddings")
    enable_sandbox_testing = True

def added_lines(diff):
    return [l[1:].strip() for l in (diff or "").splitlines()
            if l.startswith("+") and not l.startswith("+++") and len(l.strip()) > 40]

leaks, benign = [], 0
for t in SELECTED:
    prompt = build_agent_prompt(task=t, config=_C(), workspace_tree="")
    assert prompt == build_agent_prompt(task=replace(t, patch="SENTINEL", test_patch="SENTINEL"),
                                        config=_C(), workspace_tree=""), "answer keys affect the prompt"
    issue = (t.problem_statement or "") + "\n" + (getattr(t, "hints_text", "") or "")
    for src in ("patch", "test_patch"):
        for l in added_lines(getattr(t, src, "")):
            if l in prompt:
                benign += 1 if l in issue else 0
                if l not in issue:
                    leaks.append((t.instance_id, src, l[:70]))
print("prompt leakage:", "CLEAN" if not leaks else leaks[:3], f"({benign} lines came from the issue text)")
assert not leaks
print("LIMITATION: this is a data-flow check. The subprocess backend runs run_command on the host, so")
print("answer-key files remain reachable; traces must be audited for contamination before trusting a run.")
'''

REPAIR = r'''# ENVIRONMENT REPAIR (evaluation support only - never part of a submission artifact).
#
# swegemma/harness/container_setup.py returns immediately for the subprocess backend in
# install_editable_package (line 512) and install_test_dependencies (line 529). The sandbox venv
# carries _host_env.pth exposing the Kaggle host's dist-packages, which hold RELEASED
# fastapi/rich/requests/httpx, so without this repair the checkout is never imported.
# The real grader runs --sandbox docker where those functions DO execute. This moves the proxy toward
# Docker; it does NOT make it identical (dependency provisioning still differs).
import swegemma.harness.agent_runner as _ar
import swegemma.harness.verification as _vf
import swegemma.harness.container_setup as _cs

REQUIRED_BACKENDS = ["setuptools", "wheel", "editables"]
OPTIONAL_BACKENDS = ["flit_core", "hatchling", "poetry_core", "pdm_backend"]
COMP_WHEELS = str(DATA_DIR / "wheels")
_SUBPROC = {"SubprocessManager", "SubprocessSandbox"}
REPAIR_LOG = []
ACTIVE_RUN = None
ACTIVE_PHASE = "precondition"

# Idempotent: unwrap any previous patch before wrapping, so re-running this cell cannot nest wrappers.
_ORIG_INSTALL = getattr(_cs.install_editable_package, "__wrapped_original__", None) or _cs.install_editable_package


def _pip(docker, cid, pkg):
    """Run pip and KEEP the exit status; no `| tail` swallowing failures."""
    r = docker.exec(cid, "python3 -m pip install --no-index --find-links=/wheels "
                         "--find-links=" + COMP_WHEELS + " --no-build-isolation " + pkg)
    return {"rc": r.exit_code, "out": (r.stdout or ""), "err": (r.stderr or "")}


def patched_install_editable_package(docker, container_id):
    _ORIG_INSTALL(docker, container_id)
    if type(docker).__name__ not in _SUBPROC:
        return
    entry = {"container": str(container_id), "required": {}, "optional": {}, "phase": ACTIVE_PHASE, "run": ACTIVE_RUN}
    for b in REQUIRED_BACKENDS:
        entry["required"][b] = _pip(docker, container_id, b)
    for b in OPTIONAL_BACKENDS:
        entry["optional"][b] = _pip(docker, container_id, b)
    r = docker.exec(container_id, "cd /workspace && python3 -m pip install --no-index "
                                  "--find-links=/wheels --find-links=" + COMP_WHEELS +
                                  " --no-build-isolation --no-deps -e .")
    entry["editable"] = {"rc": r.exit_code, "out": (r.stdout or ""), "err": (r.stderr or "")}
    REPAIR_LOG.append(entry)
    (RESULTS/"setup_observations.json").write_text(json.dumps(REPAIR_LOG,indent=2),encoding="utf-8")
    failed_required = [b for b, v in entry["required"].items() if v["rc"] != 0]
    if failed_required:
        raise RuntimeError(f"required backend install failed: {failed_required}")
    if entry["editable"]["rc"] != 0:
        raise RuntimeError("editable install of /workspace failed rc="
                           + str(entry["editable"]["rc"]) + " :: " + entry["editable"]["err"][-300:])

    # Check imports inside the actual setup path in each agent/grading sandbox.
    pkg = (ACTIVE_RUN or {}).get('package')
    if not pkg:
        raise RuntimeError('Active task package is unavailable during setup')
    rw = docker.exec(container_id, 'cd /workspace && pwd -P')
    ws = (rw.stdout or '').strip()
    entry['workspace_real'] = ws
    for view, prefix in [('agent', ''), ('grading_flags', 'PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 ')]:
        suffix = '-s ' if view == 'grading_flags' else ''
        cmd = ('cd /workspace && ' + prefix + 'python3 ' + suffix + '-c "import ' + pkg +
               ' as m,sys; from pathlib import Path; print(Path(m.__file__).resolve()); print(sys.executable)"')
        result = docker.exec(container_id, cmd)
        lines = (result.stdout or '').strip().splitlines()
        entry[view] = {'rc': result.exit_code, 'path': lines[0] if lines else '',
                       'executable': lines[1] if len(lines)>1 else '', 'stderr': result.stderr}
    entry['provenance_ok'] = rw.exit_code == 0 and all(
        entry[v]['rc'] == 0 and under(entry[v]['path'], ws) for v in ('agent','grading_flags'))
    # Persist even a failing observation before raising; this is not an in-pytest hook.
    (RESULTS/'setup_observations.json').write_text(json.dumps(REPAIR_LOG,indent=2),encoding='utf-8')
    if not entry['provenance_ok']:
        raise RuntimeError('Actual sandbox import is outside its checkout: ' + json.dumps(entry))


patched_install_editable_package.__wrapped_original__ = _ORIG_INSTALL
for _m in (_ar, _vf, _cs):
    _m.install_editable_package = patched_install_editable_package
assert _ar.install_editable_package is _vf.install_editable_package is _cs.install_editable_package
print("repair bound on agent_runner, verification, container_setup (idempotent)")
print("NOTE: a pip success message alone is not proof; the preconditions below check what actually loads.")
'''

PRECOND = r'''# PRECONDITION for EVERY selected task, using the patched setup path. CPU work only.
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import (
    extract_snapshot, install_test_dependencies, setup_baseline_commit,
    setup_container_wheels, setup_git_exclude, setup_workspace_test_config,
)
from swegemma.config import EvalConfig
from adk_submission import ModelRegistry

async def _precondition(task):
    global ACTIVE_RUN, ACTIVE_PHASE
    ACTIVE_RUN = {"task": task.instance_id, "candidate": None, "package": pkg_of(task)}
    ACTIVE_PHASE = "precondition"
    mgr = SubprocessManager(timeout_seconds=600)
    sid = await sandbox_start(mgr)
    out = {"task": task.instance_id}
    try:
        cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots",
                         results_dir=RESULTS / "precondition", submission_dir=WORKING_DIR,
                         models=ModelRegistry(), sandbox="subprocess", timeout_seconds=600,
                         display_mode="quiet")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(_cs.install_editable_package, mgr, sid)   # the patched one
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "baseline")
        pkg = pkg_of(task)
        rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
        out["ws"] = (rw.stdout or "").strip()
        ra = await sandbox_exec(mgr, sid,
                                'cd /workspace && python3 -c "import ' + pkg + ' as m,sys; '
                                'print(m.__file__); print(sys.executable)"')
        lines = (ra.stdout or "").strip().splitlines()
        out["agent_file"] = lines[0] if ra.exit_code == 0 and lines else ""
        out["agent_exe"] = lines[1] if ra.exit_code == 0 and len(lines) > 1 else ""
        rp = await sandbox_exec(mgr, sid, "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 "
                                          'python3 -s -c "import ' + pkg + ' as m,sys; '
                                          'print(m.__file__); print(sys.executable)"')
        lines = (rp.stdout or "").strip().splitlines()
        out["grading_file"] = lines[0] if rp.exit_code == 0 and lines else ""
        out["grading_exe"] = lines[1] if rp.exit_code == 0 and len(lines) > 1 else ""
    finally:
        await sandbox_stop(mgr, sid)
        ACTIVE_RUN = None
    return out

PRECONDITIONS = []
for _t in SELECTED:
    _pc = run_sync(lambda _t=_t: _precondition(_t))
    ok = under(_pc.get("agent_file", ""), _pc.get("ws", "")) and \
         under(_pc.get("grading_file", ""), _pc.get("ws", ""))
    _pc["ok"] = ok
    PRECONDITIONS.append(_pc)
    print(f"{_pc['task']:16s} ok={ok}")
    print(f"    workspace: {_pc.get('ws','')}")
    print(f"    agent    : {_pc.get('agent_file','') or '<import failed>'}")
    print(f"    grading  : {_pc.get('grading_file','') or '<import failed>'}")
(RESULTS / "preconditions.json").write_text(json.dumps(PRECONDITIONS, indent=2), encoding="utf-8")
bad = [p["task"] for p in PRECONDITIONS if not p["ok"]]
assert not bad, f"preconditions failed for {bad}; do not start the model"
print("ALL PRECONDITIONS PASSED")
print("Caveat: passing here does not guarantee the same resolution inside every later sandbox; the")
print("per-run setup observations verify imports again in the actual sandboxes. These are grading-flags probes, not direct in-pytest observations.")
'''

CANDS = r'''# Candidates A and B, embedded as frozen zips.
import base64, hashlib, io, shutil, zipfile
BUNDLES = __BUNDLES__
CAND_ROOT = WORKING_DIR / "candidates"
assert CAND_ROOT.resolve().parent == WORKING_DIR.resolve(), 'Candidate cleanup must stay under working directory'
shutil.rmtree(CAND_ROOT, ignore_errors=True); CAND_ROOT.mkdir(parents=True)

def materialise(name, b64, want):
    payload = base64.b64decode(b64, validate=True)
    got = hashlib.sha256(payload).hexdigest()
    assert got == want, f"{name}: {got} != {want}"
    d = CAND_ROOT / name
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None and "agent.yaml" in z.namelist()
        z.extractall(d)
    return d

CAND_DIRS = {n: materialise(n, b["b64"], b["sha256"]) for n, b in BUNDLES.items()}
from adk_submission import validate_directory
from swegemma.config import build_submission_limits
from swegemma.models.discovery import validate_single_declared_model
LIMITS, GEN_CONSTRAINTS = build_submission_limits()
for n, d in CAND_DIRS.items():
    validate_directory(d, LIMITS)
    print(f"{n}: sha256={BUNDLES[n]['sha256'][:16]} model={validate_single_declared_model(d)}")
a = (CAND_DIRS["A"] / "configs" / "sampling.yaml").read_bytes()
b = (CAND_DIRS["B"] / "configs" / "sampling.yaml").read_bytes()
import difflib
delta = [l for l in difflib.unified_diff(a.decode().splitlines(), b.decode().splitlines(), lineterm="")
         if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
print("A vs B sampling delta:", delta)
assert delta == ["-  include_thoughts: false", "+  include_thoughts: true"], delta
others = {p.relative_to(CAND_DIRS["A"]).as_posix() for p in CAND_DIRS["A"].rglob("*") if p.is_file()}
other_b = {p.relative_to(CAND_DIRS['B']).as_posix() for p in CAND_DIRS['B'].rglob('*') if p.is_file()}
assert others == other_b, 'A/B file sets differ'
assert a.replace(b'include_thoughts: false', b'include_thoughts: true') == b, 'Unexpected sampling bytes'
for rel in others:
    if rel == "configs/sampling.yaml":
        continue
    assert (CAND_DIRS["A"] / rel).read_bytes() == (CAND_DIRS["B"] / rel).read_bytes(), rel
print("every other file is byte-identical between A and B")
'''

RUN = r'''# Evaluator imports these functions by name: instrument its bindings, preserving signatures.
import functools, inspect, time, traceback
import swegemma.evaluate as _ev
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig

PHASE = {}

def instrument_phase(fn, label):
    original = getattr(fn, '__pilot_original__', fn)
    @functools.wraps(original)
    async def wrapped(*a, **k):
        global ACTIVE_PHASE
        previous = ACTIVE_PHASE
        ACTIVE_PHASE = label
        started = time.perf_counter()
        context = k.get('context')
        try:
            return await original(*a, **k)
        finally:
            PHASE.setdefault(label + '_phase_s', []).append(time.perf_counter() - started)
            if label == 'agent' and context is not None and getattr(context, 'agent_start_time', None) is not None:
                PHASE.setdefault('agent_loop_s', []).append(context.agent_elapsed_seconds)
            ACTIVE_PHASE = previous
    wrapped.__pilot_original__ = original
    return wrapped

_ev.run_agent_sandbox = _ar.run_agent_sandbox = instrument_phase(_ev.run_agent_sandbox, 'agent')
_ev.verify_task = _vf.verify_task = instrument_phase(_ev.verify_task, 'grading')

ORDER = [(tid, cand) for i, tid in enumerate(TASK_IDS)
         for cand in (('A', 'B') if i % 2 == 0 else ('B', 'A'))]
RUNS = []
print('planned run order:', ORDER)
try:
    if not DISPATCH_CONFIRM:
        print('DISPATCH_CONFIRM=False: no server was started and no model run is dispatched.')
    else:
        for tid, cand in ORDER:
            # Admission limit, not a guarantee that in-flight OS processes stop at this deadline.
            if elapsed_min() + RUN_RESERVE_MIN > SESSION_CAP_MIN:
                print('Insufficient session allowance for another run; preserving partial artifacts.')
                break
            out = RESULTS / f'{cand}__{tid}'
            if out.exists() and any(out.iterdir()):
                raise RuntimeError(f'Existing results at {out}; refusing to mix runs')
            out.mkdir(parents=True, exist_ok=True)
            PHASE.clear()
            ACTIVE_RUN = {'task': tid, 'candidate': cand, 'package': pkg_of(ALL_BY_ID[tid])}
            first_repair = len(REPAIR_LOG)
            cfg = EvalConfig(
                tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR/'snapshots', results_dir=out,
                submission_dir=CAND_DIRS[cand], models=models, sandbox='subprocess',
                graph_dir=str(DATA_DIR/'graphs'), embeddings_dir=str(DATA_DIR/'embeddings'),
                task_ids=[tid], limits=LIMITS, generation_constraints=GEN_CONSTRAINTS,
                adapter_manifest=adapters, concurrency=1, display_mode='quiet',
                context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
                events_compaction_config=EventsCompactionConfig(
                    compaction_interval=15, overlap_size=2, token_threshold=32768, event_retention_size=5),
                **BUDGET)
            started = time.perf_counter()
            err = None
            try:
                run_sync(_ev.Evaluator(cfg).run)
            except Exception:
                err = traceback.format_exc()
                print(err[-1200:])
            finally:
                wall = time.perf_counter() - started
                repairs = REPAIR_LOG[first_repair:]
                # Per-phase provenance is three-valued. A phase that never ran is NOT a failure:
                # in pilot v1 candidate B raised before grading started, so the grading probe never
                # executed, and treating that absence as a provenance failure stopped two unrelated runs.
                seen = {r.get('phase'): bool(r.get('provenance_ok')) for r in repairs}
                phase_status = {ph: ('passed' if seen.get(ph) else
                                     'failed' if ph in seen else 'not_attempted')
                                for ph in ('agent', 'grading')}
                provenance_failed = any(v == 'failed' for v in phase_status.values())
                # A candidate-only model error (context window, malformed request) is a RESULT.
                candidate_error = bool(err) and any(k in (err or '') for k in (
                    'ContextWindowExceededError', 'BadRequestError', 'InvalidRequestError'))
                environment_error = bool(err) and not candidate_error
                RUNS.append(dict(task=tid, candidate=cand, dir=str(out), wall_s=round(wall,3),
                    agent_phase_s=list(PHASE.get('agent_phase_s', [])),
                    grading_phase_s=list(PHASE.get('grading_phase_s', [])),
                    agent_loop_s=list(PHASE.get('agent_loop_s', [])),
                    setup_provenance=repairs,
                    phase_status=phase_status,
                    provenance_failed=provenance_failed,
                    candidate_error=candidate_error,
                    environment_error=environment_error,
                    both_setup_imports_verified=all(v == 'passed' for v in phase_status.values()),
                    error=err, elapsed_min_at_start=elapsed_min()-wall/60))
                (RESULTS/'runs.json').write_text(json.dumps(RUNS,indent=2),encoding='utf-8')
                ACTIVE_RUN = None
            print(cand, tid, 'wall_s=', round(wall,3), 'phase_s=', PHASE)
            last = RUNS[-1]
            print('  phase status:', last['phase_status'])
            if last['provenance_failed'] or last['environment_error']:
                print('Stopping further dispatch: genuine environment/provenance failure.')
                break
            if last['candidate_error']:
                # Candidate-only failure. Continue ONLY if the server is still healthy and the next
                # run will get a clean sandbox; otherwise stop. Never continue blindly.
                healthy = False
                try:
                    import urllib.request
                    with urllib.request.urlopen(server_instance.base_url.rstrip('/') + '/models',
                                                timeout=20) as resp:
                        healthy = resp.status == 200
                except Exception as probe_err:
                    print('  model-server probe failed:', repr(probe_err)[:160])
                leftovers = sorted(Path('/tmp').glob('swegemma_sandbox_*'))
                print('  server healthy:', healthy, '| leftover sandboxes:', len(leftovers))
                if not healthy:
                    print('Stopping further dispatch: candidate error and the model server is not healthy.')
                    break
                print('Continuing: candidate-only error, server healthy, next run gets a fresh sandbox.')
finally:
    if server_instance is not None:
        server_instance.stop()
        SERVER_STOPPED = True
'''

REPORT = r'''# Result packet: per-run failure attribution derived from structured traces.
# Anything not observable is reported as "unavailable", never as 0.
import csv, json, re
from pathlib import Path

UNAVAILABLE = "unavailable"

def load_trace(d, tid):
    p = d / "traces" / ("trace_" + tid.replace("/", "__") + ".json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

TRACE_STAT_KEYS = ("tool_calls", "edit_calls", "shell_edit_hints",
                   "repeated_identical_cmds", "tool_errors",
                   "first_source_edit_attempt_step", "finish_reasons",
                   "prompt_tokens", "completion_tokens",
                   "successful_tool_calls", "rejected_tool_calls",
                   "acknowledged_source_edit_calls", "tmp_scratch_writes",
                   "repeated_identical_tool_calls", "unparsed_tool_call_texts",
                   "tool_use_flags")

# Scratch reproduction files. The system prompt tells the agent to keep them in /tmp, and
# write_file/edit_file refuse /tmp, so they arrive as shell heredocs. Counting them as source edits
# made compare kernel version 2 credit candidate A with 54 "shell-edit workarounds" on a run that
# touched no repository file at all.
_SCRATCH_DIRS = ("/tmp/", "/var/tmp/", "/dev/")
_SCRATCH_NAMES = {"repro.py", "repro2.py", "debug.py", "scratch.py", "test_repro.py", "check.py"}

_REDIRECT_TARGET = re.compile(r">>?\s*(?P<p>[^\s;|&<>()]+)")
_TEE_TARGET = re.compile(r"\btee\b(?:\s+-\S+)*\s+(?P<p>[^\s;|&<>()]+)")
_INPLACE_EDIT = re.compile(r"(^|[\s;|&])(sed\s+-i|patch\b|python3?\s+-c\s+.{0,40}(write|replace))")
_PY_TOKEN = re.compile(r"[^\s;|&<>()]+\.py\b")

# The tool rejected the call before running it: the arguments never formed a usable request. This
# is the shape seen 42 times in compare kernel version 2, where the payload was split on its own
# content and old_string was lost.
_REJECTION_MARKERS = ("mandatory input parameters are not present",
                      "unknown tool", "no such tool", "unexpected keyword argument",
                      "missing required", "invalid arguments")


def _is_scratch_path(p):
    return p.startswith(_SCRATCH_DIRS) or p.rsplit("/", 1)[-1] in _SCRATCH_NAMES


def shell_write_targets(cmd):
    """(source_targets, scratch_targets) a shell command names as write destinations.

    Only paths ending in .py count, because a repository source edit is what this metric claims to
    measure. `cat > /tmp/repro.py <<EOF` yields a scratch target and no source target.
    """
    cand = [m.group("p") for m in _REDIRECT_TARGET.finditer(cmd)]
    cand += [m.group("p") for m in _TEE_TARGET.finditer(cmd)]
    if _INPLACE_EDIT.search(cmd):
        cand += _PY_TOKEN.findall(cmd)
    src, scratch = [], []
    for p in cand:
        if not p.endswith(".py"):
            continue
        (scratch if _is_scratch_path(p) else src).append(p)
    return src, scratch


def observation_status(step):
    """('ok'|'rejected'|'error'|'none', text) for one step's tool observation.

    swegemma reports tool failures in two different shapes and the previous implementation saw only
    one of them. A rejected call carries a bare {"error": ...} with no `status` key, so counting
    `status == "error"` alone reported 1 error for a run that had 43.
    """
    obs = step.get("observation")
    if not obs:
        return "none", ""
    content = obs.get("content", "")
    parsed = None
    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            parsed = None
    if not isinstance(parsed, dict):
        return ("ok", "") if content else ("none", "")
    text = str(parsed.get("error") or parsed.get("error_message") or "")
    is_error = ("error" in parsed or parsed.get("status") == "error"
                or (isinstance(parsed.get("exit_code"), int) and parsed["exit_code"] != 0))
    if not is_error:
        return "ok", ""
    low = text.lower()
    if any(m in low for m in _REJECTION_MARKERS):
        return "rejected", text
    return "error", text


def trace_stats(tr):
    if tr is None:
        return {k: UNAVAILABLE for k in TRACE_STAT_KEYS}
    cmds, tools, calls, finish = [], [], [], []
    errors = rejected = ok_calls = 0
    edit_calls = shell_edits = scratch_writes = ack_edits = unparsed_texts = 0
    first_edit = None
    for step in tr.get("steps", []):
        status, _text = observation_status(step)
        if status == "rejected":
            rejected += 1
            errors += 1
        elif status == "error":
            errors += 1
        elif status == "ok":
            ok_calls += 1
        step_calls = step.get("tool_calls") or []
        for tc in step_calls:
            fn = tc.get("function_name", "")
            tools.append(fn)
            args = tc.get("arguments") or {}
            calls.append(json.dumps([fn, args], sort_keys=True, default=str))
            if fn in ("edit_file", "write_file"):
                edit_calls += 1
                fp = str(args.get("filepath", ""))
                if fp.endswith(".py") and not _is_scratch_path(fp):
                    if first_edit is None:
                        first_edit = step.get("step_id")
                    # The tool accepted the call. Whether the file's bytes changed is NOT
                    # measured here: no before/after comparison is made anywhere in this trace.
                    if status == "ok":
                        ack_edits += 1
            if fn == "run_command":
                c = str(args.get("command", ""))
                cmds.append(c)
                src, scratch = shell_write_targets(c)
                if scratch:
                    scratch_writes += 1
                if src:
                    shell_edits += 1
                    if first_edit is None:
                        first_edit = step.get("step_id")
                    if status == "ok":
                        ack_edits += 1
        # An agent turn that produced text but no parsed tool call, where the text still looks like
        # an attempted call. This is how candidate B's run ended in compare kernel version 2.
        if not step_calls and step.get("source") == "agent":
            msg = str(step.get("message") or "")
            if "tool_call" in msg or "tool_code" in msg:
                unparsed_texts += 1
        fr = step.get("finish_reason") or (step.get("extra") or {}).get("finish_reason")
        if fr:
            finish.append(str(fr))
    rep = sum(1 for i in range(1, len(cmds)) if cmds[i] == cmds[i - 1])
    rep_tools = sum(1 for i in range(1, len(calls)) if calls[i] == calls[i - 1])
    fm = tr.get("final_metrics") or {}
    return {"tool_calls": len(tools), "edit_calls": edit_calls, "shell_edit_hints": shell_edits,
            "repeated_identical_cmds": rep, "tool_errors": errors,
            "successful_tool_calls": ok_calls, "rejected_tool_calls": rejected,
            "acknowledged_source_edit_calls": ack_edits, "tmp_scratch_writes": scratch_writes,
            "repeated_identical_tool_calls": rep_tools,
            "unparsed_tool_call_texts": unparsed_texts,
            # DESCRIPTIVE flags, not a diagnosis. Each names an observed pattern in the trace.
            # "rejected_calls" and "unparsed_text" together are a symptom of tool-use trouble; they
            # are NOT evidence of any particular root cause, encoding or otherwise.
            "tool_use_flags": ";".join(f for f, on in (
                ("rejected_calls", rejected > 0),
                ("unparsed_text", unparsed_texts > 0),
                ("identical_repeats", rep_tools > 0),
                ("no_acknowledged_source_edit", ack_edits == 0),
            ) if on) or "none",
            "first_source_edit_attempt_step": first_edit if first_edit is not None else UNAVAILABLE,
            "finish_reasons": ";".join(sorted(set(finish))) or UNAVAILABLE,
            "prompt_tokens": fm.get("total_prompt_tokens", UNAVAILABLE),
            "completion_tokens": fm.get("total_completion_tokens", UNAVAILABLE)}

def patch_shape(patch):
    """What the diff actually contains, per diff block. A shell edit and an edit_file edit are
    indistinguishable here, which is the point: absence of edit_file is not absence of a fix."""
    files, new_files = [], set()
    is_new = False
    for line in (patch or "").splitlines():
        if line.startswith("diff --git"):
            is_new = False
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("--- ") and line.strip().endswith("/dev/null"):
            is_new = True
        elif line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path != "/dev/null":
                files.append(path)
                if is_new:
                    new_files.add(path)
    modifies_existing = any(f not in new_files for f in files)
    adds_nested = any(f in new_files and "/" in f for f in files)
    return {"patch_files": files, "patch_new_files": sorted(new_files),
            "patch_modifies_existing": modifies_existing,
            "patch_touches_source": any(Path(f).name not in {"repro.py", "debug.py"} for f in files)}

def attribute(row, patch, tr_stats, shape):
    if row.get("resolved"):
        return "passed"
    err = (row.get("error") or "")
    # Distinguish "the agent never submitted" from "a patch was produced and was empty". Both leave
    # no grade, and neither is a graded loss.
    if "completed execution without calling submit_patch" in err.lower():
        return "no_submission"
    if not patch.strip():
        return "empty_patch"
    if not shape["patch_touches_source"]:
        return "suspected_scratch_only_patch"
    if "Failed to apply" in err:
        return "patch_apply_failed"
    if "timeout" in err.lower() or "exceeded session" in err.lower():
        return "budget_time"
    if "turns budget" in err.lower() or "tool call budget" in err.lower():
        return "budget_turns_or_tools"
    return "tests_failed"

rows = []
for r in (RUNS if "RUNS" in dir() else []):
    d = Path(r["dir"]); tid = r["task"]
    jf = d / "task_results.jsonl"
    raw = [json.loads(l) for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()] if jf.exists() else []
    assert len(raw) <= 1, f'Duplicate results in {jf}'
    rec = raw[0] if raw else {}
    assert not rec or rec.get('instance_id') == tid, f'Wrong task result in {jf}' 
    safe = tid.replace("/", "__")
    pf = d / "patches" / (safe + ".patch")
    patch = pf.read_text(encoding="utf-8") if pf.exists() else ""
    tf = d / "test_outputs" / (safe + ".log")
    tests = tf.read_text(encoding="utf-8") if tf.exists() else ""
    ts = trace_stats(load_trace(d, tid))
    artifact_ok = not rec or len(patch) == rec.get('agent_patch_size')
    if rec and not artifact_ok:
        raise AssertionError(f'Patch artifact missing/mismatched for {tid}')
    shape = patch_shape(patch)
    agent_s = sum(r["agent_phase_s"]) if r["agent_phase_s"] else UNAVAILABLE
    grade_s = sum(r["grading_phase_s"]) if r["grading_phase_s"] else UNAVAILABLE
    setup_plus_agent = agent_s
    rows.append({
        "candidate": r["candidate"], "task": tid,
        "resolved": rec.get("resolved", UNAVAILABLE),
        "attribution": attribute(rec, patch, ts, shape) if rec else "run_error",
        "harness_error": (rec.get("error") or "")[:120] or UNAVAILABLE,
        "test_exit_code": rec.get("test_exit_code", UNAVAILABLE),
        "grading_ran": bool(tests.strip()) and isinstance(rec.get("test_exit_code"), int) and rec["test_exit_code"] >= 0 if rec else UNAVAILABLE,
        "patch_bytes": len(patch.encode("utf-8")),
        "patch_touches_source": shape["patch_touches_source"],
        "patch_files": ";".join(shape["patch_files"]) or UNAVAILABLE,
        "wall_s": r["wall_s"], "agent_phase_s": setup_plus_agent, "grading_phase_s": grade_s,
        "both_setup_imports_verified": r.get('both_setup_imports_verified', UNAVAILABLE),
        "phase_status": json.dumps(r.get('phase_status', UNAVAILABLE)),
        "failure_class": ("environment" if r.get('environment_error') else
                          "provenance" if r.get('provenance_failed') else
                          "candidate" if r.get('candidate_error') else "none"),
        "agent_loop_s": sum(r.get('agent_loop_s', [])) if r.get('agent_loop_s') else UNAVAILABLE,
        "termination_error": rec.get('error') or UNAVAILABLE,
        "duration_seconds_harness": rec.get("duration_seconds", UNAVAILABLE),
        **ts, "run_error": (r.get("error") or "")[:120] or "",
    })

if rows:
    with (WORKING_DIR / "pilot_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(json.dumps(r))
    print("")
    print("%-10s %-16s %-9s %-22s %s" % ("cand", "task", "resolved", "attribution", "agent_s"))
    for r in rows:
        print("%-10s %-16s %-9s %-22s %s" % (r["candidate"], r["task"], r["resolved"],
                                             r["attribution"], r["agent_phase_s"]))
    print("")
    print("A two-task pilot establishes that the experiment executes. It does NOT establish which")
    print("candidate is better. agent_phase_s covers container-A setup plus the agent loop;")
    print("grading_phase_s is container B. The harness duration_seconds bundles both and must not be")
    print("multiplied to project the 12-hour scoring runtime.")
else:
    print("no runs executed (DISPATCH_CONFIRM was False)")

MANIFEST = {
    "candidates": {n: b["sha256"] for n, b in BUNDLES.items()},
    "candidate_dirs": {n: str(d) for n, d in CAND_DIRS.items()},
    "tasks": TASK_IDS, "control_evidence": CONTROL_EVIDENCE,
    "expected_task_hashes": EXPECTED_TASK_HASHES,
    "preconditions": PRECONDITIONS if "PRECONDITIONS" in dir() else UNAVAILABLE,
    "budgets": BUDGET, "seed_in_sampling": 42,
    "package_versions": VERSIONS, "model_config_sha256": MODEL_CONFIG_SHA,
    "model_path": str(MODEL_PATH), "quantization": QUANT,
    "gpus": {"count": N_GPU, "names": GPU_NAMES},
    "run_order": ORDER if "ORDER" in dir() else UNAVAILABLE,
    "repair_log": REPAIR_LOG,
    "session_cap_min": SESSION_CAP_MIN,
    "session_cap_kind": "admission limit; no hard kill of in-flight processes",
    "run_reserve_min": RUN_RESERVE_MIN,
    "server_stopped": SERVER_STOPPED,
    "setup_observation_note": "Fresh import probes with agent and grading flags; not direct in-pytest instrumentation",
    "task_content_hashes": {t.instance_id: hashlib.sha256(json.dumps({k:getattr(t,k,None) for k in
        ('repo','base_commit','problem_statement','hints_text','patch','test_patch')},sort_keys=True).encode()).hexdigest() for t in SELECTED},
    "notes": ["thinking_budget is NOT forwarded to the server; only enable_thinking is",
              "subprocess backend is not a filesystem isolation boundary",
              "repair is evaluation support only and is not part of any submission artifact"],
}
(WORKING_DIR / "pilot_manifest.json").write_text(json.dumps(MANIFEST, indent=2, default=str), encoding="utf-8")
print("saved pilot_manifest.json and pilot_results.csv")
'''


def main() -> None:
    bundles = {}
    for name, src in CANDIDATES.items():
        if not src.is_dir():
            raise SystemExit(f"missing {src}")
        b64, sha = bundle(src)
        bundles[name] = {"b64": b64, "sha256": sha}
        print(f"candidate {name}: {src.name} sha256={sha}")
    ev = control_evidence()
    local_tasks = {t['instance_id']: t for t in
        [json.loads(l) for l in (ROOT/'reference/tasks.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]}
    task_hashes = {tid: hashlib.sha256(json.dumps({k:local_tasks[tid].get(k) for k in
        ('repo','base_commit','problem_statement','hints_text','patch','test_patch')},sort_keys=True).encode()).hexdigest()
        for tid in PILOT_TASKS}
    for t in PILOT_TASKS:
        if t not in ev:
            raise SystemExit(f"missing control evidence for {t}")

    cells = [
        ("markdown", MD),
        ("code", CFG),
        ("code", INSTALL),
        ("code", VERIFY),
        ("code", COMMON),
        ("code", TASKS.replace("__TASKS__", json.dumps(PILOT_TASKS)).replace("__EVIDENCE__", repr(ev)).replace("__TASK_HASHES__", json.dumps(task_hashes))),
        ("code", LEAK),
        ("code", CANDS.replace("__BUNDLES__", json.dumps(bundles))),
        ("code", REPAIR),
        ("code", PRECOND),
        ("code", SERVER),
        ("code", RUN),
        ("code", REPORT),
    ]
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
    (OUT / "pilot.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-pilot", "code_file": "pilot.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [],
        "model_sources": ["google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2"],
        "machine_shape": "NvidiaL4",
    }, indent=2), encoding="utf-8")
    print("wrote", OUT)


SERVER = r'''# vLLM with the grader's serving settings. Started only after preconditions pass.
import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
litellm.drop_params = True
TARGET_MODEL_NAME = "gemma-4-31b-it-qat-w4a16-ct"
tp_size = 4 if N_GPU >= 4 else (2 if N_GPU >= 2 else 1)
adapters = discover_adapters(str(CAND_DIRS["A"]), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
print("adapters discovered:", getattr(adapters, "adapters", {}) or "none (expected)")
server_instance = None
models = None
SERVER_STARTUP_S = None
SERVER_STOPPED = False
if not DISPATCH_CONFIRM:
    print('Dispatch disabled: vLLM is not instantiated or started.')
else:
    assert N_GPU == 4 and all('L4' in n for n in GPU_NAMES), 'Pilot requires 4x L4'
    assert elapsed_min() + 20 + RUN_RESERVE_MIN <= SESSION_CAP_MIN, 'Insufficient allowance for startup and one run'
    for tid in TASK_IDS:
        for cand in ('A','B'):
            target = RESULTS / f'{cand}__{tid}'
            if target.exists() and any(target.iterdir()):
                raise RuntimeError(f'Existing artifacts: {target}')
    try:
        SERVER_T0 = time.time()
        vllm_cfg = VllmConfig(
            model=str(MODEL_PATH), port=8000, host="127.0.0.1",
            tool_call_parser="gemma4", reasoning_parser="gemma4",
            default_chat_template_kwargs={"enable_thinking": True},
            max_model_len=32768,
            dtype="bfloat16" if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else "auto",
            gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
            enable_lora=True, max_loras=8, max_lora_rank=128,
            tensor_parallel_size=tp_size, startup_timeout=60 * 20)
        server_instance = VllmServer(vllm_cfg, adapter_manifest=adapters)
        server_instance.start()
        SERVER_STARTUP_S = time.time() - SERVER_T0
        print(f"vLLM up at {server_instance.base_url} (tp={tp_size}) in {SERVER_STARTUP_S/60:.1f} min")
        print("NOTE: the server default enable_thinking=True is overridden per-request by each candidate's")
        print("extra_body.chat_template_kwargs, which is what makes A and B differ.")
        models = server_instance.create_model_registry(
            aliases=[TARGET_MODEL_NAME], model_prefix="openai/", api_key="EMPTY")

    except BaseException:
        if server_instance is not None:
            server_instance.stop()
            SERVER_STOPPED = True
        raise
'''

if __name__ == "__main__":
    main()
