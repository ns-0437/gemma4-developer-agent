"""Generate notebooks/compare/ - the eight-run A/B prompt-package comparison (4 tasks x 2 candidates).

A = experiments/ab_v3_vs_short/candidate_A  (byte-identical to releases/v3, the submitted 0.06 agent)
B = experiments/ab_v3_vs_short/candidate_B  (same bytes except prompts/system.md, 1247 -> 672 words)

This REUSES make_pilot_notebook.py rather than duplicating it. Every executable cell (install, verify,
common, leak check, candidate unpack, editable-install repair, preconditions, server lifecycle, run
loop with its stop logic, report) is the code already covered by test_pilot_notebook.py (82 assertions)
and test_stop_logic.py (22). Only the inputs change: which candidates, which tasks, which saved control
evidence, and the session budget for eight runs instead of four.

Control evidence comes from the CPU screening run (reference/evalset_run2), which ran in SUBPROCESS
mode. The comparison runs under the real GPU harness. That is a documented environment difference, not
a validated equivalence - see the launch packet's unresolved risks.

Usage:
  python scripts/make_compare_notebook.py
  (review, then push manually - this script never dispatches anything)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_cells as C  # noqa: E402
import make_pilot_notebook as P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments" / "ab_v3_vs_short"
EVID = ROOT / "reference" / "evalset_run2" / "output" / "evalset" / "evidence"
TASKS = ["rich_3278", "rich_3535", "rich_3675", "rich_3942"]

# Overridable by a caller that reuses this generator (see make_stage1_notebook.py). The defaults
# reproduce the eight-run A/B comparison byte-for-byte.
SECOND_KEY = "B"                     # the non-baseline candidate's key
SECOND_DIR_NAME = "candidate_B"      # its directory under EXP
SECOND_EXP = None                    # None: use EXP; otherwise this experiment directory
ORDER_EXPR = None                    # None: alternating A/B pairs; else a replacement expression
OUT_NAME = "compare"                 # notebooks/<OUT_NAME>/
KERNEL_ID = "navin03/gemma4-swe-agent-compare"
NB_FILENAME = "compare.ipynb"
KERNEL_TITLE = "gemma4-swe-agent-compare"
CFG_LABEL = "compare config:"
RUN_COUNT_PHRASE = "the eight runs will NOT"
CUSTOMIZE_CELLS = None               # optional final specialization; defaults preserve old notebooks

# 8 runs at a 10-minute agent budget, plus grading, plus ~20 min server startup.
ARM_FOR_LAUNCH = False  # the single authorised launch (2026-09-29) has been used; disarmed 2026-09-30
SESSION_CAP_MIN = 300
RUN_RESERVE_MIN = 25


def _workspace_root(pkg_file: str) -> str:
    """Sandbox workspace root implied by a recorded grading import path, or "" if absent."""
    marker = "/workspace"
    i = pkg_file.find(marker)
    return pkg_file[: i + len(marker)] if i >= 0 else ""


FREEZE = EXP / "task_freeze.json"


def protected_holdout() -> list:
    """The frozen protected hold-out. Read, never written."""
    return list(json.loads(FREEZE.read_text(encoding="utf-8"))["protected_holdout"])


def assert_tasks_not_held_out(tasks) -> None:
    """Refuse to generate any notebook whose task set touches the protected hold-out.

    Added 2026-09-30 after a proposal named `fastapi_14873` and `requests_7427` as development tasks
    when both are protected. All seven valid fastapi/requests tasks are in the hold-out, and the
    freeze records that the dev-eligible pool is therefore 100% Textualize/rich. The freeze is not
    modified to make a task available: the guard fails instead.
    """
    held = set(protected_holdout())
    overlap = sorted(set(tasks) & held)
    if overlap:
        raise SystemExit(
            "REFUSING TO GENERATE: selected tasks intersect the protected hold-out.\n"
            f"  selected  : {sorted(tasks)}\n"
            f"  protected : {sorted(held)}\n"
            f"  overlap   : {overlap}\n"
            "Remove them from the selection. Do not edit task_freeze.json to free a task.")
    print(f"hold-out check: {len(tasks)} selected task(s) disjoint from "
          f"{len(held)} protected task(s)")


def compare_evidence() -> dict:
    """Map the screening run's baseline/reference arms onto the phase names the notebook cell expects.

    `agent_pkg_file` is reported as the string "unavailable": the screen ran no agent, so there is no
    agent-side import path for these controls. It is never filled with a placeholder that could read
    as a measurement.
    """
    out = {}
    for tid in TASKS:
        rec = {}
        for arm, phase in (("baseline", "negative"), ("reference", "positive")):
            a = json.loads((EVID / tid / arm / "arm.json").read_text(encoding="utf-8"))
            nodes = a.get("nodes") or {}
            rec[phase] = {
                "pytest_exit": a.get("pytest_exit"),
                "workspace_real": _workspace_root(a.get("grading_import", "")),
                "agent_pkg_file": "unavailable (no agent ran in the control)",
                "pytest_pkg_file": a.get("grading_import", ""),
                "import_in_checkout": a.get("import_in_checkout"),
                "patch_rc": a.get("patch_rc"),
                "test_patch_rc": a.get("test_patch_rc"),
                "nodes": dict(nodes),
                "n_cases": len(nodes),
                "failed_nodes": sorted(n for n, o in nodes.items() if o == "failed"),
                "passed_nodes": sorted(n for n, o in nodes.items() if o == "passed"),
                "failed": sorted(n for n, o in nodes.items() if o == "failed"),
                "errored": sorted(n for n, o in nodes.items() if o == "errored"),
            }
        out[tid] = rec
    return out


MD = """# Eight-run A/B prompt-package comparison

