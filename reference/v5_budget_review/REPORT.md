# V5 baseline, version 1: ERROR before any run. Environment incompatibility.

Kernel `navin03/gemma4-v5-budget` version 1, ERROR checked 2026-10-20T05:00:35Z. Download exited
cleanly; 6 files hashed before analysis into `reference/v5_budget_review/raw_sha256.json`. Log span
139.4 s.

## Corrections to the first reading of this run

- **My earlier claim that swegemma was absent from the wheelhouse was wrong.** The saved log records
  `swegemma 0.2.11`, and the install completed: `installing 41 wheels...` with no error line. The
  dataset does list `swegemma-0.2.11-py3-none-any.whl`; my grep had truncated the listing.
- **Private-grader version is unknown.** Nothing here observes the private scorer's stack. The
  versions below are the public development runtime only.
- **The GPU figure is an account-level delta**, 0.00h to 0.08h. It is not this run's measured cost.
- **Download completeness is unverified against an authoritative inventory.** The remote file listing
  returned 0 entries for this errored kernel, so completeness rests on the clean download exit and on
  which pipeline stages produced artifacts. That is weaker than a name-by-name check.

## Recorded runtime versions, from the log

```
swegemma 0.2.11 | adk-submission 0.2.13 | adk-eval-core 0.1.0
google-adk 1.36.1 | vllm 0.19.1 | transformers 5.13.1 | litellm 1.82.4
```

Our pinned expectations were swegemma 0.2.7 and adk-submission 0.2.12. The wheelhouse dataset was
updated 2026-10-12, after our last successful run on 2026-10-07. We pin the Docker image but
`dataset_sources` carries no version, so the kernel took the current dataset.

## Demonstrated cause

Cell 7: `ModuleNotFoundError: No module named 'swegemma.models.discovery'`, raised before any server
start, evaluation or exposure. Verified by inspecting the actual wheel: in swegemma 0.2.11
`swegemma/models/` contains only `__init__.py` and `task.py`, and `validate_single_declared_model`
appears **nowhere** in the distribution. It was **removed**, not moved, and 0.2.11 exposes no
equivalent helper. `swegemma/models/__init__.py` now exports only `EvaluationResult`, `Task`,
`TaskResult`, `extract_test_files_from_patch`, `load_tasks`.

The notebook used that symbol in **one print statement**, not as a gate.

## All four planned outcomes

| # | Task | Candidate | Outcome | Grading | Patch | Budget-clock time |
|---|---|---|---|---|---|---|
| 1 | rich_3278 | V5 | not attempted | no | none | unavailable: agent session never started |
| 2 | rich_3535 | V5 | not attempted | no | none | unavailable |
| 3 | rich_3675 | V5 | not attempted | no | none | unavailable |
| 4 | rich_3942 | V5 | not attempted | no | none | unavailable |

Verified solves 0. Graded failures 0. Candidate no-patch or time-budget failures **0**. **Environment
failures 1, session level, invalidating all four rows.** The primary metric is not computable: zero
attempted, not four. No candidate failure occurred. The 139.4 s log span is setup wall clock, not
budget-clock time; no budget-clock measurement exists.


## Two different checks, not to be conflated

| check | where it runs | what it establishes |
|---|---|---|
| **saved-evidence consistency** (`scripts/preflight_v5_budget_v2.py`) | **locally, offline** | the stored JUnit XML parses and agrees with the stored node maps, 8 of 8, no parse errors, no duplicates, and a negative test confirms one changed outcome is detected. **No sandbox is created and no test is executed.** |
| **fresh Kaggle control replay** (`notebooks/v5_control_replay/v5_control_replay.ipynb`) | **on Kaggle, CPU only; version 1 failed before controls, repaired version unrun** | creates fresh sandboxes and actually reruns all eight baseline/reference arms under the current dependency set, preserving raw XML, stdout and stderr, patch return codes, provenance, canonicalization mappings and cleanup evidence |

Nothing in the local check can substitute for the fresh replay, and the fresh replay has **not passed** on Kaggle. CPU version 1 failed before either identity gate; the repaired notebook has not been launched. Private-grader versions remain UNKNOWN and are not observed by either check.

## Runtime identity gates in the fresh-replay notebook

Both gates are embedded in the notebook itself, in the cell before the sandbox-creating control cell:

- `verify_runtime_compiler()`: adk-submission must be **0.2.13** with per-file hashes matching the
  recorded manifest (wheel `f156f0bd84580ccb9334726d114d7a5481f16d3a6e2887cc4d276ced0ef8d99d`).
- `verify_runtime_swegemma()`: locates the **imported** swegemma package, requires version
  **0.2.11** and per-file hashes matching the recorded manifest (wheel
  `9ad876581f3acde8ec3c369858f0834e2b9f41a3cffce3ca42f09cb090aea9d3`), persists the observed
  identity with missing, extra and changed module lists to `pilot/swegemma_identity.json`, then
  refuses control execution on any mismatch.
