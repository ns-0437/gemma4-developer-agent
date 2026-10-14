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

## Status snapshot on October 12 (IST)

At 00:24 IST on 2026-10-12, Kaggle still reported PENDING with a blank public
score. The timestamped observation and original CSV are preserved separately
from the launch receipt in `reference/submission_v4_status_2026-10-12/`.
This saved status may become stale; it is not an instruction to submit again.

Read the saved response offline:

```powershell
python -B scripts/read_submission_snapshot.py reference/submission_v4_status_2026-10-12/submissions.csv --reference 57064155
```

The parser requires exactly one matching reference and reports blank scores
as null. A numeric zero is preserved as an available score. It rejects malformed
rows, duplicate column names and nonfinite scores; it performs no network calls.
The shared offline suite tests this parser and reads the preserved snapshot.

To verify a copied release tree, the provenance checker accepts `--root PATH`.
A missing file or broken identity exits nonzero with a diagnostic. Neither this
check nor CI evaluates candidate performance or retrieves a new score.

### Verify the observation and its source together

```powershell
python -B scripts/verify_submission_observation.py reference/submission_v4_status_2026-10-12
```

This checks the saved CSV hash, requires an offset-aware UTC observation time,
and reconstructs the selected row to compare with the saved report. An altered
score or status in the report is refused even when the CSV itself is intact.
The timestamp is recorded evidence, not independently authenticated time.
Neither file is rewritten, and no live Kaggle query occurs.

CI runs both the parser and observation regressions. Offline checks now launch
Python children in UTF-8 mode, so Unicode evidence reads consistently across
Windows locales. The real-child regression tests this with non-ASCII text.

## October 14 observation and repeatable status capture

At 08:53 IST on 2026-10-14, the API returned **COMPLETE** for reference
57064155 but left the public score blank. This does not establish a numeric
score or improvement. The saved CSV and verified observation are in
`reference/submission_v4_status_2026-10-14/`; the earlier PENDING snapshots
and original receipt remain unchanged.

For an explicitly requested fresh check, use a new directory:

```powershell
python -B scripts/capture_submission_status.py reference/NEW_UNIQUE_STATUS_DIRECTORY --reference 57064155
```

This makes one read-only CLI request with a 90-second timeout. It never retries,
polls, pushes a notebook or submits a package. An existing destination is refused
before the request, and a directory created concurrently is not overwritten.
Invalid or failed responses do not create a valid-looking observation directory.
If writing fails after directory creation, preserve the partial output for
inspection and choose a fresh destination; verification must pass before use.

CI tests capture with fake responses and verifies both saved observations;
it never runs the network capture command. COMPLETE and a numeric score are
separate facts: a blank score remains null even after completion.

## Confirmed V4 timeout: supersedes the blank-score interpretation

The full API record read on 2026-10-14 reports `errorDescription`:
"Your submission notebook exceeded the allowed runtime."
Kaggle still labels the record COMPLETE, with no numeric score. Therefore
COMPLETE cannot be interpreted as scoring success. The earlier CSV snapshots
were accurately preserved but incomplete for diagnosis: both CLI CSV and CLI
JSON summaries omit the error field.

The capture command now reads full API objects and saves `submissions.json`
with `format: api_json`. The verifier continues to support old CSV observations.
The new evidence is in `reference/submission_v4_error_2026-10-14/`; its outcome
is `error`, and its score remains null. Neither the original submission receipt
nor the frozen package has been changed.

Next engineering work should examine inference and per-task time budgets before
considering a new submission. This error does not identify a particular task,
give actual execution duration, or prove that thinking alone caused the timeout.
Do not automatically resubmit V4 or infer a score of zero.
