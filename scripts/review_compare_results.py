"""Offline review of the eight-run A/B comparison's downloaded artifacts.

Separate from the launched notebook by design. It never runs a model, never contacts Kaggle, and
never modifies the downloaded artifact tree: its output goes to a SIBLING directory
(`<artifacts>_review` by default), because an earlier version wrote `review/` inside the artifacts
and claimed not to touch them.

It reuses the notebook's own report code rather than reimplementing it. The REPORT cell is read out
of `notebooks/compare/compare.ipynb`, and that notebook is PINNED by SHA-256 to the artifact that was
actually launched. If the notebook changes, this tool fails loudly instead of quietly analysing the
run with different logic than produced it.

Three things it refuses to do:

  * infer a solve from evidence that does not establish one. A single shared
    `comparison_eligible()` gates both the run table and the paired outcomes, so the two can never
    disagree. An integer exit code is not sufficient: sentinel (-1), collection or interruption
    exits (2/3/4), unobserved grading, environment or provenance failures, and unconfirmed cleanup
    all disqualify a row from the paired solve comparison. Candidate failures are never discarded;
    they are reported as their own outcome class;
  * reconstruct the plan from what happened. The eight planned runs are frozen here. A run that
    never executed still gets a row, and a runtime manifest that disagrees with the frozen plan is
    an error, not a new plan;
  * call an absence of observed answer-key access "isolation". Trace evidence is reported with the
    step, the tool and the path, graded by whether the path was merely mentioned, requested, or
    successfully read; unreadable traces are UNKNOWN and partially readable ones are INCOMPLETE.

There is no extrapolation to a leaderboard score anywhere in this file.

Usage, after downloading the kernel output:

    kaggle kernels output navin03/gemma4-swe-agent-compare -p reference/compare_run1
    python scripts/review_compare_results.py reference/compare_run1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The notebook that PRODUCED the artifacts, frozen at launch. The working copy under
# notebooks/compare/ moves on as the control bug is fixed; this must not follow it.
_FROZEN = ROOT / "releases" / "compare_v1_launched" / "compare.ipynb"
NOTEBOOK = _FROZEN if _FROZEN.exists() else ROOT / "notebooks" / "compare" / "compare.ipynb"
UNAVAILABLE = "unavailable"

# The notebook that was actually launched (kernel gemma4-swe-agent-compare version 1, 2026-09-29).
# Its REPORT cell is the code reused below. Pinned so a later notebook edit cannot silently change
# how an already-completed run is interpreted.
LAUNCHED_NOTEBOOK_SHA256 = "532d3f7e6be6bd4fcf7035b0d4af741820f40fa553c00025ca3c3156f781f15b"

# The frozen launch plan. NEVER derived from observed runs: a run that never started must still
# appear, and a truncated run must not shrink the plan.
FROZEN_TASKS = ["rich_3278", "rich_3535", "rich_3675", "rich_3942"]
FROZEN_ORDER = [(t, c) for i, t in enumerate(FROZEN_TASKS)
                for c in (("A", "B") if i % 2 == 0 else ("B", "A"))]

# pytest exit codes that constitute a pass/fail verdict. 2/3/4 are interruption and internal error,
# 5 is "no tests collected", and negative values are harness sentinels, not verdicts.
VERDICT_EXITS = (0, 1)
INTERRUPT_EXITS = (2, 3, 4)
NON_COMPARABLE_CLASSES = {"environment", "provenance", "unobserved_grading", "not_attempted"}


class ReviewError(RuntimeError):
    """Raised when the review cannot proceed honestly."""


# ----------------------------------------------------------- shared eligibility (single source)
def comparison_eligible(row) -> tuple:
    """Return (eligible, reason). The ONLY place solve-comparability is decided.

    Both the run table and the paired-outcome section call this, so a row can never be shown as
    comparable in one and excluded in the other. Ineligible does not mean bad: it means this row
    cannot support a statement about which candidate solved the task.
    """
    if row.get("attempted") is False:
        return False, "not attempted"
    code = row.get("test_exit_code")
    if not isinstance(code, int):
        return False, "no grade recorded"
    if code < 0:
        return False, f"sentinel exit {code}: grading produced no verdict"
    if code in INTERRUPT_EXITS:
        return False, f"pytest exit {code}: collection error or interrupted run"
    if code not in VERDICT_EXITS:
        return False, f"pytest exit {code} is not a pass/fail verdict"
    if row.get("grading_ran") is not True:
        return False, "grading not observed"
    fc = str(row.get("failure_class"))
    if fc in NON_COMPARABLE_CLASSES:
        return False, f"{fc} failure: the outcome is not attributable to the candidate"
    if row.get("cleanup_ok") is False:
        return False, "sandbox cleanup unconfirmed: the run state is not trustworthy"
    if not isinstance(row.get("resolved"), bool):
        return False, "resolved flag missing"
    return True, ""


def row_state(row) -> str:
    """Human label for the paired view, consistent with comparison_eligible."""
    if row is None:
        return "no row"
    ok, why = comparison_eligible(row)
    if ok:
        return "resolved" if row.get("resolved") is True else "not resolved"
    if row.get("attempted") is False:
        return "not attempted"
    if str(row.get("failure_class")) == "candidate":
        return "candidate failure"
    return f"excluded ({why.split(':')[0]})"


# ----------------------------------------------------------- shipped report code, pinned
def shipped_report_source() -> tuple:
    """(source, sha256) of the launched notebook's REPORT cell, truncated at the MANIFEST block."""
    if not NOTEBOOK.exists():
        raise ReviewError(f"notebook not found: {NOTEBOOK}")
    raw = NOTEBOOK.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != LAUNCHED_NOTEBOOK_SHA256:
        raise ReviewError(
            "notebook drift: this reviewer is pinned to the LAUNCHED notebook\n"
            f"  expected {LAUNCHED_NOTEBOOK_SHA256}\n"
            f"  found    {got}\n"
            "The run being reviewed was produced by the pinned notebook. Analysing it with a\n"
            "different version of the report code would misattribute the results. Restore the\n"
            "launched notebook, or review with the matching revision of this script.")
    nb = json.loads(raw.decode("utf-8"))
    report = None
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        if src.lstrip().startswith("# Result packet"):
            report = src
    if report is None:
        raise ReviewError("REPORT cell not found in the pinned notebook")
    cut = report.find("MANIFEST = {")
    if cut < 0:
        raise ReviewError("MANIFEST marker not found; refusing to guess where to truncate")
    return report[:cut], got


