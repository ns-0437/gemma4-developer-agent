# V5 measurement repair: October 22, 2026

V5 scored 0.13 in the saved October 20 API response (submission 57378663).
The five V5 agent files are identical to frozen ON; only evaluation limits were
added to the submission ZIP. This is not a causal attribution of the score change.

## Execution state

The four-task GPU baseline failed before evaluation on October 20. The public
wheelhouse supplied swegemma 0.2.11, which removed models.discovery, and
adk-submission 0.2.13 instead of the earlier compiler baseline.

CPU replay version 1 then failed at the same obsolete import. The replacement
had only been implemented in a local preflight, not in the generated notebook.
Neither runtime identity gate nor any of its eight control arms ran.

The repaired CPU notebook is disabled, SHA-256
`bedb8c0ab57eb5c5707aad8c1ff247987c8a30ecb2350995d675b56bb11cd9a9`.
It now embeds the replacement and runs the compiler and swegemma identity gates
before candidate validation. No repaired CPU launch or GPU baseline result is
claimed here. Private-grader dependency versions remain unknown.

## Reproduce local checks

- `python -B scripts/test_v5_control_replay_notebook.py`: simulated services;
  verifies eight controls, no model dispatch, and dependency-drift refusals.
  Included in the standard offline CI suite.
- `python -B scripts/test_v5_cands_cell_real.py`: actual extracted package sources
  and locally installed dependencies. The unchanged generated cell discovers
  package paths and versions automatically from the extracted distributions.
  Restoring the removed import fails. LiteLLM pricing-map downloads are disabled.
  This validates local discovery, not the unrun Kaggle runtime.
- `python -B scripts/preflight_v5_budget_v2.py`: stored-evidence consistency,
  candidate compilation, and effective budget checks. This is not fresh replay.

The package sources under experiments/v5_budget_v2 are preserved with their
wheel metadata and per-module SHA-256 manifests, following the existing harness
source layout. Binary wheels and bytecode are excluded.

## Evidence and next step

Both failed runs retain six raw files and their original hash manifests.
The remote listing returned no entries, so authoritative download completeness
is unverified. The failed CPU notebook source itself is not in those six files;
preserve the remote version-1 source before a new push. The launch receipt pins
that old notebook to 55a52256..., while NOTEBOOK_PREPARED pins the repaired bytes.

A separately authorized CPU replay must pass both runtime identity gates and
all eight real control arms before preparing a GPU baseline. Preserve the frozen
V5 agent, task freeze, raw evidence and failed GPU notebook. These engineering
checks are not Kaggle submissions or measured score improvements.

## Artifact protection and portable CI checks

Both V5 generators now refuse before generation when their output experiment
has a LAUNCH_RECORD.json, including an empty or malformed receipt. Their existing
default destinations have launch records, so invoking them refuses intentionally.
Prepare an explicitly versioned destination before regenerating; do not remove
a receipt or overwrite the failed notebook to make generation succeed.

The shared offline suite now includes 31 checks. New stdlib-only checks verify:

- generation refuses after launch without changing the receipt;
- dependency manifest digests, metadata versions and every Python module, with
  missing, extra and changed modules reported separately, without imports;
- the repaired CPU notebook and metadata hashes, exact V5 payload, development
  tasks, five-minute budget, disabled dispatch, and gates before control replay.

The generated replay fixture additionally requires all eight arms accepted with
cleanup confirmed. Six independent failure cases cover compiler version/file
changes and swegemma version/changed/missing/extra modules; each must persist a
refusal before controls or model dispatch. These simulate services, so they do
not replace the fresh CPU replay. The real-package discovery test remains a
separate dependency-equipped local check; CI does not install the ML stack.
