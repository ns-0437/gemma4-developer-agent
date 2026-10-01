"""Synthetic-fixture tests for scripts/review_compare_results.py.

Each fixture builds a fake downloaded-artifact tree and runs the real reviewer over it. Nothing here
talks to Kaggle and no real run is needed: the point is that the reviewer is checked out before the
eight real runs land.

  [R1]  eight complete runs
  [R2]  early stop: one run, seven not attempted, still eight rows
  [R3]  candidate, environment and grading failures stay separate
  [R4]  an ungraded side makes the pair UNDECIDED, never a win
  [R5]  failing control arm, leaked sandbox, NO_JUNIT marker
  [R6]  answer-key access graded by step/tool/access; absence is not isolation
  [R7]  a missing trace is 'audit not possible', not clean
  [R8]  eligibility: exit -1, exit 2 and provenance failure may not yield "A only"
  [R9]  the frozen plan survives a missing manifest, with zero runs and with one run
  [R10] a manifest that disagrees with the frozen plan aborts the review
  [R11] notebook drift aborts the review and names both hashes
  [R12] trace coverage: all-corrupt is UNKNOWN, mixed readable/corrupt is INCOMPLETE
  [R13] output goes to a sibling directory; the artifact tree is left byte-identical

Run:  python scripts/test_review_compare_results.py
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_compare_results as R  # noqa: E402

PASS, FAIL = [], []
TASKS = list(R.FROZEN_TASKS)
ORDER = [list(x) for x in R.FROZEN_ORDER]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


# ------------------------------------------------------------------ fixture builder
def build_tree(tmp: Path, runs, *, controls=None, preconditions=None, stop_reason=None,
               traces=None, control_files=None, manifest=True, raw_traces=None,
               manifest_order=None):
    root = tmp
    results = root / "pilot"
    results.mkdir(parents=True, exist_ok=True)
    run_records = []
    for spec in runs:
        tid, cand = spec["task"], spec["candidate"]
        d = results / f"{cand}__{tid}"
        (d / "patches").mkdir(parents=True, exist_ok=True)
        (d / "test_outputs").mkdir(parents=True, exist_ok=True)
        (d / "traces").mkdir(parents=True, exist_ok=True)
        patch = spec.get("patch", "diff --git a/rich/ansi.py b/rich/ansi.py\n"
                                  "--- a/rich/ansi.py\n+++ b/rich/ansi.py\n+fixed = True\n")
        (d / "patches" / f"{tid}.patch").write_text(patch, encoding="utf-8")
        (d / "test_outputs" / f"{tid}.log").write_text(spec.get("test_log", "1 passed"),
                                                       encoding="utf-8")
        if not spec.get("no_result_file"):
            (d / "task_results.jsonl").write_text(json.dumps({
                "instance_id": tid, "repo": "Textualize/rich",
                "resolved": spec.get("resolved", True),
                "agent_patch_size": len(patch),
                "test_exit_code": spec.get("test_exit_code", 0),
                "error": spec.get("persisted_error"),
                "duration_seconds": 9.0, "tool_calls": spec.get("tool_calls", 7),
            }) + "\n", encoding="utf-8")
        if not spec.get("no_trace"):
            tr = (traces or {}).get((tid, cand))
            (d / "traces" / f"trace_{tid}.json").write_text(
                json.dumps(tr or default_trace()), encoding="utf-8")
        run_records.append({
            "task": tid, "candidate": cand, "dir": str(d),
            "wall_s": spec.get("wall_s", 30.0),
            "agent_phase_s": spec.get("agent_phase_s", [20.0]),
            "grading_phase_s": spec.get("grading_phase_s", [6.0]),
            "agent_loop_s": spec.get("agent_loop_s", [14.0]),
            "setup_provenance": [],
            "phase_status": spec.get("phase_status", {"agent": "passed", "grading": "passed"}),
            "provenance_failed": spec.get("provenance_failed", False),
            "candidate_error": spec.get("outcome") == "candidate",
            "environment_error": spec.get("outcome") == "environment",
            "unobserved_grading": spec.get("outcome") == "unobserved_grading",
            "outcome": spec.get("outcome", "ok"),
            "outcome_reason": spec.get("outcome_reason", ""),
            "grading_observed": spec.get("grading_observed", True),
            "persisted_error": spec.get("persisted_error"),
            "n_persisted_results": 0 if spec.get("no_result_file") else 1,
            "cleanup_ok": spec.get("cleanup_ok", True),
            "owned_sandboxes": spec.get("owned_sandboxes", []),
            "both_setup_imports_verified": True,
            "error": spec.get("escaped_error"),
            "elapsed_min_at_start": 1.0,
        })
    (results / "runs.json").write_text(json.dumps(run_records, indent=2), encoding="utf-8")
    (results / "control_recheck.json").write_text(
        json.dumps(controls if controls is not None else default_controls(), indent=2),
        encoding="utf-8")
    (results / "preconditions.json").write_text(
        json.dumps(preconditions if preconditions is not None else default_preconditions(),
                   indent=2), encoding="utf-8")
    ce = results / "control_evidence"
    ce.mkdir(exist_ok=True)
    for name, body in (control_files or {}).items():
        (ce / name).write_text(body, encoding="utf-8")
    if manifest:
        (root / "pilot_manifest.json").write_text(json.dumps({
            "tasks": TASKS, "run_order": manifest_order or ORDER, "stop_reason": stop_reason,
            "budget": {"max_time_minutes": 10.0},
        }, indent=2), encoding="utf-8")
    for (tid, cand), body in (raw_traces or {}).items():
        d = results / f"{cand}__{tid}" / "traces"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"trace_{tid}.json").write_text(body, encoding="utf-8")
    return root


def default_trace(commands=None, read_file=None):
    cmds = commands or ["git grep -n strip_ansi -- '*.py'",
                        "python3 -m pytest tests/test_ansi.py -q"]
    steps = [{"step_id": i + 1,
              "tool_calls": [{"function_name": "run_command", "arguments": {"command": c}}],
              "observation": {"content": '{"status": "ok"}'}}
             for i, c in enumerate(cmds)]
    if read_file:
        steps.append({"step_id": len(steps) + 1,
                      "tool_calls": [{"function_name": "read_file",
                                      "arguments": {"filepath": read_file}}],
                      "observation": {"content": '{"status": "ok"}'}})
    return {"steps": steps,
            "final_metrics": {"total_prompt_tokens": 900, "total_completion_tokens": 40}}


def default_controls():
    out = []
    for t in TASKS:
        for arm in ("baseline", "reference"):
            out.append({"task": t, "arm": arm, "agrees_with_saved": True,
                        "pytest_exit": 1 if arm == "baseline" else 0,
                        "saved_exit": 1 if arm == "baseline" else 0,
                        "cleanup_ok": True, "owned_sandboxes": [],
                        "node_comparison": {"n_observed": 23, "n_expected": 23, "missing": [],
                                            "extra": [], "changed": [], "skipped": [],
                                            "targets_wrong": []}})
    return out


def default_preconditions():
    return [{"task": t, "ok": True, "cleanup_ok": True,
             "agent_file": "/tmp/sbx/workspace/rich/__init__.py",
             "grading_file": "/tmp/sbx/workspace/rich/__init__.py"} for t in TASKS]


def run_review(root: Path, extra=None):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = R.main([str(root)] + (extra or []))
    return buf.getvalue(), rc


def all_eight(over=None):
    over = over or {}
    runs = []
    for tid, cand in R.FROZEN_ORDER:
        spec = {"task": tid, "candidate": cand}
        spec.update(over.get((tid, cand), {}))
        runs.append(spec)
    return runs


def sec(out, start, end=None):
    part = out.split(start)[1]
    return part.split(end)[0] if end else part


def pair_lines(out):
    return [l for l in sec(out, "2. PAIRED OUTCOMES", "3. OUTCOME CLASSES").splitlines()
            if " -> " in l]


# ------------------------------------------------------------------ tests
def test_all_eight(tmp):
    print("\n[R1] eight complete runs")
    out, rc = run_review(build_tree(tmp / "r1", all_eight()))
    check("reviewer succeeded", rc == 0, str(rc))
    check("eight rows against the frozen plan",
          "planned (frozen): 8   rows produced: 8" in out, out[:400])
    check("pinned notebook hash recorded", R.LAUNCHED_NOTEBOOK_SHA256 in out)
    check("no leaderboard extrapolation",
          "leaderboard score is predicted" in out and "0.06" not in out)


def test_early_stop(tmp):
    print("\n[R2] early stop: one run, seven not attempted, eight rows")
    runs = [{"task": "rich_3278", "candidate": "A", "outcome": "environment", "resolved": False,
             "test_exit_code": -1, "persisted_error": "Sandbox execution error: device gone"}]
    out, _ = run_review(build_tree(tmp / "r2", runs, stop_reason="environment failure"))
    check("eight rows despite one run", "rows produced: 8" in out, out[:300])
    lines = pair_lines(out)
    check("four per-task pair lines", len(lines) == 4, str(lines))
    check("every pair UNDECIDED", all("UNDECIDED" in l for l in lines), str(lines))
    check("no side credited", not any("A only" in l or "B only" in l for l in lines), str(lines))
    check("skipped runs labelled not attempted",
          sum("not attempted" in l for l in lines) >= 3, str(lines))


def test_mixed_failures(tmp):
    print("\n[R3] candidate, environment and grading failures stay separate")
    over = {
        ("rich_3278", "A"): {"outcome": "candidate", "resolved": False, "test_exit_code": -1,
                             "persisted_error": "litellm.ContextWindowExceededError: maximum context length",
                             "outcome_reason": "escaped: context window"},
        ("rich_3278", "B"): {"outcome": "environment", "resolved": False, "test_exit_code": -1,
                             "persisted_error": "Failed to apply test_patch: does not apply",
                             "outcome_reason": "persisted: failed to apply test_patch"},
        ("rich_3535", "B"): {"outcome": "unobserved_grading", "grading_observed": False,
                             "grading_phase_s": [], "resolved": False, "test_exit_code": -1},
    }
    out, _ = run_review(build_tree(tmp / "r3", all_eight(over)))
    s = sec(out, "3. OUTCOME CLASSES", "4. TIMING")
    for cls in ("candidate", "environment", "unobserved_grading"):
        check(f"{cls} bucket present", cls in s, s[:400])
    check("candidate failures reported in full", "CANDIDATE FAILURES (1)" in s, s[:500])
    check("candidate failure says why it is not comparable",
          "comparable for the solve tally: no" in s, s[:700])
    check("env/provenance counted for neither", "counted for neither candidate" in s)


def test_ungraded_pair_is_undecided(tmp):
    print("\n[R4] an ungraded side makes the pair UNDECIDED, never a win")
    over = {("rich_3675", "A"): {"resolved": True, "test_exit_code": 0},
            ("rich_3675", "B"): {"outcome": "environment", "resolved": False,
                                 "no_result_file": True}}
    out, _ = run_review(build_tree(tmp / "r4", all_eight(over)))
    line = [l for l in pair_lines(out) if "rich_3675" in l]
    check("the pair is reported", bool(line), str(pair_lines(out)))
    if line:
        check("marked UNDECIDED", "UNDECIDED" in line[0], line[0])
        check("not credited to A", "A only" not in line[0], line[0])
    check("decided count excludes it", "decided pairs: 3 of 4" in out)


def test_controls_and_cleanup(tmp):
    print("\n[R5] failing control arm, leaked sandbox and NO_JUNIT marker are surfaced")
    ctl = default_controls()[:3]
    ctl[1].update({"agrees_with_saved": False, "cleanup_ok": False,
                   "owned_sandboxes": ["/tmp/swegemma_sandbox_leaked"],
                   "teardown_error": "RuntimeError: teardown blew up",
                   "junit_parse_error": "empty report",
                   "node_comparison": {"n_observed": 0, "n_expected": 23,
                                       "missing": ["test_ansi::test_decode"], "extra": [],
                                       "changed": [], "skipped": [],
                                       "targets_wrong": ["test_ansi::test_decode: ABSENT"]}})
    pre = default_preconditions()
    pre[0].update({"ok": False, "cleanup_ok": False,
                   "teardown_error": "RuntimeError: probe failed"})
    out, _ = run_review(build_tree(tmp / "r5", all_eight(), controls=ctl, preconditions=pre,
                                   control_files={"rich_3278__reference.NO_JUNIT.txt": "none"}))
    s = sec(out, "5. CONTROLS", "6. PER-RUN CLEANUP")
    check("partial control sequence flagged", "partial control sequence" in s, s[:400])
    check("failing arm shown", "agrees_with_saved=False" in s, s[:500])
    check("teardown error surfaced", "teardown_error" in s, s[:500])
    check("leaked sandbox named", "swegemma_sandbox_leaked" in s, s[:500])
    check("targets_wrong surfaced", "targets_wrong" in s, s[:600])
    check("NO_JUNIT marker counted", "NO readable JUnit report: 1" in s, s[:700])
    check("precondition failure surfaced", "ok=False" in s, s[:900])


def test_answer_key_audit(tmp):
    print("\n[R6] answer-key access graded by step/tool/access; absence is not isolation")
    traces = {
        ("rich_3278", "A"): default_trace(["cat /tmp/gold.patch"]),
        ("rich_3278", "B"): default_trace(["git grep -n decode -- '*.py'"],
                                          read_file="tests/test_ansi.py"),
    }
    out, _ = run_review(build_tree(tmp / "r6", all_eight(), traces=traces))
    s = sec(out, "8. ANSWER-KEY ACCESS AUDIT", "9. WHAT THIS REVIEW")
    check("suspected access reported for the gold-patch read",
          "SUSPECTED ANSWER-KEY ACCESS" in s, s[:1000])
    check("step, tool and access level reported",
          "step 1" in s and "run_command" in s and ("[read]" in s or "[requested]" in s), s[:1000])
    check("ordinary repository test reads listed separately",
          "ordinary repository test reads" in s, s[:1000])
    check("clean run says not observed",
          "suspected answer-key access: not observed" in s, s[:1000])
    check("absence is not isolation", "NOT proof of isolation" in s, s[:700])
    check("subprocess caveat stated", "filesystem" in s, s[:700])


def test_missing_trace_is_unknown(tmp):
    print("\n[R7] a missing trace is 'audit not possible', not clean")
    out, _ = run_review(build_tree(tmp / "r7", all_eight({("rich_3942", "A"): {"no_trace": True}})))
    s = sec(out, "8. ANSWER-KEY ACCESS AUDIT")
    line = [l for l in s.splitlines() if "A/rich_3942" in l]
    check("missing trace reported", any("audit not possible" in l for l in line), str(line))
    check("explicitly not called clean", any("not clean" in l for l in line), str(line))


def test_eligibility_rules(tmp):
    print("\n[R8] exit -1, exit 2 and provenance failure may not produce 'A only'")
    cases = [
        ("exit -1 / environment",
         {"outcome": "environment", "resolved": False, "test_exit_code": -1,
          "persisted_error": "Sandbox execution error: gone"}),
        ("exit 2 / environment",
         {"outcome": "environment", "resolved": False, "test_exit_code": 2,
          "persisted_error": "Evaluation error: collection failed"}),
        ("provenance failure",
         {"provenance_failed": True, "resolved": False, "test_exit_code": 1,
          "phase_status": {"agent": "passed", "grading": "failed"}}),
    ]
    for i, (label, bspec) in enumerate(cases):
        over = {("rich_3675", "A"): {"resolved": True, "test_exit_code": 0},
                ("rich_3675", "B"): bspec}
        out, _ = run_review(build_tree(tmp / f"r8_{i}", all_eight(over)))
        line = [l for l in pair_lines(out) if "rich_3675" in l]
        check(f"{label}: not credited to A", bool(line) and "A only" not in line[0], str(line))
        check(f"{label}: pair is UNDECIDED", bool(line) and "UNDECIDED" in line[0], str(line))
        table = sec(out, "1. ALL PLANNED RUNS", "2. PAIRED OUTCOMES")
        brow = [l for l in table.splitlines()
                if "rich_3675" in l and len(l.split()) > 1 and l.split()[1] == "B"]
        check(f"{label}: table agrees with the pairing (comparable=NO)",
              bool(brow) and "NO" in brow[0], str(brow))


def test_eligibility_unit(tmp):
    print("\n[R8b] each disqualifying rule in isolation, with nothing else wrong")
    # Isolation matters: in R8 every case also carried an environment class, which masked the
    # exit-code rules. Here the ONLY defect is the one under test.
    def row(**over):
        base = {"attempted": True, "test_exit_code": 0, "grading_ran": True,
                "failure_class": "none", "cleanup_ok": True, "resolved": True}
        base.update(over)
        return base

    check("a clean row is comparable", R.comparison_eligible(row())[0])
    for label, over, expect in [
        ("sentinel exit -1", {"test_exit_code": -1}, "sentinel"),
        ("interrupted exit 2", {"test_exit_code": 2}, "collection error or interrupted"),
        ("internal error exit 3", {"test_exit_code": 3}, "collection error or interrupted"),
        ("no tests collected exit 5", {"test_exit_code": 5}, "not a pass/fail verdict"),
        ("no grade recorded", {"test_exit_code": "unavailable"}, "no grade recorded"),
        ("grading not observed", {"grading_ran": False}, "grading not observed"),
        ("environment class", {"failure_class": "environment"}, "not attributable"),
        ("provenance class", {"failure_class": "provenance"}, "not attributable"),
        ("unobserved grading class", {"failure_class": "unobserved_grading"}, "not attributable"),
        ("cleanup unconfirmed", {"cleanup_ok": False}, "cleanup unconfirmed"),
        ("resolved flag missing", {"resolved": "unavailable"}, "resolved flag missing"),
        ("not attempted", {"attempted": False}, "not attempted"),
    ]:
        ok, why = R.comparison_eligible(row(**over))
        check(f"{label} is NOT comparable", not ok, f"eligible with {over}")
        check(f"{label} reason names the cause", expect in why, f"{why!r}")
    # a candidate failure that still produced a real verdict stays comparable, and is also
    # reported in its own section; it is not silently dropped
    ok, _ = R.comparison_eligible(row(failure_class="candidate", resolved=False, test_exit_code=1))
    check("a candidate failure with a real verdict remains comparable", ok)


def test_frozen_plan_without_manifest(tmp):
    print("\n[R9] the frozen plan survives a missing manifest, with zero runs and with one")
    out, rc = run_review(build_tree(tmp / "r9a", [], manifest=False))
    check("zero runs, no manifest: still eight rows", "rows produced: 8" in out, out[:400])
    check("zero runs: reviewer still succeeds", rc == 0, str(rc))
    check("zero runs: four pair lines", len(pair_lines(out)) == 4, str(pair_lines(out)))
    one = [{"task": "rich_3535", "candidate": "B", "resolved": True, "test_exit_code": 0}]
    out2, rc2 = run_review(build_tree(tmp / "r9b", one, manifest=False))
    check("one run, no manifest: still eight rows", "rows produced: 8" in out2, out2[:400])
    check("one run: the plan is not the observed set", all(t in out2 for t in TASKS), out2[:600])
    check("one run: reviewer still succeeds", rc2 == 0, str(rc2))


def test_manifest_disagreement_aborts(tmp):
    print("\n[R10] a manifest that disagrees with the frozen plan aborts the review")
    bad = [["rich_3278", "A"], ["rich_3278", "B"]]
    out, rc = run_review(build_tree(tmp / "r10", all_eight(), manifest_order=bad))
    check("review aborted", rc == 3, str(rc))
    check("abort names the disagreement", "disagrees with the frozen launch plan" in out, out[:400])
    check("both plans printed", "frozen   :" in out and "manifest :" in out, out[:700])


def test_notebook_drift_aborts(tmp):
    print("\n[R11] notebook drift aborts the review and names both hashes")
    original = R.LAUNCHED_NOTEBOOK_SHA256
    try:
        R.LAUNCHED_NOTEBOOK_SHA256 = "0" * 64
        out, rc = run_review(build_tree(tmp / "r11", all_eight()))
        check("review aborted on drift", rc == 3, str(rc))
        check("abort names notebook drift", "notebook drift" in out, out[:400])
        check("expected hash printed", "0" * 64 in out, out[:600])
        check("found hash printed", original in out, out[:600])
    finally:
        R.LAUNCHED_NOTEBOOK_SHA256 = original


def test_trace_coverage(tmp):
    print("\n[R12] all-corrupt traces are UNKNOWN; mixed readable/corrupt is INCOMPLETE")
    root = build_tree(tmp / "r12", all_eight(),
                      raw_traces={("rich_3278", "A"): "{not json at all"})
    (root / "pilot" / "B__rich_3278" / "traces" / "trace_extra.json").write_text(
        "{{{corrupt", encoding="utf-8")
    out, _ = run_review(root)
    s = sec(out, "8. ANSWER-KEY ACCESS AUDIT")
    a_line = [l for l in s.splitlines() if "A/rich_3278" in l]
    b_line = [l for l in s.splitlines() if "B/rich_3278" in l]
    check("all-corrupt run is COVERAGE UNKNOWN",
          any("COVERAGE UNKNOWN" in l for l in a_line), str(a_line))
    check("unknown is not called clean", "absence of evidence" in s, s[:1200])
    check("mixed run is INCOMPLETE COVERAGE",
          any("INCOMPLETE COVERAGE" in l for l in b_line), str(b_line))
    check("coverage tally reported", "coverage: {" in s, s[-500:])
    check("no isolation statement for those runs", "No isolation statement can" in s, s[-600:])


def test_output_is_sibling_and_artifacts_untouched(tmp):
    print("\n[R13] output goes to a sibling directory; artifacts left byte-identical")
    root = build_tree(tmp / "r13", all_eight())

    def snapshot(p):
        return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in sorted(p.rglob("*")) if f.is_file()}

    before = snapshot(root)
    out, rc = run_review(root)
    after = snapshot(root)
    check("reviewer succeeded", rc == 0, str(rc))
    check("artifact tree byte-identical", before == after,
          str(sorted(set(after) ^ set(before))[:5]))
    sib = root.parent / (root.name + "_review")
    check("output directory is a sibling, outside the artifacts", sib.exists(), str(sib))
    check("summary written there", (sib / "review_summary.json").exists())
    check("csv written there", (sib / "pilot_results.csv").exists())
    check("output states the artifacts were read unmodified",
          "artifacts read (unmodified)" in out, out[-600:])
    out2, rc2 = run_review(root, extra=["--out", str(root / "inside")])
    check("refuses to write inside the artifact tree", rc2 == 2, str(rc2))
    check("refusal explains why", "must stay untouched" in out2, out2[:400])
    summary = json.loads((sib / "review_summary.json").read_text(encoding="utf-8"))
    check("summary records the pinned notebook hash",
          summary.get("pinned_notebook_sha256") == R.LAUNCHED_NOTEBOOK_SHA256)
    check("summary records per-row comparability",
          len(summary.get("comparability", {})) == 8,
          str(len(summary.get("comparability", {}))))


def main() -> int:
    tests = [test_all_eight, test_early_stop, test_mixed_failures,
             test_ungraded_pair_is_undecided, test_controls_and_cleanup,
             test_answer_key_audit, test_missing_trace_is_unknown,
             test_eligibility_rules, test_eligibility_unit,
             test_frozen_plan_without_manifest,
             test_manifest_disagreement_aborts, test_notebook_drift_aborts,
             test_trace_coverage, test_output_is_sibling_and_artifacts_untouched]
    with tempfile.TemporaryDirectory() as td:
        for fn in tests:
            try:
                fn(Path(td))
            except Exception as exc:
                import traceback
                check(fn.__name__ + " crashed", False, f"{type(exc).__name__}: {exc}")
                traceback.print_exc()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
