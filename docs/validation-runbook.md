# Final-validation operating runbook

This procedure applies to the prepared `final_validation_v2` packet. It does not
itself authorize a launch. Read the [checkpoint](../experiments/final_validation_v2/CHECKPOINT.md)
and any newer launch record first; a completed launch must not be repeated.

## 1. Verify the disabled packet offline

From the repository root, with Python 3.12, run the shared CI entry point:

```powershell
python -B scripts/run_offline_checks.py
```

It stops on a failed or timed-out check and returns a nonzero exit. The runner's
own tests deliberately simulate failures; their expected error messages are
followed by the unittest result. The final suite PASS appears only if every
subprocess succeeds. For individual diagnosis, the equivalent checks are:

```powershell
python -B scripts/verify_final_validation_packet.py
python -B scripts/test_verify_final_validation_packet.py
python -B scripts/test_control_canonicalization.py
python -B scripts/test_final_validation_v2_notebook.py
python -B scripts/test_verify_artifact_manifest.py
python -B scripts/verify_artifact_manifest.py reference/control_replay_run_2026-10-07 reference/control_replay_review/raw_sha256.json
```

Stop on a nonzero exit. The preflight reads files only: it checks the notebook,
metadata, manifest, freeze and source ZIPs, and binds each embedded archive to
its candidate label. Merely finding both expected hashes would not detect
swapped V3/ON bindings. The tests execute notebook cells using simulated
services; they do not run a model or contact Kaggle.

[Offline CI](../.github/workflows/offline-validation.yml) runs these same checks
on Windows with Python 3.12. It installs no competition wheels and uses no
Kaggle credentials. A green check establishes the tested artifact and control
invariants, not candidate performance or GPU compatibility.

## 2. After authorization for this specific launch

Check existing launch records and the remote kernel before consuming a launch
approval. Preserve the disabled notebook outside its output tree. Record time,
quota, package hashes and metadata hash. Arm only `DISPATCH_CONFIRM`; retain
all six rows, both frozen packages, their sampling and the holdout freeze.

Verify the armed artifact against the preserved disabled bytes:

```powershell
python -B scripts/verify_final_validation_packet.py --armed --baseline PATH_TO_PRESERVED_DISABLED_NOTEBOOK
python -B scripts/test_final_validation_v2_notebook.py --armed --baseline PATH_TO_PRESERVED_DISABLED_NOTEBOOK
```

Both commands verify; neither arms nor pushes. The baseline must match the
prepared hash, and the armed notebook must differ by exactly the dispatch-flag
substitution. Do not weaken a check to accept another change. The default CI
checks intentionally expect a disabled packet; preserve that reviewed artifact
when preparing a separate authorized launch copy.

Push once after the checks pass and record the returned version and armed hash.
Do not infer current execution state from an old launch message. Read status
when requested; an account quota delta is not proof of the session runtime.
The 240-minute admission cap is not a hard completion deadline.

## 3. Preserve terminal outputs before interpreting them

For COMPLETE or ERROR, download into a fresh directory and wait for the actual
download process to finish. Compare every remote entry with the local inventory;
record a separately fetched kernel log as an explained extra. A partial download
must not become a report of missing experiment rows.

Create a SHA-256 manifest outside the raw directory before analysis. Its `files`
object maps relative POSIX paths to lowercase SHA-256 digests. Retain all raw
bytes, including XML and failed-arm diagnostics, and write reviews outside the
raw tree. Verify the inventory before and after analysis:

```powershell
python -B scripts/verify_artifact_manifest.py PATH_TO_RAW_DIRECTORY PATH_TO_HASH_MANIFEST
```

For pulled notebook JSON, compare normalized cell sources, notebook and cell
metadata, order and decoded candidate payloads against the recorded launch.
Serialization differences alone need not mean executable content changed.

## 4. Interpret evidence without changing the decision rule

Report all six planned rows, including never-started and ungraded outcomes.
Keep source-patch evidence, observed grading, verdict exits, verified solves,
provenance, cleanup, candidate failures and environment failures separate.
An exit of `-1` is unobserved grading, not a failed-test verdict. Preserve the
predeclared paired labels alongside end-to-end completion counts.

The exposure ledger records dispatch intent before each evaluator call; it
is not proof the agent received the task. Corrupt ledgers must stop dispatch
without being overwritten. The tests also require server cleanup on refusal.
Do not use control answers to revise a candidate or move tasks out of the
freeze. After actual exposure, retain the consumption record when deciding
which tasks can still support future holdout claims.

Apply the existing [proposal](../experiments/final_validation_v1/PROPOSAL.json)
without changing its criteria after seeing results. Three selected tasks cannot
establish general superiority or predict a leaderboard score. Competition
submission is a separate decision supported by the observed results.
