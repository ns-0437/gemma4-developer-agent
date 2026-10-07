# Final validation, version 1: ERROR at the control gate. No hold-out task was exposed.

Kernel `navin03/gemma4-final-validation` version 1. Status checked once at 2026-10-07T03:42:17Z:
**ERROR**, about 17 minutes after the 03:24:49Z push. The failure is a **control-identity mismatch before candidate dispatch**. Downloaded to
`reference/final_validation_run_2026-10-07/`, **27 files**, hashed into
`reference/final_validation_review/raw_sha256.json` before analysis. Raw evidence unchanged. No
retry, repush, cancellation or submission. Log span 427.7 s. The account's reported GPU usage moved 3.13h to 3.37h; that is an **account-level delta, not this session's runtime**.

Completeness note: the remote file listing returned **0 entries** for this errored kernel, so
per-name completeness could not be cross-checked against it. Completeness is judged by the download
exiting cleanly and by which pipeline stages produced artifacts, which is consistent and complete for
the stages that ran.

## Version 1 identity, verified

| check | result |
|---|---|
| downloaded `candidates/V3` re-bundled | `b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b` **matches** |
| downloaded `candidates/ON` re-bundled | `527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33` **matches** |
| pulled notebook byte hash | `2992e450…`, not equal to the armed `f7495570…` |
| **normalized cell sources, 13 of 13** | **identical** |
| notebook-level metadata | identical |
| embedded payloads | equal to the two pinned packages |
| `DISPATCH_CONFIRM = True` | present |

Kaggle reserializes notebook JSON, so the byte hash is not expected to reproduce. Identity is
established at the executable level.

## All six planned rows

| Order | Task | Candidate | Outcome | Grading | Patch | Runtime |
|---|---|---|---|---|---|---|
| 1 | fastapi_15280 | V3 | **missing, never started** | no | none | none |
| 2 | fastapi_15280 | ON | **missing, never started** | no | none | none |
| 3 | requests_7427 | ON | **missing, never started** | no | none | none |
| 4 | requests_7427 | V3 | **missing, never started** | no | none | none |
| 5 | rich_3894 | V3 | **missing, never started** | no | none | none |
| 6 | rich_3894 | ON | **missing, never started** | no | none | none |

| category | count |
|---|---|
| verified solves | 0 |
| graded failures | 0 |
| ungraded candidate outcomes | 0 |
| missing runs | **6 of 6** |
| **environment / instrument failures** | **1, session level** |
| candidate failures | **0** |

No run directory, patch, trace or `pilot_results.csv` exists, because no evaluation was attempted.
**Nothing here is attributable to either candidate.**

## Why it stopped: control-identity mismatch before candidate dispatch

The control re-validation gate refused to start the model:

```
AssertionError: controls do not reproduce under this notebook's setup:
['requests_7427/baseline', 'requests_7427/reference']; do not start the model
```

Controls: **4 of 6 arms agree** (`fastapi_15280` both arms, `rich_3894` both arms, with its **4 skipped nodes**
preserved and a 46/46 node map; `requests_7427` carries **13 skipped nodes**). `requests_7427` disagrees on both arms.

The difference is **node-identity instability, not behaviour**. `requests_7427` runs
`tests/test_utils.py`, which contains a parametrised test whose parameter value is the absolute
sandbox path:

```
missing: tests.test_utils.TestExtractZippedPaths::test_unzipped_paths_unchanged[
         /tmp/swegemma_sandbox_947622a7-24e_l2uqr9um/workspace/tests/test_utils.py]
extra:   ...same test...[/tmp/swegemma_sandbox_6aceb0d7-513_ihvd84uj/workspace/...]
```

The sandbox id is fresh per run, so the node ID cannot match the screening run's. `pytest_exit`
agreed with the saved value on both arms (1 and 0), `test_patch_rc` 0, `cleanup_ok` true,
`duplicate_nodes` empty, `junit_parse_error` null. The suite behaved identically; only one node's
name changed. The strict full-node-map comparison cannot distinguish that from a real difference,
so it refused, which is the gate working as designed on a case it cannot resolve.

**Exposure: none.** No `pilot/EXPOSURE.json` exists and no run directory was created, so **no
dispatch-start intent was ever recorded and none of `fastapi_15280`, `requests_7427`, `rich_3894`
was exposed.** The hold-out authorization was not consumed. `task_freeze.json` is unchanged at
`220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b`.

Preconditions: `ok: True` on all three tasks. Both provenance phases: not applicable, since grading
never ran on any task. Trace integrity: no traces exist. Cleanup: confirmed on every control arm,
`owned_sandboxes` empty.

## Predeclared decision rules

The rule required **an additional-task solve and higher observed completion than v3, with no observed
v3 solve lost**. Measured: no task was attempted, so there is no solve, no completion count and no
regression on either side.

**Unmet criteria: all of them.** Nothing was measured. This is not a tie, not a regression and not
evidence about either package; it is a missing experiment.

## Recommendation

**Do not submit frozen ON against v3 on this evidence.** The only hold-out comparison ever attempted
produced zero rows. The prior development evidence stands where it was: ON solved `rich_3278` twice
and reached grading on 3 of 3 rich development tasks where OFF produced no patch, but every pair
there was undecided, no new development task was solved, and none of it is hold-out evidence.

Uncertainty that remains, stated plainly: nothing is known about either package on fastapi or
requests; nothing is known about ON outside four rich development tasks; and v3's own 0.06 is the
only leaderboard datum. **No leaderboard score is predicted.**

The blocker is a fixable instrument issue, not a candidate one: the control comparison needs a
defensible way to handle node IDs that embed the sandbox path. That is a change to the gate, which I
have not made and would not make without authorization, since loosening a protection to pass is
exactly what should not happen quietly. Options worth your decision, not acted on here: normalize
sandbox paths inside node IDs before comparison, or reselect the requests task by the next smallest
`sha256(instance_id)`, which would expose a different hold-out task and needs its own approval.

Checkpoint: `experiments/final_validation_v1/CHECKPOINT.md`


## Repair, applied after this report was first written

The control comparison now canonicalizes each arm's own sandbox workspace prefix to a token before
comparing. Both roots come from recorded evidence: the saved arm's recorded import/workspace paths and
a new per-arm workspace probe recorded in the re-validation record. Classnames, test names, relative
paths and all other parameters are preserved; ambiguous roots, underivable roots and post-substitution
collisions all refuse. Raw XML and node maps are stored unchanged, with mappings and diagnostics saved
alongside under `canonicalization`. Exit-code, outcome, target, duplicate, provenance and cleanup
checks are unchanged, and all six arms are still required before model startup.

Verified by `scripts/test_control_canonicalization.py`: both real `requests_7427` arms match after
canonicalization with the fixture minting an observed root that differs from the saved one on all six
arms; a different relative path, a changed non-path parameter, a changed outcome, an ambiguous root
and an unreadable probe each still fail.
