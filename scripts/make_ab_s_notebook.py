"""Generate notebooks/ab_s/ - the eight-run A vs S comparison on the four Rich development tasks.

Reuses scripts/make_compare_notebook.py, which reuses make_pilot_notebook.py, so the install, verify,
common, repair, precondition, control re-validation, server lifecycle, dispatch and report cells are
the code already covered by test_pilot_notebook.py, test_compare_dispatch.py, test_stop_logic.py and
test_trace_metrics.py. Only the inputs change: candidate S in place of B, and an A/S then S/A order.

RICH-ONLY. The four development tasks are all Textualize/rich. Every validated fastapi and requests
task is in the protected hold-out and stays there, so this comparison cannot say anything about
cross-repository behaviour. The generator refuses to run if any selected task touches the hold-out.

DISPATCH_CONFIRM stays False. This script never arms anything and never pushes.

Usage:
  python scripts/make_ab_s_notebook.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import make_compare_notebook as M  # noqa: E402

TASKS = ["rich_3278", "rich_3535", "rich_3675", "rich_3942"]

MD = """# A vs S: does a concise workflow prompt reach a graded patch more often?

Eight runs, four development tasks, two candidates.

**A** is byte-identical to the submitted v3 (`b8da59c1...`), which scored 0.06. **S** differs from A in
`prompts/system.md` only: the same job at 413 words instead of 1247, as a
understand -> reproduce once -> edit -> verify -> submit workflow with one mid-run editing checkpoint.
Model, sampling, tools, analyzer prompt and budgets are identical, and the official compiler confirms
both resolve to the same generation config and the same tool list.

Order alternates A/S then S/A across tasks to blunt ordering bias. It does not remove shared-server
effects: all eight runs use one vLLM process.

**This is a Rich-only diagnostic. It is not evidence of cross-repository improvement.** All four tasks
are Textualize/rich, because every validated fastapi and requests task sits in the protected hold-out
and was not moved. A result here generalises to rich at best.

**What prompted it.** Stage 1 ran candidate R on `rich_3278` and produced no patch: 60 turns, one
command issued 56 times, no rejected calls, no source edit, no grade. R already contained five
explicit prohibitions on repeating identical calls. The feedback-path audit found token growth and
source inspection consistent with retained history and found no defect, while noting it cannot prove
what the requests contained. So the open question is whether a shorter prompt is followed more
reliably. **That is a hypothesis about prompt packaging, not a demonstrated cause.**

**Three measurements are kept separate in the report:**
  * RELIABILITY  a valid non-empty source patch, and observed grading
  * PERFORMANCE  paired solves, losses, ties and ungraded outcomes
  * MECHANISM    repeated calls and operation-level edit evidence

A patch is a source patch whatever produced it: a shell edit through `run_command` counts exactly as
an `edit_file` call does. More graded but incorrect patches is not an improvement.

Controls for these four tasks came from the CPU screen, which ran in subprocess mode. This notebook
runs under the real GPU harness and re-validates both arms before dispatch.
"""


def main(arm: bool = False) -> None:
    M.TASKS = TASKS
    M.SECOND_KEY = "S"
    M.SECOND_DIR_NAME = "candidate_S"
    M.SECOND_EXP = ROOT / "experiments" / "concise_workflow_v1"
    M.ORDER_EXPR = ("ORDER = [(tid, cand) for i, tid in enumerate(TASK_IDS)\n"
                    "         for cand in (('A', 'S') if i % 2 == 0 else ('S', 'A'))]")
    M.OUT_NAME = "ab_s"
    M.KERNEL_ID = "navin03/gemma4-swe-agent-ab-s"
    M.NB_FILENAME = "ab_s.ipynb"
    M.KERNEL_TITLE = "gemma4-swe-agent-ab-s"
    M.CFG_LABEL = "A/S config:"
    M.RUN_COUNT_PHRASE = "the eight runs will NOT"
    M.MD = MD
    M.SESSION_CAP_MIN = 300
    M.RUN_RESERVE_MIN = 25
    # ARMING. Set only by an explicit --arm on the command line, recorded in the launch record.
    # Nothing else about the notebook changes; the caller verifies that.
    M.ARM_FOR_LAUNCH = bool(arm)

    M.main()

    out = ROOT / "notebooks" / "ab_s"
    nb = out / "ab_s.ipynb"
    raw = nb.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    joined = "\n".join("".join(c["source"]) for c in doc["cells"] if c["cell_type"] == "code")

    want = "DISPATCH_CONFIRM = True" if arm else "DISPATCH_CONFIRM = False"
    other = "DISPATCH_CONFIRM = False" if arm else "DISPATCH_CONFIRM = True"
    assert want in joined, f"expected {want} in the generated notebook"
    assert other not in joined, f"unexpected {other} in the generated notebook"
    assert "('A', 'S') if i % 2 == 0 else ('S', 'A')" in joined, "run order was not set to A/S, S/A"
    assert 'TASK_IDS = ["rich_3278", "rich_3535", "rich_3675", "rich_3942"]' in joined, "task set drift"
    assert 'CAND_DIRS["S"]' in joined, "candidate S key not wired into the isolation check"
    held = set(M.protected_holdout())
    assert not (set(TASKS) & held), "selected tasks intersect the protected hold-out"
    meta = json.loads((out / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert meta["id"] == "navin03/gemma4-swe-agent-ab-s", meta["id"]
    assert meta.get("is_private") in (True, "true"), meta

    print("\nab_s notebook sha256:", hashlib.sha256(raw).hexdigest())
    print("cells:", len(doc["cells"]))
    print("kernel:", meta["id"], "| private:", meta.get("is_private"),
          "| internet:", meta.get("enable_internet"), "| gpu:", meta.get("enable_gpu"))
    order = [(t, c) for i, t in enumerate(TASKS) for c in (("A", "S") if i % 2 == 0 else ("S", "A"))]
    print("run order:", order)
    print(f"dispatch: {want}"
          + ("   ARMED: this notebook will dispatch eight runs when executed on Kaggle"
             if arm else "   (disabled)"))


if __name__ == "__main__":
    main(arm="--arm" in sys.argv)
