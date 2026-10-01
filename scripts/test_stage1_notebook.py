"""Execute the GENERATED Stage-1 cells. String assertions are not enough after parameterization.

`scripts/make_stage1_notebook.py` reuses `make_compare_notebook.py`, which reuses
`make_pilot_notebook.py`. The shared cells are covered elsewhere, but the *composition* is new: one
task, one dispatched candidate, a renamed candidate key, a narrowed run order. This suite runs
`notebooks/stage1/stage1.ipynb`'s own cells through the shared execution harness with simulated
dependencies and asserts the composition behaves as claimed.

  [S1] DISPATCH_CONFIRM=False starts no model server and evaluates no task
  [S2] enabled simulation evaluates exactly rich_3278 / R, exactly once
  [S3] candidate A is never evaluated
  [S4] a failed precondition blocks model startup
  [S5] a failed control blocks model startup
  [S6] the server is stopped on success and on failure
  [S7] no Stage-2 run exists anywhere in the artifact

Run:  NB_TARGET=stage1 python scripts/test_stage1_notebook.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["NB_TARGET"] = "stage1"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_pilot_notebook as H  # noqa: E402  (shared cell-execution harness)

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "stage1" / "stage1.ipynb"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


def nb_code() -> str:
    doc = json.loads(NB.read_text(encoding="utf-8"))
    return "\n".join("".join(c["source"]) for c in doc["cells"] if c["cell_type"] == "code")


# ------------------------------------------------------------------ S1
def test_disabled_does_nothing(tmp):
    print("\n[S1] DISPATCH_CONFIRM=False: no server, no evaluation")
    ns = H.run_cells(tmp / "s1", dispatch=False)
    c = H.counts()
    check("no server was created", c["server_created"] == 0, str(c))
    check("no server was started", c["server_started"] == 0, str(c))
    check("no task was evaluated", c["evaluations"] == 0, str(c))
    check("no run records were written", ns.get("RUNS") == [], str(ns.get("RUNS")))
    check("the report still produced one planned row",
          len(ns.get("rows", [])) == 1, str(len(ns.get("rows", []))))
    row = ns["rows"][0]
    check("that row is the planned R run, not attempted",
          (row["task"], row["candidate"], row["attempted"]) == ("rich_3278", "R", False), str(row)[:120])


# ------------------------------------------------------------------ S2 / S3
def test_enabled_runs_exactly_one(tmp):
    print("\n[S2] enabled simulation evaluates exactly rich_3278 / R, once")
    ns = H.run_cells(tmp / "s2", dispatch=True, server_healthy=True)
    c = H.counts()
    check("exactly one evaluation", c["evaluations"] == 1, str(c))
    check("exactly one run record", len(ns["RUNS"]) == 1, str(len(ns["RUNS"])))
    r = ns["RUNS"][0]
    check("the run is rich_3278 / R", (r["task"], r["candidate"]) == ("rich_3278", "R"), str(r)[:120])
    check("planned order is a single R entry",
          [tuple(x) for x in ns["ORDER"]] == [("rich_3278", "R")], str(ns["ORDER"]))
    check("the report has exactly one row", len(ns["rows"]) == 1, str(len(ns["rows"])))
    check("no stop reason was recorded", not ns.get("STOP_REASON"), str(ns.get("STOP_REASON")))

    print("\n[S3] candidate A is never evaluated")
    check("no run record names A", all(x["candidate"] != "A" for x in ns["RUNS"]))
    check("no report row names A", all(x["candidate"] != "A" for x in ns["rows"]))
    check("A is still embedded for the isolation check", "A" in ns["CAND_DIRS"], str(list(ns["CAND_DIRS"])))
    check("R is the other embedded candidate", "R" in ns["CAND_DIRS"], str(list(ns["CAND_DIRS"])))
    check("only one results directory was created",
          sorted(p.name for p in ns["RESULTS"].iterdir() if p.is_dir() and "__" in p.name)
          == ["R__rich_3278"],
          str(sorted(p.name for p in ns["RESULTS"].iterdir())))
    return ns


# ------------------------------------------------------------------ S4
def test_precondition_blocks_startup(tmp):
    print("\n[S4] a failed precondition blocks model startup")
    raised = None
    try:
        H.run_cells(tmp / "s4", dispatch=True, server_healthy=True,
                    grading_import_in_checkout=False)
    except (AssertionError, RuntimeError, SystemExit) as e:
        raised = e
    check("the notebook aborted", raised is not None, "no exception raised")
    if raised is not None:
        msg = str(raised)
        check("the reason names the checkout or the preconditions",
              "outside its checkout" in msg or "preconditions failed" in msg, msg[:120])
    c = H.counts()
    check("no model server was created", c["server_created"] == 0, str(c))
    check("no task was evaluated", c["evaluations"] == 0, str(c))


# ------------------------------------------------------------------ S5
def test_failed_control_blocks_startup(tmp):
    print("\n[S5] a failed control blocks model startup")
    # Corrupt the saved control evidence the notebook re-validates against, by making the baseline
    # arm's recorded exit code claim a PASS. The control cell must refuse before vLLM is constructed.
    needle = chr(39) + "pytest_exit" + chr(39) + ": 1"

    def hook(i, cell, ns):
        return cell.replace(needle, needle[:-1] + "0", 1) if needle in cell else cell

    raised = None
    try:
        H.run_cells(tmp / "s5", dispatch=True, server_healthy=True, hook=hook)
    except (AssertionError, RuntimeError, SystemExit) as e:
        raised = e
    check("the notebook aborted", raised is not None, "no exception raised")
    c = H.counts()
    check("no model server was created", c["server_created"] == 0, str(c))
    check("no task was evaluated", c["evaluations"] == 0, str(c))


# ------------------------------------------------------------------ S6
def test_server_cleanup(tmp):
    print("\n[S6] the server is stopped on success and on failure")
    H.run_cells(tmp / "s6a", dispatch=True, server_healthy=True)
    c = H.counts()
    check("success: started once, stopped once",
          c["server_started"] == 1 and c["server_stopped"] == 1, str(c))

    raised = None
    try:
        H.run_cells(tmp / "s6b", dispatch=True, server_healthy=True, eval_failure=True)
    except Exception as e:
        raised = e
    c = H.counts()
    check("evaluator failure: still stopped exactly once",
          c["server_started"] == 1 and c["server_stopped"] == 1, str(c))
    check("the failure was recorded rather than swallowed", raised is None, repr(raised)[:120])

    raised = None
    try:
        H.run_cells(tmp / "s6c", dispatch=True, server_healthy=True, startup_failure=True)
    except Exception as e:
        raised = e
    c = H.counts()
    check("startup failure: stop still called", c["server_stopped"] >= 1, str(c))
    check("startup failure propagates", raised is not None, "no exception")


# ------------------------------------------------------------------ S7
def test_no_stage_two():
    print("\n[S7] no Stage-2 run exists in the artifact")
    src = nb_code()
    check("the run order is the single R entry",
          "ORDER = [(tid, 'R') for tid in TASK_IDS]" in src)
    check("TASK_IDS is exactly rich_3278", 'TASK_IDS = ["rich_3278"]' in src, )
    check("no alternating A/B order remains", "('A', 'B') if i % 2 == 0" not in src)
    # The shipped dispatch state changes when the notebook is armed for its one authorised launch, so
    # this asserts the INVARIANTS rather than one state: exactly one flag, a recognised value, and a
    # notebook whose hash is one of the two recorded artifacts. A stray or unrecognised flag fails.
    import hashlib
    flags = [l for l in src.splitlines() if l.strip().startswith("DISPATCH_CONFIRM")]
    check("exactly one dispatch flag is defined", len(flags) == 1, str(flags))
    armed = "DISPATCH_CONFIRM = True" in src
    check("the flag has a recognised boolean value",
          ("DISPATCH_CONFIRM = True" in src) ^ ("DISPATCH_CONFIRM = False" in src), str(flags))
    DISABLED = "695cad7b6efb6edaa899b95cebc063bf8c934b0922ea247d4088212753c196a0"
    ARMED = "775d88dfe3b91ee8b4d5b30cffdd9f2957556b1f045f2b87a1a6b4e3aacd3158"
    got = hashlib.sha256(NB.read_bytes()).hexdigest()
    check("the notebook is one of the two recorded artifacts", got in (DISABLED, ARMED), got)
    check("its hash matches its dispatch state",
          got == (ARMED if armed else DISABLED), f"armed={armed} sha={got}")
    print(f"    shipped state: {'ARMED' if armed else 'disabled'}  sha256 {got[:16]}")
    check("no second task list is defined anywhere",
          src.count("TASK_IDS = ") == 1, str(src.count("TASK_IDS = ")))
    check("nothing schedules or pushes a follow-on kernel",
          "kernels push" not in src and "competitions submit" not in src)
    meta = json.loads((NB.parent / "kernel-metadata.json").read_text(encoding="utf-8"))
    check("kernel id is the stage1 kernel", meta["id"] == "navin03/gemma4-swe-agent-stage1", meta["id"])
    check("kernel is private", meta.get("is_private") in (True, "true"), str(meta.get("is_private")))
    check("internet is disabled", meta.get("enable_internet") in (False, "false"),
          str(meta.get("enable_internet")))


def main() -> int:
    import tempfile
    if os.environ.get("NB_TARGET") != "stage1":
        print("NB_TARGET must be 'stage1'")
        return 1
    print(f"notebook under test: {NB.relative_to(ROOT)}")
    tests = [test_disabled_does_nothing, test_enabled_runs_exactly_one,
             test_precondition_blocks_startup, test_failed_control_blocks_startup,
             test_server_cleanup]
    with tempfile.TemporaryDirectory() as td:
        for fn in tests:
            try:
                fn(Path(td))
            except Exception as e:
                import traceback
                check(fn.__name__ + " crashed", False, f"{type(e).__name__}: {e}")
                traceback.print_exc()
    try:
        test_no_stage_two()
    except Exception as e:
        check("test_no_stage_two crashed", False, f"{type(e).__name__}: {e}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
