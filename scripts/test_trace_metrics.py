"""Trace-metric tests that run the SHIPPED report cell over the REAL compare run-2 artifacts.

Nothing here re-implements a metric. Each test executes `notebooks/compare/compare.ipynb`'s own
REPORT cell (truncated at the MANIFEST block, the same way scripts/review_compare_results.py does
it) and reads the values that cell produced from the downloaded traces in
`reference/compare_run2/`. If a test passes, the shipped cell produced that number.

Why these tests exist. The run-2 reviewer reported, for candidate A, 54 "shell-edit workarounds"
and a first source-edit attempt at step 5 on a run that never touched a repository file, and for
candidate B, 1 tool error on a run with 43. Both came from `trace_stats`:

  * tool failures arrive in TWO shapes. A rejected call carries a bare {"error": ...} with no
    `status` key, and only `status == "error"` was counted;
  * the shell-edit regex matched `> /tmp/repro.py`, which the system prompt explicitly tells the
    agent to write, so every scratch reproduction counted as a repository edit;
  * `repeated_identical_cmds` compared consecutive run_command payloads only, so B's 41 identical
    rejected edit_file calls scored 0;
  * an agent turn whose text was never parsed into a tool call was invisible.

Run:  NB_TARGET=compare python scripts/test_trace_metrics.py
      python scripts/test_trace_metrics.py --original   (same tests against the launched cell:
                                                         these are EXPECTED to fail, and show what
                                                         the run-2 report actually claimed)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "reference" / "compare_run2"
WORKING_NB = ROOT / "notebooks" / "compare" / "compare.ipynb"
LAUNCHED_NB = ROOT / "releases" / "compare_v2_prepared" / "compare.ipynb"

# The notebook that produced these artifacts. Pinned so the fixture cannot silently be compared
# against a different run's evidence.
LAUNCHED_V2_SHA256 = "97873af2210b0f26276efce30c14d1b4c0491320f008e983c20c174328bfdbbc"

# Raw evidence hashes, recorded when the artifacts were copied out of the Kaggle download on
# 2026-09-30. A fixture that drifts is not a fixture.
RAW_SHA256 = {
    "pilot/A__rich_3278/traces/trace_rich_3278.json":
        "6e0ecc77cbc96ef2b2764ee57545d3e448aa1143b190b6b6e726ebf65935af7f",
    "pilot/B__rich_3278/traces/trace_rich_3278.json":
        "e53eb9874eda7e9364e9336e2572fa97639aa4b8a394f6d6d40edd046f22fb11",
}

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


def eq(name, got, want):
    check(f"{name} == {want}", got == want, f"got {got!r}")


# ----------------------------------------------------------------- shipped cell
def report_source(nb_path: Path) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    src = None
    for cell in nb["cells"]:
        text = "".join(cell["source"])
        if text.lstrip().startswith("# Result packet"):
            src = text
    assert src is not None, f"REPORT cell not found in {nb_path}"
    cut = src.find("MANIFEST = {")
    assert cut > 0, "MANIFEST marker not found; refusing to guess where to truncate"
    return src[:cut]


def shipped_namespace(nb_path: Path, out_dir: Path) -> dict:
    """Execute the notebook's REPORT cell over the real downloaded run records."""
    runs = json.loads((ARTIFACTS / "pilot" / "runs.json").read_text(encoding="utf-8"))
    for r in runs:
        # The recorded `dir` is the Kaggle path; repoint it at the downloaded copy, unchanged.
        r["dir"] = str(ARTIFACTS / "pilot" / f"{r['candidate']}__{r['task']}")
    manifest = json.loads((ARTIFACTS / "pilot_manifest.json").read_text(encoding="utf-8"))
    order = [tuple(x) for x in manifest["run_order"]]
    ns = {"__name__": "__metrics_test__", "RUNS": runs, "ORDER": order,
          "STOP_REASON": manifest.get("stop_reason"), "WORKING_DIR": out_dir,
          "TASK_IDS": list(manifest["tasks"]), "BUDGET": manifest.get("budgets", {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    exec(compile(report_source(nb_path), f"<{nb_path.name} REPORT cell>", "exec"), ns)
    return ns


def by_key(ns):
    return {(r["task"], r["candidate"]): r for r in ns["rows"]}


# ----------------------------------------------------------------- tests
def test_fixture_integrity():
    print("\n[M0] the fixture is the launched run's own evidence, unmodified")
    got = hashlib.sha256(LAUNCHED_NB.read_bytes()).hexdigest()
    eq("frozen launched notebook sha256", got, LAUNCHED_V2_SHA256)
    for rel, want in RAW_SHA256.items():
        p = ARTIFACTS / rel
        check(f"present: {rel}", p.exists())
        if p.exists():
            eq(f"sha256 {rel}", hashlib.sha256(p.read_bytes()).hexdigest(), want)
    runs = json.loads((ARTIFACTS / "pilot" / "runs.json").read_text(encoding="utf-8"))
    eq("run records downloaded", len(runs), 2)
    eq("candidate B's persisted termination message", runs[1]["persisted_error"],
       "Agent completed execution without calling submit_patch.")


def test_row_count(ns):
    print("\n[M1] eight planned rows, two attempted")
    rows = ns["rows"]
    eq("rows", len(rows), 8)
    eq("attempted", sum(1 for r in rows if r["attempted"]), 2)
    eq("not attempted", sum(1 for r in rows if r["attempted"] is False), 6)
    check("no row is recorded as resolved",
          all(r["resolved"] in (False, "unavailable") for r in rows),
          str([r["resolved"] for r in rows]))


def test_candidate_a_made_no_source_edit(ns):
    print("\n[M2] candidate A: 54 scratch writes, ZERO repository source edits")
    a = by_key(ns)[("rich_3278", "A")]
    eq("tool_calls", a["tool_calls"], 60)
    eq("successful_tool_calls", a["successful_tool_calls"], 59)
    eq("tool_errors", a["tool_errors"], 1)
    eq("rejected_tool_calls", a["rejected_tool_calls"], 0)
    eq("edit_calls", a["edit_calls"], 0)
    eq("tmp_scratch_writes", a["tmp_scratch_writes"], 54)
    eq("shell_edit_hints", a["shell_edit_hints"], 0)
    eq("acknowledged_source_edit_calls", a["acknowledged_source_edit_calls"], 0)
    eq("first_source_edit_attempt_step", a["first_source_edit_attempt_step"], "unavailable")
    eq("repeated_identical_cmds", a["repeated_identical_cmds"], 48)
    eq("repeated_identical_tool_calls", a["repeated_identical_tool_calls"], 48)
    eq("unparsed_tool_call_texts", a["unparsed_tool_call_texts"], 0)
    eq("tool_use_flags", a["tool_use_flags"],
       "identical_repeats;no_acknowledged_source_edit")
    check("the run is still a candidate outcome", a["failure_class"] == "candidate", a["failure_class"])
    check("termination names the turns budget", "turns budget" in str(a["termination_error"]),
          str(a["termination_error"]))


def test_candidate_b_every_edit_was_rejected(ns):
    print("\n[M3] candidate B: 42 edit attempts, all rejected, none applied")
    b = by_key(ns)[("rich_3278", "B")]
    eq("tool_calls", b["tool_calls"], 48)
    eq("edit_calls", b["edit_calls"], 42)
    eq("rejected_tool_calls", b["rejected_tool_calls"], 42)
    eq("tool_errors", b["tool_errors"], 43)
    eq("successful_tool_calls", b["successful_tool_calls"], 5)
    eq("acknowledged_source_edit_calls", b["acknowledged_source_edit_calls"], 0)
    eq("tmp_scratch_writes", b["tmp_scratch_writes"], 2)
    eq("shell_edit_hints", b["shell_edit_hints"], 0)
    eq("a source edit was ATTEMPTED at step 8", b["first_source_edit_attempt_step"], 8)
    eq("unparsed_tool_call_texts", b["unparsed_tool_call_texts"], 4)
    # Descriptive flags only. Their presence is a symptom of tool-use trouble and is NOT evidence of
    # an encoding root cause.
    eq("tool_use_flags", b["tool_use_flags"],
       "rejected_calls;unparsed_text;identical_repeats;no_acknowledged_source_edit")
    # 42 consecutive edit_file calls, 41 adjacent pairs, of which the two pairs touching the one
    # variant payload (step 33, the same text with CJK quotation marks round the filepath) differ.
    eq("repeated_identical_tool_calls", b["repeated_identical_tool_calls"], 39)
    eq("repeated_identical_cmds sees none of it", b["repeated_identical_cmds"], 0)


def test_no_submission_is_not_an_environment_failure(ns):
    print("\n[M4] B's termination is reported as the candidate's, and as ungraded")
    b = by_key(ns)[("rich_3278", "B")]
    eq("attribution", b["attribution"], "no_submission")
    eq("grading_ran", b["grading_ran"], False)
    check("no grade of any kind", b["resolved"] is False and b["test_exit_code"] in (-1, "unavailable"),
          f"{b['resolved']} {b['test_exit_code']}")


def test_malformed_payload_fixture(ns):
    print("\n[M5] regression fixture: the malformed edit_file payloads, as recorded")
    obs_status = ns["observation_status"]
    stats = ns["trace_stats"]
    fixture = json.loads((ROOT / "reference" / "compare_run2_malformed_calls.json")
                         .read_text(encoding="utf-8"))
    eq("distinct payloads recorded", len(fixture["payloads"]), 2)
    eq("total rejected calls recorded", fixture["total_calls"], 42)

    rejection = {"content": json.dumps({"error": fixture["rejection_message"]})}
    status, text = obs_status({"observation": rejection})
    eq("a bare {'error': ...} is classified", status, "rejected")
    check("the message is carried, not dropped", "old_string" in text, text[:80])

    # The parser's residue proves the loss: `old_string:` survives INSIDE new_string's value, so the
    # payload was split on its own content rather than parsed as JSON.
    main = fixture["payloads"][0]["arguments"]
    check("old_string is absent as a parameter", "old_string" not in main, str(list(main)))
    check("but appears as text inside new_string",
          ",old_string:" in main["new_string"], main["new_string"][-40:])
    check("two extra keys are content fragments, not parameter names",
          sum(1 for k in main if k not in ("filepath", "new_string")) == 2, str(list(main)))

    # Replaying the recorded payloads through the shipped counter reproduces the run's shape.
    steps = []
    for i, entry in enumerate(fixture["replay_sequence"]):
        payload = fixture["payloads"][entry]["arguments"]
        steps.append({"step_id": 8 + i, "source": "agent",
                      "tool_calls": [{"function_name": "edit_file", "arguments": payload}],
                      "observation": rejection})
    st = stats({"steps": steps, "final_metrics": {}})
    eq("replay: every call rejected", st["rejected_tool_calls"], 42)
    eq("replay: nothing counted as applied", st["acknowledged_source_edit_calls"], 0)
    eq("replay: identical repeats counted", st["repeated_identical_tool_calls"], 39)
    eq("replay: no call counted as successful", st["successful_tool_calls"], 0)


def test_scratch_paths_are_not_source(ns):
    print("\n[M6] shell write targets: /tmp scratch vs repository source")
    targets = ns["shell_write_targets"]
    src, scratch = targets("cat > /tmp/repro.py <<'EOF'\nimport re\nEOF")
    eq("heredoc to /tmp: source targets", src, [])
    eq("heredoc to /tmp: scratch targets", scratch, ["/tmp/repro.py"])
    src, scratch = targets("cat > rich/ansi.py <<'EOF'\nx = 1\nEOF")
    eq("heredoc to the repository: source targets", src, ["rich/ansi.py"])
    src, scratch = targets("sed -i 's/a/b/' rich/ansi.py")
    eq("in-place sed on the repository", src, ["rich/ansi.py"])
    src, scratch = targets("sed -i 's/a/b/' /tmp/repro.py")
    eq("in-place sed on scratch", src, [])
    src, scratch = targets("python3 /tmp/repro.py")
    eq("merely RUNNING a scratch file writes nothing", (src, scratch), ([], []))
    src, scratch = targets('python3 -c "print(1)" > /tmp/out.txt')
    eq("a non-.py redirect is neither", (src, scratch), ([], []))


def test_missing_grades_stay_non_comparable(ns):
    print("\n[M7] reclassifying B as a candidate outcome must NOT make it comparable")
    # The reviewer's own gate, not a copy of it. Reclassification changes who a failure belongs to;
    # it must not turn a run that was never graded into a win or a loss.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from review_compare_results import comparison_eligible
    for row in ns["rows"]:
        eligible, reason = comparison_eligible(row)
        key = f"{row['candidate']}/{row['task']}"
        check(f"{key} is not comparable", eligible is False, f"eligible={eligible}")
        check(f"{key} says why", bool(reason), reason)
    b = by_key(ns)[("rich_3278", "B")]
    _, reason = comparison_eligible(dict(b, failure_class="candidate"))
    check("a candidate class alone does not confer comparability",
          "grading" in reason or "grade" in reason or "sentinel" in reason, reason)


def main() -> int:
    original = "--original" in sys.argv
    nb = LAUNCHED_NB if original else WORKING_NB
    print(f"REPORT cell from: {nb.relative_to(ROOT)}")
    print(f"artifacts:        {ARTIFACTS.relative_to(ROOT)}  (read-only)")
    test_fixture_integrity()
    with tempfile.TemporaryDirectory() as td:
        ns = shipped_namespace(nb, Path(td) / "out")
        for fn in (test_row_count, test_candidate_a_made_no_source_edit,
                   test_candidate_b_every_edit_was_rejected,
                   test_no_submission_is_not_an_environment_failure,
                   test_malformed_payload_fixture, test_scratch_paths_are_not_source,
                   test_missing_grades_stay_non_comparable):
            try:
                fn(ns)
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
