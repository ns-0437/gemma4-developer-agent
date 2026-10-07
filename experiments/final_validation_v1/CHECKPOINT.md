# CHECKPOINT - final validation v1 ERRORED at the control gate; nothing exposed

Updated 2026-10-07. Kernel `navin03/gemma4-final-validation` version 1, pushed once
2026-10-07T03:24:49Z, **ERROR** at 03:42:17Z. No retry, repush or submission.

## State

**6 of 6 planned runs missing. 0 solves, 0 graded failures, 0 candidate failures, 1 session-level
environment failure.** The control gate refused to start the model because `requests_7427`'s controls
did not reproduce: its `tests/test_utils.py` has a parametrised test whose parameter is the absolute
sandbox path, so the node ID changes every run. `pytest_exit` matched saved on both arms; behaviour
was identical, only a node name differed. 4 of 6 control arms agreed.

**No hold-out task was exposed.** No `pilot/EXPOSURE.json`, no run directory. The authorization to
consume `fastapi_15280`, `requests_7427`, `rich_3894` was **not** used. See `EXPOSURE_RECORD.json`.
`task_freeze.json` unchanged (`220869409441c04d...`); all 12 tasks still protected.

## Identity verified

Downloaded packages re-bundle to `b8da59c1...` (V3) and `527acc54...` (ON). Pulled notebook is not
byte-identical (`2992e450...` vs armed `f7495570...`) because Kaggle reserializes JSON, but all 13
normalized cell sources, notebook metadata and both embedded payloads are identical, and
`DISPATCH_CONFIRM = True` is present.

## Paths

- raw, unchanged: `reference/final_validation_run_2026-10-07/` (27 files)
- manifest hashed before analysis: `reference/final_validation_review/raw_sha256.json`
- report: `reference/final_validation_review/REPORT.md`
- exposure record: `experiments/final_validation_v1/EXPOSURE_RECORD.json`
- launch record: `experiments/final_validation_v1/LAUNCH_RECORD.json`

## Next action, needs your decision

**No submission recommended; nothing was measured.** The blocker is the control gate's handling of
node IDs that embed the sandbox path. Two options, neither taken:
1. Normalize sandbox paths inside node IDs before comparison. A change to a protection gate, so it
   needs authorization and its own tests.
2. Reselect the requests task by the next smallest `sha256(instance_id)` (`requests_6644`), which
   would expose a different hold-out task and needs separate approval.

Candidates were NOT revised using these results, and no further experiment was launched.
