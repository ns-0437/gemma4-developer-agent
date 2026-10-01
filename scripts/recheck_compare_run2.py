"""Re-derive the eight-row compare run-2 report, original and corrected, from the same raw evidence.

Two report cells are executed over ONE set of downloaded artifacts:

  original   releases/compare_v2_prepared/compare.ipynb  (the notebook that produced the run)
  corrected  notebooks/compare/compare.ipynb             (the working copy, with the metric repairs)

Neither run is re-executed and no artifact is written inside the evidence tree. The original table is
first checked against the CSV the Kaggle session itself wrote, so "original" means what the run
actually reported, not what this script thinks it reported.

Outputs (default: reference/compare_run2_analysis/):
  original_rows.csv      the launched cell's eight rows, re-derived
  corrected_rows.csv     the repaired cell's eight rows
  column_diff.csv        every cell that changed, with both values
  RECHECK.md             the eight-row table plus what changed and why

Run:  python scripts/recheck_compare_run2.py
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "reference" / "compare_run2"
LAUNCHED_NB = ROOT / "releases" / "compare_v2_prepared" / "compare.ipynb"
WORKING_NB = ROOT / "notebooks" / "compare" / "compare.ipynb"
LAUNCHED_V2_SHA256 = "97873af2210b0f26276efce30c14d1b4c0491320f008e983c20c174328bfdbbc"


def report_source(nb_path: Path) -> tuple[str, str]:
    raw = nb_path.read_bytes()
    nb = json.loads(raw.decode("utf-8"))
    src = None
    for cell in nb["cells"]:
        text = "".join(cell["source"])
        if text.lstrip().startswith("# Result packet"):
            src = text
    if src is None:
        raise SystemExit(f"REPORT cell not found in {nb_path}")
    cut = src.find("MANIFEST = {")
    if cut < 0:
        raise SystemExit("MANIFEST marker not found; refusing to guess where to truncate")
    return src[:cut], hashlib.sha256(raw).hexdigest()


def session_stop_reason() -> str:
    """The stop reason the GPU session itself printed into its report.

    pilot_manifest.json does not carry it (a gap in the MANIFEST block), so it is read from the
    session's own pilot_results.csv rather than re-derived, which would make the replay agree with
    the session by construction.
    """
    saved = ARTIFACTS / "pilot_results.csv"
    if not saved.exists():
        return ""
    for row in csv.DictReader(saved.open(encoding="utf-8")):
        if row.get("attempted") == "False" and row.get("stop_reason"):
            return row["stop_reason"]
    return ""


def run_report(nb_path: Path, out_dir: Path) -> list[dict]:
    runs = json.loads((ARTIFACTS / "pilot" / "runs.json").read_text(encoding="utf-8"))
    for r in runs:
        r["dir"] = str(ARTIFACTS / "pilot" / f"{r['candidate']}__{r['task']}")
    manifest = json.loads((ARTIFACTS / "pilot_manifest.json").read_text(encoding="utf-8"))
    src, _sha = report_source(nb_path)
    ns = {"__name__": "__recheck__", "RUNS": runs,
          "ORDER": [tuple(x) for x in manifest["run_order"]],
          "STOP_REASON": session_stop_reason(), "WORKING_DIR": out_dir,
          "TASK_IDS": list(manifest["tasks"]), "BUDGET": manifest.get("budgets", {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(src, f"<{nb_path.name} REPORT>", "exec"), ns)
    return ns["rows"]


def shipped_classifier():
    """`classify_outcome` as the working notebook actually ships it.

    Taken from the generator's DISPATCH_HELPER and checked to be present verbatim in the notebook's
    run cell, so this cannot silently test code the notebook does not contain.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import compare_cells as C
    nb = json.loads(WORKING_NB.read_text(encoding="utf-8"))
    run_cells = [t for t in ("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
                 if "def classify_outcome" in t]
    if len(run_cells) != 1:
        raise SystemExit(f"expected one cell defining classify_outcome, found {len(run_cells)}")
    if C.DISPATCH_HELPER.strip() not in run_cells[0]:
        raise SystemExit("the notebook's classifier is not the generator's DISPATCH_HELPER; "
                         "regenerate notebooks/compare before rechecking")
    ns = {"json": json, "Path": Path}
    exec(compile(C.DISPATCH_HELPER, "<shipped DISPATCH_HELPER>", "exec"), ns)
    return ns["classify_outcome"]


def reclassify(rows: list[dict]) -> None:
    """Add what the REPAIRED classifier says about each run's own saved error strings.

    The `outcome` column is what the GPU session decided while it was running. It is evidence and it
    is never rewritten here. These extra columns show what the repaired rule would have decided from
    the same bytes, so the two can be compared instead of one quietly replacing the other.
    """
    classify_outcome = shipped_classifier()
    runs = {(r["task"], r["candidate"]): r for r in
            json.loads((ARTIFACTS / "pilot" / "runs.json").read_text(encoding="utf-8"))}
    for row in rows:
        rec = runs.get((row["task"], row["candidate"]))
        if rec is None:
            row["reclassified_outcome"] = "not_attempted"
            row["reclassified_reason"] = ""
            row["would_have_continued"] = "unavailable"
            continue
        outcome, reason = classify_outcome(rec.get("error"), rec.get("persisted_error"))
        row["reclassified_outcome"] = outcome
        row["reclassified_reason"] = reason
        row["would_have_continued"] = (outcome == "candidate" and rec.get("cleanup_ok") is True
                                       and not rec.get("provenance_failed"))


def as_text(v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, default=str)
    return "" if v is None else str(v)


def verify_against_session_csv(rows: list[dict]) -> tuple[bool, list[str]]:
    """The launched cell, replayed here, must reproduce the CSV the Kaggle session wrote."""
    saved = ARTIFACTS / "pilot_results.csv"
    if not saved.exists():
        return False, ["pilot_results.csv not present in the downloaded artifacts"]
    want = list(csv.DictReader(saved.open(encoding="utf-8")))
    notes = []
    if len(want) != len(rows):
        notes.append(f"row count {len(rows)} != session CSV {len(want)}")
    for got_row, want_row in zip(rows, want):
        for k, wv in want_row.items():
            gv = as_text(got_row.get(k))
            if gv != wv:
                notes.append(f"{want_row['candidate']}/{want_row['task']} {k}: "
                             f"replay={gv!r} session={wv!r}")
    return not notes, notes


def write_csv(path: Path, rows: list[dict]) -> None:
    keys = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: as_text(r.get(k)) for k in keys})


