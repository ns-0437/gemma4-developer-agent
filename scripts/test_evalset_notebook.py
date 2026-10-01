"""EXECUTED integration tests for the generated evalset notebook.

Three layers are reported separately, because they catch different things:
  * policy tests            -> scripts/test_evalset_policy.py (functions in isolation)
  * static notebook checks  -> section [S] here (string/shape assertions only)
  * EXECUTED notebook tests -> sections [X] here (the notebook's own code actually runs)

The executed tests load the policy from the notebook's EMBEDDED base64 (not from disk), run the
generated screening and report cells against simulated control results in a temp directory, and drive
the generated `control()` through a fake sandbox for both a completed pytest run and a setup
exception. They assert on files actually written.

Not a Kaggle run: no real sandbox, no pytest, no model, no competition data.

Run: python scripts/test_evalset_notebook.py
"""
from __future__ import annotations

import base64
import json
import re
import sys
import tempfile
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "evalset" / "evalset.ipynb"
POLICY_TESTS, STATIC, EXECUTED, FAIL = [], [], [], []


def rec(bucket, name, cond, detail=""):
    bucket.append((name, cond))
    if not cond:
        FAIL.append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


def cells():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    return [("".join(c["source"])) for c in nb["cells"] if c["cell_type"] == "code"]


def cell_with(token):
    return next(c for c in cells() if token in c)


def embedded_policy():
    """Load the policy from the NOTEBOOK's embedded base64 — not scripts/evalset_policy.py."""
    src = "\n".join(cells())
    m = re.search(r'POLICY_SRC = _b64\.b64decode\("([A-Za-z0-9+/=]+)"\)', src)
    if not m:
        return None, None
    text = base64.b64decode(m.group(1)).decode("utf-8")
    d = Path(tempfile.mkdtemp()) / "embedded_policy.py"
    d.write_text(text, encoding="utf-8")
    import importlib.util
    spec = importlib.util.spec_from_file_location("embedded_policy", d)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, text


# ----------------------------------------------------------------- static
def static_checks():
    print("\n[S] static notebook checks (string/shape only — these do NOT prove execution)")
    src = "\n".join(cells())
    rec(STATIC, "POLICY_SRC is assigned, not merely referenced",
        bool(re.search(r"^POLICY_SRC = _b64\.b64decode", src, re.M)))
    rec(STATIC, "no unsubstituted placeholder", "__POLICY_B64__" not in src)
    for fn in ("P.repo_quota(", "P.screening_order(", "P.classify(", "P.allocate("):
        rec(STATIC, f"calls {fn.rstrip('(')}", fn in src)
    rec(STATIC, "old target[:12] gone", "target[:12]" not in src)
    rec(STATIC, "old global valid-count stop gone", "valid_n >=" not in src)


# ----------------------------------------------------------------- executed
def test_embedded_policy_is_the_one_used():
    print("\n[X1] the EMBEDDED policy loads and behaves (loaded from the notebook, not from disk)")
    P, text = embedded_policy()
    if P is None:
        rec(EXECUTED, "embedded policy extractable", False, "no POLICY_SRC base64 in notebook"); return
    rec(EXECUTED, "embedded policy imports", hasattr(P, "classify") and hasattr(P, "allocate"))
    disk = (ROOT / "scripts" / "evalset_policy.py").read_text(encoding="utf-8")
    rec(EXECUTED, "embedded copy matches the source module", text == disk)
    q = P.repo_quota({"a": 67, "b": 48, "c": 13}, 24)
    rec(EXECUTED, "embedded repo_quota sums exactly", sum(q.values()) == 24, str(q))


