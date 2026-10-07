# thinking OFF/ON follow-up, six runs: ON reproduced rich_3278; no new-task solve

Kernel `navin03/gemma4-swe-agent-thinking-v3` **version 1**, COMPLETE checked 2026-10-07T02:27:01Z.
Downloaded to `reference/thinking_v3_run_2026-10-07/`, **60 files**, hashed into
`reference/thinking_v3_review/raw_sha256.json` **before analysis**. Completeness verified against the
remote listing: every remote name has a local match; the only local-only file is the kernel log, which
the listing excludes. No retry, repush or submission.

Identity: candidates OFF `640fadab…` / ON `527acc54…` as pinned, order as planned, budgets 60 turns /
100 calls / 10.0 min / 300 s, adk-submission 0.2.12. Controls agree on all six arms (baseline exit 1,
reference exit 0 on each task). Cleanup 6 of 6.

## All six planned rows

| Order | Task | Cand | Outcome | Grading | Exit | Resolved | Patch B | Loop s | Wall s | Termination |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | rich_3278 | OFF | candidate | no | -1 | false | 0 | 337.4 | 362.7 | turns budget (60) |
| 2 | rich_3278 | ON | ok | yes | **0** | **true** | 320 | 600.0 | 651.9 | completed |
| 3 | rich_3535 | ON | ok | yes | 1 | false | 465 | 283.9 | 335.8 | completed |
| 4 | rich_3535 | OFF | candidate | no | -1 | false | 0 | 77.5 | 102.8 | turns budget (60) |
| 5 | rich_3942 | OFF | candidate | no | -1 | false | 0 | 160.6 | 185.4 | turns budget (60) |
| 6 | rich_3942 | ON | candidate | **yes** | 1 | false | 541 | 600.0 | 651.6 | **session timeout (10.0 min)** |

Row 6 is worth noting: ON hit the 10-minute agent budget, yet its working-tree diff was still graded
(6 failed, 2 passed). `failure_class` is `candidate` because the agent did not finish, but grading
**was** observed, so this is a graded failure and a candidate budget failure at once.

## 1. Does ON reproduce rich_3278? **Yes.**

Under reversed order (OFF first this time), ON solved it again: exit 0, `resolved: true`, 23 passed,
provenance observed on both phases. The patch is the same mechanism as the four-run session but **not
byte-identical**:

```diff
four-run:  -(?:\x1b([(@-Z\-_]|...      +(?:\x1b([(0-Z\-_]|...      319 B
six-run:   -(?:\x1b([(@-Z\-_]|...      +(?:\x1b([ (0-Z\-_]|...     320 B
```

The follow-up also admits the **space** character into the class, so its regex additionally matches ESC
followed by space. Both widen the range start from `@` to `0`, which is what the issue asks, and both
pass all 23 tests. **The solve verdict stands: graded exit 0, resolved true, twice.** But correctness is
established only against the suite; the space insertion is unverified behaviour beyond it and this
report does not claim complete behavioural correctness. See `DIAGNOSIS.md`.

## 2. Does ON solve either additional task? **No.**

Both new tasks graded and both failed: `rich_3535` 1 failed / 7 passed, `rich_3942` 6 failed / 2
passed. Patches were produced and applied in both cases, so these are **graded failures**, not missing
outcomes.

## 3. Does ON regress against OFF? **No observed regression.**

OFF produced **no patch on any of the three tasks** and was never graded. There is no task where OFF
succeeded and ON failed.

## Pairing, preserving the predeclared labels

| Task | OFF | ON | pair |
|---|---|---|---|
| rich_3278 | ungraded (turns budget) | **solved** | **undecided** |
| rich_3535 | ungraded (turns budget) | graded, unsolved | **undecided** |
| rich_3942 | ungraded (turns budget) | graded, unsolved | **undecided** |

All three pairs are **undecided**: an ungraded side never counts as an opponent win. So this session
does not establish that thinking caused anything, even though ON is the only arm producing patches.

## End-to-end verified solves over all attempted tasks, reported separately

