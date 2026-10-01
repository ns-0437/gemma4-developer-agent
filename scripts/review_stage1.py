"""Offline reviewer for a completed Stage-1 run. Reads artifacts; never re-runs anything.

Pinned to the prepared notebook's FULL hash. Arming changes the notebook bytes, so the pin must be
updated deliberately, as a recorded decision, at the moment of arming. A mismatch aborts.

FOUR QUESTIONS, kept apart and never summed:

  INSTRUMENT VALIDITY     controls, provenance on BOTH phases, result-record integrity, cleanup
  GRADING EXERCISED       did grading actually run? Not exercised is UNOBSERVED, not a fault
  CANDIDATE RELIABILITY   rejected calls, repeated calls, unparsed text, missing submission
  TASK PERFORMANCE        syntactic validity, application evidence, and real source changes,
                          reported as three separate properties

Stage-1 success requires a syntactically valid non-empty SOURCE patch whose recorded size exists, is an
int, and matches the preserved text, plus observed grading with a verdict exit code. An accepted tool
call does not prove a source change.

RECOVERY ATTRIBUTION is deliberately conservative:
  * read-only operations never qualify. A successful `read_file` after a rejection is not a recovery
    write;
  * the operation must be an explicitly successful MODIFYING operation;
  * its target path must match a changed source path EXACTLY after normalisation. A basename
    substring match is not sufficient;
  * operation-level BEFORE/AFTER change evidence must connect that operation's result to the patch.
    Only `edit_file`'s own reported `diff` qualifies: it shows what the operation replaced with what.
    A `write_file` acknowledgment carries `filepath` and `size` and nothing else, so it cannot
    distinguish a real change from a no-op write of identical bytes, and it is NOT evidence of a byte
    change.
  Without before/after evidence the verdict is "consistent with recovery; attribution unproven".
  Causal certainty is never manufactured from the final diff.

Raw artifacts are read only. Reports are refused if the output directory is inside the artifact tree.

Usage:
  python scripts/review_stage1.py --artifacts <downloaded dir> [--out <report dir>]
                                  [--expect-notebook-sha256 <sha>] [--notebook <path>]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io as _io
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

# The Stage-1 notebook that produced the run under review.
#
# PIN HISTORY, updated deliberately at the moment of arming on 2026-09-30:
#   disabled (prepared) : 695cad7b6efb6edaa899b95cebc063bf8c934b0922ea247d4088212753c196a0
#   ARMED (launched)    : 775d88dfe3b91ee8b4d5b30cffdd9f2957556b1f045f2b87a1a6b4e3aacd3158
# The two differ in exactly one line, `DISPATCH_CONFIRM`, verified cell by cell before the push.
PREPARED_NOTEBOOK = ROOT / "notebooks" / "stage1" / "stage1.ipynb"
PREPARED_NOTEBOOK_SHA256 = "775d88dfe3b91ee8b4d5b30cffdd9f2957556b1f045f2b87a1a6b4e3aacd3158"
DISABLED_NOTEBOOK_SHA256 = "695cad7b6efb6edaa899b95cebc063bf8c934b0922ea247d4088212753c196a0"

FROZEN_TASK = "rich_3278"
FROZEN_CANDIDATE = "R"
FROZEN_ORDER = [(FROZEN_TASK, FROZEN_CANDIDATE)]
VERDICT_EXITS = (0, 1)

TEST_MARKERS = ("tests/", "test_", "_test.py", "conftest.py", "pytest.ini")
SCRATCH_MARKERS = ("/tmp/", "repro.py", "debug.py", "scratch.py")

# Tools that cannot change a file, whatever their result.
READ_ONLY_TOOLS = frozenset({
    "read_file", "get_status", "get_code_neighbors", "search_similar_code",
    "get_code_subgraph", "submit_patch",
})
# Tools whose success can be tied to one file by their own observation.
MODIFYING_TOOLS = frozenset({"edit_file", "write_file"})

# A shell command counts as modifying only when it names a write. It is still not operation-level
# change evidence, because the shell reports no structured target.
_SHELL_WRITE = re.compile(
    r"(>>?\s*\S+)|(\btee\b)|(\bsed\s+-i\b)|(\bpatch\b)|(\bcp\b)|(\bmv\b)|(write_text|write_bytes)")


class ReviewError(RuntimeError):
    pass


def h(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def norm(p) -> str:
    """Normalise a repository path for EXACT comparison."""
    if not p:
        return ""
    s = str(p).strip().strip('"').strip("'").replace("\\", "/")
    for pre in ("a/", "b/", "./"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.lstrip("/")
    if s.startswith("workspace/"):
        s = s[len("workspace/"):]
    return PurePosixPath(s).as_posix() if s else ""


# ----------------------------------------------------------------- loading
def load(artifacts: Path) -> dict:
    results = artifacts / "pilot"
    if not results.exists():
        found = list(artifacts.rglob("runs.json"))
        if not found:
            raise ReviewError(f"no runs.json anywhere under {artifacts}")
        results = found[0].parent
    art: dict = {"root": artifacts, "results": results, "present": {}}

    def rd(rel: str):
        p = results / rel
        art["present"][rel] = p.exists()
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            art.setdefault("read_errors", []).append(f"{rel}: {type(exc).__name__}: {exc}")
            return None

    art["runs"] = rd("runs.json") or []
    art["controls"] = rd("control_recheck.json") or []
    art["preconditions"] = rd("preconditions.json") or []
    man = results.parent / "pilot_manifest.json"
    art["present"]["pilot_manifest.json"] = man.exists()
    art["manifest"] = json.loads(man.read_text(encoding="utf-8")) if man.exists() else None
    return art


def run_dir(art: dict, rec: dict) -> Path:
    return art["results"] / f"{rec['candidate']}__{rec['task']}"


def read_patch(d: Path, task: str) -> str:
    p = d / "patches" / (task.replace("/", "__") + ".patch")
    return p.read_text(encoding="utf-8") if p.exists() else ""


def read_trace(d: Path, task: str):
    p = d / "traces" / ("trace_" + task.replace("/", "__") + ".json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_persisted(d: Path, task: str):
    jf = d / "task_results.jsonl"
    if not jf.exists():
        return None
    recs = [json.loads(l) for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(recs) != 1:
        return {"_error": f"{len(recs)} records in task_results.jsonl, expected 1"}
    if recs[0].get("instance_id") not in (None, task):
        return {"_error": f"result is for {recs[0].get('instance_id')}, expected {task}"}
    return recs[0]


# ----------------------------------------------------------------- experiment identity
def check_identity(art: dict) -> dict:
    """Refuse, rather than warn, when the artifacts are not the frozen single-run experiment."""
    out: dict = {"errors": []}
    seen = [(r.get("task"), r.get("candidate")) for r in art["runs"]]
    out["run_keys"] = seen
    off = [k for k in seen if k != (FROZEN_TASK, FROZEN_CANDIDATE)]
    if off:
        out["errors"].append(f"run records outside the frozen plan: {off}")
    if len(seen) != len(set(seen)):
        out["errors"].append(f"duplicate run records: {seen}")
    if len(seen) > 1:
        out["errors"].append(f"{len(seen)} run records for a single-run experiment")

    man = art["manifest"] or {}
    recorded = man.get("run_order")
    out["manifest_run_order"] = recorded
    if recorded is None:
        out["errors"].append("pilot_manifest.json records no run_order")
    else:
        got = [tuple(x) for x in recorded]
        if got != FROZEN_ORDER:
            out["errors"].append(f"manifest run_order {got} != frozen {FROZEN_ORDER}")
    tasks = man.get("tasks")
    if tasks is not None and list(tasks) != [FROZEN_TASK]:
        out["errors"].append(f"manifest tasks {list(tasks)} != ['{FROZEN_TASK}']")

    arms = [(c.get("task"), c.get("arm")) for c in art["controls"] or []]
    out["control_arms"] = arms
    if len(arms) != len(set(arms)):
        out["errors"].append(f"duplicate control arms: {arms}")
    return out


# ----------------------------------------------------------------- patch shape
def patch_paths(patch: str) -> list:
    out = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                out.append(norm(parts[3]))
    return out


def classify_patch(patch: str) -> dict:
    paths = patch_paths(patch)
    src, test, scratch = [], [], []
    for p in paths:
        low = p.lower()
        if any(m in low for m in TEST_MARKERS):
            test.append(p)
        elif any(m in low for m in SCRATCH_MARKERS):
            scratch.append(p)
        else:
            src.append(p)

    lines = patch.splitlines()
    hunks = [l for l in lines if l.startswith("@@")]
    body = [l for l in lines
            if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---"))]
    errors = []
    if patch.strip():
        if not any(l.startswith("diff --git ") for l in lines):
            errors.append("no 'diff --git' header")
        if not hunks:
            errors.append("no '@@' hunk header: a header alone is not a patch")
        if not body:
            errors.append("no added or removed lines")
        for hh in hunks:
            m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", hh)
            if not m:
                errors.append(f"malformed hunk header: {hh[:40]!r}")
                continue
            old_n = int(m.group(2) or 1)
            new_n = int(m.group(4) or 1)
            # Count the lines this hunk actually carries, up to the next hunk or file header.
            i = lines.index(hh)
            got_old = got_new = 0
            for l in lines[i + 1:]:
                if l.startswith("@@") or l.startswith("diff --git "):
                    break
                if l.startswith("-") and not l.startswith("---"):
                    got_old += 1
                elif l.startswith("+") and not l.startswith("+++"):
                    got_new += 1
                elif l.startswith(" ") or l == "":
                    got_old += 1
                    got_new += 1
            if (got_old, got_new) != (old_n, new_n):
                errors.append(f"hunk counts disagree with its body: header says "
                              f"-{old_n},+{new_n}, body has -{got_old},+{got_new}")
    return {
        "bytes": len(patch.encode("utf-8")), "chars": len(patch), "paths": paths,
        "source_paths": src, "test_paths": test, "scratch_paths": scratch,
        "non_empty": bool(patch.strip()), "touches_source": bool(src),
        "n_hunks": len(hunks), "n_changed_lines": len(body),
        "syntax_errors": errors,
        "syntactically_valid": bool(patch.strip()) and not errors,
    }


# ----------------------------------------------------------------- the four questions
def instrument(art: dict, rec, persisted, ident: dict) -> dict:
    """Machinery only. Whether grading was EXERCISED is a separate question, reported next door."""
    v: dict = {"checks": {}, "notes": []}
    controls = art["controls"] or []
    arms = {(c.get("task"), c.get("arm")) for c in controls}
    v["checks"]["controls_present"] = arms == {(FROZEN_TASK, "baseline"), (FROZEN_TASK, "reference")}
    v["checks"]["controls_not_duplicated"] = len(controls) == len(arms)
    v["checks"]["controls_agree"] = bool(controls) and all(c.get("agrees_with_saved") is True
                                                           for c in controls)
    v["checks"]["controls_cleanup_ok"] = bool(controls) and all(c.get("cleanup_ok") is True
                                                                for c in controls)
    pre = art["preconditions"] or []
    v["checks"]["preconditions_passed"] = bool(pre) and all(
        p.get("ok") is True or p.get("provenance_ok") is True for p in pre)
    v["checks"]["experiment_identity_ok"] = not ident["errors"]
    if rec is None:
        v["checks"]["run_record_present"] = False
        v["notes"].append("no run record: the dispatch loop produced nothing for this task")
        v["valid"] = False
        return v
    v["checks"]["run_record_present"] = True
    v["checks"]["provenance_not_failed"] = rec.get("provenance_failed") is False

    # BOTH phases must carry a successful observation. One is not enough.
    phases = rec.get("setup_provenance") or []
    ok_phases = {p.get("phase") for p in phases if p.get("provenance_ok") is True}
    v["phases_observed_ok"] = sorted(x for x in ok_phases if x)
    v["checks"]["agent_provenance_observed"] = "agent" in ok_phases
    v["checks"]["grading_provenance_observed"] = "grading" in ok_phases
    if "agent" in ok_phases and "grading" not in ok_phases:
        v["notes"].append("agent-side provenance only: the graded path is NOT verified")
    v["checks"]["one_result_record"] = rec.get("n_persisted_results") == 1
    v["checks"]["result_record_readable"] = bool(persisted) and "_error" not in persisted
    v["checks"]["cleanup_ok"] = rec.get("cleanup_ok") is True
    v["valid"] = all(v["checks"].values())
    return v


# Checks that can only be satisfied by grading actually running. Their failure means that path was
# NOT EXERCISED. It is not, on its own, a demonstrated fault in the machinery.
_GRADING_DEPENDENT = ("grading_provenance_observed",)


def instrument_state(v: dict) -> dict:
    """Three distinct states, so 'unobserved' is never reported as 'broken'.

      observed_checks_passed      every check that could run, ran and passed
      grading_path_unobserved     everything exercised passed; only grading-dependent checks are
                                  unmet, because grading never ran
      demonstrated_failure        a check that DID run came back false
    """
    failed = [k for k, ok in v["checks"].items() if not ok]
    exercised_failures = [k for k in failed if k not in _GRADING_DEPENDENT]
    unexercised = [k for k in failed if k in _GRADING_DEPENDENT]
    if exercised_failures:
        state = "demonstrated_failure"
        note = ("a check that ran came back false, so the instrument is demonstrably faulty: "
                + ", ".join(exercised_failures))
    elif unexercised:
        state = "grading_path_unobserved"
        note = ("every check that could run, passed. The unmet checks (" + ", ".join(unexercised) +
                ") depend on grading having run, and grading never ran. That is an UNEXERCISED "
                "path, not a demonstrated fault.")
    else:
        state = "observed_checks_passed"
        note = "every check ran and passed"
    return {"state": state, "note": note,
            "failed_checks_that_ran": exercised_failures,
            "unmet_checks_requiring_grading": unexercised}


def grading_exercised(rec, persisted, missing_submission: bool) -> dict:
    g: dict = {}
    g["observed"] = bool(rec) and rec.get("grading_observed") is True
    g["test_exit_code"] = (persisted or {}).get("test_exit_code")
    g["verdict_exit"] = g["test_exit_code"] in VERDICT_EXITS
    if g["observed"]:
        g["state"], g["note"] = "exercised", ""
    elif missing_submission:
        g["state"] = "unobserved"
        g["note"] = ("the candidate produced no patch to grade, so grading was never exercised. "
                     "UNOBSERVED, not a demonstrated instrument fault.")
    else:
        g["state"] = "unobserved"
        g["note"] = "grading did not run, and no missing-submission message explains it."
    return g


def reliability(rec, trace, row: dict) -> dict:
    r: dict = {"counts": {}, "notes": []}
    if rec is None:
        r["notes"].append("no run record")
        r["missing_submission"] = False
        r["trace_present"] = trace is not None
        return r
    for k in ("rejected_tool_calls", "repeated_identical_tool_calls", "unparsed_tool_call_texts",
              "acknowledged_source_edit_calls", "tool_calls", "tool_errors"):
        r["counts"][k] = row.get(k, "unavailable")
    r["counts"]["tool_use_flags"] = row.get("tool_use_flags", "unavailable")
    err = str(rec.get("persisted_error") or "")
    r["missing_submission_message"] = "completed execution without calling submit_patch" in err.lower()
    # Back-compat alias used by the gate.
    r["missing_submission"] = r["missing_submission_message"]
    r["termination_error"] = err or None
    r["trace_present"] = trace is not None

    # The ABSENCE of that message is not evidence that submit_patch was called. The harness only
    # emits it on one specific path (agent_runner.py: no submit_patch AND an empty fallback diff),
    # so a run that ended on the turns budget never reaches it whatever the agent did. Count the
    # actual calls instead.
    if trace is None:
        r["submit_patch_calls"] = "unavailable"
        r["submission_evidence"] = "no trace: whether submit_patch was called cannot be determined"
        r["notes"].append("no trace: tool-use behaviour cannot be reviewed")
        return r
    calls = 0
    for st in trace.get("steps") or []:
        for tc in st.get("tool_calls") or []:
            if tc.get("function_name") == "submit_patch":
                calls += 1
    r["submit_patch_calls"] = calls
    if calls:
        r["submission_evidence"] = f"submit_patch was called {calls} time(s), observed in the trace"
    else:
        r["submission_evidence"] = (
            "submit_patch was NEVER called (0 occurrences in the trace). The missing-submission "
            "message is absent only because the run ended on a different path, not because a "
            "submission happened.")
        r["notes"].append("submit_patch call count is 0")
    return r


def performance(rec, patch: str, persisted, grading: dict) -> dict:
    """Three distinct properties, reported separately, never collapsed into one flag."""
    p: dict = {"patch": classify_patch(patch), "notes": []}
    shape = p["patch"]
    if rec is None:
        p.update({"size_recorded": None, "size_type_ok": False, "size_matches": False,
                  "syntactically_valid": False, "application_evidence": False,
                  "changes_source": False, "valid_source_patch": False, "resolved": None,
                  "verdict": "no run record: no performance result"})
        return p
    p["persisted_record_error"] = (persisted or {}).get("_error")
    size = (persisted or {}).get("agent_patch_size", None)
    p["size_recorded"] = size
    p["size_type_ok"] = isinstance(size, int) and not isinstance(size, bool)
    p["size_matches"] = bool(p["size_type_ok"] and size == len(patch))
    if size is None:
        p["notes"].append("agent_patch_size is ABSENT: the patch artifact cannot be tied to the "
                          "evaluator's record")
    elif not p["size_type_ok"]:
        p["notes"].append(f"agent_patch_size has type {type(size).__name__}, expected int")
    elif not p["size_matches"]:
        p["notes"].append(f"agent_patch_size {size} != preserved patch length {len(patch)}")

    p["syntactically_valid"] = shape["syntactically_valid"]
    p["application_evidence"] = bool(p["size_matches"] and grading["observed"]
                                     and grading["verdict_exit"])
    p["changes_source"] = bool(shape["touches_source"] and shape["n_changed_lines"] > 0)
    p["valid_source_patch"] = bool(shape["non_empty"] and p["syntactically_valid"]
                                   and p["size_matches"] and p["changes_source"])
    p["resolved"] = (persisted or {}).get("resolved")
    return p


# ----------------------------------------------------------------- recovery
def _obs(step):
    obs = step.get("observation") or {}
    content = obs.get("content")
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _accepted(parsed) -> bool:
    return bool(parsed) and "error" not in parsed and parsed.get("status") != "error"


def _is_rejection(parsed) -> bool:
    return bool(parsed) and "mandatory input parameters are not present" in str(
        parsed.get("error", "")).lower()


def classify_operation(tool: str, args: dict, parsed) -> dict:
    """Is this MODIFYING, what exact path does it target, and is there operation-level evidence?"""
    info = {"tool": tool, "modifying": False, "read_only": tool in READ_ONLY_TOOLS,
            "target": None, "change_evidence": None}
    if info["read_only"]:
        return info
    if tool in MODIFYING_TOOLS:
        info["modifying"] = True
        reported = (parsed or {}).get("filepath")
        info["target"] = norm(reported or args.get("filepath", ""))
        info["target_from_tool"] = bool(reported)
        if tool == "edit_file":
            diff = (parsed or {}).get("diff")
            if isinstance(diff, str) and diff.strip():
                # A before/after record of what this operation replaced.
                info["change_evidence"] = "edit_file reported a diff for its own edit"
        elif tool == "write_file":
            # An acknowledgment only: filepath and size cannot distinguish a real change from a
            # no-op write of identical bytes, so it is NOT evidence that any byte changed.
            info["ack_only"] = bool(reported and isinstance((parsed or {}).get("size"), int))
            info["change_evidence"] = None
        return info
    if tool == "run_command":
        cmd = str(args.get("command", ""))
        info["modifying"] = bool(_SHELL_WRITE.search(cmd))
        info["shell"] = cmd[:120]
        return info      # no structured target, no per-file change evidence
    return info


def recovery(trace) -> dict:
    out: dict = {"rejections": [], "candidates": [], "read_only_after": [],
                 "verdict": "recovery unproven", "link": None, "reason": None}
    if trace is None:
        out["reason"] = "no trace"
        return out
    rejected_at = rejected_tool = None
    for st in trace.get("steps") or []:
        parsed = _obs(st)
        calls = st.get("tool_calls") or []
        tool = calls[0].get("function_name") if calls else None
        args = (calls[0].get("arguments") or {}) if calls else {}
        if _is_rejection(parsed):
            rejected_at, rejected_tool = st.get("step_id"), tool
            out["rejections"].append({"step": rejected_at, "tool": tool})
            continue
        if rejected_at is None or not tool or tool == rejected_tool:
            continue
        if not _accepted(parsed):
            continue
        op = classify_operation(tool, args, parsed)
        entry = {"step": st.get("step_id"), "after_rejection_at": rejected_at, **op}
        if op["read_only"]:
            out["read_only_after"].append(entry)
        elif op["modifying"]:
            out["candidates"].append(entry)
    return out


def link_recovery(rec_info: dict, perf: dict) -> dict:
    if rec_info.get("reason"):
        return rec_info
    if not rec_info["rejections"]:
        rec_info["reason"] = "no rejected call in the trace"
        return rec_info
    if not rec_info["candidates"]:
        if rec_info["read_only_after"]:
            tools = sorted({c["tool"] for c in rec_info["read_only_after"]})
            rec_info["reason"] = (f"after the rejection only read-only operations succeeded ({tools}); "
                                  "a read never changes a file, so it cannot be a recovery write")
        else:
            rec_info["reason"] = ("a rejection occurred but no different MODIFYING operation was "
                                  "accepted after it")
        return rec_info
    src = {norm(p) for p in perf["patch"]["source_paths"]}
    if not src:
        rec_info["reason"] = ("a modifying operation was accepted, but the final patch changes no "
                              "source file, so nothing connects it to a verified change")
        return rec_info

    exact = [c for c in rec_info["candidates"] if c.get("target") and c["target"] in src]
    rec_info["exact_path_matches"] = exact
    if not exact:
        basenames = {PurePosixPath(p).name for p in src}
        near = [c for c in rec_info["candidates"]
                if c.get("target") and PurePosixPath(c["target"]).name in basenames]
        rec_info["same_basename_only"] = near
        rec_info["reason"] = (
            "no accepted modifying operation names a changed source path exactly"
            + (f"; a same-basename file matched ({[c['target'] for c in near]}), which is not "
               "sufficient" if near else ""))
        return rec_info

    with_evidence = [c for c in exact if c.get("change_evidence")]
    if not with_evidence:
        ack = [c for c in exact if c.get("ack_only")]
        rec_info["acknowledged_only"] = ack
        rec_info["verdict"] = "consistent with recovery; attribution unproven"
        detail = ("; the accepted write was acknowledged with a path and size only, which cannot "
                  "distinguish a real change from a no-op write of identical bytes" if ack else "")
        rec_info["reason"] = ("an accepted modifying operation targets a changed source path, but no "
                              "operation-level before/after change evidence ties its result to the "
                              "patch; the final diff alone does not establish which operation "
                              "produced it" + detail)
        return rec_info
    rec_info["verdict"] = "recovery observed"
    rec_info["link"] = with_evidence
    rec_info["reason"] = ("rejection, then a different accepted modifying operation on an exactly "
                          "matching changed source path, carrying that operation's own before/after "
                          "change evidence")
    return rec_info


# ----------------------------------------------------------------- report cell
def shipped_rows(art: dict, out_dir: Path, notebook: Path) -> list:
    raw = notebook.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    src = None
    for cell in doc["cells"]:
        text = "".join(cell["source"])
        if text.lstrip().startswith("# Result packet"):
            src = text
    if src is None:
        raise ReviewError("REPORT cell not found in the pinned notebook")
    cut = src.find("MANIFEST = {")
    if cut < 0:
        raise ReviewError("MANIFEST marker not found; refusing to guess where to truncate")
    runs = []
    for r in art["runs"]:
        r = dict(r)
        r["dir"] = str(run_dir(art, r))
        runs.append(r)
    man = art["manifest"] or {}
    order = [tuple(x) for x in man.get("run_order", [[FROZEN_TASK, FROZEN_CANDIDATE]])]
    ns = {"__name__": "__stage1_review__", "RUNS": runs, "ORDER": order,
          "STOP_REASON": man.get("stop_reason"), "WORKING_DIR": out_dir,
          "TASK_IDS": [FROZEN_TASK], "BUDGET": man.get("budgets", {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(_io.StringIO()):
        exec(compile(src[:cut], "<pinned stage1 REPORT cell>", "exec"), ns)
    return ns.get("rows", [])


# ----------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--expect-notebook-sha256", default=None)
    ap.add_argument("--notebook", default=None)
    args = ap.parse_args()

    artifacts = Path(args.artifacts).resolve()
    notebook = Path(args.notebook).resolve() if args.notebook else PREPARED_NOTEBOOK
    out_dir = Path(args.out).resolve() if args.out else (ROOT / "reference" / "stage1_review")

    if out_dir == artifacts or artifacts in out_dir.parents:
        print(f"REFUSING: the report directory {out_dir} is inside the artifact tree {artifacts}")
        return 2

    want = args.expect_notebook_sha256 or PREPARED_NOTEBOOK_SHA256
    if not notebook.exists():
        print(f"REVIEW ABORTED: notebook not found: {notebook}")
        return 3
    got = hashlib.sha256(notebook.read_bytes()).hexdigest()
    if got != want:
        print("REVIEW ABORTED: notebook hash mismatch\n"
              f"  notebook : {notebook}\n  expected : {want}\n  found    : {got}\n"
              "Arming the notebook changes its bytes. Update PREPARED_NOTEBOOK_SHA256 deliberately, "
              "recording both values, or pass --expect-notebook-sha256 for the armed artifact.")
        return 3
    print(f"pinned notebook: {notebook.name}  sha256 {got}")

    try:
        art = load(artifacts)
    except ReviewError as exc:
        print(f"REVIEW ABORTED: {exc}")
        return 3

    ident = check_identity(art)
    if ident["errors"]:
        print("REVIEW ABORTED: the artifacts are not the frozen single-run experiment")
        for e in ident["errors"]:
            print(f"  - {e}")
        return 3

    rec = art["runs"][0] if art["runs"] else None
    d = run_dir(art, rec) if rec else artifacts
    patch = read_patch(d, FROZEN_TASK) if rec else ""
    trace = read_trace(d, FROZEN_TASK) if rec else None
    persisted = read_persisted(d, FROZEN_TASK) if rec else None

    report_cell_error = None
    try:
        rows = shipped_rows(art, out_dir, notebook)
    except ReviewError as exc:
        print(f"REVIEW ABORTED: {exc}")
        return 3
    except Exception as exc:
        # The shipped REPORT cell asserts artifact integrity of its own accord, for instance that the
        # preserved patch length equals the recorded agent_patch_size. A refusal there is a FINDING
        # about the artifacts, not a reviewer crash, so it is recorded and the review continues.
        rows, report_cell_error = [], f"{type(exc).__name__}: {exc}"
        print(f"  the notebook's REPORT cell refused these artifacts: {report_cell_error}")
    row = next((x for x in rows if (x["task"], x["candidate"]) == (FROZEN_TASK, FROZEN_CANDIDATE)), {})

    rel = reliability(rec, trace, row)
    grading = grading_exercised(rec, persisted, rel.get("missing_submission", False))
    inst = instrument(art, rec, persisted, ident)
    inst["checks"]["report_cell_accepted_artifacts"] = report_cell_error is None
    if report_cell_error:
        inst["notes"].append(f"the notebook's own REPORT cell refused the artifacts: {report_cell_error}")
        inst["valid"] = False
    inst["report_cell_error"] = report_cell_error
    inst["state"] = instrument_state(inst)
    perf = performance(rec, patch, persisted, grading)
    rcv = link_recovery(recovery(trace), perf)

    h("1. INSTRUMENT VALIDITY (machinery only)")
    for k, v in inst["checks"].items():
        print(f"  {'OK  ' if v else 'FAIL'}  {k}")
    print(f"  phases with a successful provenance observation: {inst.get('phases_observed_ok')}")
    for n in inst["notes"]:
        print(f"  note: {n}")
    st = inst["state"]
    print(f"  -> STATE: {st['state'].upper()}")
    print(f"     {st['note']}")
    if st["state"] == "grading_path_unobserved":
        print("     This is NOT a demonstrated instrument failure. It is also not a pass:")
        print("     the graded path remains unverified.")

    h("2. GRADING EXERCISED?")
    print(f"  state                              {grading['state'].upper()}")
    print(f"  grading observed                   {grading['observed']}")
    print(f"  test_exit_code                     {grading['test_exit_code']}")
    print(f"  verdict exit code                  {grading['verdict_exit']}")
    if grading["note"]:
        print(f"  note: {grading['note']}")

    h("3. CANDIDATE RELIABILITY (operational, never a solve or a loss)")
    for k, v in rel.get("counts", {}).items():
        print(f"  {k:<34} {v}")
    print(f"  submit_patch calls observed        {rel.get('submit_patch_calls')}")
    print(f"  submission evidence                {rel.get('submission_evidence')}")
    print(f"  missing-submission MESSAGE present {rel.get('missing_submission_message')}")
    print(f"  termination_error                  {str(rel.get('termination_error'))[:90]}")
    for n in rel.get("notes", []):
        print(f"  note: {n}")
    if rel.get("missing_submission"):
        print("  -> UNGRADED CANDIDATE OUTCOME. The candidate's own tool use. Grading was not")
        print("     exercised, which is UNOBSERVED, not a demonstrated instrument fault.")

    h("4. TASK PERFORMANCE (three distinct properties)")
    ps = perf["patch"]
    print(f"  patch bytes / chars                {ps['bytes']} / {ps['chars']}")
    print(f"  hunks / changed lines              {ps['n_hunks']} / {ps['n_changed_lines']}")
    print(f"  source paths                       {ps['source_paths'] or 'none'}")
    print(f"  test paths (reset before grading)  {ps['test_paths'] or 'none'}")
    print(f"  scratch paths                      {ps['scratch_paths'] or 'none'}")
    print(f"  [a] syntactically valid            {perf.get('syntactically_valid')}"
          + (f"   {ps['syntax_errors']}" if ps["syntax_errors"] else ""))
    print(f"  [b] application evidence           {perf.get('application_evidence')}"
          f"   (recorded size {perf.get('size_recorded')!r},"
          f" type_ok {perf.get('size_type_ok')}, matches {perf.get('size_matches')})")
    print(f"  [c] changes source                 {perf.get('changes_source')}")
    print(f"  => valid non-empty SOURCE patch    {perf.get('valid_source_patch')}")
    print(f"  resolved                           {perf.get('resolved')}")
    for n in perf.get("notes", []) or []:
        print(f"  note: {n}")
    if perf.get("persisted_record_error"):
        print(f"  RESULT RECORD PROBLEM              {perf['persisted_record_error']}")

    h("5. RECOVERY ATTRIBUTION")
    print(f"  rejections                         {rcv['rejections'] or 'none'}")
    print(f"  read-only successes after          "
          f"{[c['tool'] for c in rcv['read_only_after']] or 'none'}")
    print(f"  modifying candidates               "
          f"{[(c['tool'], c.get('target')) for c in rcv['candidates']] or 'none'}")
    print(f"  exact path matches                 "
          f"{[(c['tool'], c['target']) for c in rcv.get('exact_path_matches', [])] or 'none'}")
    print(f"  before/after change evidence       "
          f"{[c['change_evidence'] for c in (rcv['link'] or [])] or 'none'}")
    print(f"  acknowledged-only writes           "
          f"{[(c['tool'], c.get('target')) for c in rcv.get('acknowledged_only', [])] or 'none'}")
    print(f"  -> {rcv['verdict'].upper()}: {rcv.get('reason')}")

    h("6. STAGE-1 VERDICT")
    gate = {
        "instrument valid": inst["valid"],
        "grading exercised": grading["observed"],
        "verdict exit code": grading["verdict_exit"],
        "valid non-empty source patch": bool(perf.get("valid_source_patch")),
        "patch tied to the recorded size": bool(perf.get("size_matches")),
        # The absence of the harness's missing-submission message does not mean a submission
        # happened, so the observed submit_patch count is reported in section 3 and is NOT gated on:
        # agent_runner captures the working-tree diff as a fallback patch, so a run can produce a
        # gradeable patch without ever calling submit_patch.
        "no missing-submission message": not rel.get("missing_submission_message"),
    }
    for k, v in gate.items():
        print(f"  {'OK  ' if v else 'FAIL'}  {k}")
    passed = all(gate.values())
    print(f"\n  STAGE 1 {'PASSED' if passed else 'NOT PASSED'}")
    print("  A pass means the evaluation path produces a grade end to end. It does NOT mean the")
    print("  recovery rule helped, and it is not a performance result: one task, one arm, no pairing.")
    if passed and rcv["verdict"] != "recovery observed":
        print(f"  Recovery on this run: {rcv['verdict']}.")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage1_review.json").write_text(json.dumps({
        "pinned_notebook": {"path": str(notebook), "sha256": got},
        "artifacts_dir": str(artifacts), "artifacts_present": art["present"],
        "experiment_identity": ident,
        "instrument_validity": inst, "grading": grading, "candidate_reliability": rel,
        "task_performance": perf, "recovery": rcv,
        "stage1_gate": gate, "stage1_passed": passed,
        "instrument_state": inst["state"],
        "claims": [
            "Instrument reporting has three states: observed checks passed, grading path "
            "unobserved, and demonstrated failure. Unobserved is never reported as broken.",
            "The absence of a missing-submission message is not evidence that submit_patch was "
            "called; the observed call count is reported instead.",
            "A pass shows the path produces a grade, not that the rule helped.",
            "An accepted tool call does not prove a source change.",
            "A missing submission means grading was not exercised: UNOBSERVED, not a fault.",
            "Read-only operations never qualify as recovery writes.",
            "A write_file acknowledgment (filepath plus size) does not establish a byte change: it "
            "cannot distinguish a real change from a no-op write of identical bytes.",
            "Recovery is 'observed' only with a rejection, a different accepted MODIFYING operation "
            "on an exactly matching changed source path, and that operation's own BEFORE/AFTER change "
            "evidence; otherwise 'consistent with recovery; attribution unproven' or 'recovery "
            "unproven'.",
        ],
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_dir / 'stage1_review.json'} (raw artifacts untouched)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
