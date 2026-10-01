"""Executable tests for notebooks/pilot/pilot.ipynb.

These EXECUTE the generated cells in fresh namespaces, in notebook order, with dependency-injected
stubs for the expensive/host-specific parts (pip, torch, vLLM, the swegemma sandbox and Evaluator).
Syntax parsing is explicitly not enough: the previous generator parsed cleanly and still raised
NameError on a real run because the repair cell used names defined only in a later cell.

WHAT THIS IS NOT: a real Kaggle execution. No model is served, no sandbox is created, no task is
solved. It proves cell ordering, failure handling, idempotency and the report schema — nothing about
agent quality.

Run:  python scripts/test_pilot_notebook.py
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
import types
from pathlib import Path

# Windows test hosts cannot create symlinks without elevation; the INSTALL cell symlinks wheels.
# Copy instead. This is a limitation of THIS TEST HOST, not of the notebook.
_REAL_SYMLINK = os.symlink
import subprocess as _subprocess
_REAL_RUN = _subprocess.run
def _symlink_or_copy(src, dst, **kw):
    try:
        _REAL_SYMLINK(src, dst, **kw)
    except (OSError, NotImplementedError):
        shutil.copyfile(src, dst)
os.symlink = _symlink_or_copy

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "pilot" / "pilot.ipynb"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- fixtures
@dataclasses.dataclass
class FakeTask:
    instance_id: str
    repo: str
    base_commit: str = "deadbeef"
    problem_statement: str = "super_len should count bytes for str input."
    hints_text: str = ""
    patch: str = "--- a/src/requests/utils.py\n+++ b/src/requests/utils.py\n+        o = o.encode('utf-8')\n"
    test_patch: str = "--- a/tests/test_utils.py\n+++ b/tests/test_utils.py\n+def test_super_len_str():\n+    assert True\n"


class FakeExec:
    def __init__(self, stdout="", exit_code=0, stderr=""):
        self.stdout, self.exit_code, self.stderr = stdout, exit_code, stderr


def make_env(tmp: Path, *, pip_rc=0, required_backend_rc=0, editable_rc=0,
             grading_import_in_checkout=True):
    """Build a temp Kaggle-like tree and install stub modules. Returns (data_dir, working_dir)."""
    data = tmp / "input" / "competitions" / "gemma-4-developer-agent"
    (data / "snapshots").mkdir(parents=True, exist_ok=True)
    (data / "wheels").mkdir(parents=True, exist_ok=True)
    (data / "graphs").mkdir(exist_ok=True)
    (data / "embeddings").mkdir(exist_ok=True)
    tasks = [FakeTask("requests_7309", "psf/requests"), FakeTask("rich_3471", "Textualize/rich")]
    (data / "tasks.jsonl").write_text("\n".join(json.dumps(dataclasses.asdict(t)) for t in tasks),
                                      encoding="utf-8")
    for t in tasks:
        (data / "snapshots" / f"{t.instance_id}.tgz").write_bytes(b"x")
    model = tmp / "input" / "models" / "google" / "gemma-4" / "other" / "gemma-4-31b-it-qat-w4a16-ct" / "2"
    model.mkdir(parents=True, exist_ok=True)
    (model / "config.json").write_text(json.dumps(
        {"architectures": ["Gemma4ForConditionalGeneration"],
         "quantization_config": {"format": "pack-quantized", "num_bits": 4}}), encoding="utf-8")
    working = tmp / "working"
    working.mkdir(parents=True, exist_ok=True)
    wheelhouse = tmp / "input" / "datasets" / "metric" / "gemma-4-developer-agent-wheelhouse"
    wheelhouse.mkdir(parents=True, exist_ok=True)
    (wheelhouse / "swegemma-0.2.7-py3-none-any.whl").write_bytes(b"x")

    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    # patch only subprocess.run on the REAL module; replacing the module breaks other imports
    import subprocess as _sp
    _sp.run = lambda *a, **k: types.SimpleNamespace(returncode=pip_rc, stdout="", stderr="boom")
    mod("torch", cuda=types.SimpleNamespace(
        is_available=lambda: True, device_count=lambda: 4,
        get_device_name=lambda i: "NVIDIA L4", is_bf16_supported=lambda: True))
    mod("litellm", drop_params=False)

    mod("swegemma")
    mod("swegemma.models", load_tasks=lambda p: tasks)
    mod("swegemma.models.discovery", validate_single_declared_model=lambda d: "gemma-4-31b-it-qat-w4a16-ct")
    mod("swegemma.config",
        EvalConfig=lambda **k: types.SimpleNamespace(**k),
        build_submission_limits=lambda: (object(), object()),
        ALLOWED_ADAPTER_EXTENSIONS=frozenset({".safetensors"}))

    ws = "/tmp/sbx_test/workspace"

    async def sandbox_exec(mgr, sid, cmd):
        if "pwd -P" in cmd:
            return FakeExec(ws)
        if "PYTHONSAFEPATH" in cmd:
            p = f"{ws}/requests/__init__.py" if grading_import_in_checkout \
                else "/usr/local/lib/python3.12/dist-packages/requests/__init__.py"
            return FakeExec(p + "\n/venv/bin/python3")
        if "import" in cmd:
            return FakeExec(f"{ws}/requests/__init__.py\n/venv/bin/python3")
        return FakeExec("")

    async def noop_async(*a, **k):
        return None

    class SubprocessManager:  # name matters: the repair branches on type name
        def __init__(self, *a, **k):
            pass

        def exec(self, cid, cmd):
            if "pip install" in cmd and "-e ." in cmd:
                return FakeExec("ok", editable_rc, "editable boom")
            if "pip install" in cmd:
                is_req = any(b in cmd for b in ("setuptools", "wheel", "editables"))
                return FakeExec("ok", required_backend_rc if is_req else 1, "backend boom")
            return FakeExec("ok")

    mod("swegemma.sandbox", SubprocessManager=SubprocessManager, sandbox_exec=sandbox_exec,
        sandbox_start=noop_async, sandbox_stop=noop_async)
    mod("swegemma.harness")
    mod("swegemma.harness.container_setup",
        install_editable_package=lambda d, c: None,
        extract_snapshot=lambda *a, **k: None, install_test_dependencies=lambda *a, **k: None,
        setup_baseline_commit=lambda *a, **k: None, setup_container_wheels=lambda *a, **k: None,
        setup_git_exclude=lambda *a, **k: None, setup_workspace_test_config=lambda *a, **k: None)
    mod("swegemma.harness.agent_runner",
        build_agent_prompt=lambda task, config, workspace_tree="": "ISSUE:\n" + task.problem_statement,
        run_agent_sandbox=noop_async, install_editable_package=lambda d, c: None)
    mod("swegemma.harness.verification", verify_task=noop_async,
        install_editable_package=lambda d, c: None)
    mod("swegemma.evaluate", Evaluator=lambda cfg: types.SimpleNamespace(run=noop_async))
    mod("adk_submission", validate_directory=lambda d, l: None, ModelRegistry=lambda: {},
        VllmConfig=lambda **k: types.SimpleNamespace(**k),
        VllmServer=lambda cfg, adapter_manifest=None: types.SimpleNamespace(
            start=lambda: None, base_url="http://127.0.0.1:8000/v1",
            create_model_registry=lambda **k: {}),
        discover_adapters=lambda d, adapter_extensions=None: types.SimpleNamespace(adapters={}))
    mod("google"); mod("google.adk"); mod("google.adk.agents"); mod("google.adk.apps")
    mod("google.adk.agents.context_cache_config", ContextCacheConfig=lambda **k: None)
    mod("google.adk.apps._configs", EventsCompactionConfig=lambda **k: None)
    return data, working, model, wheelhouse


def cells():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    return [("".join(c["source"])) for c in nb["cells"] if c["cell_type"] == "code"]


def rewrite(src, data, working, model, wheelhouse):
    """Only the absolute Kaggle roots are redirected; all other logic runs unmodified."""
    return (src
            .replace("/kaggle/input/competitions/gemma-4-developer-agent", data.as_posix())
            .replace("/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2", model.as_posix())
            .replace("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse", wheelhouse.as_posix())
            .replace("/kaggle/working", working.as_posix()))


def run_cells(tmp, upto=None, ns=None, **envkw):
    data, working, model, wh = make_env(tmp, **envkw)
    ns = ns if ns is not None else {"__name__": "__main__"}
    src_cells = cells()[:upto]
    for i, c in enumerate(src_cells):
        exec(compile(rewrite(c, data, working, model, wh), f"<cell {i+1}>", "exec"), ns)
    return ns


# ---------------------------------------------------------------- tests
def test_ordered_execution(tmp):
    print("\n[T1] all cells execute in notebook order (DISPATCH_CONFIRM=False)")
    try:
        ns = run_cells(tmp / "t1")
        check("no NameError / ordering is valid", True)
        check("TASK_IDS defined before use", ns.get("TASK_IDS") == ["requests_7309", "rich_3471"])
        check("run_sync available to the repair cell", callable(ns.get("run_sync")))
        check("preconditions ran for every task", len(ns.get("PRECONDITIONS", [])) == 2,
              str(ns.get("PRECONDITIONS")))
        check("ORDER alternates per task",
              ns.get("ORDER") == [("requests_7309", "A"), ("requests_7309", "B"),
                                  ("rich_3471", "B"), ("rich_3471", "A")], str(ns.get("ORDER")))
        check("no runs dispatched when DISPATCH_CONFIRM is False", ns.get("RUNS") == [])
        check("manifest written", (tmp / "t1" / "working" / "pilot_manifest.json").exists())
    except Exception as e:
        check("no NameError / ordering is valid", False, f"{type(e).__name__}: {e}")


def test_install_failure(tmp):
    print("\n[T2] wheelhouse install failure must abort (exit status not swallowed)")
    try:
        run_cells(tmp / "t2", upto=2, pip_rc=1)
        check("nonzero pip rc raises", False, "no exception")
    except SystemExit as e:
        check("nonzero pip rc raises SystemExit", "failed rc=1" in str(e), str(e))
    except Exception as e:
        check("nonzero pip rc raises SystemExit", False, f"{type(e).__name__}: {e}")


def test_repair_idempotent(tmp):
    print("\n[T3] repair cell is idempotent and binds all three modules")
    ns = run_cells(tmp / "t3", upto=8)
    import swegemma.harness.agent_runner as ar
    import swegemma.harness.container_setup as cs
    import swegemma.harness.verification as vf
    first = cs.install_editable_package
    check("all three modules share the patch",
          ar.install_editable_package is vf.install_editable_package is cs.install_editable_package)
    orig1 = getattr(first, "__wrapped_original__", None)
    check("wrapper records the original", orig1 is not None)
    # re-execute the repair cell (simulates re-running the setup cell)
    data, working, model, wh = make_env(tmp / "t3", )
    exec(compile(rewrite(cells()[7], data, working, model, wh), "<repair-again>", "exec"), ns)
    second = cs.install_editable_package
    orig2 = getattr(second, "__wrapped_original__", None)
    check("re-running does not wrap the wrapper", orig2 is orig1,
          f"orig1={orig1} orig2={orig2}")
    check("original is not itself a wrapper", not hasattr(orig2, "__wrapped_original__"))


def test_repair_required_failure(tmp):
    print("\n[T4] a failed REQUIRED backend or editable install must raise, not pass silently")
    for label, kw in (("required backend rc=1", dict(required_backend_rc=1)),
                      ("editable install rc=1", dict(editable_rc=1))):
        ns = run_cells(tmp / f"t4_{label[:8]}", upto=8, **kw)
        import swegemma.sandbox as sb
        try:
            ns["patched_install_editable_package"](sb.SubprocessManager(), "cid")
            check(f"{label} raises", False, "no exception")
        except RuntimeError as e:
            check(f"{label} raises RuntimeError", True)
        except Exception as e:
            check(f"{label} raises RuntimeError", False, f"{type(e).__name__}: {e}")


def test_precondition_failure(tmp):
    print("\n[T5] precondition must fail when grading imports outside the checkout")
    try:
        run_cells(tmp / "t5", upto=10, grading_import_in_checkout=False)
        check("bad grading import aborts", False, "no exception")
    except AssertionError as e:
        check("bad grading import raises AssertionError", "preconditions failed" in str(e), str(e)[:80])
    except Exception as e:
        check("bad grading import raises AssertionError", False, f"{type(e).__name__}: {e}")


def test_report_schema(tmp):
    print("\n[T6] report: attribution from real artifact schema; missing data is 'unavailable'")
    ns = run_cells(tmp / "t6")
    working = tmp / "t6" / "working"
    d = working / "pilot" / "A__requests_7309"
    (d / "patches").mkdir(parents=True, exist_ok=True)
    (d / "traces").mkdir(exist_ok=True)
    (d / "test_outputs").mkdir(exist_ok=True)
    # real swegemma serializer field names
    (d / "task_results.jsonl").write_text(json.dumps({
        "instance_id": "requests_7309", "repo": "psf/requests", "resolved": False,
        "agent_patch_size": 40, "test_exit_code": 1, "duration_seconds": 150.7,
        "error": "Agent exceeded turns budget (40 turns)", "tool_calls": 39}) + "\n", encoding="utf-8")
    (d / "patches" / "requests_7309.patch").write_text(
        "diff --git a/repro.py b/repro.py\nnew file mode 100644\nindex 0000000..3b2d6dbd\n"
        "--- /dev/null\n+++ b/repro.py\n+print(1)\n", encoding="utf-8")
    (d / "test_outputs" / "requests_7309.log").write_text("1 failed\n", encoding="utf-8")
    (d / "traces" / "trace_requests_7309.json").write_text(json.dumps({"steps": [
        {"step_id": 1, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "grep x"}}],
         "observation": {"content": '{"status": "ok"}'}},
        {"step_id": 2, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "py x"}}],
         "observation": {"content": '{"status": "error"}'}},
        {"step_id": 3, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "py x"}}],
         "observation": {"content": '{"status": "ok"}'}},
        {"step_id": 4, "tool_calls": [{"function_name": "write_file", "arguments": {"filepath": "repro.py"}}],
         "observation": {"content": '{"status": "ok"}'}},
    ], "final_metrics": {"total_prompt_tokens": 1000, "total_completion_tokens": 50}}), encoding="utf-8")
    ns["RUNS"] = [{"task": "requests_7309", "candidate": "A", "dir": str(d), "wall_s": 160.0,
                   "agent_phase_s": [150.0], "grading_phase_s": [], "error": None}]
    data, working2, model, wh = make_env(tmp / "t6")
    exec(compile(rewrite(cells()[11], data, working2, model, wh), "<report>", "exec"), ns)
    # cells()[11] is REPORT (0-based: 11 -> 12th code cell)
    rows = None
    for k, v in ns.items():
        if k == "rows" and isinstance(v, list) and v:
            rows = v
    check("report produced a row", bool(rows))
    if rows:
        r = rows[0]
        check("repeated identical commands counted", r["repeated_identical_cmds"] == 1, str(r))
        check("tool errors counted from trace", r["tool_errors"] == 1, str(r))
        check("scratch-only patch attributed", r["attribution"] == "scratch_only_patch", str(r["attribution"]))
        check("patch_touches_source False for scratch", r["patch_touches_source"] is False)
        check("missing grading phase reported unavailable, not 0",
              r["grading_phase_s"] == "unavailable", str(r["grading_phase_s"]))
        check("harness duration kept separate from phase timing",
              r["duration_seconds_harness"] == 150.7 and r["agent_phase_s"] == 150.0)


def main() -> int:
    import tempfile
    saved = dict(sys.modules)
    tmp = Path(tempfile.mkdtemp(prefix="pilot_test_"))
    try:
        for fn in (test_ordered_execution, test_install_failure, test_repair_idempotent,
                   test_repair_required_failure, test_precondition_failure, test_report_schema):
            try:
                fn(tmp)
            except Exception as e:
                check(fn.__name__ + " crashed", False, f"{type(e).__name__}: {e}")
            finally:
                sys.modules.clear()
                sys.modules.update(saved)
    finally:
        sys.modules.clear()
        sys.modules.update(saved)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
