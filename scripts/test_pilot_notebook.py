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
_HEALTHY_SERVERS = []


def _healthy_model_server():
    """A real HTTP server answering /v1/models with 200, started once per process.

    The dispatch cell probes the model server with urllib before continuing after a candidate
    failure. Until now the suite could only make that probe FAIL (port 9 refuses), so no test could
    reach the "continue to the next planned run" branch at all. Stubbing urllib would remove the
    very code under test, so a real socket is opened instead.
    """
    if _HEALTHY_SERVERS:
        return _HEALTHY_SERVERS[0]
    import atexit
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"data": [{"id": "gemma-4-31b-it-qat-w4a16-ct"}]}'
            self.send_response(200 if self.path.endswith("/models") else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    atexit.register(srv.shutdown)
    url = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    _HEALTHY_SERVERS.append(url)
    return url


def _symlink_or_copy(src, dst, **kw):
    try:
        _REAL_SYMLINK(src, dst, **kw)
    except (OSError, NotImplementedError):
        shutil.copyfile(src, dst)
os.symlink = _symlink_or_copy

ROOT = Path(__file__).resolve().parent.parent
import os as _os
import re as _re
_which = _os.environ.get("NB_TARGET", "pilot")
COMPARE_NB = True

def _nb_task_ids():
    import json as _j
    src = "\n".join("".join(c["source"]) for c in
                     _j.loads(NB.read_text(encoding="utf-8"))["cells"])
    m = _re.search(r"^TASK_IDS = (\[[^\]]*\])", src, _re.M)
    assert m, "TASK_IDS not found in notebook"
    return _j.loads(m.group(1))
NB = ROOT / "notebooks" / _which / (_which + ".ipynb")
SEL_IDS = _nb_task_ids()
NRUNS = 2 * len(SEL_IDS)
T0ID = SEL_IDS[0]
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


CONTROL_FIXTURE = {}
SANDBOX_ROOT_FOR_TEST = ["/tmp"]


def _control_maps():
    """(pytest_cmd -> task_id, task_id -> saved evidence) for the notebook under test.

    Read from the generator's own evidence loader, so the fixture compares the cell against the
    same saved controls the notebook embeds rather than a hand-written copy.
    """
    if _which not in ("compare", "stage1", "ab_s", "temperature"):
        return {}, {}
    import make_compare_notebook as _M
    # The notebook under test decides its own task set. stage1 ships one task; compare ships four,
    # and for compare SEL_IDS is generated from the same list, so this is a no-op there.
    _M.TASKS = list(SEL_IDS)
    cmds = {}
    import json as _j
    for t in _M.TASKS:
        a = _j.loads((_M.EVID / t / "baseline" / "arm.json").read_text(encoding="utf-8"))
        cmds[a["pytest_cmd"]] = t
    return cmds, _M.compare_evidence()


CONTROL_CMDS, CONTROL_SAVED = _control_maps()


def make_env(tmp: Path, *, pip_rc=0, required_backend_rc=0, editable_rc=0,
             grading_import_in_checkout=True, startup_failure=False, eval_failure=False, bad_phase=None,
             persisted_error=None, skip_grading=False, server_unhealthy=False, leak_sandbox=False,
             escaped_error=None, control_stop_raises=False, control_leak=False,
             all_stop_raises=False, control_stop_raises_after_cleanup=False,
             server_healthy=False):
    """Build a temp Kaggle-like tree and install stub modules. Returns (data_dir, working_dir)."""
    SANDBOX_ROOT_FOR_TEST[0] = (tmp / "working" / "sbxroot").as_posix()
    data = tmp / "input" / "competitions" / "gemma-4-developer-agent"
    (data / "snapshots").mkdir(parents=True, exist_ok=True)
    (data / "wheels").mkdir(parents=True, exist_ok=True)
    (data / "graphs").mkdir(exist_ok=True)
    (data / "embeddings").mkdir(exist_ok=True)
    selected_ids = set(SEL_IDS)
    fields = {f.name for f in dataclasses.fields(FakeTask)}
    tasks = [FakeTask(**{k:v for k,v in t.items() if k in fields}) for t in
             [json.loads(l) for l in (ROOT/'reference/tasks.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
             if t['instance_id'] in selected_ids]
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
    counts = dict(server_created=0, server_started=0, server_stopped=0, registry=0, evaluations=0)
    mod("pilot_test_counts", counts=counts)

    async def sandbox_exec(mgr, sid, cmd):
        # Control re-validation fixture: serve a JUnit report matching the notebook's own saved
        # evidence, so the re-validation cell exercises its real comparison logic.
        if cmd.startswith("cat /tmp/ctl_"):
            arm = "baseline" if "ctl_baseline" in cmd else "reference"
            tid = CONTROL_FIXTURE.get("task")
            ev = CONTROL_SAVED.get(tid, {})
            phase = ev.get("negative" if arm == "baseline" else "positive", {})
            if CONTROL_FIXTURE.get("break_arm") == arm:
                phase = {"failed_nodes": [], "passed_nodes": []}
            # Degraded-report modes, applied to the arm under test. Each one is a report the
            # acceptance logic must REJECT; none of them is a report the cell may synthesise.
            mode = CONTROL_FIXTURE.get("xml_mode")
            if mode and CONTROL_FIXTURE.get("xml_arm", "reference") == arm:
                if mode == "missing":
                    return FakeExec("", 1, "cat: No such file or directory")
                if mode == "empty":
                    return FakeExec("")
                if mode == "malformed":
                    return FakeExec("<testsuite><testcase classname='tests.t' name='a'>")
                if mode == "no_testcases":
                    return FakeExec("<testsuite></testsuite>")
                if mode == "all_skipped":
                    phase = {"failed_nodes": [], "passed_nodes": [],
                             "skipped_nodes": sorted(phase.get("passed_nodes", []))}
                if mode == "unrelated_only":
                    phase = {"failed_nodes": [], "passed_nodes": ["test_other::test_unrelated"]}
                if mode == "drop_target":
                    keep = sorted(phase.get("passed_nodes", []))[1:]
                    phase = {"failed_nodes": [], "passed_nodes": keep}
                if mode == "duplicate":
                    dup = sorted(phase.get("passed_nodes", []))[:1]
                    phase = dict(phase, passed_nodes=sorted(phase.get("passed_nodes", [])) + dup)
            # Built with ElementTree, not string formatting: rich_3278's parametrised node names
            # contain '<' and '>', which a raw f-string would emit as malformed XML.
            import xml.etree.ElementTree as _ETF
            suite = _ETF.Element("testsuite")
            for outcome, key in (("failed", "failed_nodes"), ("passed", "passed_nodes"),
                                 ("skipped", "skipped_nodes")):
                for n in phase.get(key, []):
                    if "::" not in n:
                        continue
                    cls, name = n.split("::", 1)
                    tc = _ETF.SubElement(suite, "testcase",
                                         {"classname": "tests." + cls, "name": name})
                    if outcome == "failed":
                        _ETF.SubElement(tc, "failure", {"message": "x"})
                    elif outcome == "skipped":
                        _ETF.SubElement(tc, "skipped", {"message": "s"})
            return FakeExec(_ETF.tostring(suite, encoding="unicode"))
        if cmd.startswith("wc -c < "):
            if CONTROL_FIXTURE.get("patch_missing"):
                return FakeExec("MISSING", 1, "no such file")
            if CONTROL_FIXTURE.get("patch_empty"):
                return FakeExec("0")
            return FakeExec(str(CONTROL_FIXTURE.get("last_copied_bytes", 120)))
        if "importlib.metadata" in cmd:
            return FakeExec("{'swegemma': '0.2.7', 'adk-submission': '0.2.11', "
                            "'adk-eval-core': '0.1.0', 'google-adk': '1.36.1'}")
        if "-m pytest" in cmd:
            arm = "baseline" if "ctl_baseline" in cmd else "reference"
            for _c, _t in CONTROL_CMDS.items():
                if _c in cmd:
                    CONTROL_FIXTURE["task"] = _t
                    break
            if CONTROL_FIXTURE.get("break_arm") == arm:
                return FakeExec("", 2, "boom")
            return FakeExec("", 1 if arm == "baseline" else 0)
        if "git apply" in cmd:
            return FakeExec("", CONTROL_FIXTURE.get("patch_rc", 0))
        if "pwd -P" in cmd:
            return FakeExec(ws)
        if "PYTHONSAFEPATH" in cmd:
            p = f"{ws}/requests/__init__.py" if grading_import_in_checkout \
                else "/usr/local/lib/python3.12/dist-packages/requests/__init__.py"
            return FakeExec(p + "\n/venv/bin/python3")
        if "import" in cmd:
            return FakeExec(f"{ws}/requests/__init__.py\n/venv/bin/python3")
        return FakeExec("")

    # A real-enough sandbox lifecycle: start CREATES a directory under the rewritten sandbox root
    # and stop REMOVES it. Without this the control cleanup check would have nothing to observe.
    _sbx_n = [0]

    def _sbx_dir(sid):
        return Path(SANDBOX_ROOT_FOR_TEST[0]) / ("swegemma_sandbox_" + str(sid))

    async def fake_sandbox_start(mgr, *a, **k):
        _sbx_n[0] += 1
        sid = "s%d" % _sbx_n[0]
        d = _sbx_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        return sid

    async def fake_sandbox_stop(mgr, sid, *a, **k):
        is_control = getattr(mgr, "timeout_seconds", None) == 900
        if control_stop_raises_after_cleanup and is_control:
            # Partial teardown: the sandbox IS removed, then teardown fails on a later step. The
            # directory check cannot see this, so teardown_error has to disqualify on its own.
            import shutil as _sh
            _sh.rmtree(_sbx_dir(sid), ignore_errors=True)
            raise RuntimeError("simulated teardown failure after the sandbox was removed")
        targeted = is_control or all_stop_raises
        if (control_stop_raises and targeted) or all_stop_raises:
            raise RuntimeError("simulated sandbox teardown failure")
        if control_leak and is_control:
            return                      # returns cleanly, leaves the directory behind
        import shutil as _sh
        _sh.rmtree(_sbx_dir(sid), ignore_errors=True)

    async def noop_async(*a, **k):
        return None

    class SubprocessManager:  # name matters: the repair branches on type name
        def __init__(self, *a, **k):
            # The control arms construct this with timeout_seconds=900 and the preconditions with
            # 600, which is how a fault can be aimed at control teardown specifically.
            self.timeout_seconds = k.get("timeout_seconds", a[0] if a else None)

        def copy_to(self, sid, host, dest):
            # The real manager copies a host file into the sandbox; the fixture records the
            # size so the notebook's creation probe has something true to report.
            CONTROL_FIXTURE["last_copied_bytes"] = Path(host).stat().st_size
            return None

        def exec(self, cid, cmd):
            if "pip install" in cmd and "-e ." in cmd:
                return FakeExec("ok", editable_rc, "editable boom")
            if "pip install" in cmd:
                is_req = cmd.rsplit(" ", 1)[-1] in {"setuptools", "wheel", "editables"}
                return FakeExec("ok", required_backend_rc if is_req else 1, "backend boom")
            if "pwd -P" in cmd:
                return FakeExec(ws)
            if "import" in cmd:
                import re
                pkg = re.search(r"import (\w+) as m", cmd).group(1)
                bad = ("PYTHONSAFEPATH" in cmd and not grading_import_in_checkout) or (
                    bad_phase and str(cid).startswith(bad_phase))
                location = "/usr/local/lib/python3.12/dist-packages" if bad else ws
                return FakeExec(f"{location}/{pkg}/__init__.py\n/venv/bin/python3")
            return FakeExec("ok")

    mod("swegemma.sandbox", SubprocessManager=SubprocessManager, sandbox_exec=sandbox_exec,
        sandbox_start=fake_sandbox_start, sandbox_stop=fake_sandbox_stop)
    mod("swegemma.harness")
    mod("swegemma.harness.container_setup",
        install_editable_package=lambda d, c: None,
        extract_snapshot=lambda *a, **k: None, install_test_dependencies=lambda *a, **k: None,
        setup_baseline_commit=lambda *a, **k: None, setup_container_wheels=lambda *a, **k: None,
        setup_git_exclude=lambda *a, **k: None, setup_workspace_test_config=lambda *a, **k: None)
    mod("swegemma.harness.agent_runner",
        build_agent_prompt=lambda task, config, workspace_tree="": "ISSUE:\n" + task.problem_statement,
        run_agent_sandbox=noop_async, install_editable_package=lambda d, c: None)
    def fake_apply_patch(mgr, sid, path, **k):
        # Mirrors the harness contract: (exit_code, stdout, stderr).
        if CONTROL_FIXTURE.get("apply_fails"):
            return 128, "", "error: can't open patch " + str(path)
        return 0, "Applied patch cleanly.", ""

    mod("swegemma.harness.verification", verify_task=noop_async,
        install_editable_package=lambda d, c: None,
        apply_patch_in_container=fake_apply_patch)
    async def fake_agent(docker, config, task, snapshot_path, *, context=None, **kwargs):
        sys.modules["swegemma.harness.agent_runner"].install_editable_package(docker, "agent_" + task.instance_id)
        if context is not None:
            context.agent_start_time = 1.0
            context.agent_elapsed_seconds = 3.25
        return "patch", None, None

    async def fake_verify(docker, config, task, **kwargs):
        sys.modules["swegemma.harness.verification"].install_editable_package(docker, "grading_" + task.instance_id)

    sys.modules["swegemma.harness.agent_runner"].run_agent_sandbox = fake_agent
    sys.modules["swegemma.harness.verification"].verify_task = fake_verify
    ev = mod("swegemma.evaluate", run_agent_sandbox=fake_agent, verify_task=fake_verify)
    # Execute the real Evaluator dispatch method from the installed harness source.
    # Its globals resolve through ev, just as the real module's imported-by-name function does.
    import ast
    source = ROOT / "reference/harness_src/src_swegemma/swegemma/evaluate.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Evaluator")
    method = next(n for n in klass.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_agent_sandbox")
    method_tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(method_tree), "<real Evaluator dispatch method>", "exec"), ev.__dict__)

    class FakeEvaluator:
        _run_agent_sandbox = ev._run_agent_sandbox

        def __init__(self, config):
            self.config = config
            self.docker = SubprocessManager()

        async def run(self):
            counts["evaluations"] += 1
            if eval_failure:
                raise RuntimeError("simulated evaluator failure")
            task = next(t for t in tasks if t.instance_id == self.config.task_ids[0])
            context = types.SimpleNamespace(agent_start_time=None, agent_elapsed_seconds=0)
            await self._run_agent_sandbox(task, Path("snapshot.tgz"), 1, 1, context=context)
            if leak_sandbox:
                # A sandbox this run created and did not tear down, made AFTER the pre-run
                # snapshot so the cell must attribute it to THIS run specifically.
                root = Path(SANDBOX_ROOT_FOR_TEST[0])
                root.mkdir(parents=True, exist_ok=True)
                (root / ("swegemma_sandbox_" + task.instance_id)).mkdir(exist_ok=True)
            if not skip_grading:
                await ev.verify_task(self.docker, self.config, task)
            d = self.config.results_dir
            (d / "patches").mkdir(exist_ok=True)
            (d / "test_outputs").mkdir(exist_ok=True)
            patch = "diff --git a/pkg/module.py b/pkg/module.py\n--- a/pkg/module.py\n+++ b/pkg/module.py\n+fixed = True\n"
            (d / "patches" / (task.instance_id + ".patch")).write_text(patch, encoding="utf-8")
            (d / "test_outputs" / (task.instance_id + ".log")).write_text("1 passed", encoding="utf-8")
            (d / "task_results.jsonl").write_text(json.dumps({"instance_id": task.instance_id,
                "agent_patch_size": len(patch),
                "test_exit_code": -1 if persisted_error else 0,
                "resolved": False if persisted_error else True,
                "error": persisted_error, "duration_seconds": 4.0, "tool_calls": 2}) + "\n", encoding="utf-8")
            if escaped_error:
                # Real ordering: the evaluator persists its result, then an exception escapes.
                raise RuntimeError(escaped_error)

    ev.Evaluator = FakeEvaluator

    class FakeServer:
        # port 9 (discard) refuses immediately, so the REAL health probe in the dispatch
        # cell fails for real rather than being stubbed out. server_healthy points it at a real
        # listening socket instead, so the same probe can also genuinely succeed.
        base_url = ("http://127.0.0.1:9/v1" if server_unhealthy else
                    _healthy_model_server() if server_healthy else
                    "http://127.0.0.1:8000/v1")
        def __init__(self, *args, **kwargs):
            counts["server_created"] += 1
        def start(self):
            counts["server_started"] += 1
            if startup_failure:
                raise RuntimeError("simulated server startup failure")
        def create_model_registry(self, **kwargs):
            counts["registry"] += 1
            return {}
        def stop(self):
            counts["server_stopped"] += 1

    mod("adk_submission", validate_directory=lambda d, l: None, ModelRegistry=lambda: {},
        VllmConfig=lambda **k: types.SimpleNamespace(**k), VllmServer=FakeServer,
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
            .replace("/kaggle/working", working.as_posix())
            .replace("/tmp/wheelhouse", (working / "wheelhouse").as_posix())
            .replace(chr(83) + 'ANDBOX_ROOT_STR = "/tmp"',
                     chr(83) + "ANDBOX_ROOT_STR = " + repr((working / "sbxroot").as_posix()))
            .replace("CLEANUP_GRACE_S  = 45", "CLEANUP_GRACE_S  = 1"))


def run_cells(tmp, upto=None, ns=None, dispatch=False, hook=None, **envkw):
    data, working, model, wh = make_env(tmp, **envkw)
    ns = ns if ns is not None else {"__name__": "__main__"}
    src_cells = cells()[:upto]
    for i, c in enumerate(src_cells):
        if i == 0:
            # The saved artifact may be launch-enabled. Each test explicitly selects
            # its simulated dispatch state, independently of the shipping default.
            import re
            c, replaced = re.subn(r"(?m)^(DISPATCH_CONFIRM\s*=\s*)(?:True|False)\b",
                                 lambda m: m.group(1) + repr(bool(dispatch)), c, count=1)
            assert replaced == 1, "Missing literal dispatch flag in config cell"
        if hook:
            c = hook(i, c, ns)
        exec(compile(rewrite(c, data, working, model, wh), f"<cell {i+1}>", "exec"), ns)
    return ns


# ---------------------------------------------------------------- tests
def test_ordered_execution(tmp):
    print("\n[T1] all cells execute in notebook order (DISPATCH_CONFIRM=False)")
    try:
        ns = run_cells(tmp / "t1")
        check("no NameError / ordering is valid", True)
        check("TASK_IDS defined before use", ns.get("TASK_IDS") == SEL_IDS)
        check("run_sync available to the repair cell", callable(ns.get("run_sync")))
        check("preconditions ran for every task", len(ns.get("PRECONDITIONS", [])) == len(SEL_IDS),
              str(ns.get("PRECONDITIONS")))
        check("ORDER alternates per task",
              ns.get("ORDER") == [(t, c) for i, t in enumerate(SEL_IDS)
                                  for c in (("A", "B") if i % 2 == 0 else ("B", "A"))],
              str(ns.get("ORDER")))
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
    exec(compile(cells()[7], "<repair-again>", "exec"), ns)
    second = cs.install_editable_package
    orig2 = getattr(second, "__wrapped_original__", None)
    check("re-running does not wrap the wrapper", orig2 is orig1,
          f"orig1={orig1} orig2={orig2}")
    check("original is not itself a wrapper", not hasattr(orig2, "__wrapped_original__"))
    check("repair cell really replaced the installed function", first is not second)
    check("repeated repair still bound on all modules", ar.install_editable_package is vf.install_editable_package is second)


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
    except (AssertionError, RuntimeError) as e:
        check("bad grading import aborts", "outside its checkout" in str(e) or "preconditions failed" in str(e), str(e)[:80])
    except Exception as e:
        check("bad grading import raises AssertionError", False, f"{type(e).__name__}: {e}")


def test_report_schema(tmp):
    print("\n[T6] report: attribution from real artifact schema; missing data is 'unavailable'")
    ns = run_cells(tmp / "t6")
    working = tmp / "t6" / "working"
    d = working / "pilot" / ("A__" + T0ID)
    (d / "patches").mkdir(parents=True, exist_ok=True)
    (d / "traces").mkdir(exist_ok=True)
    (d / "test_outputs").mkdir(exist_ok=True)
    # real swegemma serializer field names
    (d / "task_results.jsonl").write_text(json.dumps({
        "instance_id": T0ID, "repo": "x/y", "resolved": False,
        "agent_patch_size": 40, "test_exit_code": 1, "duration_seconds": 150.7,
        "error": "Agent exceeded turns budget (40 turns)", "tool_calls": 39}) + "\n", encoding="utf-8")
    (d / "patches" / (T0ID + ".patch")).write_text(
        "diff --git a/repro.py b/repro.py\nnew file mode 100644\nindex 0000000..3b2d6dbd\n"
        "--- /dev/null\n+++ b/repro.py\n+print(1)\n", encoding="utf-8")
    (d / "test_outputs" / (T0ID + ".log")).write_text("1 failed\n", encoding="utf-8")
    (d / "traces" / ("trace_" + T0ID + ".json")).write_text(json.dumps({"steps": [
        {"step_id": 1, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "grep x"}}],
         "observation": {"content": '{"status": "ok"}'}},
        {"step_id": 2, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "py x"}}],
         "observation": {"content": '{"status": "error"}'}},
        {"step_id": 3, "tool_calls": [{"function_name": "run_command", "arguments": {"command": "py x"}}],
         "observation": {"content": '{"status": "ok"}'}},
        {"step_id": 4, "tool_calls": [{"function_name": "write_file", "arguments": {"filepath": "repro.py"}}],
         "observation": {"content": '{"status": "ok"}'}},
    ], "final_metrics": {"total_prompt_tokens": 1000, "total_completion_tokens": 50}}), encoding="utf-8")
    record_path = d / "task_results.jsonl"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["agent_patch_size"] = len((d / "patches" / (T0ID + ".patch")).read_text(encoding="utf-8"))
    record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    ns["RUNS"] = [{"task": T0ID, "candidate": "A", "dir": str(d), "wall_s": 160.0,
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
        check("scratch-only patch attributed", r["attribution"] == "suspected_scratch_only_patch", str(r["attribution"]))
        check("patch_touches_source False for scratch", r["patch_touches_source"] is False)
        check("missing grading phase reported unavailable, not 0",
              r["grading_phase_s"] == "unavailable", str(r["grading_phase_s"]))
        check("harness duration kept separate from phase timing",
              r["duration_seconds_harness"] == 150.7 and r["agent_phase_s"] == 150.0)


def counts():
    return sys.modules['pilot_test_counts'].counts


def expect_failure(name, action, contains):
    try:
        action()
        check(name, False, 'no exception')
    except (AssertionError, RuntimeError, SystemExit) as e:
        check(name, contains in str(e), repr(e))


def test_disabled_server(tmp):
    print('\n[T7] disabled dispatch means zero server startup, registry or evaluation calls')
    ns = run_cells(tmp / 't7')
    check('disabled path never instantiates server', counts()['server_created'] == 0)
    check('disabled path never starts model or registry', counts()['server_started'] == counts()['registry'] == 0)
    check('disabled path never evaluates', counts()['evaluations'] == 0)
    check('optional backend failures tolerated after editable/provenance success',
          ns['REPAIR_LOG'] and all(r['provenance_ok'] for r in ns['REPAIR_LOG']) and
          all(r['optional']['hatchling']['rc'] == 1 for r in ns['REPAIR_LOG']))


def test_dispatch_lifecycle(tmp):
    print('\n[T8] actual dispatch calls through real harness forwarding method; cleanup and timings')
    ns = run_cells(tmp / 't8', dispatch=True)
    check('evaluations in specified order', counts()['evaluations'] == NRUNS and
          [(r['task'], r['candidate']) for r in ns['RUNS']] == ns['ORDER'])
    check('one model start and one stop', counts()['server_started'] == counts()['server_stopped'] == 1)
    check('server stopped flag recorded', ns['SERVER_STOPPED'] is True)
    check('actual evaluator bindings record both phases', all(
          len(r['agent_phase_s']) == len(r['grading_phase_s']) == 1 for r in ns['RUNS']))
    check('agent loop timing distinct from setup/grading', all(r['agent_loop_s'] == [3.25] for r in ns['RUNS']))
    check('both actual setup paths observed on every run', all(r['both_setup_imports_verified'] for r in ns['RUNS']))
    check('setup evidence tied to current candidate and task', all(
        len(r['setup_provenance']) == 2 and all(e['run']['candidate'] == r['candidate'] and
        e['run']['task'] == r['task'] for e in r['setup_provenance']) for r in ns['RUNS']))
    check('report rows read real schema', len(ns['rows']) == NRUNS and all(r['resolved'] is True for r in ns['rows']))
    check('grading executed as reported', all(r['grading_ran'] is True for r in ns['rows']))
    check('manifest contains model, hardware, task and candidate hashes',
          ns['MANIFEST']['gpus']['count'] == 4 and len(ns['MANIFEST']['task_content_hashes']) == len(SEL_IDS)
          and len(ns['MANIFEST']['candidates']) == 2 and ns['MANIFEST']['server_stopped'])


def test_startup_cleanup(tmp):
    print('\n[T9] startup failure stops partial server and cannot evaluate')
    expect_failure('startup failure propagates',
                   lambda: run_cells(tmp / 't9', dispatch=True, startup_failure=True), 'server startup failure')
    check('partial startup stopped exactly once', counts()['server_stopped'] == 1)
    check('startup failure prevents evaluations', counts()['evaluations'] == 0)


def test_eval_cleanup(tmp):
    print('\n[T10] evaluator failure persists evidence, stops server, prevents later runs')
    ns = run_cells(tmp / 't10', dispatch=True, eval_failure=True)
    check('only first failing run dispatched', counts()['evaluations'] == 1 and len(ns['RUNS']) == 1)
    check('error run stops server', counts()['server_stopped'] == 1 and ns['SERVER_STOPPED'])
    check('error report preserves missing data', ns['rows'][0]['attribution'] == 'run_error' and
          ns['rows'][0]['agent_phase_s'] == ns['rows'][0]['grading_ran'] == 'unavailable')
    check('runs persisted on evaluator failure', (ns['RESULTS'] / 'runs.json').exists())


def test_setup_failure_stops_dispatch(tmp):
    print('\n[T11] bad import during actual grading stops further GPU dispatch')
    ns = run_cells(tmp / 't11', dispatch=True, bad_phase='grading')
    check('actual grading import failure stops after one run', counts()['evaluations'] == 1)
    check('failed setup cannot be reported as verified', not ns['RUNS'][0]['both_setup_imports_verified'])
    check('failed setup probe persisted', (ns['RESULTS'] / 'setup_observations.json').exists() and
          ns['RUNS'][0]['setup_provenance'][-1]['provenance_ok'] is False)
    check('setup failure stops server', counts()['server_stopped'] == 1)


def test_saved_evidence_guards(tmp):
    print('\n[T12] evidence fails closed: both imports and same failed tests must pass with gold')
    import ast
    for name in ('missing', 'positive_import', 'no_matching_nodes', 'positive_error'):
        def hook(i, c, ns):
            if i != 4:
                return c
            node = next(n for n in ast.parse(c).body if isinstance(n, ast.Assign) and
                        any(isinstance(t, ast.Name) and t.id == 'CONTROL_EVIDENCE' for t in n.targets))
            ev = ast.literal_eval(node.value)
            t = T0ID
            if name == 'missing':
                del ev[t]
            elif name == 'positive_import':
                ev[t]['positive']['pytest_pkg_file'] = '/usr/lib/requests/__init__.py'
            elif name == 'no_matching_nodes':
                ev[t]['positive']['passed_nodes'] = ['totally_different_test']
            else:
                ev[t]['positive']['errored'] = ['test_target']
            return c.replace(ast.get_source_segment(c, node), 'CONTROL_EVIDENCE = ' + repr(ev))
        expect_failure('reject control ' + name, lambda: run_cells(tmp / ('t12_' + name), hook=hook),
                       'missing saved' if name == 'missing' else 'does not support')
        check('invalid evidence never starts server: ' + name, counts()['server_started'] == 0)


def test_path_boundaries(tmp):
    print('\n[T13] checkout containment is component-based')
    ns = run_cells(tmp / 't13', upto=4)
    under = ns['under']
    check('accept actual descendant', under('/tmp/ws/workspace/pkg/__init__.py', '/tmp/ws/workspace'))
    check('reject common prefix sibling', not under('/tmp/ws/workspace-else/pkg.py', '/tmp/ws/workspace'))
    check('reject path escaping through parent', not under('/tmp/ws/workspace/../pkg.py', '/tmp/ws/workspace'))
    check('reject missing workspace and relative path', not under('/workspace/pkg.py', '') and not under('pkg.py', '/workspace'))


def test_candidate_extra_file(tmp):
    print('\n[T14] B-only files cannot slip through a one-sided candidate comparison')
    import ast, base64, hashlib, io, zipfile
    def hook(i, c, ns):
        if i != 6:
            return c
        node = next(n for n in ast.parse(c).body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == 'BUNDLES' for t in n.targets))
        bundles = ast.literal_eval(node.value)
        buf = io.BytesIO(base64.b64decode(bundles['B']['b64']))
        with zipfile.ZipFile(buf, 'a') as z:
            z.writestr('extra_unreviewed.txt', 'not in A')
        payload = buf.getvalue()
        bundles['B'] = dict(b64=base64.b64encode(payload).decode(), sha256=hashlib.sha256(payload).hexdigest())
        return c.replace(ast.get_source_segment(c, node), 'BUNDLES = ' + repr(bundles))
    expect_failure('reject extra file on B', lambda: run_cells(tmp / 't14', hook=hook), 'file sets differ')
    check('candidate mismatch stops before server', counts()['server_started'] == 0)


def test_stale_outputs(tmp):
    print('\n[T15] existing results abort before starting model')
    def hook(i, c, ns):
        if i == 9:
            d = ns['RESULTS'] / ('A__' + T0ID)
            d.mkdir(exist_ok=True)
            (d / 'existing.json').write_text('{}', encoding='utf-8')
        return c
    expect_failure('reject stale output', lambda: run_cells(tmp / 't15', dispatch=True, hook=hook), 'Existing artifacts')
    check('stale results never start server', counts()['server_started'] == 0)


def test_admission_deadline(tmp):
    print('\n[T16] admission deadline stops new runs and shuts model down')
    def hook(i, c, ns):
        if i == 10:
            ns['elapsed_min'] = lambda: ns['SESSION_CAP_MIN'] - 1
        return c
    ns = run_cells(tmp / 't16', dispatch=True, hook=hook)
    check('no run admitted without planning reserve', counts()['evaluations'] == 0)
    check('admission deadline stops server', counts()['server_started'] == counts()['server_stopped'] == 1)
    check('manifest admits this is not a hard timeout', 'no hard kill' in ns['MANIFEST']['session_cap_kind'])


def test_report_integrity(tmp):
    print('\n[T17] artifact schema and Unicode length, sentinels, missing/duplicate results')
    ns = run_cells(tmp / 't17', dispatch=True)
    report = cells()[11]
    def rerun_report():
        exec(compile(report, '<report fixture>', 'exec'), ns)
    d = Path(ns['RUNS'][0]['dir'])
    path = d / 'task_results.jsonl'
    rec = json.loads(path.read_text(encoding='utf-8'))
    patch_path = d / 'patches' / (T0ID + '.patch')
    patch = patch_path.read_text(encoding='utf-8') + '+text = "\\u00e9"\n'.replace('\\u00e9', '\u00e9')
    patch_path.write_text(patch, encoding='utf-8')
    rec['agent_patch_size'] = len(patch)
    rec['test_exit_code'] = -1
    rec['resolved'] = False
    rec['error'] = 'Agent exceeded turns budget (40 turns)'
    path.write_text(json.dumps(rec), encoding='utf-8')
    rerun_report()
    check('Unicode patch compared as chars while bytes reported separately',
          ns['rows'][0]['patch_bytes'] > rec['agent_patch_size'])
    check('minus-one sentinel never implies grading', ns['rows'][0]['grading_ran'] is False)
    check('termination budget recorded independently', 'turns budget' in ns['rows'][0]['termination_error'])
    bad = dict(rec, agent_patch_size=rec['agent_patch_size'] + 1)
    path.write_text(json.dumps(bad), encoding='utf-8')
    expect_failure('reject patch mismatch', rerun_report, 'Patch artifact missing/mismatched')
    path.write_text(json.dumps(rec) + '\n' + json.dumps(rec), encoding='utf-8')
    expect_failure('reject duplicate task results', rerun_report, 'Duplicate results')
    path.write_text(json.dumps(dict(rec, instance_id='wrong')), encoding='utf-8')
    expect_failure('reject wrong task result', rerun_report, 'Wrong task result')
    ts = ns['trace_stats']({'steps': [
        {'observation': {'content': '{"status":"error"}'}},
        {'observation': {'content': '{"status":"success","exit_code":2}'}},
    ]})
    check('minified tool errors and command nonzero exits counted', ts['tool_errors'] == 2)
    shape = ns['patch_shape']('diff --git a/new_module.py b/new_module.py\nnew file mode 100644\n--- /dev/null\n+++ b/new_module.py\n+x=1\n')
    check('new root Python module is not assumed scratch', shape['patch_touches_source'])


def test_task_fingerprint(tmp):
    print('\n[T18] changed task content cannot reuse prior control evidence')
    def hook(i, c, ns):
        if i == 4:
            ns['ALL_BY_ID'][T0ID].problem_statement += ' CHANGED'
        return c
    expect_failure('changed task data aborts', lambda: run_cells(tmp / 't18', hook=hook), 'task content changed')
    check('changed task data stops before server', counts()['server_started'] == 0)


def test_dispatch_enabled_artifact(tmp):
    print('\n[T19] tests explicitly control dispatch even after the launch artifact is enabled')
    global cells
    original = cells
    source = original()
    source[0] = source[0].replace('DISPATCH_CONFIRM = False', 'DISPATCH_CONFIRM = True')
    cells = lambda: list(source)
    try:
        off = run_cells(tmp / 't19_off', dispatch=False)
        check('enabled artifact can simulate disabled dispatch', off['DISPATCH_CONFIRM'] is False)
        check('enabled artifact disabled test never starts server',
              counts()['server_started'] == counts()['evaluations'] == 0)
        on = run_cells(tmp / 't19_on', dispatch=True)
        check('enabled artifact can simulate all enabled runs',
              on['DISPATCH_CONFIRM'] is True and counts()['evaluations'] == NRUNS)
        check('enabled artifact lifecycle stops server once',
              counts()['server_started'] == counts()['server_stopped'] == 1)
    finally:
        cells = original


def main() -> int:
    import tempfile
    saved = dict(sys.modules)
    tmp = Path(tempfile.mkdtemp(prefix="pilot_test_"))
    try:
        for fn in (test_ordered_execution, test_install_failure, test_repair_idempotent,
                   test_repair_required_failure, test_precondition_failure, test_report_schema,
                   test_disabled_server, test_dispatch_lifecycle, test_startup_cleanup, test_eval_cleanup,
                   test_setup_failure_stops_dispatch, test_saved_evidence_guards, test_path_boundaries,
                   test_candidate_extra_file, test_stale_outputs, test_admission_deadline,
                   test_report_integrity, test_task_fingerprint, test_dispatch_enabled_artifact):
            try:
                fn(tmp)
            except Exception as e:
                check(fn.__name__ + " crashed", False, f"{type(e).__name__}: {e}")
            finally:
                sys.modules.clear()
                sys.modules.update(saved)
                _subprocess.run = _REAL_RUN
    finally:
        sys.modules.clear()
        sys.modules.update(saved)
        _subprocess.run = _REAL_RUN
        os.symlink = _REAL_SYMLINK
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
