# Verification discipline candidate — offline only

No submission recommended yet. S_shellread produced one incorrect graded patch
and one ungraded outcome, versus two ungraded baseline outcomes. Zero solves.

The issue visible to rich_3675's agent says implement TTY_COMPATIBLE and links an
external discussion; it does not specify the empty-value or precedence rules.
Those grading expectations must not be inserted into a task-specific prompt.
The observed reproduction defect is independent: step 6 comments out the desired
assertion; step 7 enables it but catches AssertionError and exits 0. Step 11 passes
that same incomplete check after the edit. Existing repository tests pass; the
added grading test fails. Passing existing tests is not full feature verification.

V changes only the reproduction paragraph of S_shellread. It requires active
assertions, nonzero failures, fixed before/after expectations, a preservation
check, and a distinction between supported requirements and assumptions. No task
identifier, target environment variable, gold patch or expected hidden-test value
is added. This is a prompt hypothesis, not an enforced execution policy.

Offline acceptance: official 0.2.12 compilation, equal generation/client settings,
one-paragraph-only diff, real subprocess checks demonstrating swallowed versus
propagated assertion exits. These do not prove the model follows the instruction.

Before another launch, prepare a paired V versus S_shellread comparison on existing
development tasks, keeping budgets/runtime fixed and all planned outcomes visible.
No hold-out access, new GPU dispatch or submission is authorized by this file.
Promote only on verified solves; fewer weak tests or more incorrect patches do
not justify a leaderboard prediction. Do not force a patch for an underspecified
issue or tune generic instructions to hidden expected constants.