def _inventory(P):
    tasks = ROOT / "reference" / "tasks.jsonl"
    if not tasks.exists():
        return None
    inv = []
    for line in tasks.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        n = sum(1 for l in (t["patch"] or "").splitlines()
                if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
        inv.append({"id": t["instance_id"], "repo": t["repo"], "size": P.size_band(n),
                    "task_sha256": "sha_" + t["instance_id"]})
    return inv


def test_executed_report_cell():
    print("\n[X2] EXECUTE the generated report cell; assert on the manifest it writes")
    P, _ = embedded_policy()
    inv = _inventory(P)
    if inv is None:
        rec(EXECUTED, "real inventory available", False, "reference/tasks.jsonl missing"); return
    quota = P.repo_quota(Counter(r["repo"] for r in inv), 24)
    order = P.screening_order(inv, quota, 40)

    # simulate screening: every candidate valid, one with 37 target nodes
    screen = []
    for i, r in enumerate(order):
        n = 37 if i == 0 else 3
        screen.append({"id": r["id"], "repo": r["repo"], "size": r["size"],
                       "task_sha256": r["task_sha256"], "valid": True, "exclusion_reasons": [],
                       "target_nodes": [f"t::n{k}" for k in range(n)], "n_target_nodes": n,
                       "evidence_dirs": {"baseline": "/x/b", "reference": "/x/r"}})
    tmp = Path(tempfile.mkdtemp())
    ns = {
        "SCREEN": screen, "CANDIDATES": order, "P": P, "QUOTA": quota,
        "TARGET_DEV": 12, "TARGET_HOLDOUT": 12,
        "ALL": {r["id"]: types.SimpleNamespace(repo=r["repo"]) for r in inv},
        "WORKING": tmp, "VERSIONS": {"swegemma": "0.2.7"}, "POLICY_SHA": "abc",
        "SAMPLING_PLAN": {"quota": quota}, "HTTPX_PREFLIGHT": {}, "HTTPX_USABLE": False,
        "DEV": [], "HOLD": [], "json": json,
    }
    exec(compile(cell_with("PROPOSED GPU COMPARISON BUDGET"), "<report>", "exec"), ns)

    man = json.loads((tmp / "evalset_manifest.json").read_text(encoding="utf-8"))
    dev, hold = man["dev"], man["holdout"]
    repo_of = {r["id"]: r["repo"] for r in inv}
    sel = Counter(repo_of[i] for i in dev + hold)
    print("    manifest selection per repo:", dict(sel))
    rec(EXECUTED, "manifest written by the notebook cell", (tmp / "evalset_manifest.json").exists())
    rec(EXECUTED, "psf/requests present in the WRITTEN manifest", sel.get("psf/requests", 0) > 0, str(dict(sel)))
    rec(EXECUTED, "dev filled exactly in manifest", len(dev) == 12, str(len(dev)))
    rec(EXECUTED, "held-out filled exactly in manifest", len(hold) == 12, str(len(hold)))
    rec(EXECUTED, "no repo exceeds quota in manifest", all(sel[r] <= quota[r] for r in sel), str(dict(sel)))
    rec(EXECUTED, "held-out excludes previously studied",
        not (set(hold) & P.PREVIOUSLY_STUDIED), str(set(hold) & P.PREVIOUSLY_STUDIED))
    tn = man["target_nodes"]
    biggest = max(tn.values(), key=len)
    rec(EXECUTED, "all 37 target ids survive into the manifest", len(biggest) == 37, str(len(biggest)))
    rec(EXECUTED, "screen csv written", (tmp / "evalset_screen.csv").exists())


def _fake_sandbox_env(fail_at_setup=False, xml="<testsuite/>"):
    """Install stub modules so the generated control() can run without Kaggle."""
    class Res:
        def __init__(self, out="", rc=0, err=""):
            self.stdout, self.exit_code, self.stderr = out, rc, err

    class Mgr:
        def __init__(self, *a, **k):
            pass

        def exec(self, sid, cmd):
            return Res("ok", 0)

        def copy_to(self, sid, host, dest):
            return None

    async def sandbox_exec(mgr, sid, cmd):
        if "pwd -P" in cmd:
            return Res("/tmp/ws")
        if "PYTHONSAFEPATH" in cmd and "import" in cmd and "pytest" not in cmd:
            return Res("/tmp/ws/pkg/__init__.py")
        if "pytest" in cmd:
            return Res("1 failed, 2 passed", 1, "")
        if cmd.startswith("cat "):
            return Res(xml)
        return Res("")

    async def start(mgr):
        return "sid"

    async def stop(mgr, sid):
        return None

    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    def setup_ok(*a, **k):
        if fail_at_setup:
            raise RuntimeError("editable install failed rc=1")

    mod("swegemma"); mod("swegemma.harness"); mod("swegemma.models")
    mod("swegemma.sandbox", SubprocessManager=Mgr, sandbox_exec=sandbox_exec,
        sandbox_start=start, sandbox_stop=stop)
    mod("swegemma.config", EvalConfig=lambda **k: types.SimpleNamespace(**k))
    mod("swegemma.harness.container_setup",
        extract_snapshot=lambda *a, **k: None, install_editable_package=lambda *a, **k: None,
        install_test_dependencies=setup_ok, setup_baseline_commit=lambda *a, **k: None,
        setup_container_wheels=lambda *a, **k: None, setup_git_exclude=lambda *a, **k: None,
        setup_workspace_test_config=lambda *a, **k: None)
    mod("swegemma.harness.verification",
        apply_patch_in_container=lambda mgr, sid, p: (0, "", ""))
    mod("adk_submission", ModelRegistry=lambda: {})
    return Mgr


def _run_control(fail_at_setup):
    """Execute the generated control() coroutine against the fake sandbox."""
    import asyncio, hashlib, os, uuid, xml.etree.ElementTree as ET
    saved = dict(sys.modules)
    try:
        _fake_sandbox_env(fail_at_setup=fail_at_setup)
        import swegemma.sandbox as _sb
        tmp = Path(tempfile.mkdtemp())
        P, _ = embedded_policy()
        ns = {"__name__": "__main__", "RESULTS": tmp, "WORKING": tmp, "DATA_DIR": tmp,
              "TASKS_PATH": tmp / "tasks.jsonl", "TIMEOUT_SECONDS": 60,
              "PKG": {"r/r": "pkg"}, "COMP_WHEELS": "/w", "VERSIONS": {"swegemma": "x"},
              "POLICY_SHA": "sha", "HTTPX_USABLE": False, "P": P,
              "json": json, "re": re, "os": os, "uuid": uuid, "tempfile": tempfile,
              "hashlib": hashlib, "Path": Path, "asyncio": asyncio, "ET": ET,
              "time": __import__("time"), "collections": __import__("collections"),
              # these names come from an earlier notebook cell in a real run
              "SubprocessManager": _sb.SubprocessManager, "sandbox_exec": _sb.sandbox_exec,
              "sandbox_start": _sb.sandbox_start, "sandbox_stop": _sb.sandbox_stop,
              "task_sha": lambda t: "tasksha_" + t.instance_id}
        ctl = cell_with("async def control")
        body = ctl.split("RESULTS_FILE")[0]          # definitions only, not the screening loop
        exec(compile(body, "<controls>", "exec"), ns)
        task = types.SimpleNamespace(instance_id="requests_7309", repo="r/r",
                                     patch="p", test_patch="--- a/t\n+++ b/t\n")
        (tmp / "snapshots").mkdir(exist_ok=True)
        log = []
        out = asyncio.run(ns["control"](task, "", "baseline", log))
        return out, tmp
    finally:
        sys.modules.clear(); sys.modules.update(saved)


def test_executed_control_success():
    print("\n[X3a] EXECUTE control() — completed pytest run writes real evidence files")
    try:
        out, tmp = _run_control(fail_at_setup=False)
    except Exception as e:
        rec(EXECUTED, "control() executes", False, f"{type(e).__name__}: {e}"); return
    ev = tmp / "evidence" / "requests_7309" / "baseline"
    rec(EXECUTED, "control() executes", True)
    rec(EXECUTED, "junit.xml actually written", (ev / "junit.xml").exists())
    rec(EXECUTED, "stdout.txt actually written", (ev / "stdout.txt").exists())
    rec(EXECUTED, "arm.json actually written", (ev / "arm.json").exists())
    if (ev / "arm.json").exists():
        a = json.loads((ev / "arm.json").read_text(encoding="utf-8"))
        rec(EXECUTED, "arm.json records reached_pytest=True", a.get("reached_pytest") is True, str(a.get("reached_pytest")))
        rec(EXECUTED, "arm.json carries hashes and versions",
            "task_sha256" in a and "environment_versions" in a and "policy_sha256" in a)
        rec(EXECUTED, "pytest exit recorded", a.get("pytest_exit") == 1, str(a.get("pytest_exit")))


def test_executed_control_setup_exception():
    print("\n[X3b] EXECUTE control() — setup exception still persists evidence, no fabricated XML")
    try:
        out, tmp = _run_control(fail_at_setup=True)
    except Exception as e:
        rec(EXECUTED, "control() survives a setup exception", False, f"{type(e).__name__}: {e}"); return
    ev = tmp / "evidence" / "requests_7309" / "baseline"
    rec(EXECUTED, "control() survives a setup exception", True)
    rec(EXECUTED, "arm.json written despite the exception", (ev / "arm.json").exists())
    rec(EXECUTED, "NO_PYTEST_RUN marker written", (ev / "NO_PYTEST_RUN.txt").exists())
    rec(EXECUTED, "no fabricated junit.xml", not (ev / "junit.xml").exists())
    rec(EXECUTED, "traceback persisted", (ev / "traceback.txt").exists())
    if (ev / "arm.json").exists():
        a = json.loads((ev / "arm.json").read_text(encoding="utf-8"))
        rec(EXECUTED, "reached_pytest=False recorded", a.get("reached_pytest") is False)
        rec(EXECUTED, "exception detail recorded", bool(a.get("exception")), str(a.get("exception")))
        rec(EXECUTED, "setup commands preserved", isinstance(a.get("setup_commands"), list))


def test_executed_classification_rejects_fixture_errors():
    print("\n[X4] EXECUTE the embedded classifier on a fixture-error baseline")
    P, _ = embedded_policy()
    base = {"pytest_exit": 1, "nodes": {"t::a": "failed", "t::b": "errored"},
            "import_in_checkout": True, "patch_rc": 0, "test_patch_rc": 0, "collection_error": False}
    ref = {"pytest_exit": 0, "nodes": {"t::a": "passed", "t::b": "passed"},
           "import_in_checkout": True, "patch_rc": 0, "test_patch_rc": 0, "collection_error": False}
    valid, reasons, _ = P.classify(base, ref)
    rec(EXECUTED, "fixture-error baseline rejected by embedded policy", not valid, str(reasons))
    ok2, r2, _ = P.classify({k: v for k, v in base.items() if k != "nodes"} |
                            {"nodes": {"t::a": "failed"}}, {**ref, "pytest_exit": 1})
    rec(EXECUTED, "nonzero reference exit rejected by embedded policy", not ok2, str(r2))


def main() -> int:
    if not NB.exists():
        print("generated notebook missing"); return 1
    static_checks()
    for fn in (test_embedded_policy_is_the_one_used, test_executed_report_cell,
               test_executed_control_success, test_executed_control_setup_exception,
               test_executed_classification_rejects_fixture_errors):
        fn()
    print("\n" + "=" * 60)
    print(f"static notebook checks : {sum(1 for _, c in STATIC if c)}/{len(STATIC)} passed")
    print(f"EXECUTED notebook tests: {sum(1 for _, c in EXECUTED if c)}/{len(EXECUTED)} passed")
    print(f"(policy-in-isolation tests live in scripts/test_evalset_policy.py)")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