Four development tasks x two candidates. **A** is byte-identical to the submitted v3
(`b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b`), which scored 0.06. **B** differs
only in `prompts/system.md`: the same workflow at 672 words instead of 1247, with the arbitrary
two-attempt surrender rule removed. Model, sampling, tools, analyzer prompt and budgets are identical;
the official compiler confirms both resolve to the same generation config and the same tool list.

Order alternates A/B then B/A across tasks to blunt systematic ordering bias. It does not remove
shared-server effects: all eight runs use one vLLM process.

**Four tasks cannot establish which prompt is better.** Eight runs at this sample size can show whether
the experiment produces usable, gradeable evidence and can surface a large effect. Read it as an
instrument check, not as a result.

Controls for these four tasks came from the CPU screen, which ran in subprocess mode. This notebook
runs under the real GPU harness. Treat the controls as task-selection evidence, not as proof that the
same baseline/reference behaviour holds here.
"""


def main() -> None:
    assert_tasks_not_held_out(TASKS)
    second_exp = SECOND_EXP or EXP
    P.CANDIDATES = {"A": EXP / "candidate_A", SECOND_KEY: second_exp / SECOND_DIR_NAME}
    P.PILOT_TASKS = TASKS
    P.OUT = ROOT / "notebooks" / OUT_NAME
    P.KERNEL_ID = KERNEL_ID
    P.control_evidence = compare_evidence
    P.MD = MD
    # The screening controls ran with NO agent, so there is no agent-side import path to check.
    # Rather than fill that field with a placeholder that would read as a measurement, the guard is
    # narrowed to the provenance the evidence actually carries, and the notebook prints the fact.
    old = "for e in (neg,pos) for key in ('agent_pkg_file','pytest_pkg_file')))"
    new = "for e in (neg,pos) for key in ('pytest_pkg_file',)))"
    assert old in P.TASKS, "provenance guard not found; refusing to generate"
    old_print = 'print(f"    baseline-fails / gold-passes / imports-in-checkout: {ok}")'
    assert old_print in P.TASKS, "guard print not found; refusing to generate"
    new_print = "\n".join([
        'print(f"    baseline-fails / gold-passes / grading-import-in-checkout: {ok}")',
        '    print("    agent-side import provenance: UNAVAILABLE (no agent ran in the control)")',
        '    print(f"    control patch_rc={neg.get(\'patch_rc\')}'
        ' test_patch_rc={neg.get(\'test_patch_rc\')}")',
    ])
    P.TASKS = P.TASKS.replace(old, new).replace(old_print, new_print)

    # The pilot's A/B differed in configs/sampling.yaml (a thinking flag). This experiment's A/B must
    # differ in prompts/system.md and in NOTHING else, so the isolation check is inverted: sampling
    # must be byte-identical and the system prompt must be the only file that differs.
    iso_old = ('assert delta == ["-  include_thoughts: false", "+  include_thoughts: true"], delta')
    assert iso_old in P.CANDS, "isolation assertion not found; refusing to generate"
    P.CANDS = P.CANDS.replace(iso_old, 'assert delta == [], f"sampling must be identical, got {delta}"')
    eq_old = '    if rel == "configs/sampling.yaml":'
    assert eq_old in P.CANDS, "per-file equality check not found; refusing to generate"
    P.CANDS = P.CANDS.replace(eq_old, '    if rel == "prompts/system.md":')
    sb_old = "assert a.replace(b'include_thoughts: false', b'include_thoughts: true') == b, 'Unexpected sampling bytes'"
    assert sb_old in P.CANDS, "sampling byte check not found; refusing to generate"
    P.CANDS = P.CANDS.replace(sb_old, "assert a == b, 'sampling.yaml must be byte-identical between A and B'")
    P.CANDS = P.CANDS.replace(
        'print("every other file is byte-identical between A and B")',
        'sa = (CAND_DIRS["A"] / "prompts" / "system.md").read_bytes()\n'
        'sb = (CAND_DIRS["B"] / "prompts" / "system.md").read_bytes()\n'
        'assert sa != sb, "A and B have the same system prompt: nothing is being compared"\n'
        'print(f"prompts/system.md is the ONLY difference: A={len(sa)}B B={len(sb)}B")\n'
        'print("every other file is byte-identical between A and B")')
    # Rename the non-baseline candidate's key only if a caller asked for a different one, so the
    # default eight-run artifact stays byte-identical.
    if SECOND_KEY != "B":
        P.CANDS = (P.CANDS
                   .replace('CAND_DIRS["B"]', f'CAND_DIRS["{SECOND_KEY}"]')
                   .replace("CAND_DIRS['B']", f"CAND_DIRS['{SECOND_KEY}']")
                   .replace('"A and B have the same system prompt',
                            f'"A and {SECOND_KEY} have the same system prompt')
                   .replace('B={len(sb)}B', SECOND_KEY + '={len(sb)}B')
                   .replace('byte-identical between A and B', f'byte-identical between A and {SECOND_KEY}'))

    # --- shared sandbox-cleanup helpers, available to the controls AND the dispatch loop ---
    P.COMMON = P.COMMON + C.COMMON_CLEANUP_HELPERS

    # --- dispatch classification, cleanup gating and stop reasons (review items 2 and 3) ---
    P.RUN = P.RUN.replace("ORDER = [(tid, cand)", C.DISPATCH_HELPER + "\nORDER = [(tid, cand)", 1)
    if ORDER_EXPR is not None:
        order_old = ("ORDER = [(tid, cand) for i, tid in enumerate(TASK_IDS)\n"
                     "         for cand in (('A', 'B') if i % 2 == 0 else ('B', 'A'))]")
        assert order_old in P.RUN, "run-order anchor missing; refusing to generate"
        P.RUN = P.RUN.replace(order_old, ORDER_EXPR, 1)
    for old, new in C.RUN_REPLACEMENTS:
        assert old in P.RUN, f"RUN anchor missing, refusing to generate: {old[:70]!r}"
        P.RUN = P.RUN.replace(old, new, 1)

    # --- one report row per planned ORDER entry (review item 4) ---
    for old, new in C.REPORT_REPLACEMENTS:
        assert old in P.REPORT, f"REPORT anchor missing, refusing to generate: {old[:70]!r}"
        P.REPORT = P.REPORT.replace(old, new, 1)

    # --- re-validate the four controls under THIS setup before dispatch (review item 7) ---
    cmds = {t: json.loads((EVID / t / "baseline" / "arm.json").read_text(encoding="utf-8"))["pytest_cmd"]
            for t in TASKS}
    screen = {r["id"]: r for r in json.loads(
        (ROOT / "reference" / "evalset_run2" / "output" / "evalset" / "screen.json")
        .read_text(encoding="utf-8"))}
    target_nodes = {t: sorted(screen[t]["target_nodes"]) for t in TASKS}
    assert all(target_nodes.values()), "a selected task has no target nodes"
    for _old, _new in C.PRECOND_REPLACEMENTS:
        assert _old in P.PRECOND, f"PRECOND anchor missing: {_old[:60]!r}"
        P.PRECOND = P.PRECOND.replace(_old, _new, 1)
    P.PRECOND = (P.PRECOND.replace(
                     "from swegemma.config import EvalConfig",
                     "from swegemma.config import EvalConfig\n"
                     "import base64 as _b64mod\n"
                     "import hashlib as _hashlib\n"
                     "import tempfile as _tempfile\n"
                     "import re as _re_mod\n"
                     "import os\n"
                     "from swegemma.harness.verification import apply_patch_in_container\n"
                     "import traceback as _tbmod")
                 + "\nCONTROL_PYTEST_CMD = " + repr(cmds)
                 + "\nCONTROL_TARGET_NODES = " + repr(target_nodes)
                 + "\n" + C.CONTROL_REVALIDATION)

    old_close, new_close = C.CLOSING_REPLACEMENT
    assert old_close in P.REPORT, "closing-note anchor missing; refusing to generate"
    P.REPORT = P.REPORT.replace(old_close, new_close, 1)

    # --- context headroom (review item 6) ---
    # CORRECTED against the installed ADK 1.36.1 execution path. An earlier comment here called
    # token_threshold "post-invocation only", which is wrong.
    #
    #   flows/llm_flows/single_flow.py:49    wires compaction.request_processor into the chain
    #   flows/llm_flows/compaction.py        CompactionRequestProcessor.run_async, documented as
    #                                        "Compacts session events before contents are prepared
    #                                        for model calls" -> it runs PRE-model-call
    #   apps/compaction.py:425               _run_compaction_for_token_threshold_config
    #   apps/compaction.py:474               _run_compaction_for_token_threshold, the post-invocation
    #                                        helper; runners.py:603 handles the sliding-window path
    #
    # The trigger is _latest_prompt_token_count(session.events): the most recently RECORDED prompt
    # token count from an earlier response's usage metadata. If that is None or below the threshold,
    # nothing is compacted. So the threshold is a LAGGING signal, driven by prior usage, and it is
    # not a reservation of input or output space. Tool output produced since that measurement is not
    # counted, so a request can still exceed the window even while the threshold is respected.
    # Lowering it only widens the margin; it cannot guarantee the next request fits.
    #
    # 20480 sits below max_model_len - max_output_tokens (32768 - 8192 = 24576), leaving room for
    # the retained raw events and for growth before the next measurement. This is an EVALUATION
    # setting, applied identically to A and B, and it differs from the submitted configuration:
    # EvalConfig.events_compaction_config defaults to None and agent_runner only forwards it when
    # set, so grading applies no compaction at all unless the graders configure one.
    old_compaction = "compaction_interval=15, overlap_size=2, token_threshold=32768, event_retention_size=5)"
    assert old_compaction in P.RUN, "compaction config anchor missing; refusing to generate"
    P.RUN = P.RUN.replace(old_compaction,
                          "compaction_interval=15, overlap_size=2, token_threshold=20480, event_retention_size=5)")

    # LAUNCH ARMING. User authorised exactly one private GPU launch on 2026-09-29.
    # This is the ONLY executable difference from the reviewed, disabled notebook
    # (216f7d8c8a40323af1da60b752b6d5c6c6586a73c2347364aee8a783b66884f5).
    # Set ARM_FOR_LAUNCH back to False to regenerate the disabled artifact.
    if ARM_FOR_LAUNCH:
        assert "DISPATCH_CONFIRM = False" in P.CFG, "dispatch flag not found; refusing to arm"
        P.CFG = P.CFG.replace("DISPATCH_CONFIRM = False", "DISPATCH_CONFIRM = True", 1)

    P.CFG = (P.CFG
             .replace("SESSION_CAP_MIN  = 150", f"SESSION_CAP_MIN  = {SESSION_CAP_MIN}")
             .replace("RUN_RESERVE_MIN = 25", f"RUN_RESERVE_MIN = {RUN_RESERVE_MIN}")
             .replace("SESSION_CAP_MIN  =",
                      chr(83) + "ANDBOX_ROOT_STR = " + chr(34) + "/tmp" + chr(34) +
                      "    # where swegemma creates its sandbox directories" + chr(10) +
                      "CLEANUP_GRACE_S  = 45        # bounded wait for THIS run's sandboxes to be torn down" + chr(10) +
                      "SESSION_CAP_MIN  =")
             .replace("pilot config:", CFG_LABEL)
             .replace("the four runs will NOT", RUN_COUNT_PHRASE))
    if CUSTOMIZE_CELLS is not None:
        CUSTOMIZE_CELLS(P)
    P.main()

    out = P.OUT
    nb = out / "pilot.ipynb"
    tgt = out / NB_FILENAME
    if nb.exists():
        tgt.write_text(nb.read_text(encoding="utf-8"), encoding="utf-8")
        nb.unlink()
    meta = json.loads((out / "kernel-metadata.json").read_text(encoding="utf-8"))
    meta["title"] = KERNEL_TITLE
    meta["code_file"] = NB_FILENAME
    (out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("notebook sha256:", hashlib.sha256(tgt.read_bytes()).hexdigest())
    print("cells:", len(json.loads(tgt.read_text(encoding='utf-8'))["cells"]))


if __name__ == "__main__":
    main()
