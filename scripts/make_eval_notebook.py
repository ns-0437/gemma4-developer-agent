"""Generate notebooks/eval/ — a Kaggle GPU notebook that runs the REAL swegemma harness with the
REAL gemma-4-31b-it-qat-w4a16-ct model over our frozen candidates, for paired offline comparison.

Candidate bundles are embedded as base64 zips (same trick as make_submit_notebook.py) so the notebook
is self-contained and runs with internet disabled.

Usage:
  python scripts/make_eval_notebook.py                     # embeds releases/v2 + releases/v2_reviewed
  python -m kaggle kernels push -p notebooks/eval

The notebook defaults to MODE="smoke" (1 task, 1 candidate). Paired/thinking modes additionally
require FULL_RUN_CONFIRM=True, so an accidental Run-All cannot burn hours of GPU quota.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "eval"
KERNEL_ID = "navin03/gemma4-swe-agent-eval"
TEXT_EXT = {".yaml", ".yml", ".md", ".txt", ".py", ".json"}


def bundle(src: Path) -> tuple[str, str]:
    """Zip a submission dir deterministically; return (base64, sha256)."""
    buf = io.BytesIO()
    files = sorted((p for p in src.rglob("*") if p.is_file()), key=lambda p: p.relative_to(src).as_posix())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            if p.suffix not in TEXT_EXT:
                raise SystemExit(f"non-text file {p}; adapters must ship via a dataset, not the notebook")
            info = zipfile.ZipInfo(p.relative_to(src).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    data = buf.getvalue()
    return base64.b64encode(data).decode("ascii"), hashlib.sha256(data).hexdigest()


MD_INTRO = '''# Gemma 4 SWE agent — offline paired evaluation

Runs the **real** `swegemma` harness and the **real** `gemma-4-31b-it-qat-w4a16-ct` weights over frozen
candidate bundles, so prompt changes can be compared without spending a daily submission.

**Modes** (set in the config cell):
- `smoke` *(default)* — 1 task, 1 candidate. Proves tools, patch extraction, grading and traces work.
- `paired` — the same N tasks for every candidate. Requires `FULL_RUN_CONFIRM = True`.
- `thinking` — `v2_reviewed` with `enable_thinking` off vs on. Requires `FULL_RUN_CONFIRM = True`.

The prompt excludes reference fixes and grading tests; a sentinel check verifies that data flow.
Grading uses a separate workspace. The subprocess backend is NOT a filesystem security boundary: host
answer-key files may remain reachable through shell commands. Audit traces for contamination before
interpreting results. Model identity and matching GPU names alone do not prove full grader equivalence.
'''

CFG = '''# ============================ CONFIG ============================
MODE = "smoke"              # "smoke" | "paired" | "thinking"
FULL_RUN_CONFIRM = False    # must be True for "paired"/"thinking" — guards GPU quota

N_TASKS = 8                 # paired/thinking task count (max = the validated set size)
SEED = 42

# Identical budgets for every candidate. These bound the experiment; they are NOT what we submit
# (submissions ship no eval_config). Per-task runtime is recorded so we can choose budgets later.
BUDGET = dict(max_time_minutes=10.0, max_tool_calls=100, max_turns=60, timeout_seconds=300)
SMOKE_BUDGET = dict(max_time_minutes=8.0, max_tool_calls=60, max_turns=40, timeout_seconds=300)

REQUIRE_4_GPUS = True       # hard-fail paired/thinking if the grader's 4x L4 shape is not present
# ================================================================
import os, json, shutil, subprocess, sys, time
from pathlib import Path

assert MODE in {"smoke", "paired", "thinking"}, MODE
if MODE != "smoke" and not FULL_RUN_CONFIRM:
    raise SystemExit(f"MODE={MODE!r} needs FULL_RUN_CONFIRM=True. Refusing to start a multi-hour run.")
BUDGETS = SMOKE_BUDGET if MODE == "smoke" else BUDGET
print("MODE:", MODE, "| budgets:", BUDGETS)
'''

INSTALL = '''# Install the host wheelhouse (swegemma, adk-submission, adk-eval-core, vllm, ...) — offline.
import glob, importlib, os, subprocess, sys
from pathlib import Path

os.environ.update({
    "LITELLM_LOCAL_MODEL_COST_MAP": "True", "TRANSFORMERS_NO_TF": "1",
    "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": "1",
    "VLLM_ENGINE_READY_TIMEOUT_S": "1200", "VLLM_NO_USAGE_STATS": "1",
    "OTEL_SDK_DISABLED": "true", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
})
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
    tgt = tmp_whl / name
    if not tgt.exists():
        os.symlink(w, tgt)

wheels = sorted(str(w) for w in tmp_whl.glob("*.whl"))
print(f"Installing {len(wheels)} wheels...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--force-reinstall", *wheels], check=True)
importlib.invalidate_caches()
print("done")
'''

VERIFY = '''# Verify this box matches the grader before trusting any comparison.
import importlib.metadata as md, json, torch
from pathlib import Path

DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
MODEL_PATH = Path("/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2")
WORKING_DIR = Path("/kaggle/working"); WORKING_DIR.mkdir(parents=True, exist_ok=True)

n_gpu = torch.cuda.device_count() if torch.cuda.is_available() else 0
names = [torch.cuda.get_device_name(i) for i in range(n_gpu)]
print(f"GPUs: {n_gpu} {names}")
for pkg in ("swegemma", "adk-submission", "adk-eval-core", "google-adk", "vllm", "transformers", "litellm"):
    try:
        print(f"  {pkg:16s} {md.version(pkg)}")
    except Exception as e:
        print(f"  {pkg:16s} MISSING ({e})")

assert MODEL_PATH.exists(), f"attach model google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2 ({MODEL_PATH})"
print("model revision dir:", MODEL_PATH.name, "| files:", len(list(MODEL_PATH.glob('*'))))
cfg = json.loads((MODEL_PATH / "config.json").read_text())
qc = cfg.get("quantization_config") or cfg.get("text_config", {}).get("quantization_config")
print("architectures:", cfg.get("architectures"), "| quantization_config:", json.dumps(qc)[:300])
assert DATA_DIR.exists(), f"attach the competition data ({DATA_DIR})"

# The grader serves on 4x L4 with tensor_parallel_size=4. Fewer GPUs changes throughput and sharding,
# so timing is not directly comparable to the leaderboard.
if MODE != "smoke" and REQUIRE_4_GPUS:
    assert n_gpu == 4 and all("L4" in n for n in names), f"paired/thinking needs the 4x L4 accelerator (found {n_gpu}). Set it in notebook settings."
elif n_gpu < 4:
    print(f"WARNING: {n_gpu} GPU(s), grader uses 4. Fine for a smoke test, not for comparisons.")
'''

CANDIDATES = '''# Materialise frozen candidate bundles (embedded; identical bytes to the submitted/frozen zips).
import base64, hashlib, io, zipfile, shutil
from pathlib import Path

BUNDLES = __BUNDLES__
CAND_ROOT = Path("/kaggle/working/candidates")
shutil.rmtree(CAND_ROOT, ignore_errors=True); CAND_ROOT.mkdir(parents=True)

def materialise(name, b64, want_sha):
    payload = base64.b64decode(b64, validate=True)
    got = hashlib.sha256(payload).hexdigest()
    assert got == want_sha, f"{name}: {got} != {want_sha}"
    d = CAND_ROOT / name
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None and "agent.yaml" in z.namelist()
        z.extractall(d)
    return d

CANDIDATE_DIRS = {n: materialise(n, b["b64"], b["sha256"]) for n, b in BUNDLES.items()}
for n, d in CANDIDATE_DIRS.items():
    print(f"{n:14s} sha256 {BUNDLES[n]['sha256'][:12]}…  {d}")

# thinking variant: v2_reviewed with enable_thinking ON (include_thoughts True).
# NOTE: adk_submission.resolvers.generation maps include_thoughts=False -> chat_template_kwargs
# {"enable_thinking": False}; thinking_budget is never forwarded. So every candidate we have
# submitted so far ran with thinking OFF.
if MODE == "thinking":
    src = CANDIDATE_DIRS["v2_reviewed"]; dst = CAND_ROOT / "v2_reviewed_thinking"
    shutil.copytree(src, dst)
    (dst / "configs" / "sampling.yaml").write_text(
        "temperature: 0.2\\ntop_p: 0.95\\ntop_k: 40\\nmax_output_tokens: 8192\\nseed: 42\\n"
        "thinking_config:\\n  thinking_budget: 4096\\n  include_thoughts: true\\n", encoding="utf-8")
    CANDIDATE_DIRS["v2_reviewed_thinking"] = dst

if MODE == "smoke":
    CANDIDATE_DIRS = {"v2_reviewed": CANDIDATE_DIRS["v2_reviewed"]}
elif MODE == "thinking":
    CANDIDATE_DIRS = {k: v for k, v in CANDIDATE_DIRS.items() if k.startswith("v2_reviewed")}
print("running candidates:", list(CANDIDATE_DIRS))

# Official structural validation of each candidate, with the competition's limits.
from adk_submission import validate_directory
from swegemma.config import build_submission_limits
from swegemma.models.discovery import validate_single_declared_model
LIMITS, GEN_CONSTRAINTS = build_submission_limits()
for n, d in CANDIDATE_DIRS.items():
    validate_directory(d, LIMITS)
    print(f"  {n}: valid, model={validate_single_declared_model(d)}")
'''

TASKS = '''# Task selection + proof that reference fixes and grading tests never reach the agent.
import re
from swegemma.models import load_tasks

TASKS_PATH = DATA_DIR / "tasks.jsonl"
all_tasks = load_tasks(TASKS_PATH)
by_repo = {}
for t in all_tasks:
    by_repo.setdefault(t.repo, []).append(t)
for r in by_repo:
    by_repo[r].sort(key=lambda t: t.instance_id)

# Validated on 2026-09-27 (CPU controls, WITH the environment repair): target tests fail at baseline
# and pass with the gold patch, with agent and grading both importing the checkout.
# requests_7309 was proven separately in the provenance run (5 failures -> 0 with gold); the verdict
# code missed it only because its test_patch edits existing tests instead of adding new ones.
VALIDATED = ["fastapi_11194", "fastapi_14794", "fastapi_15588",
             "rich_2725", "rich_3471", "rich_3676", "rich_3934", "requests_7309"]
# Excluded and why: fastapi_14246/14361/14482 collection interrupted (exit 2);
# requests_6589 target tests ERROR on the httpbin fixture; httpx_3672 import still not in checkout
# (hatchling will not install offline); rich_3105 pending failure review.
def pick(n_total):
    assert 1 <= n_total <= len(VALIDATED), "N_TASKS must be 1..%d" % len(VALIDATED)
    return [ALL_BY_ID[t] for t in VALIDATED[:n_total]]

ALL_BY_ID = {t.instance_id: t for t in all_tasks}
SMOKE_TASK_ID = "rich_3471"
if MODE == "smoke":
    SELECTED = [ALL_BY_ID[SMOKE_TASK_ID]]
else:
    SELECTED = pick(min(N_TASKS, len(VALIDATED)))

def n_files(p):
    return len(re.findall(r"^\\+\\+\\+ b/(\\S+)", p or "", re.M))
def n_lines(p):
    return sum(1 for l in (p or "").splitlines()
               if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
print(f"{len(SELECTED)} task(s):")
for t in SELECTED:
    print(f"  {t.instance_id:22s} {t.repo:18s} ref_fix: {n_files(t.patch)} file(s)/{n_lines(t.patch)} lines"
          f" | problem {len(t.problem_statement)} chars")
'''

LEAK = '''# Prompt data-flow check only. The subprocess backend does not isolate the host filesystem.
from swegemma.harness.agent_runner import build_agent_prompt
from dataclasses import replace

class _B:  # mirrors EvaluationBudget/HarnessLimits shape for prompt construction only
    time_minutes, tool_calls, turns, cost_usd = BUDGETS["max_time_minutes"], BUDGETS["max_tool_calls"], BUDGETS["max_turns"], None
class _H:
    command_timeout_seconds, max_stdout_chars, max_file_lines, max_file_chars = BUDGETS["timeout_seconds"], 5000, 150, 10000
class _C:
    budget, harness = _B(), _H()
    graph_dir, embeddings_dir = str(DATA_DIR / "graphs"), str(DATA_DIR / "embeddings")
    enable_sandbox_testing = True

def added_lines(diff):
    return [l[1:].strip() for l in (diff or "").splitlines()
            if l.startswith("+") and not l.startswith("+++") and len(l.strip()) > 40]

# A real leak = answer-key text in the prompt that the graders did NOT already put in the issue.
# Overlap that also appears in problem_statement/hints is the issue author's own repro snippet,
# which the harness is supposed to pass through.
leaks, benign = [], 0
for t in SELECTED:
    prompt = build_agent_prompt(task=t, config=_C(), workspace_tree="")
    changed = replace(t, patch="SENTINEL_REFERENCE_PATCH", test_patch="SENTINEL_TEST_PATCH")
    assert prompt == build_agent_prompt(task=changed, config=_C(), workspace_tree=""), "Answer keys affect prompt"
    issue_text = (t.problem_statement or "") + "\\n" + (getattr(t, "hints_text", "") or "")
    for src in ("patch", "test_patch"):
        for l in added_lines(getattr(t, src, "")):
            if l in prompt:
                if l in issue_text:
                    benign += 1
                else:
                    leaks.append((t.instance_id, src, l[:80]))
print("prompt leakage check:", "CLEAN" if not leaks else f"LEAK {leaks[:5]}")
print(f"  ({benign} overlapping line(s) came from the issue text itself — expected, not a leak)")
assert not leaks, "answer-key text reached the prompt from somewhere other than the issue text"
print("  harness builds prompts from problem_statement/hints only; test_patch is applied in a separate grading workspace")

# Caveat worth remembering when reading the scores below: some public problem statements are PR
# descriptions that name the fix (e.g. fastapi_14794 says which function to change), so local pass
# rates can flatter an agent relative to terser hidden-set issues.
pr_style = [t.instance_id for t in SELECTED
            if any(k in (t.problem_statement or "")[:400] for k in ("## Summary", "## Changes", "Fixes #"))]
print("PR-description-style statements in this subset:", pr_style or "none")

print("LIMITATION: run_command uses host subprocesses; answer-key files remain potentially reachable. Prompt invariance is not an isolation guarantee.")
'''

REPAIR = r'''# ENVIRONMENT REPAIR + PRECONDITION. Runs BEFORE vLLM starts, so a broken environment costs no GPU.
#
# Why this is needed: swegemma/harness/container_setup.py returns immediately for the subprocess
# backend in BOTH install_editable_package (line 512) and install_test_dependencies (line 529).
# So in subprocess mode the checkout is never installed; the sandbox venv carries a `_host_env.pth`
# that exposes the Kaggle host's /usr/local/lib/python3.12/dist-packages, which hold RELEASED
# fastapi/rich/requests/httpx. Under PYTHONSAFEPATH=1 pytest does not add cwd, so the released copy
# wins and both the agent's reproduction and the grading can exercise the wrong code.
# The real grader runs --sandbox docker, where both functions do execute, so this repair moves the
# subprocess proxy TOWARD the grader rather than away from it.
import swegemma.harness.agent_runner as _ar
import swegemma.harness.verification as _vf
import swegemma.harness.container_setup as _cs

BACKENDS = ["setuptools", "wheel", "editables", "flit_core", "hatchling", "poetry_core", "pdm_backend"]
COMP_WHEELS = str(DATA_DIR / "wheels")
_SUBPROC = {"SubprocessManager", "SubprocessSandbox"}
_orig_install_editable = _cs.install_editable_package
REPAIR_LOG = []


def patched_install_editable_package(docker, container_id):
    """Original behaviour, plus a real editable install when running on the subprocess backend."""
    _orig_install_editable(docker, container_id)
    if type(docker).__name__ not in _SUBPROC:
        return  # docker backend already did it
    entry = {"container": str(container_id)[:24], "backends": {}}
    # One package per call: pip aborts the whole command if a single name is unresolvable, and the
    # sandbox stages only 41 of the competition's 124 wheels (editables/poetry_core are missing there).
    for b in BACKENDS:
        r = docker.exec(container_id, "python3 -m pip install --no-index --find-links=/wheels "
                                      "--find-links=" + COMP_WHEELS + " --no-build-isolation " + b +
                                      " 2>&1 | tail -1")
        entry["backends"][b] = (r.stdout or "").strip()[-80:]
    r = docker.exec(container_id, "cd /workspace && python3 -m pip install --no-index "
                                  "--find-links=/wheels --find-links=" + COMP_WHEELS +
                                  " --no-build-isolation --no-deps -e . 2>&1 | tail -2")
    entry["editable"] = (r.stdout or "").strip()[-200:]
    REPAIR_LOG.append(entry)


# Each module binds the name at import time, so patch all three:
#   agent_runner  -> Container A, the agent's own environment
#   verification  -> Container B, grading
#   container_setup -> its internal call site
for _m in (_ar, _vf, _cs):
    _m.install_editable_package = patched_install_editable_package
print("repair installed on:", [m.__name__ for m in (_ar, _vf, _cs)])

# ---- PRECONDITION: prove the repair works before any GPU time is spent ----
import asyncio
from swegemma.sandbox import SubprocessManager, sandbox_exec, sandbox_start, sandbox_stop
from swegemma.harness.container_setup import (
    extract_snapshot, install_test_dependencies, setup_baseline_commit,
    setup_container_wheels, setup_git_exclude, setup_workspace_test_config,
)
from swegemma.config import EvalConfig
from adk_submission import ModelRegistry

PKG = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich",
       "psf/requests": "requests", "encode/httpx": "httpx"}


async def _precondition(task):
    mgr = SubprocessManager(timeout_seconds=600)
    sid = await sandbox_start(mgr)
    out = {}
    try:
        cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots",
                         results_dir=WORKING_DIR / "precondition", submission_dir=WORKING_DIR,
                         models=ModelRegistry(), sandbox="subprocess", timeout_seconds=600,
                         display_mode="quiet")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, DATA_DIR / "snapshots" / (task.instance_id + ".tgz"))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(patched_install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "baseline")
        pkg = PKG.get(task.repo, task.repo.split("/")[-1])
        rw = await sandbox_exec(mgr, sid, "cd /workspace && pwd -P")
        out["ws"] = (rw.stdout or "").strip()
        # agent's view: plain python3, as run_command uses
        ra = await sandbox_exec(mgr, sid, 'cd /workspace && python3 -c "import ' + pkg +
                                          ' as m; print(m.__file__)"')
        out["agent"] = (ra.stdout or "").strip().splitlines()[-1] if ra.exit_code == 0 else ""
        # grading's view: the flags the harness uses for pytest (no cwd on sys.path)
        rp = await sandbox_exec(mgr, sid, "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 "
                                          'python3 -s -c "import ' + pkg + ' as m; print(m.__file__)"')
        out["pytest_like"] = (rp.stdout or "").strip().splitlines()[-1] if rp.exit_code == 0 else ""
    finally:
        await sandbox_stop(mgr, sid)
    return out


_t = ALL[TASK_IDS[0]]
_pc = run_sync(lambda: _precondition(_t))
_ws = _pc.get("ws", "")
_ok = lambda p: bool(p) and (p.startswith("/workspace/") or (_ws and p.startswith(_ws)))
print("precondition on", _t.instance_id)
print("  workspace :", _ws)
print("  agent     :", _pc.get("agent", "") or "<import failed>")
print("  pytest-like:", _pc.get("pytest_like", "") or "<import failed>")
if REPAIR_LOG:
    print("  editable  :", (REPAIR_LOG[-1].get("editable") or "").replace(chr(10), " ")[-120:])
assert _ok(_pc.get("agent", "")), "agent-side import is NOT the checkout; fix before spending GPU"
assert _ok(_pc.get("pytest_like", "")), "grading-side import is NOT the checkout; fix before spending GPU"
print("PRECONDITION PASSED - both sides resolve to the checkout")
'''

SERVER = '''# Start vLLM with the grader's serving settings.
import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
litellm.drop_params = True

TARGET_MODEL_NAME = "gemma-4-31b-it-qat-w4a16-ct"
n_gpu = torch.cuda.device_count()
tp_size = 4 if n_gpu >= 4 else (2 if n_gpu >= 2 else 1)

# No candidate ships adapters (LoRA is broken on the pinned vLLM 0.19.1 — discussion 743508).
adapters = discover_adapters(str(next(iter(CANDIDATE_DIRS.values()))), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)

vllm_cfg = VllmConfig(
    model=str(MODEL_PATH), port=8000, host="127.0.0.1",
    tool_call_parser="gemma4", reasoning_parser="gemma4",
    default_chat_template_kwargs={"enable_thinking": True},
    max_model_len=32768,
    dtype="bfloat16" if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else "auto",
    gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
    enable_lora=True, max_loras=8, max_lora_rank=128,
    tensor_parallel_size=tp_size, startup_timeout=60 * 20,
)
server_instance = VllmServer(vllm_cfg, adapter_manifest=adapters)
server_instance.start()
print(f"vLLM up at {server_instance.base_url} (tp={tp_size})")
models = server_instance.create_model_registry(
    aliases=[TARGET_MODEL_NAME], model_prefix="openai/", api_key="EMPTY")
'''

RUN = '''# Run each candidate over the SAME tasks with the SAME budgets. Results land incrementally
# in results/<candidate>/task_results.jsonl (+ summary.json, patches/, traces/, logs/).
import asyncio, concurrent.futures, time, traceback
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator

def run_sync(fn):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(fn())).result()
    return asyncio.run(fn())

RESULTS_ROOT = WORKING_DIR / "results" / MODE
TASK_IDS = [t.instance_id for t in SELECTED]
runtimes = {}

try:
    for name, agent_dir in CANDIDATE_DIRS.items():
        out = RESULTS_ROOT / name
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f"Existing results at {out}. Preserve them and choose a fresh output directory; partial or stale results must not be silently reused.")
        out.mkdir(parents=True, exist_ok=True)
        print(f"\\n===== {name} — {len(TASK_IDS)} task(s) =====", flush=True)
        cfg = EvalConfig(
            tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots", results_dir=out,
            submission_dir=agent_dir, models=models, sandbox="subprocess",
            graph_dir=str(DATA_DIR / "graphs"), embeddings_dir=str(DATA_DIR / "embeddings"),
            task_ids=TASK_IDS, limits=LIMITS, generation_constraints=GEN_CONSTRAINTS,
            adapter_manifest=adapters, concurrency=1, display_mode="quiet",
            context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
            events_compaction_config=EventsCompactionConfig(
                compaction_interval=15, overlap_size=2, token_threshold=32768, event_retention_size=5),
            **BUDGETS,
        )
        t0 = time.time()
        try:
            res = run_sync(Evaluator(cfg).run)
            print(f"{name}: resolution_rate={getattr(res, 'resolution_rate', '?')}")
        except Exception:
            traceback.print_exc()
            print(f"{name}: RUN FAILED — partial results kept in {out}")
        runtimes[name] = time.time() - t0
        print(f"{name}: wall clock {runtimes[name]/60:.1f} min", flush=True)

finally:
    server_instance.stop()
'''

REPORT = '''# Read the actual swegemma JSONL schema plus its separate patch and test artifacts.
import csv, json, re
from collections import Counter
from pathlib import Path

def read_candidate(results_root, name):
    out = results_root / name
    file = out / 'task_results.jsonl'
    rows = []
    if not file.exists():
        return rows
    seen = set()
    for line in file.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        tid = r['instance_id']
        if tid in seen:
            raise ValueError(f'Duplicate result for {name}/{tid}; do not silently combine reruns')
        seen.add(tid)
        safe = tid.replace('/', '__')
        patch_path = out / 'patches' / f'{safe}.patch'
        test_path = out / 'test_outputs' / f'{safe}.log'
        log_path = out / 'logs' / (tid.replace('/', '_') + '.log')
        patch = patch_path.read_text(encoding='utf-8') if patch_path.exists() else ''
        tests = test_path.read_text(encoding='utf-8') if test_path.exists() else ''
        log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
        error = r.get('error') or ''
        reported_size = r.get('agent_patch_size', 0)
        artifact_ok = len(patch) == reported_size
        exit_code = r.get('test_exit_code')
        grading_ran = exit_code is not None and exit_code >= 0 and bool(tests.strip())
        if not artifact_ok:
            cause = 'artifact_missing_or_mismatched'
        elif r.get('resolved'):
            cause = 'passed'
        elif 'Failed to apply' in error:
            cause = 'patch_apply_failed'
        elif 'timeout' in error.lower() or 'exceeded session' in error.lower():
            cause = 'budget_time'
        elif 'budget' in error.lower():
            cause = 'budget_exhausted'
        elif not grading_ran:
            cause = 'pipeline_error'
        elif not patch:
            cause = 'empty_patch'
        else:
            cause = 'tests_failed'
        rows.append(dict(candidate=name, task=tid, resolved=bool(r.get('resolved')),
            cause=cause, total_minutes=round(float(r.get('duration_seconds') or 0)/60, 3),
            tool_calls=r.get('tool_calls', 0), patch_bytes=len(patch.encode('utf-8')),
            artifact_ok=artifact_ok, test_exit=exit_code, grading_ran=grading_ran,
            trace_saved=(out/'traces'/f'trace_{safe}.json').exists(),
            log_saved=log_path.exists(),
            truncation_mentions=len(re.findall(r'reached the token limit', log)),
            tool_error_mentions=len(re.findall(r'"status":\\s*"error"', log)), error=error))
    return rows

def paired_counts(rows, names):
    a, b = names
    by_name = {n: {r['task']: r['resolved'] for r in rows if r['candidate'] == n} for n in names}
    common = sorted(by_name[a].keys() & by_name[b].keys())
    counts = Counter((by_name[a][t], by_name[b][t]) for t in common)
    return dict(both=counts[True, True], neither=counts[False, False],
                only_a=counts[True, False], only_b=counts[False, True],
                missing_a=sorted(by_name[b].keys()-by_name[a].keys()),
                missing_b=sorted(by_name[a].keys()-by_name[b].keys()))

rows = [r for n in CANDIDATE_DIRS for r in read_candidate(RESULTS_ROOT, n)]
if rows:
    with (WORKING_DIR / 'eval_results.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
for name in CANDIDATE_DIRS:
    subset = [r for r in rows if r['candidate'] == name]
    expected = set(TASK_IDS)
    actual = {r['task'] for r in subset}
    print(name, 'solved', sum(r['resolved'] for r in subset), '/', len(subset),
          'missing', sorted(expected-actual), 'unexpected', sorted(actual-expected))
    print('failure categories:', dict(Counter(r['cause'] for r in subset)))
    for r in subset:
        print(json.dumps(r))
if len(CANDIDATE_DIRS) == 2:
    print('PAIRED (completed common tasks only):', paired_counts(rows, list(CANDIDATE_DIRS)))
print('total_minutes includes setup, agent execution AND grading; it is not an inference-time projection.')
print('Log mention counts are diagnostics, not authoritative event counts.')
print('Prompt checks do not establish filesystem isolation for the subprocess backend.')
if MODE == 'smoke':
    assert len(rows) == 1 and rows[0]['task'] == TASK_IDS[0], 'Expected exactly the smoke task result'
    r = rows[0]
    checks = dict(summary=(RESULTS_ROOT/r['candidate']/'summary.json').exists(),
        trace=r['trace_saved'], agent_log=r['log_saved'], tools=r['tool_calls'] > 0,
        patch_artifact_consistent=r['artifact_ok'], phase_2=r['grading_ran'])
    print('SMOKE STAGES:', checks, 'resolved=', r['resolved'], 'patch_bytes=', r['patch_bytes'])
    assert all(checks.values()), 'Pipeline stage failed; inspect saved results before a paired run'
    if r['patch_bytes'] == 0:
        print('EMPTY PATCH: pipeline reached grading, but nonempty patch extraction/apply remains unproven.')
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="*", default=["v2", "v2_reviewed"])
    a = ap.parse_args()

    bundles = {}
    for name in a.candidates:
        src = ROOT / "releases" / name
        if not src.is_dir():
            raise SystemExit(f"missing {src}")
        b64, sha = bundle(src)
        bundles[name] = {"b64": b64, "sha256": sha}
        print(f"embedded {name}: sha256 {sha}")

    cells = [
        ("markdown", MD_INTRO),
        ("code", CFG),
        ("code", INSTALL),
        ("code", VERIFY),
        ("code", CANDIDATES.replace("__BUNDLES__", json.dumps(bundles))),
        ("code", TASKS),
        ("code", LEAK),
        ("code", REPAIR),
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
    (OUT / "eval.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL_ID, "title": "gemma4-swe-agent-eval", "code_file": "eval.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [],
        "model_sources": ["google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2"],
        "machine_shape": "NvidiaL4",
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
