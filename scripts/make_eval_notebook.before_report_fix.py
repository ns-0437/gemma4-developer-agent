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


MD_INTRO = """# Gemma 4 SWE agent — offline paired evaluation

Runs the **real** `swegemma` harness and the **real** `gemma-4-31b-it-qat-w4a16-ct` weights over frozen
candidate bundles, so prompt changes can be compared without spending a daily submission.

**Modes** (set in the config cell):
- `smoke` *(default)* — 1 task, 1 candidate. Proves tools, patch extraction, grading and traces work.
- `paired` — the same N tasks for every candidate. Requires `FULL_RUN_CONFIRM = True`.
- `thinking` — `v2_reviewed` with `enable_thinking` off vs on. Requires `FULL_RUN_CONFIRM = True`.

Reference fixes (`patch`) and grading tests (`test_patch`) are never shown to the agent: the harness builds
the agent prompt from `problem_statement`/`hints_text` only, and applies `test_patch` in a separate container
afterwards. Cell 4 asserts this instead of assuming it.
"""

CFG = '''# ============================ CONFIG ============================
MODE = "smoke"              # "smoke" | "paired" | "thinking"
FULL_RUN_CONFIRM = False    # must be True for "paired"/"thinking" — guards GPU quota

N_TASKS = 14                # paired/thinking task count (stratified across repos)
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
# so results would not be comparable to the leaderboard.
if MODE != "smoke" and REQUIRE_4_GPUS:
    assert n_gpu >= 4, f"paired/thinking needs the 4x L4 accelerator (found {n_gpu}). Set it in notebook settings."
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

# Stratified, deterministic, evenly spaced within each repo (covers easy and hard localisation).
QUOTA = {"fastapi/fastapi": 6, "Textualize/rich": 5, "psf/requests": 2, "encode/httpx": 1}
def pick(n_total):
    out = []
    for repo, quota in QUOTA.items():
        pool = by_repo.get(repo, [])
        k = min(quota, len(pool))
        if k:
            step = max(1, len(pool) // k)
            out += [pool[min(i * step, len(pool) - 1)] for i in range(k)]
    seen, uniq = set(), []
    for t in out:
        if t.instance_id not in seen:
            seen.add(t.instance_id); uniq.append(t)
    return uniq[:n_total]

# Smoke: one small-snapshot (~37 MB) task with a 3-line reference fix, so a *pass* is plausible and
# the resolved=True path gets exercised, not just the failure path.
SMOKE_TASK_ID = "requests_6589"
if MODE == "smoke":
    SELECTED = [t for t in all_tasks if t.instance_id == SMOKE_TASK_ID] or pick(1)
else:
    SELECTED = pick(N_TASKS)

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

LEAK = '''# Leakage check: build the exact prompt the harness would send and assert the answer is not in it.
from swegemma.harness.agent_runner import build_agent_prompt

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
print("  harness builds prompts from problem_statement/hints only; test_patch is applied in container B")

# Caveat worth remembering when reading the scores below: some public problem statements are PR
# descriptions that name the fix (e.g. fastapi_14794 says which function to change), so local pass
# rates can flatter an agent relative to terser hidden-set issues.
pr_style = [t.instance_id for t in SELECTED
            if any(k in (t.problem_statement or "")[:400] for k in ("## Summary", "## Changes", "Fixes #"))]
print("PR-description-style statements in this subset:", pr_style or "none")
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

RESULTS_ROOT = WORKING_DIR / "results"
TASK_IDS = [t.instance_id for t in SELECTED]
runtimes = {}

for name, agent_dir in CANDIDATE_DIRS.items():
    out = RESULTS_ROOT / name
    if (out / "summary.json").exists():
        print(f"== {name}: already has results, skipping (delete {out} to redo)"); continue
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
'''

REPORT = '''# Per-task table, failure taxonomy, and the paired comparison.
import json, re
import pandas as pd
from pathlib import Path

