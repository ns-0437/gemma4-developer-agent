# Repaired final validation: prepared, disabled

Recorded 2026-10-07. This checkpoint reflects the files reviewed and committed;
it is not a live kernel-status reading. Before a future launch, inspect any
new `LAUNCH_RECORD.json` and the kernel so an existing push is not repeated.

## What changed

The first final-validation attempt stopped before model startup because a
Requests test parameter included a different temporary workspace root.
The comparison now normalizes only the recorded workspace prefix, rejects
collisions and failed probes, and preserves the complete node/outcome maps.
Its six controls passed in the separate CPU replay. The repaired GPU packet's
control and compiler-check cells match the CPU-tested cells.

The CPU replay has 27 preserved files with matching hashes. Its Requests arms
have 229 nodes and 13 skips each; Rich has 46 nodes and 4 skips each; FastAPI
has one node in each arm. All baseline exits are 1 and reference exits are 0.
All six cleanup checks pass. This is control evidence, not agent performance.

## Pinned packet

| Item | SHA-256 |
| --- | --- |
| Disabled notebook | `1a8075284d0a028c4694b98b6c9b7108445585ab02f02eb1826476935cb412b3` |
| Kernel metadata | `3283548c19ab1657910ddefcd7a8e7bfa19cc6afb7d471882bbd3dfaeae6faa8` |
| Validation manifest | `8ddca206000e0ee41aab5a9ccc28242b9007f2a88b2612829591adeb8b1249f0` |
| Submitted V3 package | `b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b` |
| Frozen ON package | `527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33` |
| Holdout freeze | `220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b` |

Kernel: `navin03/gemma4-final-validation-v2`. The prepared notebook contains
exactly one `DISPATCH_CONFIRM = False`. Metadata requests private execution,
NvidiaL4, internet off and the tested image digest
`37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`.
The compiler gate checks version 0.2.12 and its recorded Python-file hashes;
it does not establish identity of the entire installed runtime.

## Six planned rows

1. `fastapi_15280`, V3
2. `fastapi_15280`, ON
3. `requests_7427`, ON
4. `requests_7427`, V3
5. `rich_3894`, V3
6. `rich_3894`, ON

Both packages retain their own prompts and sampling. Per-run budgets remain
60 turns, 100 tool calls, 10 minutes and a 300-second command timeout.
The 240-minute session admission cap is not a hard completion deadline.

The freeze is unchanged. Dispatch intent is recorded separately before each
Evaluator call; the record is not proof that an agent received the task.
The CPU replay ran no agent. Control evidence must not be used to revise
candidate answers. Other protected tasks remain outside this selection.

## Checks and next action

`scripts/test_final_validation_v2_notebook.py` verifies packet identity,
disabled/enabled simulated execution, exact order, the exposure ledger and
compiler/candidate/control refusal before server startup. The strengthened
canonicalization suite checks persisted rejection reasons, including actual
outcome changes, conflicting recorded roots and normalization collisions.

After explicit GPU authorization, preserve the disabled bytes, arm only the
dispatch flag, run the armed-artifact check, record quota/time/hash and push
once. Keep the earlier launched notebook unchanged. No new launch or submission
was performed by the commit-maintenance work that added this checkpoint.

After completion, verify download completeness and hashes before analysis.
Report all six rows, including ungraded and never-started cases, and distinguish
verified solves, graded failures, candidate failures and environment failures.
Apply the existing proposal's decision rules without revising them after seeing
results. Competition submission is a separate decision; no score is promised.

Evidence links: [CPU report](../../reference/control_replay_review/REPORT.md),
[CPU integrity manifest](../../reference/control_replay_review/raw_sha256.json),
[validation manifest](VALIDATION_MANIFEST.json),
[original proposal](../final_validation_v1/PROPOSAL.json).