Practical task completion, with failure kinds kept distinct:

| | ON | OFF |
|---|---|---|
| attempted | 3 | 3 |
| **verified solves** | **1 of 3** (`rich_3278`) | **0 of 3** |
| graded failures | 2 (`rich_3535`, `rich_3942`) | 0 |
| candidate budget failures, ungraded | 0 | **3** (all turns budget) |
| candidate budget failure that still graded | 1 (`rich_3942`, session timeout) | 0 |
| environment failures | 0 | 0 |

OFF's three ungraded rows are **not** grading verdicts and are not counted as failed tests. They are
visible here because they are the practical outcome: **OFF completed no task end to end.** ON reached
grading on 3 of 3 and solved 1.

## Combined view, four-run and six-run kept separate

`rich_3278` is a **repeated** task, not an independent new task.

| Task | four-run OFF | four-run ON | six-run OFF | six-run ON | status |
|---|---|---|---|---|---|
| rich_3278 *(repeated)* | ungraded | **solved** | ungraded | **solved** | ON solved **twice**; OFF ungraded twice |
| rich_3675 *(four-run only)* | graded unsolved | graded unsolved | — | — | tie, both incorrect |
| rich_3535 *(new)* | — | — | ungraded | graded unsolved | undecided |
| rich_3942 *(new)* | — | — | ungraded | graded unsolved | undecided |

Distinct tasks attempted across both sessions: 4. **ON verified solves: 1 distinct task, twice.**
OFF verified solves: 0. Observed regressions: 0.

## Mechanism and cost

| | OFF 3278 | ON 3278 | ON 3535 | OFF 3535 | OFF 3942 | ON 3942 |
|---|---|---|---|---|---|---|
| tool calls | 60 | 52 | 23 | 60 | 57 | 49 |
| repeated identical | 20 | 12 | 0 | **44** | 0 | 0 |
| rejected calls | 1 | **16** | 0 | 0 | 0 | 0 |
| edit calls | 1 | 21 | 3 | 0 | 0 | 4 |

ON's solve was not a clean run: 16 rejected calls and 12 repeats, and it still produced a correct
patch. Reduced repetition is therefore not what distinguishes the arms here, and per the predeclared
rules it would not count even if it were.

**Thinking activation, positively evidenced, not inferred from token totals:** `extra.event_type ==
"thinking"` appears on 52, 24 and 50 steps in the three ON runs and **zero times in all three OFF
runs**. This does not establish that the server enforced the 1,024-token budget; no recorded field
reports an enforced budget.

Runtime: **all three** ON runs recorded 600.0 s of loop time where they used the full budget; 600 s is
exactly `max_time_minutes 10.0`, so this is the agent time budget being reached, not an early finish.
OFF's loops were shorter (77.5 to 337.4 s) because it exhausted turns first. The kernel log spans
**about 50 minutes (3,013 s)** including roughly **6 minutes of vLLM startup**. The **1.67h quota change
is a separate account-level observation** and is not the session's measured wall clock.

## Decision against the predeclared rules

Rule 4 required **a reproduced solve plus at least one new-task solve, with no observed matched
regression**, to warrant considering an exploratory submission. Measured: reproduced solve **yes**, new-task
solve **no**, regression **none**. **The condition is not met.**

Per rule 5 this is a mixed result, so it triggers **targeted diagnosis, not an automatic rerun and not
more prompt rules.** No submission is recommended.

The most informative diagnosis targets available, in order, are: why OFF produces no patch at all on
any task while ON reaches grading on all three (the arms differ only in sampling, so this is the
sharpest contrast in hand); and what the two graded failures actually got wrong, since ON produced
applied patches on both and the gap to correct is visible in the grading output.

Not established: that thinking caused the solve (all three pairs undecided), budget enforcement,
non-inferiority, or anything about the leaderboard. Four selected Rich development tasks cannot predict
public score, and three submissions have each scored 0.06. OFF remains a new 4,096-output baseline, not
submitted v3.