# The columns whose meaning the repair changed, and why. Anything else that moves is unexpected and
# is printed as such.
EXPLAINED = {
    "tool_errors": "was counting only {'status':'error'}; a rejected call carries a bare {'error':...}",
    "shell_edit_hints": "was matching `> /tmp/repro.py`, which the prompt tells the agent to write",
    "first_source_edit_attempt_step": "was set by a /tmp scratch write, not by a repository edit",
    "attribution": "a run that never submitted is no_submission, not empty_patch",
    "successful_tool_calls": "new: calls the tools accepted",
    "rejected_tool_calls": "new: calls rejected before execution for unusable arguments",
    "acknowledged_source_edit_calls": "new: accepted edits to a repository .py file",
    "tmp_scratch_writes": "new: scratch reproduction writes, counted apart from source edits",
    "repeated_identical_tool_calls": "new: identical consecutive calls to ANY tool, not just run_command",
    "unparsed_tool_call_texts": "new: agent turns whose text never became a parsed tool call",
    "reclassified_outcome": "new: the repaired classifier's verdict on the same saved error strings",
    "reclassified_reason": "new: why",
    "would_have_continued": "new: whether the repaired rule would have allowed the next planned run",
}

# `outcome`, `failure_class` and `stop_reason` are NOT in that table on purpose. They were decided
# by the GPU session as it ran and are preserved exactly; the repaired verdict is reported beside
# them in the reclassified_* columns rather than overwriting them.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reference" / "compare_run2_analysis"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    got_sha = hashlib.sha256(LAUNCHED_NB.read_bytes()).hexdigest()
    if got_sha != LAUNCHED_V2_SHA256:
        print(f"REFUSING: {LAUNCHED_NB} is not the launched version 2 notebook\n"
              f"  expected {LAUNCHED_V2_SHA256}\n  found    {got_sha}")
        return 3

    with tempfile.TemporaryDirectory() as td:
        original = run_report(LAUNCHED_NB, Path(td) / "orig")
        corrected = run_report(WORKING_NB, Path(td) / "corr")
    reclassify(corrected)

    ok, notes = verify_against_session_csv(original)
    print("replay of the launched cell reproduces the session's own pilot_results.csv:", ok)
    for n in notes:
        print("   ", n)

    write_csv(out / "original_rows.csv", original)
    write_csv(out / "corrected_rows.csv", corrected)

    diffs = []
    for o, c in zip(original, corrected):
        assert (o["candidate"], o["task"]) == (c["candidate"], c["task"])
        for k in sorted(set(o) | set(c)):
            ov, cv = as_text(o.get(k, "(absent)")), as_text(c.get(k, "(absent)"))
            if ov != cv:
                diffs.append({"candidate": o["candidate"], "task": o["task"], "column": k,
                              "original": ov, "corrected": cv,
                              "explained": EXPLAINED.get(k, "UNEXPECTED - review")})
    write_csv(out / "column_diff.csv", diffs) if diffs else None

    print(f"\n{len(diffs)} changed cells across {len(original)} rows")
    unexpected = [d for d in diffs if d["explained"] == "UNEXPECTED - review"]
    for d in diffs:
        if d["column"] in ("tool_calls", "edit_calls") or d in unexpected:
            print(f"  {d['candidate']}/{d['task']:<10} {d['column']:<34} "
                  f"{d['original'][:28]:<30} -> {d['corrected'][:28]}")
    if unexpected:
        print("\nUNEXPECTED CHANGES (columns the repair did not set out to touch):")
        for d in unexpected:
            print(f"  {d['candidate']}/{d['task']} {d['column']}: {d['original']!r} -> {d['corrected']!r}")

    cols = ["candidate", "task", "attempted", "outcome", "reclassified_outcome",
            "would_have_continued", "attribution", "grading_ran",
            "tool_calls", "successful_tool_calls", "rejected_tool_calls",
            "acknowledged_source_edit_calls", "tmp_scratch_writes", "repeated_identical_tool_calls",
            "unparsed_tool_call_texts", "tool_errors"]
    lines = ["# Compare run 2, re-derived", "",
             "Artifacts: `reference/compare_run2/` (unmodified). Original report cell: "
             f"`releases/compare_v2_prepared/compare.ipynb` (`{got_sha[:12]}...`). Corrected cell: "
             "`notebooks/compare/compare.ipynb`.", "",
             f"Replay of the launched cell reproduces the session's own `pilot_results.csv`: **{ok}**.",
             "", "## Corrected eight rows", "",
             "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in corrected:
        lines.append("| " + " | ".join(as_text(r.get(c)) for c in cols) + " |")
    lines += ["", "## What changed, and why", ""]
    seen = {}
    for d in diffs:
        seen.setdefault(d["column"], d["explained"])
    for k, why in sorted(seen.items()):
        lines.append(f"- `{k}`: {why}")
    lines += ["", "`outcome` is what the GPU session recorded while running and is preserved "
                  "unchanged. `reclassified_outcome` is what the repaired classifier says about the "
                  "same saved error strings, and `would_have_continued` is whether the repaired rule "
                  "would have let the next planned run start.", "",
                  "Original rows are preserved in `original_rows.csv`; every changed cell with both "
                  "values is in `column_diff.csv`. No grade exists for either attempted run, so "
                  "neither candidate is comparable and neither won.", ""]
    (out / "RECHECK.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {out / 'RECHECK.md'} and the two CSVs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
