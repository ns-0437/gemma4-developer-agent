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


def control_evidence() -> dict:
    """Summarise the saved repaired-control evidence for the pilot tasks."""
    if not EVIDENCE.exists():
        return {}
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
                "failed": [x["name"] for x in cases if x["outcome"] == "failed"],
                "errored": [x["name"] for x in cases if x["outcome"] == "errored"],
            }
        out[tid] = rec
    return out


MD = """# Thinking A/B pilot — four runs, two tasks

| candidate | source | effective difference |
| --- | --- | --- |
| **A** | frozen `releases/pilot_A` (= `v2_reviewed`, unchanged) | `enable_thinking: false` |
| **B** | `releases/pilot_B` | `enable_thinking: true` — **only** `include_thoughts` differs (1 line, 1 byte) |

Everything else is byte-identical: prompts, tools, temperature, top_p, top_k, seed,
max_output_tokens, adapters (none), budgets.

Tasks: `requests_7309`, `rich_3471` — the two with directly measured repaired controls
(baseline fails, gold passes, agent **and** grading importing the checkout).

Four runs, order alternated per task (A→B, then B→A) so a shared-server ordering effect cannot be
mistaken for a candidate effect. This pilot establishes that the experiment executes and produces
usable evidence. **It cannot establish which candidate is better** — two tasks is not a comparison.

`thinking_budget: 4096` is **not** forwarded to the server (verified: only
`extra_body.chat_template_kwargs.enable_thinking` is). Do not describe it as an enforced limit.
"""

CFG = r'''# ============================ CONFIG ============================
DISPATCH_CONFIRM = False     # must be True to run the pilot; guards GPU quota
SESSION_CAP_MIN  = 150       # hard stop: no NEW run starts past this; worst case = cap + one run

# Identical for A and B. Not tuned per variant.
BUDGET = dict(max_time_minutes=10.0, max_tool_calls=100, max_turns=60, timeout_seconds=300)
# ================================================================
import json, os, sys, time
from pathlib import Path
T0 = time.time()
def elapsed_min():
    return (time.time() - T0) / 60.0
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
    return bool(path) and (path.startswith("/workspace/") or (bool(ws) and path.startswith(ws)))

print("loaded", len(all_tasks), "tasks")
'''

TASKS = r'''# Task manifest + the saved control evidence these tasks were selected on.
TASK_IDS = __TASKS__
CONTROL_EVIDENCE = __EVIDENCE__

missing = [t for t in TASK_IDS if t not in ALL_BY_ID]
assert not missing, f"unknown task ids: {missing}"
SELECTED = [ALL_BY_ID[t] for t in TASK_IDS]

print("PILOT TASKS and the evidence they were chosen on:")
for tid in TASK_IDS:
    ev = CONTROL_EVIDENCE.get(tid)
    print("\n ", tid, ALL_BY_ID[tid].repo)
    if not ev:
        print("    NO SAVED CONTROL EVIDENCE - do not use this task")
        continue
    for phase in ("negative", "positive"):
        e = ev.get(phase, {})
        print(f"    {phase:9s} exit={e.get('pytest_exit')} cases={e.get('n_cases')} "
              f"failed={len(e.get('failed', []))} errored={len(e.get('errored', []))}")
        print(f"              agent  import: {e.get('agent_pkg_file','')}")
        print(f"              pytest import: {e.get('pytest_pkg_file','')}")
    neg, pos = ev.get("negative", {}), ev.get("positive", {})
    ws = neg.get("workspace_real", "")
    ok = (neg.get("pytest_exit") == 1 and pos.get("pytest_exit") == 0
          and not neg.get("errored") and not pos.get("errored")
          and under(neg.get("agent_pkg_file", ""), ws) and under(neg.get("pytest_pkg_file", ""), ws))
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

# Idempotent: unwrap any previous patch before wrapping, so re-running this cell cannot nest wrappers.
_ORIG_INSTALL = getattr(_cs.install_editable_package, "__wrapped_original__", None) or _cs.install_editable_package


def _pip(docker, cid, pkg):
    """Run pip and KEEP the exit status; no `| tail` swallowing failures."""
    r = docker.exec(cid, "python3 -m pip install --no-index --find-links=/wheels "
                         "--find-links=" + COMP_WHEELS + " --no-build-isolation " + pkg)
    return {"rc": r.exit_code, "out": (r.stdout or "")[-1500:], "err": (r.stderr or "")[-1500:]}


def patched_install_editable_package(docker, container_id):
    _ORIG_INSTALL(docker, container_id)
    if type(docker).__name__ not in _SUBPROC:
        return
    entry = {"container": str(container_id)[:28], "required": {}, "optional": {}}
    for b in REQUIRED_BACKENDS:
        entry["required"][b] = _pip(docker, container_id, b)
    for b in OPTIONAL_BACKENDS:
        entry["optional"][b] = _pip(docker, container_id, b)
    r = docker.exec(container_id, "cd /workspace && python3 -m pip install --no-index "
                                  "--find-links=/wheels --find-links=" + COMP_WHEELS +
                                  " --no-build-isolation --no-deps -e .")
    entry["editable"] = {"rc": r.exit_code, "out": (r.stdout or "")[-1500:], "err": (r.stderr or "")[-1500:]}
    REPAIR_LOG.append(entry)
    failed_required = [b for b, v in entry["required"].items() if v["rc"] != 0]
    if failed_required:
        raise RuntimeError(f"required backend install failed: {failed_required}")
    if entry["editable"]["rc"] != 0:
        raise RuntimeError("editable install of /workspace failed rc="
                           + str(entry["editable"]["rc"]) + " :: " + entry["editable"]["err"][-300:])


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
assert not bad, f"preconditions failed for {bad}; do not spend GPU time"
print("ALL PRECONDITIONS PASSED")
print("Caveat: passing here does not guarantee the same resolution inside every later sandbox; the")
print("per-run manifest records the imports actually observed during each run.")
'''