# ----------------------------------------------------------- artifacts
def load_artifacts(root: Path) -> dict:
    results = root / "pilot"
    if not results.exists():
        found = list(root.rglob("runs.json"))
        if found:
            results = found[0].parent
    art = {"root": root, "results": results, "present": {}}

    def rd(name):
        p = results / name
        art["present"][name] = p.exists()
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            art.setdefault("read_errors", []).append(f"{name}: {type(exc).__name__}: {exc}")
            return None

    art["runs"] = rd("runs.json") or []
    art["controls"] = rd("control_recheck.json") or []
    art["preconditions"] = rd("preconditions.json") or []
    man = results.parent / "pilot_manifest.json"
    art["present"]["pilot_manifest.json"] = man.exists()
    try:
        art["manifest"] = json.loads(man.read_text(encoding="utf-8")) if man.exists() else None
    except Exception as exc:
        art["manifest"] = None
        art.setdefault("read_errors", []).append(f"pilot_manifest.json: {exc}")
    ce = results / "control_evidence"
    art["control_evidence_dir"] = ce if ce.exists() else None
    art["control_arm_files"] = sorted(p.name for p in ce.glob("*.json")) if ce.exists() else []
    art["control_raw_xml"] = sorted(p.name for p in ce.glob("*.junit.xml")) if ce.exists() else []
    art["control_no_junit"] = sorted(p.name for p in ce.glob("*NO_JUNIT*")) if ce.exists() else []
    return art


def planned_order(art: dict) -> list:
    """The frozen eight-run plan. A manifest may confirm it; it may never replace it."""
    man = art.get("manifest") or {}
    recorded = man.get("run_order")
    if recorded:
        got = [tuple(x) for x in recorded]
        if got != FROZEN_ORDER:
            raise ReviewError(
                "the run manifest disagrees with the frozen launch plan\n"
                f"  frozen   : {FROZEN_ORDER}\n"
                f"  manifest : {got}\n"
                "Either the wrong artifacts are being reviewed, or the launched plan changed.")
    tasks = man.get("tasks")
    if tasks and sorted(tasks) != sorted(FROZEN_TASKS):
        raise ReviewError(f"manifest task set {sorted(tasks)} != frozen {sorted(FROZEN_TASKS)}")
    return list(FROZEN_ORDER)