def load(name):
    f = RESULTS_ROOT / name / "task_results.jsonl"
    if not f.exists():
        return pd.DataFrame()
    rows = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        tid = r.get("task_id") or r.get("instance_id")
        log = RESULTS_ROOT / name / "logs" / f"{str(tid).replace('/', '_')}.log"
        txt = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
        patch = r.get("agent_patch") or ""
        err = (r.get("error_message") or "")
        if r.get("resolved"):
            cause = "passed"
        elif not patch.strip():
            cause = "empty_patch"
        elif "timeout" in err.lower() or "exceeded session" in err.lower():
            cause = "budget_time"
        elif "tool call budget" in err.lower() or "turns budget" in err.lower():
            cause = "budget_calls"
        elif "Failed to apply agent_patch" in err:
            cause = "patch_apply_failed"
        else:
            cause = "tests_failed"
        rows.append({
            "candidate": name, "task": tid, "resolved": bool(r.get("resolved")),
            "cause": cause, "minutes": round(float(r.get("duration_seconds") or 0) / 60, 1),
            "tool_calls": r.get("tool_calls"), "patch_bytes": len(patch),
            "test_exit": r.get("test_exit_code"),
            "truncations": len(re.findall(r"reached the token limit", txt)),
            "tool_errors": len(re.findall(r'"status":\\s*"error"', txt)),
            "error": err[:90],
        })
    return pd.DataFrame(rows)

if MODE == "smoke":
    # Review point 2: prove every stage ran, independently of whether the task was solved.
    name = next(iter(CANDIDATE_DIRS)); out = RESULTS_ROOT / name
    rows = [json.loads(l) for l in (out / "task_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows, "no task result written"
    r = rows[0]
    checks = {
        "task_results.jsonl": True,
        "summary.json": (out / "summary.json").exists(),
        "trace saved": any((out / "traces").glob("*.json")) if (out / "traces").exists() else False,
        "agent log saved": any((out / "logs").glob("*.log")) if (out / "logs").exists() else False,
        "tools executed": (r.get("tool_calls") or 0) > 0,
        "patch extracted": len(r.get("agent_patch") or "") > 0,
        "phase 2 grading ran": r.get("test_exit_code") is not None and bool(r.get("test_output")),
    }
    for k, v in checks.items():
        print(f"  [{'ok ' if v else 'FAIL'}] {k}")
    print(f"\\n  resolved={r.get('resolved')}  status={r.get('status')}  error={(r.get('error_message') or '')[:120]}")
    print("  (a smoke FAIL on the task is acceptable; a FAIL on any stage above is not)")
    if not (out / "patches").exists() or not any((out / "patches").glob("*.patch")):
        print("  note: patches/ empty — expected only if the agent produced no diff at all")
    assert all(v for k, v in checks.items() if k != "patch extracted"), "pipeline stage failed; fix before paired run"

frames = [load(n) for n in CANDIDATE_DIRS]
df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
if df.empty:
    print("no results yet")
else:
    pd.set_option("display.width", 200, "display.max_colwidth", 60)
    display(df.sort_values(["task", "candidate"]))
    print("\\nresolution rate per candidate:")
    display(df.groupby("candidate").agg(
        solved=("resolved", "sum"), n=("resolved", "size"), rate=("resolved", "mean"),
        med_min=("minutes", "median"), max_min=("minutes", "max"),
        empty_patches=("patch_bytes", lambda s: int((s == 0).sum())),
        truncations=("truncations", "sum"), tool_errors=("tool_errors", "sum")).round(3))
    print("\\nfailure causes:")
    display(df.pivot_table(index="cause", columns="candidate", values="task", aggfunc="count", fill_value=0))
    names = list(df.candidate.unique())
    if len(names) == 2:
        a, b = names
        piv = df.pivot_table(index="task", columns="candidate", values="resolved", aggfunc="first")
        both = int((piv[a] & piv[b]).sum()); neither = int((~piv[a] & ~piv[b]).sum())
        only_a = int((piv[a] & ~piv[b]).sum()); only_b = int((~piv[a] & piv[b]).sum())
        print(f"\\nPAIRED {a} vs {b}:  both={both}  neither={neither}  {a}-only={only_a}  {b}-only={only_b}")
        print(f"Discordant pairs = {only_a + only_b}. With so few tasks this is directional, not significant;")
        print("inspect every discordant task's log before concluding anything.")
        if only_a or only_b:
            display(piv[piv[a] != piv[b]])
    tot = sum(runtimes.values()) / 60 if runtimes else 0
    print(f"\\ntotal wall clock this session: {tot:.1f} min")
    if not df.empty:
        per = df.groupby("candidate").minutes.mean().mean()
        print(f"mean {per:.1f} min/task -> ~{per * 120 / 60:.1f} h for 120 tasks (12 h cap; excludes grading).")
    df.to_csv(WORKING_DIR / "eval_results.csv", index=False)
    print("saved /kaggle/working/eval_results.csv")
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
