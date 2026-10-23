# V5 measurement status and safeguards: October 23, 2026

The last saved V5 competition score is 0.13 (submission 57378663). V5 adds
evaluation limits to the frozen ON agent. No score change is inferred from
repository commits, control tests, or the running baseline experiment.

## What ran

The October 20 GPU baseline and first CPU replay both failed at the removed
swegemma.models.discovery import. The repaired CPU replay subsequently passed:
compiler 0.2.13 and swegemma 0.2.11 module identities matched; all eight controls
and four preconditions passed with cleanup. Its 27 raw files are preserved under
reference/v5_control_replay_v2_2026-10-22T16-01-44Z. Remote basenames matched;
remote byte completeness remains unverified because listed sizes disagreed.

The repaired GPU baseline was pushed once on October 22 at 16:10:30Z, kernel
navin03/gemma4-v5-budget-v2, version 1. Its launch receipt is under
experiments/v5_budget_v2/gpu_baseline. Armed SHA-256:
066b5fb71f8d432826fe251b69a88a54dbf7725ce756427f2e8bdb1eb4f1fdc9.
The preserved disabled SHA-256 is
70f9d5d98baa44ae77396013cc036bbec6a6a3599f43a9cd55a54dee1bc10989.

No new Kaggle status request was made while preparing these seven commits.
This document does not claim that the GPU run is complete or that its candidate
improved. A later read-only status check and artifact review are still needed.

## Reproduce verification

Run `python -B scripts/run_offline_checks.py` for all 36 portable CI checks.
The following checks cover the recent work:

- `verify_v5_budget_launch.py` verifies the armed notebook equals the frozen
  disabled bytes plus exactly one dispatch substitution. It checks metadata,
  version, candidate, order, budgets and single-push receipt without execution.
- `test_v5_budget_v2_notebook.py` validates that receipt before simulating both
  dispatch states. Four rows remain visible; compiler drift and control cleanup
  failure block model startup. The launched file is never rewritten.
- `verify_v5_cpu_evidence.py` hashes the full saved inventory, verifies dependency
  identities, all eight distinct arms, preconditions, checkout import paths,
  patch return codes and cleanup, and cross-checks per-arm records and raw XML
  against the aggregate. This audits saved evidence, not fresh test execution.
- `verify_v5_dependencies.py` checks pinned manifests and source trees without
  importing the ML packages. Missing, extra and changed modules stay distinct.
- `test_v5_cands_cell_real.py` remains a separate dependency-equipped local test.
  It executes the unchanged generated candidate cell with automatic discovery of
  extracted distributions. LiteLLM pricing-map fetches are disabled. This does
  not substitute for Kaggle runtime evidence or prove GPU serving works.

## Preserve uncertainty and evidence

Generators refuse any matching LAUNCH_RECORD.json or LAUNCH_RECORD_*.json in
an experiment directory, even malformed receipts. Use fresh versioned paths;
never remove a launch receipt to regenerate over launched evidence.

Shared packet JSON parsing rejects duplicate keys, NaN, Infinity and float
overflow. A full Kaggle submission response can omit errorDescription. Capture
now preserves its score with outcome `score_observed_error_unknown`, rather
than failing the capture or inventing a no-error field. Explicit errors still
take precedence, and unknown error details remain explicit in saved observations.

Frozen releases, raw evidence, notebook bytes and the task freeze were not edited.
Private-grader versions and runtime parity remain unknown. Next: review the four
V5 baseline outcomes before proposing a matched candidate improvement; do not
predict 0.45 or claim any score gain from these engineering checks.