def build_rows(art: dict, out_dir: Path, report_src: str) -> list:
    order = planned_order(art)
    runs = []
    for r in art["runs"]:
        r = dict(r)
        r["dir"] = str(art["results"] / f"{r['candidate']}__{r['task']}")
        runs.append(r)
    ns = {"__name__": "__review__", "RUNS": runs, "ORDER": order,
          "STOP_REASON": (art.get("manifest") or {}).get("stop_reason"),
          "WORKING_DIR": out_dir, "TASK_IDS": list(FROZEN_TASKS),
          "BUDGET": (art.get("manifest") or {}).get("budget", {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    exec(compile(report_src, "<pinned REPORT cell>", "exec"), ns)
    return ns.get("rows", [])


# ----------------------------------------------------------- trace audit
READ_VERBS = re.compile(r"\b(cat|head|tail|less|more|sed\s+-n|awk|grep|python3?\s+-c|open\()", re.I)
SUSPECT_PATTERNS = [
    ("gold or verification patch file", re.compile(r"[\w/\.-]*(gold|test_?patch)[\w/\.-]*\.patch", re.I)),
    ("harness task payload", re.compile(r"[\w/\.-]*tasks\.jsonl", re.I)),
    ("fail/pass node lists", re.compile(r"\b(FAIL_TO_PASS|PASS_TO_PASS)\b")),
    ("harness internals", re.compile(r"/sandbox/|swegemma[\w/\.-]*", re.I)),
]
ORDINARY_PATTERNS = [
    ("repository test file", re.compile(r"\btests?/[\w/]*test_[\w]+\.py")),
]


def audit_trace_file(path: Path):
    """Return (findings, status). status: ok | corrupt."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"corrupt ({type(exc).__name__})"
    findings = []
    for step in doc.get("steps") or []:
        sid = step.get("step_id")
        obs = (step.get("observation") or {}).get("content", "") or ""
        succeeded = '"status": "ok"' in obs or '"status":"ok"' in obs
        for tc in step.get("tool_calls") or []:
            fn = tc.get("function_name", "")
            args = tc.get("arguments") or {}
            text = " ".join(str(v) for v in args.values())
            for kind, patterns in (("suspected", SUSPECT_PATTERNS), ("ordinary", ORDINARY_PATTERNS)):
                for label, pat in patterns:
                    for hit in dict.fromkeys(pat.findall(text)):
                        hit = hit if isinstance(hit, str) else hit[0]
                        if fn in ("read_file",) or READ_VERBS.search(text):
                            access = "read" if succeeded else "requested"
                        else:
                            access = "mentioned"
                        findings.append({"step": sid, "tool": fn, "path": hit,
                                         "kind": kind, "label": label, "access": access})
    return findings, "ok"


def audit_run_traces(trace_dir: Path):
    """Return (findings, coverage, detail). coverage: none | complete | incomplete | unknown."""
    if not trace_dir.exists():
        return [], "none", "no traces directory"
    files = sorted(trace_dir.glob("*.json"))
    if not files:
        return [], "none", "no trace files"
    findings, ok, bad = [], 0, []
    for f in files:
        got, status = audit_trace_file(f)
        if status == "ok":
            ok += 1
            findings.extend(got)
        else:
            bad.append(f"{f.name}: {status}")
    if ok == 0:
        return [], "unknown", f"all {len(files)} trace files unreadable: {bad}"
    if bad:
        return findings, "incomplete", f"{ok} of {len(files)} readable; unreadable: {bad}"
    return findings, "complete", f"{ok} trace file(s) read"


# ----------------------------------------------------------- sections
def h(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def section_rows(rows, order, nb_sha):
    h("1. ALL PLANNED RUNS (frozen plan; one row each, executed or not)")
    print(f"report code from pinned notebook sha256 {nb_sha}")
    print(f"planned (frozen): {len(order)}   rows produced: {len(rows)}")
    if len(rows) != len(order):
        print("  !! row count does not match the frozen plan; the rest of this review is unreliable")
    print(f"{'#':<3}{'cand':<6}{'task':<13}{'attempted':<11}{'comparable':<12}"
          f"{'resolved':<10}{'failure_class':<20}reason if excluded")
    for i, r in enumerate(rows, 1):
        ok, why = comparison_eligible(r)
        print(f"{i:<3}{r['candidate']:<6}{r['task']:<13}{str(r.get('attempted')):<11}"
              f"{('yes' if ok else 'NO'):<12}{str(r.get('resolved')):<10}"
              f"{str(r.get('failure_class')):<20}{why}")
        if r.get("stop_reason"):
            print(f"      stop_reason: {r['stop_reason']}")


def section_pairs(rows):
    h("2. PAIRED OUTCOMES PER TASK")
    print("Gated by the same comparison_eligible() used in section 1.")
    print("A pair is decided only when BOTH sides are comparable. Nothing else is a win.\n")
    by_task = defaultdict(dict)
    for r in rows:
        by_task[r["task"]][r["candidate"]] = r
    tally = Counter()
    for task in FROZEN_TASKS:
        a, b = by_task.get(task, {}).get("A"), by_task.get(task, {}).get("B")
        ea = comparison_eligible(a)[0] if a else False
        eb = comparison_eligible(b)[0] if b else False
        sa, sb = row_state(a), row_state(b)
        if ea and eb:
            ra, rb = a.get("resolved") is True, b.get("resolved") is True
            verdict = ("both" if ra and rb else "neither" if not ra and not rb
                       else "A only" if ra else "B only")
        else:
            verdict = "UNDECIDED (a side is not comparable)"
        tally[verdict] += 1
        print(f"  {task:<13} A={sa:<24} B={sb:<24} -> {verdict}")
    print("\n  pair tally:", dict(tally))
    decided = sum(v for k, v in tally.items() if not k.startswith("UNDECIDED"))
    print(f"  decided pairs: {decided} of {len(FROZEN_TASKS)}")
    print("  Four tasks from ONE repository. No ranking and no leaderboard estimate follow from")
    print("  this tally, whatever it says.")


def section_candidate_failures(rows):
    h("3. OUTCOME CLASSES (candidate failures preserved, not discarded)")
    buckets = defaultdict(list)
    for r in rows:
        buckets[str(r.get("failure_class"))].append(f"{r['candidate']}/{r['task']}")
    for k in ["candidate", "environment", "unobserved_grading", "provenance", "not_attempted", "none"]:
        if buckets.get(k):
            print(f"  {k:<20} {len(buckets[k]):>2}  {', '.join(buckets[k])}")
    for k in sorted(set(buckets) - {"candidate", "environment", "unobserved_grading",
                                    "provenance", "not_attempted", "none"}):
        print(f"  {k:<20} {len(buckets[k]):>2}  {', '.join(buckets[k])}")
    cand = [r for r in rows if str(r.get("failure_class")) == "candidate"]
    print(f"\n  CANDIDATE FAILURES ({len(cand)}): attributable to the agent, reported in full.")
    for r in cand:
        ok, why = comparison_eligible(r)
        print(f"    {r['candidate']}/{r['task']}: {r.get('outcome_reason') or r.get('attribution')}")
        print(f"        comparable for the solve tally: {'yes' if ok else 'no -> ' + why}")
    print("\n  Environment, provenance and grading failures are excluded from the solve tally and")
    print("  are counted for neither candidate.")


def section_timing(rows):
    h("4. TIMING (separated where observable)")
    print("  agent_loop_s  : the agent loop alone")
    print("  setup_s       : agent_phase_s - agent_loop_s, only when both are numbers")
    print("  agent_phase_s : container-A setup PLUS the agent loop, as the harness bundles them")
    print("  grading_phase_s: container B\n")
    print(f"{'cand':<6}{'task':<13}{'agent_loop_s':>14}{'setup_s':>12}{'agent_phase_s':>15}"
          f"{'grading_s':>12}{'wall_s':>10}")
    for r in rows:
        al, ap = r.get("agent_loop_s"), r.get("agent_phase_s")
        setup = (round(ap - al, 2) if isinstance(al, (int, float)) and isinstance(ap, (int, float))
                 else UNAVAILABLE)

        def f(x):
            return f"{x:.2f}" if isinstance(x, (int, float)) else str(x)
        print(f"{r['candidate']:<6}{r['task']:<13}{f(al):>14}{f(setup):>12}{f(ap):>15}"
              f"{f(r.get('grading_phase_s')):>12}{f(r.get('wall_s')):>10}")


def section_controls(art):
    h("5. CONTROLS, IMPORT PROVENANCE AND CLEANUP")
    ctl = art["controls"]
    if not ctl:
        print("  control_recheck.json absent: control validity for this run is UNKNOWN.")
    else:
        expected = 2 * len(FROZEN_TASKS)
        print(f"  control arms recorded: {len(ctl)} (expected {expected})")
        if len(ctl) != expected:
            print("  !! a partial control sequence is not a clean one")
        for c in ctl:
            nc = c.get("node_comparison") or {}
            print(f"  {str(c.get('task')):<13} {str(c.get('arm')):<10} "
                  f"agrees_with_saved={c.get('agrees_with_saved')} "
                  f"exit={c.get('pytest_exit')} (saved {c.get('saved_exit')}) "
                  f"nodes={nc.get('n_observed')}/{nc.get('n_expected')} "
                  f"cleanup_ok={c.get('cleanup_ok')}")
            for k in ("missing", "extra", "changed", "skipped", "targets_wrong"):
                if nc.get(k):
                    print(f"        {k}: {nc[k][:3]}{' ...' if len(nc[k]) > 3 else ''}")
            for k in ("teardown_error", "junit_parse_error", "exception"):
                if c.get(k):
                    print(f"        {k}: {str(c[k])[:120]}")
            if c.get("owned_sandboxes"):
                print(f"        leaked sandboxes: {c['owned_sandboxes']}")
    print(f"\n  raw control JUnit files preserved : {len(art['control_raw_xml'])}")
    print(f"  arms with NO readable JUnit report: {len(art['control_no_junit'])} "
          f"{art['control_no_junit'] or ''}")
    pre = art["preconditions"]
    print(f"\n  precondition probes: {len(pre)}")
    for p in pre:
        print(f"    {str(p.get('task')):<13} ok={p.get('ok')} cleanup_ok={p.get('cleanup_ok')}")
        print(f"        agent  import: {p.get('agent_file') or '<import failed>'}")
        print(f"        grading import: {p.get('grading_file') or '<import failed>'}")
        if p.get("teardown_error"):
            print(f"        teardown_error: {str(p['teardown_error'])[:120]}")


def section_cleanup(rows):
    h("6. PER-RUN CLEANUP")
    for r in rows:
        if r.get("attempted") is False:
            continue
        print(f"  {r['candidate']}/{r['task']:<13} cleanup_ok={r.get('cleanup_ok')} "
              f"owned={r.get('owned_sandboxes') or '(none)'}")


def section_behaviour(rows):
    h("7. AGENT BEHAVIOUR: PATCH SHAPE, REPEATS, REJECTED EDITS, CONTEXT ERRORS")
    print(f"{'cand':<6}{'task':<13}{'files changed':<34}{'tools':>7}{'edits':>7}"
          f"{'repeat':>8}{'errors':>8}")
    for r in rows:
        print(f"{r['candidate']:<6}{r['task']:<13}{str(r.get('patch_files') or '')[:32]:<34}"
              f"{str(r.get('tool_calls')):>7}{str(r.get('edit_calls')):>7}"
              f"{str(r.get('repeated_identical_cmds')):>8}{str(r.get('tool_errors')):>8}")
    print("\n  rejected edits and context errors, where recorded:")
    seen = False
    for r in rows:
        bits = []
        if r.get("shell_edit_hints") not in (0, UNAVAILABLE, None):
            bits.append(f"shell-edit workarounds={r['shell_edit_hints']}")
        err = str(r.get("termination_error") or "")
        if re.search(r"context|BadRequest|maximum context|token", err, re.I):
            bits.append(f"context error: {err[:90]}")
        if r.get("attempted") is not False and r.get("first_source_edit_attempt_step") in (None, UNAVAILABLE):
            bits.append("no source edit attempt observed in the trace")
        if bits:
            seen = True
            print(f"    {r['candidate']}/{r['task']}: " + "; ".join(bits))
    if not seen:
        print("    none recorded")


def section_answer_key(art, rows):
    h("8. ANSWER-KEY ACCESS AUDIT")
    print("  Ordinary repository test reads are normal engineering and are listed separately from")
    print("  SUSPECTED answer-key access (gold/verification patch files, tasks.jsonl, FAIL_TO_PASS,")
    print("  harness internals). Access is graded: mentioned < requested < read.")
    print("  Absence of a hit is NOT proof of isolation: the subprocess backend is not a filesystem")
    print("  boundary, and this audit sees only what the trace recorded.\n")
    coverage_tally = Counter()
    audit = {}
    for r in rows:
        key = f"{r['candidate']}/{r['task']}"
        if r.get("attempted") is False:
            print(f"  {key:<20} run not attempted -> no trace expected")
            coverage_tally["not attempted"] += 1
            continue
        td = art["results"] / f"{r['candidate']}__{r['task']}" / "traces"
        findings, coverage, detail = audit_run_traces(td)
        coverage_tally[coverage] += 1
        audit[key] = {"coverage": coverage, "detail": detail, "findings": findings}
        suspect = [f for f in findings if f["kind"] == "suspected"]
        ordinary = [f for f in findings if f["kind"] == "ordinary"]
        if coverage == "unknown":
            print(f"  {key:<20} COVERAGE UNKNOWN -> {detail}")
            print(f"  {'':<20} this is not a clean result; it is an absence of evidence")
            continue
        if coverage == "none":
            print(f"  {key:<20} NO TRACE -> audit not possible (unknown, not clean)")
            continue
        flag = "INCOMPLETE COVERAGE" if coverage == "incomplete" else "complete"
        print(f"  {key:<20} {flag} ({detail})")
        if suspect:
            print(f"  {'':<20} SUSPECTED ANSWER-KEY ACCESS: {len(suspect)}")
            for f in suspect[:6]:
                print(f"  {'':<22} step {f['step']} {f['tool']} [{f['access']}] "
                      f"{f['label']}: {f['path'][:70]}")
        else:
            print(f"  {'':<20} suspected answer-key access: not observed")
        if ordinary:
            shown = ", ".join(sorted({f['path'] for f in ordinary})[:4])
            print(f"  {'':<20} ordinary repository test reads: {len(ordinary)} ({shown})")
    print(f"\n  coverage: {dict(coverage_tally)}")
    if coverage_tally.get("unknown") or coverage_tally.get("incomplete"):
        print("  Some runs have unknown or incomplete trace coverage. No isolation statement can")
        print("  be made for those runs at all.")
    return audit


def section_claims():
    h("9. WHAT THIS REVIEW DOES NOT CLAIM")
    for line in [
        "These four tasks are all Textualize/rich. Nothing here generalises beyond them.",
        "No leaderboard score is predicted or implied. There is no extrapolation in this tool.",
        "A row that is not comparable is never counted against either candidate.",
        "Environment, provenance and grading failures are excluded, not scored.",
        "An unobserved answer-key access is not evidence of isolation.",
        "Eight runs on one shared server cannot separate candidate effects from session drift.",
    ]:
        print("  * " + line)


# ----------------------------------------------------------- entry point
def default_out_dir(artifacts: Path) -> Path:
    """A SIBLING of the artifact tree, so downloaded evidence is never written into."""
    return artifacts.parent / (artifacts.name.rstrip("/\\") + "_review")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline review of the eight-run A/B comparison.")
    ap.add_argument("artifacts", type=Path, help="downloaded kernel output directory")
    ap.add_argument("--out", type=Path, default=None,
                    help="output directory (default: a sibling <artifacts>_review)")
    a = ap.parse_args(argv)
    if not a.artifacts.exists():
        print(f"artifact directory not found: {a.artifacts}")
        return 2
    artifacts = a.artifacts.resolve()
    out_dir = (a.out.resolve() if a.out else default_out_dir(artifacts))
    if out_dir == artifacts or artifacts in out_dir.parents:
        print(f"refusing to write inside the artifact tree: {out_dir}")
        print("the downloaded evidence must stay untouched; choose a directory outside it")
        return 2

    try:
        report_src, nb_sha = shipped_report_source()
        art = load_artifacts(artifacts)
        order = planned_order(art)
        rows = build_rows(art, out_dir, report_src)
    except ReviewError as exc:
        print("REVIEW ABORTED\n" + str(exc))
        return 3

    section_rows(rows, order, nb_sha)
    section_pairs(rows)
    section_candidate_failures(rows)
    section_timing(rows)
    section_controls(art)
    section_cleanup(rows)
    section_behaviour(rows)
    audit = section_answer_key(art, rows)
    section_claims()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review_summary.json").write_text(json.dumps({
        "pinned_notebook_sha256": nb_sha,
        "frozen_plan": [list(x) for x in FROZEN_ORDER],
        "planned": [list(x) for x in order],
        "rows": rows,
        "comparability": {f"{r['candidate']}/{r['task']}": dict(
            zip(("eligible", "reason"), comparison_eligible(r))) for r in rows},
        "trace_audit": audit,
        "artifacts_present": art["present"],
        "artifacts_dir": str(artifacts),
        "output_dir": str(out_dir),
        "control_arms": len(art["controls"]),
        "control_raw_xml_files": art["control_raw_xml"],
        "control_no_junit_markers": art["control_no_junit"],
        "read_errors": art.get("read_errors", []),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nartifacts read (unmodified): {artifacts}")
    print(f"wrote {out_dir / 'review_summary.json'}")
    print(f"wrote {out_dir / 'pilot_results.csv'} (from the pinned notebook's own CSV writer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
