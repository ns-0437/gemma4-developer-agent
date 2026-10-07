# CHECKPOINT — thinking_v3 six-run follow-up PREPARED, disabled, awaiting one authorization

Written 2026-10-06. **Nothing launched, pushed or submitted. `DISPATCH_CONFIRM = False`.**

## Artifacts

| item | sha256 |
|---|---|
| disabled notebook `notebooks/thinking_v3/thinking_v3.ipynb` | `94ccce2797f77ddbc1b035e9df90f548516e91dccc8e1a4f9af3a33cb199ad06` |
| `notebooks/thinking_v3/kernel-metadata.json` | `414b7fdf56c7610faac6c398b37f8b222d94dedaba9b1304c4dcf19f4272fa12` |
| OFF package (unchanged, frozen) | `640fadab5b5b638a7e8a31abb26fcecb6b2e139929d77cdb6691f2d832ca2ec1` |
| ON package (unchanged, frozen) | `527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33` |
| image pin (tested by the CPU probe) | `gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461` |
| protected freeze, unmodified | `220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b` |

Proposed kernel `navin03/gemma4-swe-agent-thinking-v3`. Reused unchanged: both packages, sampling,
budgets (60 turns, 100 calls, 10.0 min, 300 s), compaction 20480, compiler per-file gate for 0.2.12,
saved control evidence, prompts and tools. **No prompt change and no new agent framework.** Session
admission cap raised 150 to 210 minutes for six runs; that is an admission limit, not a hard kill.

Order: `3278 OFF, 3278 ON, 3535 ON, 3535 OFF, 3942 OFF, 3942 ON`.

## Freeze check

`protected_holdout` holds 12 tasks: rich_3180, rich_3938, rich_3894, rich_3486, rich_3521,
fastapi_15280, fastapi_14873, fastapi_13537, fastapi_15800, fastapi_14479, requests_7427,
requests_6644. **None of rich_3278, rich_3535, rich_3942 is protected**; all three are in the
development `tasks` list. The freeze file was read only and still hashes `2208694094…`.

## Integrity audit of the existing ON/rich_3278 solve

| check | evidence |
|---|---|
| grading output | `test_outputs/rich_3278.log`: `23 passed`, no `failed`, exit 0 |
| result row | `resolved: true`, `test_exit_code: 0`, `agent_patch_size: 319`, `error: null` |
| patch application | `patch_touches_source: True`, `patch_files: rich/ansi.py`, `grading_ran: True` |
| both provenance phases | `both_setup_imports_verified: True`; `runs.json` shows 1 agent phase and 1 grading phase; `phase_status {"agent":"passed","grading":"passed"}` |
| precondition | `rich_3278` `ok: True`, agent and grading import paths both inside the checkout |
| cleanup | `cleanup_ok: True`, `attribution: passed`, `failure_class: none` |
| controls | 4 arms agree: baseline exit 1, reference exit 0 on both tasks |
| answer-key scan | no hit for `tasks.jsonl`, `solution.parquet`, `FAIL_TO_PASS`/`PASS_TO_PASS`, `test_patch`, gold/verification patch, or `/kaggle/input/competitions`. 18 `swegemma` hits inspected: **all are the `/tmp/swegemma_sandbox_*` path echoed in the agent's own repro tracebacks and stderr** |

**Absence of trace hits is not isolation.** The subprocess backend is not a filesystem boundary and
this scan sees only what the trace recorded.

## Predeclared decision rules

1. Record explicitly **whether `rich_3278` reproduces** under reversed order.
2. Record new-task solves (`rich_3535`, `rich_3942`), regressions, candidate budget failures and
   runtime, each separately.
3. More graded-incorrect patches, or fewer repetitions, is **insufficient** on its own.
4. **A reproduced `rich_3278` solve plus at least one new-task solve, with no observed matched
   regression, warrants considering an exploratory submission.** That is a decision to consider, not a
   promised leaderboard improvement.
5. Mixed or negative results trigger **targeted diagnosis**, not an automatic rerun and not more
   prompt rules.

## Reporting rules

- Keep the four-run and six-run results **separate**. In any combined table, `rich_3278` is a
  **repeated** task and must not be counted as an independent new task.
- Preserve the four-run report's pairing labels: an ungraded side makes a pair **undecided**, never an
  opponent win.
- Report, in addition and separately, **end-to-end verified solves over all attempted tasks**, with
  candidate budget failures, grading failures and environment failures kept distinct. An ungraded
  candidate budget failure is **not** a grading verdict, but it stays visible when judging practical
  task completion.
- Do not infer thinking-budget enforcement from total completion tokens. `extra.event_type ==
  "thinking"` per step is positive activation evidence; its absence is unknown, not proof.

## Checks run

`scripts/test_thinking_v3_notebook.py` PASS (disabled, six-run order, lifecycle, compiler
version/source drift, candidate drift, controls, provenance; simulated dependencies).
`scripts/test_thinking_v2_notebook.py --armed` still PASS, so the shared fixture change did not
regress the previous experiment. The only shared-fixture edit was adding `"thinking_v3"` to the
`_control_maps` allowlist, the same one-word addition previously made for `temperature`, `shellread`
and `verification`. No guard was weakened.

## Next action

**Awaiting ONE launch authorization for this exact six-run GPU experiment.** On approval: record UTC
time and quota, arm only `DISPATCH_CONFIRM` via `scripts/arm_thinking_v2.py <path>`, verify the single
flag diff, run the armed check, record notebook and metadata hashes, push once. No retry, no polling,
no submission.
