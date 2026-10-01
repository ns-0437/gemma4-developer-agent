"""Generate notebooks/stage1/ - ONE run: candidate R on rich_3278. No Stage 2, no automatic follow-on.

Reuses scripts/make_compare_notebook.py, which itself reuses make_pilot_notebook.py, so the install,
verify, common, repair, precondition, control re-validation, server lifecycle, dispatch and report
cells are the code already covered by test_pilot_notebook.py, test_compare_dispatch.py,
test_stop_logic.py and test_trace_metrics.py. Only the inputs change: one task, one dispatched
candidate, a smaller session cap.

Candidate A is still embedded and still checked against R, because that check is what proves R differs
from the scored 0.06 agent in prompts/system.md and nothing else. **A is not dispatched.**

DISPATCH_CONFIRM stays False. This script never arms anything and never pushes.

Usage:
  python scripts/make_stage1_notebook.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import make_compare_notebook as M  # noqa: E402

TASK = "rich_3278"

MD = """# Stage 1: one task, one candidate, does the path produce a grade?

Candidate **R** on `rich_3278`. R is `experiments/tool_recovery_v1/candidate_R`; it differs from
candidate **A** (byte-identical to the submitted v3, which scored 0.06) in `prompts/system.md` and in
nothing else. A is embedded here only so that isolation can be checked, and **A is not run**.

**This notebook answers one question: does the evaluation path produce a grade end to end?** Success
is a valid non-empty source patch plus an observed grade, with valid controls, provenance and cleanup.
It is not a measurement of whether the recovery rule helps, and it cannot be: one task, one arm, no
paired comparison.

A grade proves the path works. Recovery is a separate claim, and it is supported only if the trace
shows a rejection followed by a **different** accepted operation and a verified source change.

Three questions are kept apart in the report:
  * instrument validity  - controls, provenance, grading machinery, cleanup
  * candidate reliability - rejected calls, repeated calls, missing submissions
  * task performance      - a verified solve, or not

A candidate that ends without submitting is an **ungraded candidate outcome**. It is not evidence that
the instrument is broken.

There is no Stage 2 in this notebook. Any broader comparison is a separate, separately reviewed
artifact.
"""


def main(arm: bool = False) -> None:
    M.TASKS = [TASK]
    M.SECOND_KEY = "R"
    M.SECOND_DIR_NAME = "candidate_R"
    M.SECOND_EXP = ROOT / "experiments" / "tool_recovery_v1"
    M.ORDER_EXPR = "ORDER = [(tid, 'R') for tid in TASK_IDS]   # Stage 1: R only, A is not dispatched"
    M.OUT_NAME = "stage1"
    M.KERNEL_ID = "navin03/gemma4-swe-agent-stage1"
    M.NB_FILENAME = "stage1.ipynb"
    M.KERNEL_TITLE = "gemma4-swe-agent-stage1"
    M.CFG_LABEL = "stage1 config:"
    M.RUN_COUNT_PHRASE = "the single run will NOT"
    M.MD = MD
    # One agent run plus CPU setup, two control arms and one precondition. Generous, not a promise:
    # startup has varied 6 to 9.6 minutes across past sessions.
    M.SESSION_CAP_MIN = 90
    M.RUN_RESERVE_MIN = 25
    # ARMING. Set only by an explicit --arm on the command line, which the launch record documents.
    # Everything else about the notebook is identical either way; the caller verifies that.
    M.ARM_FOR_LAUNCH = bool(arm)

    M.main()

    out = ROOT / "notebooks" / "stage1"
    nb = out / "stage1.ipynb"
    raw = nb.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    sources = ["".join(c["source"]) for c in doc["cells"] if c["cell_type"] == "code"]
    joined = "\n".join(sources)

    # Refuse to ship anything that is armed or that plans more than one run.
    want = "DISPATCH_CONFIRM = True" if arm else "DISPATCH_CONFIRM = False"
    other = "DISPATCH_CONFIRM = False" if arm else "DISPATCH_CONFIRM = True"
    assert want in joined, f"expected {want} in the generated notebook"
    assert other not in joined, f"unexpected {other} in the generated notebook"
    assert "ORDER = [(tid, 'R') for tid in TASK_IDS]" in joined, "run order was not narrowed to R"
    assert "TASK_IDS" in joined
    meta = json.loads((out / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert meta["id"] == "navin03/gemma4-swe-agent-stage1", meta["id"]
    assert meta.get("is_private") in (True, "true"), meta

    print("stage1 notebook sha256:", hashlib.sha256(raw).hexdigest())
    print("cells:", len(doc["cells"]))
    print("kernel:", meta["id"], "| private:", meta.get("is_private"),
          "| internet:", meta.get("enable_internet"), "| gpu:", meta.get("enable_gpu"))
    print(f"dispatch: {want}"
          + ("   ARMED: this notebook will dispatch one run when executed on Kaggle"
             if arm else "   (disabled)"))


if __name__ == "__main__":
    main(arm="--arm" in sys.argv)
