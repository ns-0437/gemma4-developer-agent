"""Tests for scripts/review_stage1.py, over synthetic artifact trees.

Each case builds a Stage-1 artifact directory shaped like the real download, runs the reviewer as a
subprocess, and asserts on its exit code and its JSON report. The reviewer executes the pinned
notebook's own REPORT cell, so these also exercise that path.

Cases required by review:
  [V1] valid graded source patch            -> Stage 1 passed, recovery unproven without a link
  [V2] missing submission                   -> ungraded candidate outcome, instrument still valid
  [V3] empty or absent patch                -> not passed, even with a grade
  [V4] failed controls                      -> instrument not valid
  [V5] missing trace                        -> reliability unreviewable, recovery unproven
  [V6] early termination (no run record)     -> not passed, reported as such
  [V7] artifact hash mismatch                -> review aborts
Plus:
  [V8] a scratch-only or test-only patch is not a source patch
  [V9] recovery observed when a rejection is followed by a different accepted op naming a changed path
  [V2b] missing submission as the only failing gate item (covers that line on its own)
  [V9c] a different accepted operation with no link to a changed path -> recovery unproven
  [N1]  read-only success after a rejection             -> never recovery
  [N2]  unrelated same-basename file                    -> not an exact match
  [N2b] exact match without operation-level evidence    -> attribution unproven
  [N9]  accepted write_file acknowledgment               -> not proof of a byte change
  [N3]  absent agent_patch_size, [N3b] wrong type       -> patch not accepted
  [N4]  header-only, [N4b] malformed hunk, [N4c] bad counts -> not syntactically valid
  [N8]  graded with exit 2, [N8b] the -1 sentinel        -> not a verdict
  [N5]  agent-only provenance                           -> graded path not verified
  [N6]  duplicate control arms                          -> review aborts
  [N7]  off-plan run, [N7b] mismatched manifest order   -> review aborts
  [V10] the reviewer refuses to write inside the artifact tree

Run:  python scripts/test_review_stage1.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWER = ROOT / "scripts" / "review_stage1.py"
NB = ROOT / "notebooks" / "stage1" / "stage1.ipynb"
TASK = "rich_3278"
CAND = "R"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


# A syntactically valid single-hunk patch: the header counts match the body it carries
# (3 context/removed lines old, 3 context/added lines new).
SOURCE_PATCH = (
    "diff --git a/rich/ansi.py b/rich/ansi.py\n"
    "--- a/rich/ansi.py\n+++ b/rich/ansi.py\n"
    "@@ -10,3 +10,3 @@\n"
    " import re\n"
    "-old line\n"
    "+new line\n"
    " tail\n"
)
TEST_ONLY_PATCH = (
    "diff --git a/tests/test_ansi.py b/tests/test_ansi.py\n"
    "--- a/tests/test_ansi.py\n+++ b/tests/test_ansi.py\n"
    "@@ -1,1 +1,1 @@\n-a\n+b\n"
)
HEADER_ONLY_PATCH = (
    "diff --git a/rich/ansi.py b/rich/ansi.py\n"
    "--- a/rich/ansi.py\n+++ b/rich/ansi.py\n"
)
MALFORMED_HUNK_PATCH = (
    "diff --git a/rich/ansi.py b/rich/ansi.py\n"
    "--- a/rich/ansi.py\n+++ b/rich/ansi.py\n"
    "@@ not-a-hunk-header @@\n-a\n+b\n"
)
BAD_COUNT_PATCH = (
    "diff --git a/rich/ansi.py b/rich/ansi.py\n"
    "--- a/rich/ansi.py\n+++ b/rich/ansi.py\n"
    "@@ -10,7 +10,7 @@\n-old line\n+new line\n"
)


def trace(steps):
    return {"schema_version": "9", "agent": {"name": "t", "version": "1"},
            "steps": steps, "final_metrics": {"total_prompt_tokens": 10,
                                              "total_completion_tokens": 5}}


REJECT_OBS = {"content": json.dumps({"error": "Invoking `edit_file()` failed as the following "
                                              "mandatory input parameters are not present:\nold_string"})}
OK_OBS = {"content": json.dumps({"status": "ok", "stdout": "written", "exit_code": 0})}
READ_OBS = {"content": json.dumps({"status": "ok", "filepath": "rich/ansi.py",
                                   "content": "import re\n"})}


def edit_ok(path="rich/ansi.py", diff="@@ -10,3 +10,3 @@\n-old line\n+new line\n"):
    """write_file / edit_file success as swegemma reports it, with its own change evidence."""
    return {"content": json.dumps({"status": "ok", "filepath": path, "occurrences": 1,
                                   "strategy": "exact", "diff": diff, "is_truncated": False})}


def write_ok(path="rich/ansi.py", size=42):
    return {"content": json.dumps({"status": "ok", "filepath": path, "size": size})}


def edit_ok_no_evidence(path="rich/ansi.py"):
    """Accepted, names the path, but carries no diff: evidence is unavailable."""
    return {"content": json.dumps({"status": "ok", "filepath": path, "occurrences": 1})}


def build(tmp: Path, *, patch=SOURCE_PATCH, grading=True, exit_code=0, resolved=True,
          persisted_error=None, controls_agree=True, with_trace=True, with_run=True,
          trace_steps=None, patch_size="auto", phases=("agent", "grading"),
          duplicate_controls=False, run_order=None, extra_runs=(), manifest_tasks=None) -> Path:
    art = tmp / "artifacts"
    res = art / "pilot"
    d = res / f"{CAND}__{TASK}"
    (d / "patches").mkdir(parents=True, exist_ok=True)
    (d / "traces").mkdir(exist_ok=True)
    (d / "test_outputs").mkdir(exist_ok=True)
    if patch:
        (d / "patches" / f"{TASK}.patch").write_text(patch, encoding="utf-8")
    (d / "test_outputs" / f"{TASK}.log").write_text("1 passed", encoding="utf-8")
    if with_trace:
        steps = trace_steps if trace_steps is not None else [
            {"step_id": 1, "source": "system", "message": "sys"},
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "read_file", "arguments": {"filepath": "rich/ansi.py"}}],
             "observation": OK_OBS},
        ]
        (d / "traces" / f"trace_{TASK}.json").write_text(json.dumps(trace(steps)), encoding="utf-8")
    record = {"instance_id": TASK, "repo": "Textualize/rich", "resolved": resolved,
              "test_exit_code": exit_code, "duration_seconds": 100.0,
              "error": persisted_error, "tool_calls": 5}
    if patch_size == "auto":
        record["agent_patch_size"] = len(patch)
    elif patch_size is not None:            # an explicit wrong value or wrong type
        record["agent_patch_size"] = patch_size
    # patch_size None: the key is absent entirely
    (d / "task_results.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    runs = []
    if with_run:
        runs.append({
            "task": TASK, "candidate": CAND, "dir": str(d), "wall_s": 120.0,
            "agent_phase_s": [110.0], "grading_phase_s": [10.0] if grading else [],
            "agent_loop_s": [100.0],
            "setup_provenance": [{"phase": ph, "provenance_ok": True} for ph in phases],
            "phase_status": {"agent": "passed", "grading": "passed" if grading else "not_attempted"},
            "provenance_failed": False, "candidate_error": False, "environment_error": False,
            "unobserved_grading": False, "outcome": "ok", "outcome_reason": "",
            "grading_observed": grading, "persisted_error": persisted_error,
            "n_persisted_results": 1, "cleanup_ok": True, "owned_sandboxes": [],
            "both_setup_imports_verified": True, "error": None, "elapsed_min_at_start": 20.0,
        })
    runs = list(runs) + list(extra_runs)
    (res / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    arms = ["baseline", "reference"] + (["baseline"] if duplicate_controls else [])
    (res / "control_recheck.json").write_text(json.dumps([
        {"task": TASK, "arm": arm, "agrees_with_saved": controls_agree, "cleanup_ok": True,
         "pytest_exit": 1 if arm == "baseline" else 0}
        for arm in arms]), encoding="utf-8")
    (res / "preconditions.json").write_text(json.dumps(
        [{"task": TASK, "ok": True, "provenance_ok": True}]), encoding="utf-8")
    (res.parent / "pilot_manifest.json").write_text(json.dumps({
        "tasks": manifest_tasks if manifest_tasks is not None else [TASK],
        "run_order": run_order if run_order is not None else [[TASK, CAND]],
        "budgets": {"max_time_minutes": 10.0}}), encoding="utf-8")
    return art


def run_reviewer(art: Path, out: Path, extra=None):
    cmd = [sys.executable, str(REVIEWER), "--artifacts", str(art), "--out", str(out)]
    if extra:
        cmd += extra
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    rep = out / "stage1_review.json"
    data = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else None
    return p.returncode, p.stdout, data


def main() -> int:
    if not NB.exists():
        print(f"missing {NB}")
        return 1
    print(f"reviewer pinned to stage1.ipynb sha256 "
          f"{hashlib.sha256(NB.read_bytes()).hexdigest()[:16]}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("\n[V1] valid graded source patch")
        art = build(tmp / "v1")
        rc, out, data = run_reviewer(art, tmp / "v1" / "report")
        check("exit 0", rc == 0, f"rc={rc}\n{out[-500:]}")
        check("stage 1 passed", data and data["stage1_passed"] is True)
        check("instrument valid", data and data["instrument_validity"]["valid"] is True)
        check("valid source patch recognised", data and data["task_performance"]["valid_source_patch"])
        check("source path listed", data and data["task_performance"]["patch"]["source_paths"] == ["rich/ansi.py"])
        check("recovery unproven without a rejection",
              data and data["recovery"]["verdict"] == "recovery unproven",
              str(data and data["recovery"]))
        check("report written outside the artifacts", not (art / "stage1_review.json").exists())

        print("\n[V2] missing submission")
        art = build(tmp / "v2", patch="", grading=False, resolved=False, exit_code=-1,
                    persisted_error="Agent completed execution without calling submit_patch.")
        rc, out, data = run_reviewer(art, tmp / "v2" / "report")
        check("exit 1 (not passed)", rc == 1, f"rc={rc}")
        check("flagged as a missing submission", data and data["candidate_reliability"]["missing_submission"])
        check("reported as an ungraded candidate outcome",
              "UNGRADED CANDIDATE OUTCOME" in out)
        check("instrument NOT blamed: controls and provenance still pass",
              data and data["instrument_validity"]["checks"]["controls_agree"] is True
              and data["instrument_validity"]["checks"]["provenance_not_failed"] is True)
        check("no solve claimed", data and data["task_performance"]["valid_source_patch"] is False)

        print("\n[N10] an absent missing-submission message is not proof submit_patch was called")
        # The default fixture trace contains no submit_patch call and no missing-submission message.
        # The reviewer must report the observed count rather than inferring a submission.
        art = build(tmp / "n10")
        rc, out, data = run_reviewer(art, tmp / "n10" / "report")
        check("the missing-submission MESSAGE is absent",
              data and data["candidate_reliability"]["missing_submission_message"] is False)
        check("the observed submit_patch count is 0",
              data and data["candidate_reliability"]["submit_patch_calls"] == 0,
              str(data and data["candidate_reliability"].get("submit_patch_calls")))
        check("the evidence line says it was never called",
              data and "NEVER called" in data["candidate_reliability"]["submission_evidence"],
              str(data and data["candidate_reliability"].get("submission_evidence")))
        check("the count is NOT gated on, because the harness grades a fallback diff",
              data and "submit_patch was actually called" not in data["stage1_gate"],
              str(data and list(data["stage1_gate"])))

        print("\n[N11] a real submit_patch call is counted")
        steps = [{"step_id": 2, "source": "agent",
                  "tool_calls": [{"function_name": "submit_patch", "arguments": {}}],
                  "observation": OK_OBS}]
        art = build(tmp / "n11", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "n11" / "report")
        check("counted once", data and data["candidate_reliability"]["submit_patch_calls"] == 1,
              str(data and data["candidate_reliability"].get("submit_patch_calls")))
        check("evidence says it was called",
              data and "was called 1 time" in data["candidate_reliability"]["submission_evidence"])

        print("\n[N12] the three instrument states are distinguished")
        art = build(tmp / "n12", grading=False, phases=("agent",), exit_code=-1, resolved=False)
        rc, out, data = run_reviewer(art, tmp / "n12" / "report")
        check("state is grading_path_unobserved",
              data and data["instrument_state"]["state"] == "grading_path_unobserved",
              str(data and data["instrument_state"]))
        check("no check that ran came back false",
              data and data["instrument_state"]["failed_checks_that_ran"] == [],
              str(data and data["instrument_state"]["failed_checks_that_ran"]))
        check("the note says unexercised, not faulty",
              data and "not a demonstrated fault" in data["instrument_state"]["note"])
        check("Stage 1 still NOT passed", data and data["stage1_passed"] is False)

        art = build(tmp / "n12b", controls_agree=False)
        rc, out, data = run_reviewer(art, tmp / "n12b" / "report")
        check("a control that ran and disagreed is a demonstrated failure",
              data and data["instrument_state"]["state"] == "demonstrated_failure",
              str(data and data["instrument_state"]["state"]))
        check("the failing check is named",
              data and "controls_agree" in data["instrument_state"]["failed_checks_that_ran"])

        art = build(tmp / "n12c")
        rc, out, data = run_reviewer(art, tmp / "n12c" / "report")
        check("a clean run reports observed_checks_passed",
              data and data["instrument_state"]["state"] == "observed_checks_passed",
              str(data and data["instrument_state"]["state"]))

        print("\n[V3] graded but empty patch")
        art = build(tmp / "v3", patch="", resolved=False, exit_code=1)
        rc, out, data = run_reviewer(art, tmp / "v3" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("gate fails on the source patch",
              data and data["stage1_gate"]["valid non-empty source patch"] is False)
        check("grading still recorded as observed",
              data and data["stage1_gate"]["grading exercised"] is True)

        print("\n[V4] failed controls")
        art = build(tmp / "v4", controls_agree=False)
        rc, out, data = run_reviewer(art, tmp / "v4" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("instrument marked not valid", data and data["instrument_validity"]["valid"] is False)
        check("the failing check is named",
              data and data["instrument_validity"]["checks"]["controls_agree"] is False)
        check("stage 1 not passed", data and data["stage1_passed"] is False)

        print("\n[V5] missing trace")
        art = build(tmp / "v5", with_trace=False)
        rc, out, data = run_reviewer(art, tmp / "v5" / "report")
        check("trace absence recorded", data and data["candidate_reliability"]["trace_present"] is False)
        check("recovery unproven", data and data["recovery"]["verdict"] == "recovery unproven")
        check("reason names the missing trace", data and data["recovery"].get("reason") == "no trace",
              str(data and data["recovery"].get("reason")))

        print("\n[V6] early termination, no run record")
        art = build(tmp / "v6", with_run=False)
        rc, out, data = run_reviewer(art, tmp / "v6" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("instrument not valid", data and data["instrument_validity"]["valid"] is False)
        check("absence of a run record is named",
              data and any("no run record" in n for n in data["instrument_validity"]["notes"]))
        check("no performance result claimed",
              data and data["task_performance"]["valid_source_patch"] is False
              and data["grading"]["observed"] is False,
              str(data and data["task_performance"].get("verdict")))

        print("\n[V7] artifact hash mismatch")
        art = build(tmp / "v7")
        rc, out, data = run_reviewer(art, tmp / "v7" / "report",
                                     extra=["--expect-notebook-sha256", "0" * 64])
        check("review aborts with exit 3", rc == 3, f"rc={rc}")
        check("the mismatch is explained", "notebook hash mismatch" in out)
        check("arming is named as the reason the hash moves", "Arming the notebook changes" in out)
        check("no report was written", data is None)

        print("\n[V8] a test-only patch is not a source patch")
        art = build(tmp / "v8", patch=TEST_ONLY_PATCH, resolved=False, exit_code=1)
        rc, out, data = run_reviewer(art, tmp / "v8" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("no source paths", data and data["task_performance"]["patch"]["source_paths"] == [])
        check("test path recognised as such",
              data and data["task_performance"]["patch"]["test_paths"] == ["tests/test_ansi.py"])
        check("gate fails", data and data["stage1_passed"] is False)

        print("\n[V9] recovery observed, with a link to a changed source path")
        steps = [
            {"step_id": 1, "source": "system", "message": "sys"},
            # The rejection is on write_file and the recovery is a DIFFERENT tool, edit_file, whose
            # own reported diff is before/after evidence. Note: candidate R's documented ladder runs
            # edit_file -> write_file -> run_command, and neither of those later steps can supply
            # before/after evidence, so on a real R run the best reachable verdict is
            # "consistent with recovery; attribution unproven". That is the honest ceiling.
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "write_file",
                             "arguments": {"filepath": "rich/ansi.py"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "old_string": "old line",
                                           "new_string": "new line"}}],
             "observation": edit_ok()},
        ]
        art = build(tmp / "v9", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "v9" / "report")
        check("exit 0", rc == 0, f"rc={rc}")
        check("recovery observed", data and data["recovery"]["verdict"] == "recovery observed",
              str(data and data["recovery"]))
        check("the link names the changed path exactly",
              data and data["recovery"]["link"]
              and data["recovery"]["link"][0]["target"] == "rich/ansi.py",
              str(data and data["recovery"]["link"]))
        check("the accepted operation is a DIFFERENT modifying tool",
              data and data["recovery"]["candidates"][0]["tool"] == "edit_file",
              str(data and data["recovery"]["candidates"]))
        check("before/after change evidence was required and found",
              data and "diff" in str(data["recovery"]["link"][0]["change_evidence"]),
              str(data and data["recovery"]["link"][0]["change_evidence"]))

        print("\n[V9b] same tool re-accepted is NOT recovery")
        steps_same = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "edit_file", "arguments": {"filepath": "rich/ansi.py"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "old_string": "a",
                                           "new_string": "b"}}],
             "observation": OK_OBS},
        ]
        art = build(tmp / "v9b", trace_steps=steps_same)
        rc, out, data = run_reviewer(art, tmp / "v9b" / "report")
        check("recovery unproven when the same tool is retried",
              data and data["recovery"]["verdict"] == "recovery unproven",
              str(data and data["recovery"].get("reason")))

        print("\n[V9c] a different accepted op with NO link to a changed path is unproven")
        steps_nolink = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "new_string": "x"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "run_command",
                             "arguments": {"command": "sed -i s/a/b/ rich/other.py"}}],
             "observation": OK_OBS},
        ]
        art = build(tmp / "v9c", trace_steps=steps_nolink)
        rc, out, data = run_reviewer(art, tmp / "v9c" / "report")
        check("a rejection and a different accepted modifying op were both found",
              data and data["recovery"]["rejections"] and data["recovery"]["candidates"],
              str(data and data["recovery"]))
        check("but the verdict is recovery unproven",
              data and data["recovery"]["verdict"] == "recovery unproven",
              str(data and data["recovery"]["verdict"]))
        check("the reason names the missing exact path match",
              data and "exactly" in str(data["recovery"].get("reason")),
              str(data and data["recovery"].get("reason")))
        check("no link was recorded", data and not data["recovery"]["link"])

        print("\n[N1] read-only success after a rejection is NOT recovery")
        steps = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "new_string": "x"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "read_file",
                             "arguments": {"filepath": "rich/ansi.py"}}],
             "observation": READ_OBS},
        ]
        art = build(tmp / "n1", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "n1" / "report")
        check("the read is recorded as read-only, not as a candidate",
              data and [c["tool"] for c in data["recovery"]["read_only_after"]] == ["read_file"]
              and data["recovery"]["candidates"] == [],
              str(data and data["recovery"]))
        check("verdict is recovery unproven",
              data and data["recovery"]["verdict"] == "recovery unproven",
              str(data and data["recovery"]["verdict"]))
        check("the reason says a read cannot be a recovery write",
              data and "read never changes a file" in str(data["recovery"].get("reason")),
              str(data and data["recovery"].get("reason")))

        print("\n[N2] an unrelated file with the SAME basename does not qualify")
        steps = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "new_string": "x"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "write_file",
                             "arguments": {"filepath": "docs/ansi.py", "content": "x"}}],
             "observation": write_ok(path="docs/ansi.py")},
        ]
        art = build(tmp / "n2", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "n2" / "report")
        check("no exact path match", data and data["recovery"].get("exact_path_matches") == [])
        check("the same-basename match is recorded and rejected",
              data and data["recovery"].get("same_basename_only"),
              str(data and data["recovery"].get("same_basename_only")))
        check("verdict is recovery unproven",
              data and data["recovery"]["verdict"] == "recovery unproven")
        check("the reason says a basename match is not sufficient",
              data and "not \nsufficient" not in str(data["recovery"]["reason"])
              and "sufficient" in str(data["recovery"]["reason"]),
              str(data and data["recovery"]["reason"]))

        print("\n[N2b] exact path match but no operation-level evidence")
        steps = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "write_file",
                             "arguments": {"filepath": "rich/ansi.py", "content": "x"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "old_string": "a",
                                           "new_string": "b"}}],
             "observation": edit_ok_no_evidence()},
        ]
        art = build(tmp / "n2b", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "n2b" / "report")
        check("the exact path matched", data and data["recovery"]["exact_path_matches"])
        check("verdict is 'consistent with recovery; attribution unproven'",
              data and data["recovery"]["verdict"] == "consistent with recovery; attribution unproven",
              str(data and data["recovery"]["verdict"]))
        check("the reason refuses to infer cause from the final diff",
              data and "final \ndiff" not in str(data["recovery"]["reason"])
              and "does not establish which operation" in str(data["recovery"]["reason"]),
              str(data and data["recovery"]["reason"]))

        print("\n[N9] an accepted write_file is an acknowledgment, not proof of a byte change")
        # The tool reports only filepath and size. A no-op write of identical bytes produces the same
        # acknowledgment, so it cannot establish that anything changed.
        steps = [
            {"step_id": 2, "source": "agent",
             "tool_calls": [{"function_name": "edit_file",
                             "arguments": {"filepath": "rich/ansi.py", "new_string": "x"}}],
             "observation": REJECT_OBS},
            {"step_id": 3, "source": "agent",
             "tool_calls": [{"function_name": "write_file",
                             "arguments": {"filepath": "rich/ansi.py", "content": "identical"}}],
             "observation": write_ok(size=9)},
        ]
        art = build(tmp / "n9", trace_steps=steps)
        rc, out, data = run_reviewer(art, tmp / "n9" / "report")
        check("the write is an exact path match", data and data["recovery"]["exact_path_matches"])
        check("it carries NO change evidence",
              data and data["recovery"]["exact_path_matches"][0]["change_evidence"] is None,
              str(data and data["recovery"]["exact_path_matches"][0].get("change_evidence")))
        check("it is recorded as acknowledged-only",
              data and data["recovery"].get("acknowledged_only"),
              str(data and data["recovery"].get("acknowledged_only")))
        check("verdict is 'consistent with recovery; attribution unproven'",
              data and data["recovery"]["verdict"] == "consistent with recovery; attribution unproven",
              str(data and data["recovery"]["verdict"]))
        check("the reason names the no-op-write ambiguity",
              data and "no-op write of identical bytes" in str(data["recovery"]["reason"]),
              str(data and data["recovery"]["reason"]))
        check("recovery is NOT reported as observed",
              data and data["recovery"]["verdict"] != "recovery observed")

        print("\n[N3] absent agent_patch_size")
        art = build(tmp / "n3", patch_size=None)
        rc, out, data = run_reviewer(art, tmp / "n3" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("absence recorded, not defaulted",
              data and data["task_performance"]["size_recorded"] is None
              and data["task_performance"]["size_type_ok"] is False)
        check("the patch is not accepted", data and data["task_performance"]["valid_source_patch"] is False)
        check("the gate names the size tie", data and data["stage1_gate"]["patch tied to the recorded size"] is False)
        check("but syntax is still reported as valid",
              data and data["task_performance"]["syntactically_valid"] is True)
        check("the notebook's own REPORT cell also refused the artifacts",
              data and data["instrument_validity"]["checks"]["report_cell_accepted_artifacts"] is False,
              str(data and data["instrument_validity"].get("report_cell_error")))
        check("that refusal invalidates the instrument",
              data and data["instrument_validity"]["valid"] is False
              and data["stage1_gate"]["instrument valid"] is False,
              str(data and data["instrument_validity"]["valid"]))
        check("the refusal is explained in the notes",
              data and any("REPORT cell refused" in n
                           for n in data["instrument_validity"]["notes"]),
              str(data and data["instrument_validity"]["notes"]))

        print("\n[N3b] agent_patch_size of the wrong type")
        art = build(tmp / "n3b", patch_size="117")
        rc, out, data = run_reviewer(art, tmp / "n3b" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("the wrong type is rejected",
              data and data["task_performance"]["size_type_ok"] is False
              and data["task_performance"]["size_matches"] is False)

        print("\n[N8] graded with a non-verdict exit code")
        # pytest exit 2 is an interrupted collection, not a pass/fail verdict. Everything else about
        # this run is clean, so the verdict-exit gate line is the only one that may fail.
        art = build(tmp / "n8", exit_code=2, resolved=False)
        rc, out, data = run_reviewer(art, tmp / "n8" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("the verdict-exit line is the failing one",
              data and data["stage1_gate"]["verdict exit code"] is False
              and data["stage1_gate"]["instrument valid"] is True
              and data["stage1_gate"]["grading exercised"] is True
              and data["stage1_gate"]["valid non-empty source patch"] is True
              and data["stage1_gate"]["no missing-submission message"] is True,
              str(data and data["stage1_gate"]))
        check("grading is still reported as exercised",
              data and data["grading"]["state"] == "exercised")
        check("exit code 2 is not treated as a verdict",
              data and data["grading"]["test_exit_code"] == 2
              and data["grading"]["verdict_exit"] is False)
        check("application evidence withheld without a verdict",
              data and data["task_performance"]["application_evidence"] is False)

        print("\n[N8b] the -1 grading sentinel is not a verdict")
        art = build(tmp / "n8b", exit_code=-1, resolved=False)
        rc, out, data = run_reviewer(art, tmp / "n8b" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("sentinel rejected", data and data["grading"]["verdict_exit"] is False)

        print("\n[N4] header-only patch")
        art = build(tmp / "n4", patch=HEADER_ONLY_PATCH, resolved=False, exit_code=1)
        rc, out, data = run_reviewer(art, tmp / "n4" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("not syntactically valid", data and data["task_performance"]["syntactically_valid"] is False)
        check("the missing hunk is named",
              data and any("@@" in e for e in data["task_performance"]["patch"]["syntax_errors"]),
              str(data and data["task_performance"]["patch"]["syntax_errors"]))
        check("zero changed lines", data and data["task_performance"]["patch"]["n_changed_lines"] == 0)
        check("does not count as a source change",
              data and data["task_performance"]["changes_source"] is False)

        print("\n[N4b] malformed hunk header")
        art = build(tmp / "n4b", patch=MALFORMED_HUNK_PATCH, resolved=False, exit_code=1)
        rc, out, data = run_reviewer(art, tmp / "n4b" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("not syntactically valid", data and data["task_performance"]["syntactically_valid"] is False)
        check("the malformation is named",
              data and any("malformed" in e or "@@" in e
                           for e in data["task_performance"]["patch"]["syntax_errors"]),
              str(data and data["task_performance"]["patch"]["syntax_errors"]))

        print("\n[N4c] hunk counts that disagree with the body")
        art = build(tmp / "n4c", patch=BAD_COUNT_PATCH, resolved=False, exit_code=1)
        rc, out, data = run_reviewer(art, tmp / "n4c" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("the count mismatch is named",
              data and any("counts disagree" in e
                           for e in data["task_performance"]["patch"]["syntax_errors"]),
              str(data and data["task_performance"]["patch"]["syntax_errors"]))

        print("\n[N5] agent-only provenance does not verify the graded path")
        art = build(tmp / "n5", phases=("agent",))
        rc, out, data = run_reviewer(art, tmp / "n5" / "report")
        check("exit 1", rc == 1, f"rc={rc}")
        check("agent phase observed", data and data["instrument_validity"]["checks"]["agent_provenance_observed"] is True)
        check("grading phase NOT observed",
              data and data["instrument_validity"]["checks"]["grading_provenance_observed"] is False)
        check("instrument marked not valid", data and data["instrument_validity"]["valid"] is False)
        check("the note says the graded path is not verified",
              data and any("graded path is NOT verified" in n
                           for n in data["instrument_validity"]["notes"]),
              str(data and data["instrument_validity"]["notes"]))

        print("\n[N6] duplicate control arms abort the review")
        art = build(tmp / "n6", duplicate_controls=True)
        rc, out, data = run_reviewer(art, tmp / "n6" / "report")
        check("review aborts with exit 3", rc == 3, f"rc={rc}")
        check("duplication is named, not merely warned", "duplicate control arms" in out, out[-300:])
        check("no report was written", data is None)

        print("\n[N7] an off-plan run aborts the review")
        other = {"task": "rich_9999", "candidate": "A", "dir": "x", "wall_s": 1.0,
                 "agent_phase_s": [1.0], "grading_phase_s": [], "agent_loop_s": [1.0],
                 "setup_provenance": [], "phase_status": {}, "provenance_failed": False,
                 "grading_observed": False, "persisted_error": None, "n_persisted_results": 0,
                 "cleanup_ok": True, "owned_sandboxes": [], "error": None}
        art = build(tmp / "n7", extra_runs=(other,))
        rc, out, data = run_reviewer(art, tmp / "n7" / "report")
        check("review aborts with exit 3", rc == 3, f"rc={rc}")
        check("the off-plan run is named", "outside the frozen plan" in out, out[-300:])

        print("\n[N7b] a mismatched manifest run order aborts the review")
        art = build(tmp / "n7b", run_order=[[TASK, "A"], [TASK, CAND]])
        rc, out, data = run_reviewer(art, tmp / "n7b" / "report")
        check("review aborts with exit 3", rc == 3, f"rc={rc}")
        check("the mismatch is named", "run_order" in out, out[-300:])

        print("\n[V10] the reviewer refuses to write inside the artifact tree")
        art = build(tmp / "v10")
        rc, out, data = run_reviewer(art, art / "inside")
        check("exit 2", rc == 2, f"rc={rc}")
        check("the refusal is explained", "inside the artifact tree" in out)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
