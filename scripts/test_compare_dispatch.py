"""Dispatch and report tests that execute the ACTUAL generated cells of notebooks/compare.

Every test here drives `notebooks/compare/compare.ipynb`'s own code through `run_cells`, with the
harness stubbed at its real boundaries (Evaluator, verify_task, vLLM server, sandbox). Nothing
re-implements or copies the classifier: if a test passes, the shipped cell produced that behaviour.

Covers the six cases a reviewer asked for by name:

  [D1] evaluator returns normally but persists a context-window error   -> candidate failure
  [D2] evaluator returns normally but persists an environment error     -> environment failure, stop
  [D3] grading never starts                                             -> unobserved_grading, stop
  [D4] server health probe fails after a candidate error                -> stop
  [D5] a sandbox this run created is never cleaned up                   -> stop before the next run
  [D6] an early stop still produces all eight report rows

Plus two the reviewer's reasoning implies:

  [D7] an unexplained BadRequestError is NOT charged to the candidate
  [D8] a graded run with zero passes is a RESULT, not a failure

And five for the termination message compare kernel version 2 actually produced, verbatim:

  [D14] "Agent completed execution without calling submit_patch." -> candidate, not environment
  [D15] a clean missing submission lets every other planned run go ahead
  [D16] a genuine environment failure still stops
  [D17] environment wins when both occur in the same run
  [D18] a cleanup failure still stops, and all eight rows survive the early stop

Run:  NB_TARGET=compare python scripts/test_compare_dispatch.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("NB_TARGET", "compare")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_pilot_notebook as H  # noqa: E402  (the shared cell-execution harness)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


def rows_by_key(ns):
    return {(r["task"], r["candidate"]): r for r in ns["rows"]}


def first_run(ns):
    return ns["RUNS"][0] if ns.get("RUNS") else None


# ------------------------------------------------------------------ D1
def test_persisted_context_error(tmp):
    print("\n[D1] evaluator RETURNS NORMALLY but persists a context-window error")
    ns = H.run_cells(tmp / "d1", dispatch=True, persisted_error=(
        "litellm.ContextWindowExceededError: BadRequestError - This model's maximum context length "
        "is 32768 tokens, however you requested 34011 tokens"))
    r = first_run(ns)
    check("run recorded despite no escaped exception", r is not None and r["error"] is None, str(r and r["error"]))
    check("persisted error was read from task_results.jsonl",
          bool(r and r["persisted_error"]), str(r and r["persisted_error"])[:80])
    check("classified as a candidate failure", r and r["outcome"] == "candidate", str(r and r["outcome"]))
    check("reason names the cause", r and "context" in r["outcome_reason"], str(r and r["outcome_reason"]))
    check("not misreported as an environment failure", r and not r["environment_error"])
    check("report carries the outcome", rows_by_key(ns)[(r["task"], r["candidate"])]["failure_class"] == "candidate")


# ------------------------------------------------------------------ D2
def test_persisted_environment_error(tmp):
    print("\n[D2] evaluator RETURNS NORMALLY but persists an environment error")
    ns = H.run_cells(tmp / "d2", dispatch=True,
                     persisted_error="Failed to apply test_patch: git apply failed (1): patch does not apply")
    r = first_run(ns)
    check("classified as an environment failure", r and r["outcome"] == "environment", str(r and r["outcome"]))
    check("not charged to the candidate", r and not r["candidate_error"])
    check("dispatch stopped after it", H.counts()["evaluations"] == 1, str(H.counts()["evaluations"]))
    check("stop reason recorded", bool(ns.get("STOP_REASON")), str(ns.get("STOP_REASON")))
    check("server stopped exactly once",
          H.counts()["server_started"] == H.counts()["server_stopped"] == 1)
    check("partial artifacts preserved", (ns["RESULTS"] / "runs.json").exists())


# ------------------------------------------------------------------ D3
def test_grading_never_starts(tmp):
    print("\n[D3] grading never starts: absence of observation, not a provenance failure")
    ns = H.run_cells(tmp / "d3", dispatch=True, skip_grading=True)
    r = first_run(ns)
    check("grading recorded as unobserved", r and r["grading_observed"] is False, str(r and r["grading_observed"]))
    check("classified as unobserved_grading", r and r["outcome"] == "unobserved_grading", str(r and r["outcome"]))
    check("NOT reported as a provenance failure", r and not r["provenance_failed"],
          str(r and r["phase_status"]))
    check("grading phase status is not_attempted, not failed",
          r and r["phase_status"]["grading"] == "not_attempted", str(r and r["phase_status"]))
    check("dispatch stopped", H.counts()["evaluations"] == 1)
    check("report distinguishes it", rows_by_key(ns)[(r["task"], r["candidate"])]["failure_class"]
          == "unobserved_grading")


# ------------------------------------------------------------------ D4
def test_server_health_failure(tmp):
    print("\n[D4] candidate failure plus an unhealthy model server stops dispatch")
    ns = H.run_cells(tmp / "d4", dispatch=True, server_unhealthy=True,
                     persisted_error="litellm.ContextWindowExceededError: maximum context length")
    r = first_run(ns)
    check("still classified as a candidate failure", r and r["outcome"] == "candidate")
    check("dispatch stopped rather than continuing blindly", H.counts()["evaluations"] == 1,
          str(H.counts()["evaluations"]))
    check("stop reason names server health",
          "server is not healthy" in (ns.get("STOP_REASON") or ""), str(ns.get("STOP_REASON")))
    check("server stopped once", H.counts()["server_stopped"] == 1)


# ------------------------------------------------------------------ D5
def test_cleanup_failure(tmp):
    print("\n[D5] a sandbox THIS run created and left behind stops the next candidate")
    ns = H.run_cells(tmp / "d5", dispatch=True, leak_sandbox=True)
    r = first_run(ns)
    check("cleanup not confirmed", r and r["cleanup_ok"] is False, str(r and r["cleanup_ok"]))
    check("only this run's sandbox is counted",
          r and len(r["owned_sandboxes"]) == 1, str(r and r["owned_sandboxes"]))
    check("dispatch stopped before the next candidate", H.counts()["evaluations"] == 1,
          str(H.counts()["evaluations"]))
    check("stop reason names cleanup", "cleanup" in (ns.get("STOP_REASON") or ""), str(ns.get("STOP_REASON")))
    check("server stopped once", H.counts()["server_stopped"] == 1)
    check("it is a gate, not a printed count",
          len(ns["RUNS"]) == 1 and len(ns["rows"]) == len(ns["ORDER"]))


def test_cleanup_ignores_unrelated_sandboxes(tmp):
    print("\n[D5b] a pre-existing unrelated sandbox must NOT be attributed to this run")
    root = Path((tmp / "d5b" / "working" / "sbxroot").as_posix())
    root.mkdir(parents=True, exist_ok=True)
    (root / "swegemma_sandbox_someone_else").mkdir(exist_ok=True)
    ns = H.run_cells(tmp / "d5b", dispatch=True)
    runs = ns.get("RUNS") or []
    check("all runs dispatched", len(runs) == len(ns["ORDER"]), str(len(runs)))
    check("no run blamed for the stranger", all(r["cleanup_ok"] for r in runs),
          str([r["owned_sandboxes"] for r in runs]))
    check("stranger still on disk, simply not attributed", (root / "swegemma_sandbox_someone_else").exists())


# ------------------------------------------------------------------ D6
def test_early_stop_full_report(tmp):
    print("\n[D6] an early stop still produces one row per planned run")
    ns = H.run_cells(tmp / "d6", dispatch=True,
                     persisted_error="Sandbox execution error: device disappeared")
    order = ns["ORDER"]
    rows = ns["rows"]
    check("eight planned runs", len(order) == 8, str(len(order)))
    check("one row per planned run", len(rows) == len(order), str(len(rows)))
    keys = [(r["task"], r["candidate"]) for r in rows]
    check("each planned run appears exactly once", keys == list(order), str(keys))
    attempted = [r for r in rows if r["attempted"] is True]
    skipped = [r for r in rows if r["attempted"] is False]
    check("exactly one attempted", len(attempted) == 1, str(len(attempted)))
    check("seven not_attempted", len(skipped) == 7, str(len(skipped)))
    check("every skipped row carries a stop reason",
          all(r["attribution"] == "not_attempted" and r["stop_reason"] for r in skipped),
          str([r["stop_reason"] for r in skipped][:2]))
    check("skipped rows never fabricate an outcome",
          all(r["resolved"] == "unavailable" and r["test_exit_code"] == "unavailable" for r in skipped))
    check("csv written with every planned run",
          (ns["WORKING_DIR"] / "pilot_results.csv").exists())


# ------------------------------------------------------------------ D7
def test_unexplained_bad_request_not_candidate(tmp):
    print("\n[D7] a BadRequestError with no identified cause is NOT charged to the candidate")
    ns = H.run_cells(tmp / "d7", dispatch=True,
                     persisted_error="Evaluation error: litellm.BadRequestError: OpenAIException - <html>502</html>")
    r = first_run(ns)
    check("not classified as a candidate failure", r and r["outcome"] != "candidate", str(r and r["outcome"]))
    check("classified as environment", r and r["outcome"] == "environment", str(r and r["outcome"]))
    check("reason says the cause was not identified",
          r and "no identified cause" in r["outcome_reason"], str(r and r["outcome_reason"]))
    check("dispatch stopped", H.counts()["evaluations"] == 1)


# ------------------------------------------------------------------ D8
def test_zero_passes_is_a_result(tmp):
    print("\n[D8] a graded run with zero passing tests is a RESULT, not a failure")
    ns = H.run_cells(tmp / "d8", dispatch=True,
                     persisted_error="Pytest stdout summary indicates zero or no passing tests")
    runs = ns.get("RUNS") or []
    check("classified as ok", runs and runs[0]["outcome"] == "ok", str(runs and runs[0]["outcome"]))
    check("dispatch continued through all runs", len(runs) == len(ns["ORDER"]), str(len(runs)))
    check("no stop reason", not ns.get("STOP_REASON"), str(ns.get("STOP_REASON")))
    check("all eight rows present", len(ns["rows"]) == 8, str(len(ns["rows"])))


# ---------------------------------------------------------- control acceptance (C1..C7)
def _control_rejects(tmp, name, **fixture):
    """Run the generated PRECOND cell with a degraded report and require it to refuse."""
    H.CONTROL_FIXTURE.clear()
    H.CONTROL_FIXTURE.update(fixture)
    try:
        H.run_cells(tmp, upto=10)          # cells 0..9: PRECOND is the last one
        check(name, False, "acceptance PASSED a report it should have rejected")
        return None
    except AssertionError as e:
        msg = str(e)
        check(name, "do not start the model" in msg or "controls do not reproduce" in msg, msg[:120])
        return msg
    finally:
        H.CONTROL_FIXTURE.clear()


def test_control_missing_xml(tmp):
    print("\n[C1] a MISSING JUnit report must not satisfy the reference arm")
    _control_rejects(tmp / "c1", "missing report rejected", xml_mode="missing", xml_arm="reference")
    ev = tmp / "c1" / "working" / "pilot" / "control_evidence"
    marks = sorted(x.name for x in ev.glob("*NO_JUNIT*")) if ev.exists() else []
    check("absence recorded, nothing synthesised", bool(marks), str(marks))
    check("no junit.xml fabricated for that arm",
          not list(ev.glob("*reference.junit.xml")) if ev.exists() else False)


def test_control_malformed_xml(tmp):
    print("\n[C2] an unparseable report must not satisfy the reference arm")
    _control_rejects(tmp / "c2", "malformed report rejected", xml_mode="malformed", xml_arm="reference")


def test_control_empty_xml(tmp):
    print("\n[C3] an empty report, and one with no testcase elements, must be rejected")
    _control_rejects(tmp / "c3a", "empty report rejected", xml_mode="empty", xml_arm="reference")
    _control_rejects(tmp / "c3b", "report with zero testcases rejected",
                     xml_mode="no_testcases", xml_arm="reference")


def test_control_all_skipped(tmp):
    print("\n[C4] a reference arm where every test SKIPPED must be rejected")
    _control_rejects(tmp / "c4", "all-skipped reference rejected",
                     xml_mode="all_skipped", xml_arm="reference")


def test_control_unrelated_only(tmp):
    print("\n[C5] a reference arm where only an UNRELATED test passed must be rejected")
    _control_rejects(tmp / "c5", "unrelated-test-only reference rejected",
                     xml_mode="unrelated_only", xml_arm="reference")


def test_control_missing_target(tmp):
    print("\n[C6] a reference arm missing one saved TARGET node must be rejected")
    _control_rejects(tmp / "c6", "missing target rejected",
                     xml_mode="drop_target", xml_arm="reference")


def test_control_duplicate_nodes(tmp):
    print("\n[C7] duplicate node identities must be rejected, not silently overwritten")
    _control_rejects(tmp / "c7", "duplicate node identity rejected",
                     xml_mode="duplicate", xml_arm="reference")


def test_control_evidence_persisted_per_arm(tmp):
    print("\n[C8] completed arms survive a later arm failing")
    H.CONTROL_FIXTURE.clear()
    H.CONTROL_FIXTURE.update({"xml_mode": "missing", "xml_arm": "reference"})
    try:
        H.run_cells(tmp / "c8", upto=10)
    except AssertionError:
        pass
    finally:
        H.CONTROL_FIXTURE.clear()
    ev = tmp / "c8" / "working" / "pilot" / "control_evidence"
    jsons = sorted(x.name for x in ev.glob("*.json")) if ev.exists() else []
    xmls = sorted(x.name for x in ev.glob("*.junit.xml")) if ev.exists() else []
    check("per-arm json written as each arm finished", len(jsons) >= 2, str(jsons[:4]))
    check("the baseline arm's raw XML survived the later failure",
          any("baseline" in x for x in xmls), str(xmls[:4]))
    check("evidence written before the assertion fired", bool(jsons))


def test_control_target_outside_saved_map(tmp):
    print("\n[C9] a target node absent from the saved node map must be rejected")
    # The full-map comparison alone cannot catch this: if the saved evidence itself omits a target,
    # observed == expected while the target was never verified. This is what makes the explicit
    # target check load-bearing rather than redundant.
    def hook(i, c, ns):
        if "CONTROL_TARGET_NODES = " in c:
            import re as _r
            c = _r.sub(r"(?m)^CONTROL_TARGET_NODES = (\{.*\})$",
                       lambda m: "CONTROL_TARGET_NODES = {k: v + ['test_ghost::test_never_recorded']"
                                 " for k, v in " + m.group(1) + ".items()}", c)
        return c
    H.CONTROL_FIXTURE.clear()
    try:
        H.run_cells(tmp / "c9", upto=10, hook=hook)
        check("ghost target rejected", False, "acceptance PASSED an unverified target")
    except AssertionError as e:
        check("ghost target rejected", "do not start the model" in str(e), str(e)[:120])
    finally:
        H.CONTROL_FIXTURE.clear()


# ------------------------------------------------- control sandbox cleanup (C10..C12)
def _precond_upto_server(tmp, **envkw):
    """Execute cells 0..10, i.e. through PRECOND and into SERVER.

    Running as far as SERVER is what makes "model startup count stays zero" a real assertion: if
    PRECOND accepted a dirty control, the server cell would run and the count would rise.
    """
    return H.run_cells(tmp, upto=11, dispatch=True, **envkw)


def _evidence_dir(tmp):
    return tmp / "working" / "pilot" / "control_evidence"


def test_control_teardown_raises(tmp):
    print("\n[C10] sandbox_stop RAISING must reject the control arm and stop before the model")
    try:
        _precond_upto_server(tmp / "c10", control_stop_raises=True)
        check("teardown failure rejected", False, "acceptance PASSED an arm whose teardown raised")
    except AssertionError as e:
        check("teardown failure rejected", "cleanup" in str(e).lower(), str(e)[:140])
    check("model never started", H.counts()["server_started"] == 0, str(H.counts()))
    ev = _evidence_dir(tmp / "c10")
    recs = sorted(x.name for x in ev.glob("*.json")) if ev.exists() else []
    check("the failing arm's evidence was persisted", bool(recs), str(recs))
    if recs:
        import json as _j
        rec = _j.loads((ev / recs[0]).read_text(encoding="utf-8"))
        check("teardown_error recorded", bool(rec.get("teardown_error")), str(rec.get("teardown_error")))
        check("cleanup result recorded alongside it", rec.get("cleanup_ok") is False, str(rec.get("cleanup_ok")))
        # Isolates the ACCEPTANCE verdict from the stop-reason gate. The two overlap, so without
        # this a mutation that drops teardown_error from `agree` is masked by the stop gate.
        check("the arm's own verdict is reject", rec.get("agrees_with_saved") is False,
              str(rec.get("agrees_with_saved")))
    check("no further arms ran after the failure", len(recs) == 1, str(recs))


def test_control_teardown_raises_but_cleans(tmp):
    print("\n[C10b] teardown that REMOVES the sandbox and then fails must still be rejected")
    # Here cleanup_ok is True, so only the teardown_error check can reject the arm. Without this
    # case, dropping teardown_error from the acceptance condition changes nothing observable.
    try:
        _precond_upto_server(tmp / "c10b", control_stop_raises_after_cleanup=True)
        check("teardown error alone rejects the arm", False, "acceptance PASSED a failed teardown")
    except AssertionError as e:
        check("teardown error alone rejects the arm", "cleanup" in str(e).lower(), str(e)[:140])
    check("model never started", H.counts()["server_started"] == 0, str(H.counts()))
    ev = _evidence_dir(tmp / "c10b")
    recs = sorted(x.name for x in ev.glob("*.json")) if ev.exists() else []
    check("evidence persisted", bool(recs), str(recs))
    if recs:
        import json as _j
        rec = _j.loads((ev / recs[0]).read_text(encoding="utf-8"))
        check("the sandbox really was removed", rec.get("cleanup_ok") is True, str(rec.get("cleanup_ok")))
        check("teardown_error recorded anyway", bool(rec.get("teardown_error")), str(rec.get("teardown_error")))
        check("the arm's own verdict is reject", rec.get("agrees_with_saved") is False,
              str(rec.get("agrees_with_saved")))


def test_control_teardown_leaks(tmp):
    print("\n[C11] sandbox_stop RETURNING but leaving the arm's sandbox must still be rejected")
    try:
        _precond_upto_server(tmp / "c11", control_leak=True)
        check("silent leak rejected", False, "acceptance PASSED an arm that leaked its sandbox")
    except AssertionError as e:
        check("silent leak rejected", "cleanup" in str(e).lower(), str(e)[:140])
    check("model never started", H.counts()["server_started"] == 0, str(H.counts()))
    ev = _evidence_dir(tmp / "c11")
    recs = sorted(x.name for x in ev.glob("*.json")) if ev.exists() else []
    check("evidence persisted before stopping", bool(recs), str(recs))
    if recs:
        import json as _j
        rec = _j.loads((ev / recs[0]).read_text(encoding="utf-8"))
        check("no teardown exception, yet cleanup failed",
              not rec.get("teardown_error") and rec.get("cleanup_ok") is False,
              str((rec.get("teardown_error"), rec.get("cleanup_ok"))))
        check("the leaked sandbox is named", bool(rec.get("owned_sandboxes")),
              str(rec.get("owned_sandboxes")))
        check("the arm's own verdict is reject", rec.get("agrees_with_saved") is False,
              str(rec.get("agrees_with_saved")))
    check("no further arms ran after the failure", len(recs) == 1, str(recs))


def test_control_unrelated_sandbox_not_blamed(tmp):
    print("\n[C12] an unrelated PRE-EXISTING sandbox must not fail the controls")
    root = Path((tmp / "c12" / "working" / "sbxroot").as_posix())
    root.mkdir(parents=True, exist_ok=True)
    stranger = root / "swegemma_sandbox_not_ours"
    stranger.mkdir(exist_ok=True)
    ok = True
    try:
        _precond_upto_server(tmp / "c12")
    except AssertionError as e:
        ok = False
        check("controls accepted despite the stranger", False, str(e)[:140])
    if ok:
        check("controls accepted despite the stranger", True)
    ev = _evidence_dir(tmp / "c12")
    recs = sorted(x.name for x in ev.glob("*.json")) if ev.exists() else []
    check("all eight control arms ran", len(recs) == 8, str(len(recs)))
    check("the stranger was never deleted", stranger.exists())
    if recs:
        import json as _j
        rec = _j.loads((ev / recs[0]).read_text(encoding="utf-8"))
        check("stranger not attributed to any arm", rec.get("cleanup_ok") is True,
              str(rec.get("owned_sandboxes")))


def test_precondition_teardown_also_gated(tmp):
    print("\n[C13] the PRECONDITION probe's own teardown is gated too")
    # Found while writing C10: _precondition called sandbox_stop bare in a finally block, so a
    # teardown failure escaped as a raw exception and a silent leak there was never noticed. A
    # precondition leak is just as damaging, because the dispatch loop would later snapshot it as
    # pre-existing and attribute it to nobody.
    try:
        _precond_upto_server(tmp / "c13", all_stop_raises=True)
        check("precondition teardown failure rejected", False, "acceptance PASSED a dirty probe")
    except AssertionError as e:
        check("precondition teardown failure rejected", "preconditions failed" in str(e), str(e)[:140])
    check("it is an assertion, not a raw exception escaping", True)
    check("model never started", H.counts()["server_started"] == 0, str(H.counts()))


def test_patch_creation_failure_is_named(tmp):
    print("\n[C14] a patch file that was never created is named as such, not an opaque git 128")
    # Version 1 failed exactly here: 12 of 12 applications returned 128, which real git returns for
    # a MISSING or EMPTY patch file, never for a patch that simply does not apply (that is 1).
    for label, fixture in (("missing", {"patch_missing": True}), ("empty", {"patch_empty": True})):
        H.CONTROL_FIXTURE.clear()
        H.CONTROL_FIXTURE.update(fixture)
        try:
            _precond_upto_server(tmp / f"c14_{label}")
            check(f"{label} patch file rejected", False, "acceptance PASSED an unwritten patch")
        except AssertionError as e:
            check(f"{label} patch file rejected", "do not start the model" in str(e), str(e)[:120])
        finally:
            H.CONTROL_FIXTURE.clear()
        ev = _evidence_dir(tmp / f"c14_{label}")
        recs = sorted(ev.glob("*.json")) if ev.exists() else []
        check(f"{label}: evidence persisted", bool(recs), str(recs))
        if recs:
            import json as _j
            rec = _j.loads(recs[0].read_text(encoding="utf-8"))
            tev = rec.get("test_patch_evidence") or {}
            check(f"{label}: creation was checked before application",
                  "created_bytes" in tev or tev.get("error"), str(tev)[:200])
            check(f"{label}: the reason names patch creation",
                  "not created" in str(tev.get("error", "")), str(tev.get("error"))[:160])
            check(f"{label}: application was not attempted", "apply_rc" not in tev, str(tev)[:200])


def test_baseline_patch_rc_is_not_zero(tmp):
    print("\n[C15] the baseline arm reports no source patch as None, never as a successful 0")
    H.CONTROL_FIXTURE.clear()
    try:
        H.run_cells(tmp / "c15", upto=10)
    except AssertionError:
        pass
    ev = _evidence_dir(tmp / "c15")
    recs = {f.name: f for f in ev.glob("*.json")} if ev.exists() else {}
    base = [v for k, v in recs.items() if "baseline" in k]
    ref = [v for k, v in recs.items() if "reference" in k]
    check("a baseline arm was recorded", bool(base), str(sorted(recs)))
    if base:
        import json as _j
        rec = _j.loads(base[0].read_text(encoding="utf-8"))
        check("baseline patch_rc is None, not 0", rec.get("patch_rc") is None, str(rec.get("patch_rc")))
        check("baseline says why", "no source patch" in str((rec.get("patch_evidence") or {}).get("note", "")),
              str(rec.get("patch_evidence"))[:160])
    if ref:
        import json as _j
        rec = _j.loads(ref[0].read_text(encoding="utf-8"))
        check("reference patch_rc is 0", rec.get("patch_rc") == 0, str(rec.get("patch_rc")))


# ---------------------------------------------------------- error precedence (E1..E2)
def test_wrapped_context_error_is_candidate(tmp):
    print("\n[E1] a context error inside a generic wrapper is a CANDIDATE failure")
    ns = H.run_cells(tmp / "e1", dispatch=True, persisted_error=(
        "Unexpected evaluation worker error: litellm.ContextWindowExceededError: "
        "OpenAIException - maximum context length is 32768 tokens"))
    r = first_run(ns)
    check("classified as candidate, not environment", r and r["outcome"] == "candidate",
          str(r and (r["outcome"], r["outcome_reason"])))
    check("reason names the real cause inside the wrapper",
          r and "context" in r["outcome_reason"], str(r and r["outcome_reason"]))


def test_environment_not_hidden_by_candidate(tmp):
    print("\n[E2] a persisted environment failure is not hidden by an escaped candidate error")
    ns = H.run_cells(tmp / "e2", dispatch=True,
                     escaped_error="litellm.ContextWindowExceededError: maximum context length",
                     persisted_error="Sandbox execution error: device disappeared")
    r = first_run(ns)
    check("both sources classified before deciding", r is not None)
    check("environment wins over candidate", r and r["outcome"] == "environment",
          str(r and (r["outcome"], r["outcome_reason"])))
    check("reason records the other source too",
          r and "also" in r["outcome_reason"], str(r and r["outcome_reason"]))
    check("dispatch stopped", H.counts()["evaluations"] == 1)


# ==============================================================================================
# [D14]-[D18] the termination message compare kernel version 2 actually produced.
#
# Candidate B on rich_3278 ended with swegemma persisting exactly this string. No marker matched
# it, so it fell through to 'unclassified error' -> environment -> stop, and six planned runs of
# BOTH candidates were cancelled on the strength of one candidate's tool use. These tests use the
# real message verbatim, not a paraphrase.
# ==============================================================================================
NO_SUBMIT = "Agent completed execution without calling submit_patch."


def test_no_submission_is_a_candidate_outcome(tmp):
    print("\n[D14] the real 'without calling submit_patch' message is a CANDIDATE outcome")
    # skip_grading mirrors the real run: the agent never submitted, so grading never started.
    ns = H.run_cells(tmp / "d14", dispatch=True, server_healthy=True, persisted_error=NO_SUBMIT,
                     skip_grading=True)
    r = first_run(ns)
    check("the real message was read from task_results.jsonl",
          r and r["persisted_error"] == NO_SUBMIT, str(r and r["persisted_error"]))
    check("classified as a candidate outcome", r and r["outcome"] == "candidate", str(r and r["outcome"]))
    check("not an environment failure", r and not r["environment_error"])
    check("reason says no environment cause was found",
          r and "no environment cause" in r["outcome_reason"], str(r and r["outcome_reason"]))
    check("grading is recorded as not observed, not stopped over",
          r and r["grading_observed"] is False and r["unobserved_grading"] is False,
          str(r and (r["grading_observed"], r["unobserved_grading"])))
    row = rows_by_key(ns)[(r["task"], r["candidate"])]
    check("report class is candidate, not environment", row["failure_class"] == "candidate", str(row["failure_class"]))
    check("attributed as a missing submission, not an empty patch",
          row["attribution"] == "no_submission", str(row["attribution"]))
    check("not recorded as resolved", row["resolved"] is False, str(row["resolved"]))


def test_no_submission_allows_the_next_planned_run(tmp):
    print("\n[D15] a clean missing submission does NOT cancel the other candidate's runs")
    ns = H.run_cells(tmp / "d15", dispatch=True, server_healthy=True, persisted_error=NO_SUBMIT,
                     skip_grading=True)
    n = H.counts()["evaluations"]
    check("dispatch continued past the first run", n > 1, f"evaluations={n}")
    check("every planned run was dispatched", n == len(ns["ORDER"]), f"{n} of {len(ns['ORDER'])}")
    check("no stop reason was recorded", not ns.get("STOP_REASON"), str(ns.get("STOP_REASON")))
    both = {r["candidate"] for r in ns["RUNS"]}
    check("runs of BOTH candidates went ahead", both == {"A", "B"}, str(both))
    check("all eight rows present and attempted",
          len(ns["rows"]) == 8 and all(r["attempted"] for r in ns["rows"]),
          str(len(ns["rows"])))
    check("server stopped exactly once",
          H.counts()["server_started"] == H.counts()["server_stopped"] == 1)


def test_genuine_environment_failure_still_stops(tmp):
    print("\n[D16] a genuine environment failure still stops dispatch")
    ns = H.run_cells(tmp / "d16", dispatch=True, server_healthy=True,
                     persisted_error="Sandbox execution error: container exited during setup")
    r = first_run(ns)
    check("classified as an environment failure", r and r["outcome"] == "environment", str(r and r["outcome"]))
    check("dispatch stopped after one run", H.counts()["evaluations"] == 1, str(H.counts()["evaluations"]))
    check("stop reason names the environment", "environment failure" in (ns.get("STOP_REASON") or ""),
          str(ns.get("STOP_REASON")))


def test_environment_takes_precedence_over_no_submission(tmp):
    print("\n[D17] environment failure wins when it occurs WITH a missing submission")
    ns = H.run_cells(tmp / "d17", dispatch=True, server_healthy=True, persisted_error=NO_SUBMIT,
                     escaped_error="Failed to apply test_patch: git apply failed (1): patch does not apply")
    r = first_run(ns)
    check("environment wins over the candidate outcome",
          r and r["outcome"] == "environment", str(r and r["outcome"]))
    check("not charged to the candidate", r and not r["candidate_error"])
    check("reason records both sources", r and "also" in r["outcome_reason"], str(r and r["outcome_reason"]))
    check("dispatch stopped", H.counts()["evaluations"] == 1, str(H.counts()["evaluations"]))


def test_cleanup_failure_still_stops_on_no_submission(tmp):
    print("\n[D18] a leaked sandbox stops dispatch even when the run is only a missing submission")
    ns = H.run_cells(tmp / "d18", dispatch=True, server_healthy=True, persisted_error=NO_SUBMIT,
                     leak_sandbox=True)
    r = first_run(ns)
    check("still classified as a candidate outcome", r and r["outcome"] == "candidate", str(r and r["outcome"]))
    check("cleanup was not confirmed", r and r["cleanup_ok"] is False, str(r and r["cleanup_ok"]))
    check("dispatch stopped on cleanup, not on classification",
          H.counts()["evaluations"] == 1 and "cleanup" in (ns.get("STOP_REASON") or ""),
          f"evals={H.counts()['evaluations']} stop={ns.get('STOP_REASON')}")
    rows = ns["rows"]
    check("all eight planned rows still present after the early stop", len(rows) == 8, str(len(rows)))
    check("seven rows carry the stop reason",
          sum(1 for r2 in rows if r2["attempted"] is False) == 7, str(rows and len(rows)))
    check("unattempted rows are not scored",
          all(r2["resolved"] == "unavailable" for r2 in rows if r2["attempted"] is False))


def test_environment_cause_inside_the_same_message_wins(tmp):
    print("\n[D19] one string naming BOTH a real environment cause and the missing submission")
    # Pins the ORDER of the checks inside _classify_one, which D17 cannot: there the two causes
    # arrive as two separate sources and _PRECEDENCE decides. Here they are one string, so only the
    # position of the missing-submission tier relative to _ENVIRONMENT_MARKERS can produce the
    # right answer.
    ns = H.run_cells(tmp / "d19", dispatch=True, server_healthy=True, skip_grading=True,
                     persisted_error="Sandbox execution error: no such file or directory; "
                                     + NO_SUBMIT)
    r = first_run(ns)
    check("the named environment cause wins inside one message",
          r and r["outcome"] == "environment", str(r and (r["outcome"], r["outcome_reason"])))
    check("dispatch stopped", H.counts()["evaluations"] == 1, str(H.counts()["evaluations"]))


def main() -> int:
    import tempfile
    if os.environ.get("NB_TARGET") != "compare":
        print("NB_TARGET must be 'compare'"); return 1
    tests = [test_persisted_context_error, test_persisted_environment_error,
             test_grading_never_starts, test_server_health_failure,
             test_cleanup_failure, test_cleanup_ignores_unrelated_sandboxes,
             test_early_stop_full_report, test_unexplained_bad_request_not_candidate,
             test_zero_passes_is_a_result,
             test_control_missing_xml, test_control_malformed_xml,
             test_control_empty_xml, test_control_all_skipped,
             test_control_unrelated_only, test_control_missing_target,
             test_control_duplicate_nodes, test_control_evidence_persisted_per_arm,
             test_control_target_outside_saved_map,
             test_control_teardown_raises, test_control_teardown_raises_but_cleans,
             test_control_teardown_leaks,
             test_control_unrelated_sandbox_not_blamed,
             test_precondition_teardown_also_gated,
             test_patch_creation_failure_is_named,
             test_baseline_patch_rc_is_not_zero,
             test_wrapped_context_error_is_candidate,
             test_environment_not_hidden_by_candidate,
             test_no_submission_is_a_candidate_outcome,
             test_no_submission_allows_the_next_planned_run,
             test_genuine_environment_failure_still_stops,
             test_environment_takes_precedence_over_no_submission,
             test_cleanup_failure_still_stops_on_no_submission,
             test_environment_cause_inside_the_same_message_wins]
    with tempfile.TemporaryDirectory() as td:
        for fn in tests:
            try:   # counts are re-created by make_env inside each run_cells call
                fn(Path(td))
            except Exception as e:
                import traceback
                check(fn.__name__ + " crashed", False, f"{type(e).__name__}: {e}")
                traceback.print_exc()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
