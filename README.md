# Gemma 4 Developer Agent Lab

Declarative agent packages and reproducible evaluation tooling for the
[Gemma 4 Developer Agent competition](https://www.kaggle.com/competitions/gemma-4-developer-agent).

The repository preserves submitted packages, experiment notebooks, downloaded
evidence and offline regression checks. Notebook completion, control validity
and candidate task-solving performance are reported separately.

## Recorded progress

| Artifact | Recorded result | What it establishes |
| --- | --- | --- |
| Submitted V3 | Public score 0.06 | Historical submission result |
| Frozen thinking ON | `rich_3278` solved in two development runs | A reproduced solve on that task, not a leaderboard forecast |
| CPU control replay | Six of six baseline/reference arms accepted | Repaired controls reproduce across the selected FastAPI, Requests and Rich tasks |
| Repaired final validation | Disabled GPU packet prepared | Ready for an authorized V3-versus-ON measurement; no candidate result from this packet yet |

See the [current handoff](experiments/final_validation_v2/CHECKPOINT.md) before
continuing. These are saved results, not live Kaggle status. Check any launch
record and the kernel before starting another run.

## Repository map

- `submission/`: working declarative agent configuration.
- `releases/`: frozen submitted packages and deterministic ZIP archives.
- `experiments/`: candidate snapshots, plans, manifests and launch records.
- `notebooks/`: generated CPU probes and GPU evaluation packets.
- `reference/`: preserved run outputs, source references and separate reviews.
- `scripts/`: generators, validators, reviewers and offline tests.

The selected validation compares whole packages, each retaining its own
sampling configuration. It is not a thinking-only ablation. Three selected
tasks cannot establish general superiority or predict the hidden-set score.

## Offline checks

Run from the repository root with Python 3.12 or newer:

```powershell
python scripts/test_control_canonicalization.py
python scripts/test_final_validation_v2_notebook.py
python scripts/test_verify_artifact_manifest.py
python scripts/verify_artifact_manifest.py reference/control_replay_run_2026-10-07 reference/control_replay_review/raw_sha256.json
```

These checks use simulated services or saved files. They do not launch a model,
contact Kaggle, submit a package or evaluate a held-out task with an agent.
The artifact verifier writes nothing and rejects changed, missing or extra files.

After an authorized arming step, the packet test can check the exact transition:

```powershell
python scripts/test_final_validation_v2_notebook.py --armed --baseline PATH_TO_PRESERVED_DISABLED_NOTEBOOK
```

The supplied baseline must match the prepared notebook hash. This option
does not itself arm or launch anything.

## Evidence conventions

Preserve downloaded artifacts unchanged and write reviews outside their tree.
Verify completeness before interpreting missing outputs. A grading sentinel
such as `-1` is not a failed-test verdict; retain ungraded and never-started rows.
Keep control, candidate, provenance and cleanup failures distinguishable.

The subprocess evaluation backend is not filesystem isolation, and no private
grader parity is claimed. Trace audits describe observed access only.

`.gitattributes` deliberately disables line-ending conversion so frozen hashes
survive Windows checkouts. Do not normalize frozen notebooks, archives or raw
evidence. Wheels, credentials and the competition's full task payload are not
part of the intended Git inventory.