CANDS = r'''# Candidates A and B, embedded as frozen zips.
import base64, hashlib, io, shutil, zipfile
BUNDLES = __BUNDLES__
CAND_ROOT = WORKING_DIR / "candidates"
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
for rel in others:
    if rel == "configs/sampling.yaml":
        continue
    assert (CAND_DIRS["A"] / rel).read_bytes() == (CAND_DIRS["B"] / rel).read_bytes(), rel
print("every other file is byte-identical between A and B")
'''

RUN = r'''# FOUR RUNS: 2 tasks x {A,B}, order alternated per task. Phase timings recorded separately.
import time, traceback
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator

# Phase instrumentation: duration_seconds bundles setup+agent+grading, so wrap the two phase entry
# points. run_agent_sandbox = container A setup + agent loop; verify_task = grading (container B).
PHASE = {}
_orig_run_agent = _ar.run_agent_sandbox
_orig_verify = _vf.verify_task

async def _timed_agent(*a, **k):
    t = time.time()
    try:
        return await _orig_run_agent(*a, **k)
    finally:
        PHASE.setdefault("agent_phase_s", []).append(time.time() - t)

async def _timed_verify(*a, **k):
    t = time.time()
    try:
        return await _orig_verify(*a, **k)
    finally:
        PHASE.setdefault("grading_phase_s", []).append(time.time() - t)

if getattr(_ar.run_agent_sandbox, "__name__", "") != "_timed_agent":
    _ar.run_agent_sandbox = _timed_agent
if getattr(_vf.verify_task, "__name__", "") != "_timed_verify":
    _vf.verify_task = _timed_verify

# alternate order per task so a shared-server ordering effect cannot masquerade as a candidate effect
ORDER = []
for i, tid in enumerate(TASK_IDS):
    ORDER += [(tid, "A"), (tid, "B")] if i % 2 == 0 else [(tid, "B"), (tid, "A")]
print("planned run order:", ORDER)

RUNS = []
if not DISPATCH_CONFIRM:
    print("DISPATCH_CONFIRM is False - stopping before the four runs.")
else:
    for tid, cand in ORDER:
        if elapsed_min() > SESSION_CAP_MIN:
            print(f"session cap {SESSION_CAP_MIN} min reached; stopping with partial artifacts")
            break
        out = RESULTS / f"{cand}__{tid}"
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f"existing results at {out}; use a fresh directory")
        out.mkdir(parents=True, exist_ok=True)
        PHASE.clear()
        cfg = EvalConfig(
            tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots", results_dir=out,
            submission_dir=CAND_DIRS[cand], models=models, sandbox="subprocess",
            graph_dir=str(DATA_DIR / "graphs"), embeddings_dir=str(DATA_DIR / "embeddings"),
            task_ids=[tid], limits=LIMITS, generation_constraints=GEN_CONSTRAINTS,
            adapter_manifest=adapters, concurrency=1, display_mode="quiet",
            context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
            events_compaction_config=EventsCompactionConfig(
                compaction_interval=15, overlap_size=2, token_threshold=32768, event_retention_size=5),
            **BUDGET)
        t0 = time.time()
        err = None
        try:
            run_sync(Evaluator(cfg).run)
        except Exception:
            err = traceback.format_exc()[-1200:]
            print(err)
        wall = time.time() - t0
        RUNS.append({"task": tid, "candidate": cand, "dir": str(out), "wall_s": round(wall, 1),
                     "agent_phase_s": PHASE.get("agent_phase_s", []),
                     "grading_phase_s": PHASE.get("grading_phase_s", []),
                     "error": err, "elapsed_min_at_start": round(elapsed_min() - wall / 60, 1)})
        (RESULTS / "runs.json").write_text(json.dumps(RUNS, indent=2), encoding="utf-8")
        print(f"{cand} {tid}: wall={wall/60:.1f} min agent={PHASE.get('agent_phase_s')} "
              f"grading={PHASE.get('grading_phase_s')}", flush=True)
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

def trace_stats(tr):
    if tr is None:
        return {k: UNAVAILABLE for k in ("tool_calls", "edit_calls", "shell_edits",
                                         "repeated_identical_cmds", "tool_errors",
                                         "first_source_edit_step", "finish_reasons",
                                         "prompt_tokens", "completion_tokens")}
    cmds, tools, errors, finish = [], [], 0, []
    edit_calls = shell_edits = 0
    first_edit = None
    SHELL_EDIT = re.compile(r"(^|\s|\|)(sed\s+-i|tee\b|patch\b|python3?\s+-c\s+.{0,40}(write|replace)|>\s*\S+\.py)")
    for step in tr.get("steps", []):
        for tc in step.get("tool_calls") or []:
            fn = tc.get("function_name", "")
            tools.append(fn)
            args = tc.get("arguments") or {}
            if fn in ("edit_file", "write_file"):
                edit_calls += 1
                fp = str(args.get("filepath", ""))
                if first_edit is None and not fp.startswith("/tmp") and fp.endswith(".py"):
                    first_edit = step.get("step_id")
            if fn == "run_command":
                c = str(args.get("command", ""))
                cmds.append(c)
                if SHELL_EDIT.search(c):
                    shell_edits += 1
                    if first_edit is None:
                        first_edit = step.get("step_id")
        obs = (step.get("observation") or {}).get("content", "")
        if isinstance(obs, str) and '"status": "error"' in obs:
            errors += 1
        fr = step.get("finish_reason") or (step.get("extra") or {}).get("finish_reason")
        if fr:
            finish.append(str(fr))
    rep = 0
    for i in range(1, len(cmds)):
        if cmds[i] == cmds[i - 1]:
            rep += 1
    fm = tr.get("final_metrics") or {}
    return {"tool_calls": len(tools), "edit_calls": edit_calls, "shell_edits": shell_edits,
            "repeated_identical_cmds": rep, "tool_errors": errors,
            "first_source_edit_step": first_edit if first_edit is not None else UNAVAILABLE,
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
            "patch_touches_source": bool(modifies_existing or adds_nested)}

def attribute(row, patch, tr_stats, shape):
    if row.get("resolved"):
        return "passed"
    err = (row.get("error") or "")
    if not patch.strip():
        return "empty_patch"
    if not shape["patch_touches_source"]:
        return "scratch_only_patch"
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
    rec = raw[0] if raw else {}
    safe = tid.replace("/", "__")
    pf = d / "patches" / (safe + ".patch")
    patch = pf.read_text(encoding="utf-8") if pf.exists() else ""
    tf = d / "test_outputs" / (safe + ".log")
    tests = tf.read_text(encoding="utf-8") if tf.exists() else ""
    ts = trace_stats(load_trace(d, tid))
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
        "grading_ran": bool(tests.strip()) if tests or rec else UNAVAILABLE,
        "patch_bytes": len(patch.encode("utf-8")),
        "patch_touches_source": shape["patch_touches_source"],
        "patch_files": ";".join(shape["patch_files"]) or UNAVAILABLE,
        "wall_s": r["wall_s"], "agent_phase_s": setup_plus_agent, "grading_phase_s": grade_s,
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
    "preconditions": PRECONDITIONS if "PRECONDITIONS" in dir() else UNAVAILABLE,
    "budgets": BUDGET, "seed_in_sampling": 42,
    "package_versions": VERSIONS, "model_config_sha256": MODEL_CONFIG_SHA,
    "model_path": str(MODEL_PATH), "quantization": QUANT,
    "gpus": {"count": N_GPU, "names": GPU_NAMES},
    "run_order": ORDER if "ORDER" in dir() else UNAVAILABLE,
    "repair_log": REPAIR_LOG,
    "session_cap_min": SESSION_CAP_MIN,
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
    for t in PILOT_TASKS:
        if t not in ev:
            print(f"WARNING: no saved control evidence for {t}")

    cells = [
        ("markdown", MD),
        ("code", CFG),
        ("code", INSTALL),
        ("code", VERIFY),
        ("code", COMMON),
        ("code", TASKS.replace("__TASKS__", json.dumps(PILOT_TASKS)).replace("__EVIDENCE__", json.dumps(ev))),
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
'''

if __name__ == "__main__":
    main()
