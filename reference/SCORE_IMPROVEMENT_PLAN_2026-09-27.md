# Plan to improve the score with evidence

The current measured result is 0.06 for both submitted versions. No measurement proves a reviewed candidate is better. Top three cannot be guaranteed; the live public leader is 0.15 and the final leaderboard uses different tasks. The goal is more correct unseen-task patches within the total runtime, with a defensible measurement at every step.

## Next: four runs, one variable

Run the corrected two-task A/B pilot only after the existing GPU hold is lifted. A and B differ only in thinking configuration. Use the real model, four verified L4 GPUs, fresh task workspaces and identical budgets. This establishes that the proxy executes, captures usable evidence and exposes how the two settings behave. It does not reproduce Docker grading exactly or establish general score superiority.

The stopping rule is meaningful: setup/provenance/server failures stop further dispatch; an ordinary wrong answer remains a measured outcome. Capture partial artifacts before deciding on a rerun. Audit every pilot trace for answer-key access. Preserve raw results so report fixes do not require more GPU time.

## Then: choose the bottleneck from traces

| Observation in our own runs | Next isolated experiment | Evidence needed |
|---|---|---|
| Correct source located, but no substantive edit | Shorten analysis after a supported root-cause hypothesis; make one reversible source change and test it | Earlier successful edit, fewer repeated commands, more nonempty useful patches and solved tasks |
| Edit calls rejected repeatedly | Exact snippet/indentation handling with a reread-and-small-replacement fallback | Fewer failed edit calls, valid diffs, no new regressions |
| Plausible patches miss behavior | Issue-derived acceptance checks: ordinary case, reported failure, named edge case; precise API/error semantics | Better target outcomes without worsening previously solved tasks |
| Thinking consumes output then truncates | Test output allowance or thinking setting separately, holding workflow fixed | Finish evidence, usable tool calls, solved tasks per unit of agent time |
| Analyzer repeatedly rereads what coder knows | One architecture/delegation ablation, same sampling and issue input | Lower duplicate reads/time with stable or better task resolution |
| Relevant source never found | Small lexical/identifier locator or focused analyzer question | Better localization and ultimately resolution; retrieval rank alone is insufficient |

The strongest new competitor clue is an author-reported failure to edit after localization. That motivates measuring successful edits. It does not justify forcing an arbitrary edit on every issue, or installing another search subsystem before our own traces support it.

## Establish a real comparison set

The eight screened tasks are an initial development set, not a held-out estimate. After the pilot, screen additional public tasks with CPU controls before spending model time. Aim for roughly 24–32 usable tasks across at least five repositories if the environment supports them. Predeclare a development portion and an untouched holdout portion; keep some repositories out of prompt iteration where feasible. Record infrastructure exclusions before looking at candidate outcomes. Keep difficult valid tasks.

Every admitted task needs a clean checkout, correct runtime imports, target-relevant baseline failures and explicit passes of those same target nodes with gold. Modifications to existing tests must be covered too. Track task/snapshot/dependency versions. Separate evaluator repairs from candidate code. If the proxy diverges materially from grader behavior, label that limitation and do not promote its aggregate as official expected score.

Compare an exact archived public 0.12 baseline with our best measured candidate under the same environment. Also benchmark the genuinely submitted v2 when quota permits; pilot A is not that artifact. Pin notebook/version/archive hashes and verify the score-to-version relationship where available. Do not copy the top-ranked team's presumed method—their exact submitted source has not been verified.

## Promotion and runtime

Keep at most two experimental candidates active at once. Use matched task outcomes, report candidate-only wins, baseline-only wins, shared passes and shared failures, plus valid-pair count and exclusions. Repeat discordant or unstable results under a predeclared rule. An eight-task improvement is useful development evidence, not a statistically secure private-score estimate. Check the chosen candidate on untouched tasks before a release.

Report total agent time for all tasks, setup, grading, token output, empty patches and errors. Measure runtime tails and model-serving overhead before deciding whether a candidate fits the global scoring budget. A few short tasks cannot establish a full-set runtime ceiling. Avoid blindly assigning every task a five-minute timeout or unlimited reasoning from one anecdote.

Freeze only a candidate with a justified improvement hypothesis and completed release checks. Validate and compile the frozen directory, generate the submit notebook from that directory, download its actual output and compare full SHA-256. A competition submission remains a separate user-authorized action. Preserve the known best scored artifact.

## Research priorities

1. Execution reliability and meaningful patches before larger agent teams or more prompt rules.
2. Small workflow/verification improvements selected from observed failures.
3. A lawful reusable skill only if it beats the corresponding ordinary tool workflow on matched tasks.
4. LoRA only after current host support, adapter activation, permitted training data and a held-out evaluation are verified. Old reports of broken adapters need rechecking before a training investment.

Public sources read on 27 September:

- [Live leaderboard](https://www.kaggle.com/competitions/gemma-4-developer-agent/leaderboard).
- [Public notebooks by score](https://www.kaggle.com/competitions/gemma-4-developer-agent/code?competitionId=149921&sortBy=scoreDescending&excludeNonAccessedDatasources=true).
- [Pathfinder baseline](https://www.kaggle.com/code/mizeroluckygall/pathfinder-gemma-4-agent-eda-baseline).
- [Competitor's grader and trajectory audit](https://www.kaggle.com/code/busyaprime/119-of-129-sound-the-gemma-4-grader-rebuilt).

The working cycle is: Claude executes one bounded experiment; Codex reviews the artifacts and traces; the next prompt targets the demonstrated failure. More elaborate plans are not a substitute for measured wins.
