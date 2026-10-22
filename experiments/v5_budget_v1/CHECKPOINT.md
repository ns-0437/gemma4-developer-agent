# CHECKPOINT - V5 baseline LAUNCHED and ERRORED on an environment change; repair prepared offline

Updated 2026-10-22. Supersedes the prelaunch state this file previously described.

## What happened

Kernel `navin03/gemma4-v5-budget` version 1, pushed once 2026-10-20T04:51:16Z, armed hash
`8169ade01183908e54b8eb86b07f2fd98159d674642d03836de866668ceebe79`, disabled original preserved at
`experiments/v5_budget_v1/v5_budget_disabled.ipynb` (`7b85d464...`). **ERROR at 05:00:35Z before any
run.** All four rows not attempted: 0 solves, 0 graded failures, **0 candidate failures**, **1
session-level environment failure** invalidating the comparison. No budget-clock time exists.

## Demonstrated cause

`ModuleNotFoundError: No module named 'swegemma.models.discovery'` in cell 7. The log records
**swegemma 0.2.11** and **adk-submission 0.2.13**; the 41-wheel install succeeded. Inspecting the
actual 0.2.11 wheel: `swegemma/models/` holds only `__init__.py` and `task.py`, and
`validate_single_declared_model` is absent from the whole distribution with no equivalent helper.
**Removed, not moved.** The wheelhouse dataset was updated 2026-10-12; we pin the image but
`dataset_sources` has no version, so the kernel took the current dataset.

An earlier claim of mine that swegemma was absent from the wheelhouse was **wrong** and is corrected
in `reference/v5_budget_review/REPORT.md`, along with: private-grader version unknown, the GPU figure
is an account-level delta, and download completeness is unverified against an authoritative
inventory.

## Repair chosen, and the tradeoff

**Adaptation, not a dependency rollback.** The removed symbol was used in a single print, so it is
replaced by reading the single declared model from the candidate's own YAML, which the notebook
already hash-pins byte-for-byte. No validation is deleted: `validate_directory`, `compile_submission`
and the candidate-drift gate all remain.

The compiler baseline moves 0.2.12 to **0.2.13, explicitly verified**: wheel sha256
`f156f0bd84580ccb9334726d114d7a5481f16d3a6e2887cc4d276ced0ef8d99d`, 20 modules with per-file hashes
recorded in `experiments/v5_budget_v2/compiler_0_2_13_hashes.json`. swegemma 0.2.11 is likewise
extracted and hashed (`swegemma_0_2_11_hashes.json`, wheel `9ad876581f3acde8...`, 34 modules). The
identity gate is re-based, never bypassed.

Tradeoff: rolling the dataset back to a pre-2026-10-12 version would reproduce the known-good stack
exactly, but `dataset_sources` carries no version pin in our metadata today, so it would require a
metadata change and would freeze us on an older public stack. Adapting keeps us on the current public
wheelhouse at the cost of a new, explicitly verified compiler baseline. **Which stack the private
grader runs is UNKNOWN and is not observed by anything here**, so neither option can be justified by
grader alignment.

## CPU preflight, passing

`scripts/preflight_v5_budget_v2.py` -> `experiments/v5_budget_v2/PREFLIGHT.json`:

- imports: adk_submission, swegemma, swegemma.config, swegemma.models, google.adk, litellm, yaml
- versions observed: adk-submission 0.2.13, swegemma 0.2.11, google-adk 1.36.1, litellm 1.102.1
  (local litellm differs from the runtime's 1.82.4; recorded, not claimed equivalent)
- compiler identity against recorded 0.2.13 hashes: **True**
- removed symbol still absent: True; replacement returns `gemma-4-31b-it-qat-w4a16-ct`
- candidate `527acc5403d21a14...` validates and compiles: `swe_coder` + `code_analyzer`
- **saved-evidence consistency, 8 of 8**, with no parse errors and no duplicate identities. This
  parses stored XML against stored node maps and is **NOT a fresh control replay**; a negative test
  confirms one changed outcome is detected. Fresh replay is the separate CPU notebook below.
- `declared_model` edge cases all raise: zero models, multiple models, blank model string. The blank
  case exposed a real defect in my first implementation, now fixed. It is **sufficient for this
  frozen candidate's YAML shape only**; broader equivalence with the removed swegemma helper is
  **not** established.
- **swegemma identity** verified against recorded 0.2.11 per-file hashes, alongside the compiler
- **all four effective limits asserted**, not merely recorded: `time_minutes 5.0`, `turns 60`,
  `tool_calls 100`, `harness.command_timeout_seconds 60`. The earlier claim of a timeout mapping
  difference is **withdrawn**: `config.py` lines 181-183 map `timeout_seconds` into
  `harness.command_timeout_seconds`, and `tools/execution.py:32` consumes it.

**CPU success does not verify GPU inference, vLLM startup or any agent behaviour.**

## Preserved

Failed notebook kept as launched (`8169ade0...`); repair work lives separately under
`experiments/v5_budget_v2/`. V5 package `ca7ebe43...`, candidate V5 bytes, tasks, budgets and
`task_freeze.json` (`220869409441c04d...`) all unchanged.

## Fresh CPU control replay, prepared and disabled

`notebooks/v5_control_replay/v5_control_replay.ipynb` creates fresh sandboxes and reruns **all eight**
baseline/reference arms for the four development tasks under the current dependency set, preserving
raw JUnit XML, pytest stdout and stderr, patch and test-patch return codes, import provenance,
canonicalization mappings and cleanup evidence. CPU only, `enable_gpu false`, no machine shape. The
server, run loop and result packet cells are dropped by role marker and their absence asserted; no
`Evaluator(`, `submit_patch(`, `vllm serve`, `vllm.entrypoints` or `start_server` survives.

**Both runtime identity gates are now embedded in the notebook**, in the cell before the
sandbox-creating control cell: the existing `verify_runtime_compiler()` for adk-submission 0.2.13,
and a new `verify_runtime_swegemma()` that locates the imported package, requires version 0.2.11 and
matching per-file hashes, persists the observed identity plus missing/extra/changed lists to
`pilot/swegemma_identity.json`, and refuses control execution on mismatch.

`scripts/test_v5_control_replay_notebook.py` proves both directions: matching identities reach the
control stage with 8 arms, 0 evaluations and 0 servers; a changed swegemma module
(`version_ok=True, hashes_ok=False, changed=['config.py']`) and a wrong version
(`version_ok=False`) each refuse with **0 sandboxes created and no `control_recheck.json`**, with
details persisted.

**Local saved-evidence consistency is not fresh replay.** The local check parses stored XML against
stored node maps; the fresh replay executes the arms on Kaggle and has not passed on Kaggle. CPU version 1 was launched on October 20 and failed at the obsolete import before either identity gate; the repaired notebook has not been launched.

## Next decision

Authorize one CPU launch of the fresh control replay, which proves the repair on the real current
stack, before any GPU baseline. Not done this turn: no launch, no submission, no retry.
