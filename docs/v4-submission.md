# V4 submission handoff

Submitted on 2026-10-11 at 05:56:45 UTC (11:26:45 IST), reference **57064155**,
from `navin03/gemma4-swe-agent-submit` version **4**. The saved receipt records
PENDING at 05:57:17 UTC; this is historical evidence, not live status.

The package is unchanged frozen thinking-ON, SHA-256
`527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33`.
Official compiler 0.2.12 source validation passed. Its Kaggle-downloaded ZIP
was compared byte-for-byte with the release archive before submission.

## Evidence and limits

The candidate solved `rich_3278` twice in development. Broader validation
criteria were not met; the user explicitly requested a submission today, so
this was recorded as exploratory. There is no supported prediction of an
improvement over V3's historical 0.06. The repaired six-run holdout comparison
was not launched as part of this submission.

## Verify offline

```powershell
python -B scripts/verify_v4_submission.py
python -B scripts/test_verify_v4_submission.py
python -B scripts/run_offline_checks.py
```

These checks are also in CI. They link the source files, frozen candidate ZIP,
release ZIP, notebook payload and downloaded ZIP. The raw log and download are
covered by a separate inventory. Verification does not query the current score.

## Resume safely

Read the competition submission history once and locate reference `57064155`.
If terminal, record its observed status and score with a timestamp; do not infer
a score from notebook COMPLETE. Preserve the original pending receipt and raw
artifacts, adding later observations separately. Do not push or submit again
merely to check status. Any further experiment or candidate change is separate
from this saved release.

- [Original receipt](../releases/v4_submission_record.json)
- [Raw output inventory](../reference/submission_v4_review/raw_sha256.json)
- [Prepared validation checkpoint](../experiments/final_validation_v2/CHECKPOINT.md)
