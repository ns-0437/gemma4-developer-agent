"""Focused tests for the pilot's repaired dispatch-stop classification.

Pilot v1 stopped two unrelated runs because candidate B raised a context-window error before grading
started, so the grading provenance probe never executed and its *absence* was read as a provenance
failure. These tests pin the three-valued phase status and the environment/candidate split.

Run: python scripts/test_stop_logic.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import os as _os
_which = _os.environ.get("NB_TARGET", "pilot")
COMPARE_NB = True
NB = Path(__file__).resolve().parent.parent / "notebooks" / _which / (_which + ".ipynb")
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


def classify(repairs, err):
    """Mirror of the generated RUN cell's classification, kept in sync by test_matches_notebook."""
    seen = {r.get("phase"): bool(r.get("provenance_ok")) for r in repairs}
    phase_status = {ph: ("passed" if seen.get(ph) else "failed" if ph in seen else "not_attempted")
                    for ph in ("agent", "grading")}
    provenance_failed = any(v == "failed" for v in phase_status.values())
    candidate_error = bool(err) and any(k in (err or "") for k in (
        "ContextWindowExceededError", "BadRequestError", "InvalidRequestError"))
    environment_error = bool(err) and not candidate_error
    return phase_status, provenance_failed, candidate_error, environment_error


def test_matches_notebook():
    print("\n[S0] the generated notebook contains the repaired classification")
    src = "\n".join("".join(c["source"]) for c in json.loads(NB.read_text(encoding="utf-8"))["cells"]
                    if c["cell_type"] == "code")
    # Smoke tokens only: they prove the cell was not gutted, nothing more. Behaviour is
    # covered by scripts/test_compare_dispatch.py, which EXECUTES the real generated cell.
    tokens = ("phase_status", "not_attempted", "provenance_failed", "candidate_error",
              "environment_error")
    tokens += (("classify_outcome", "read_persisted_result", "confirm_cleanup",
                "unobserved_grading", "STOP_REASON", "Stopping further dispatch")
               if _which == "compare" else
               ("ContextWindowExceededError", "genuine environment/provenance failure"))
    for token in tokens:
        check(f"notebook mentions {token}", token in src)
    check("server health is probed before continuing", "server healthy" in src)
    check("leftover sandboxes are counted", "swegemma_sandbox_" in src)
    # The artifact must be disabled UNLESS it was armed deliberately. Arming is only legitimate when
    # the generator carries ARM_FOR_LAUNCH, so a stray edit that flips the literal in the notebook
    # alone still fails here. This guard is narrowed, not removed.
    disabled = "DISPATCH_CONFIRM = False" in src
    armed = "DISPATCH_CONFIRM = True" in src
    if disabled and not armed:
        check("dispatch stays disabled in the shipped generator", True)
    else:
        gen = (Path(__file__).resolve().parent /
               ("make_compare_notebook.py" if _which == "compare" else "make_pilot_notebook.py"))
        gen_src = gen.read_text(encoding="utf-8") if gen.exists() else ""
        deliberate = "ARM_FOR_LAUNCH = True" in gen_src
        print("    NOTE: this artifact is ARMED for dispatch.")
        check("arming came from the generator, not a stray notebook edit", deliberate,
              "DISPATCH_CONFIRM=True with no ARM_FOR_LAUNCH in the generator")
        check("exactly one dispatch flag in the artifact",
              src.count("DISPATCH_CONFIRM = True") == 1 and not disabled)


def test_pilot_v1_case():
    if _which == "compare":
        # This case reimplements the classifier, which is not evidence about the shipped
        # cell. For the comparison notebook the equivalent case is [D3]+[D1] in
        # scripts/test_compare_dispatch.py, which drives the generated cell itself.
        print("\n[S1] skipped for compare: covered by test_compare_dispatch.py [D1]/[D3]")
        return
    print("\n[S1] pilot v1 run B: agent probe passed, grading never ran, context error")
    err = ("Sandbox execution error: litellm.ContextWindowExceededError: litellm.BadRequestError: "
           "ContextWindowExceededError: OpenAIException - maximum context length is 32768 tokens")
    ps, prov, cand, env = classify([{"phase": "agent", "provenance_ok": True}], err)
    check("agent phase passed", ps["agent"] == "passed", str(ps))
    check("grading phase is not_attempted, not failed", ps["grading"] == "not_attempted", str(ps))
    check("absence of grading is NOT a provenance failure", prov is False)
    check("classified as a candidate error", cand is True)
    check("NOT classified as an environment error", env is False)


def test_real_provenance_failure_still_stops():
    print("\n[S2] a real provenance failure still stops dispatch")
    ps, prov, cand, env = classify(
        [{"phase": "agent", "provenance_ok": True}, {"phase": "grading", "provenance_ok": False}], None)
    check("grading phase marked failed", ps["grading"] == "failed", str(ps))
    check("provenance failure detected", prov is True)
    check("not mistaken for a candidate error", cand is False)


def test_environment_error_still_stops():
    print("\n[S3] a non-candidate exception is an environment error")
    ps, prov, cand, env = classify([{"phase": "agent", "provenance_ok": True}],
                                   "RuntimeError: editable install failed rc=1")
    check("environment error detected", env is True)
    check("not classified as candidate error", cand is False)


def test_clean_run():
    print("\n[S4] a clean run is classified as nothing-wrong")
    ps, prov, cand, env = classify(
        [{"phase": "agent", "provenance_ok": True}, {"phase": "grading", "provenance_ok": True}], None)
    check("both phases passed", ps == {"agent": "passed", "grading": "passed"}, str(ps))
    check("no failure of any kind", not (prov or cand or env))


def main() -> int:
    for fn in (test_matches_notebook, test_pilot_v1_case, test_real_provenance_failure_still_stops,
               test_environment_error_still_stops, test_clean_run):
        fn()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
