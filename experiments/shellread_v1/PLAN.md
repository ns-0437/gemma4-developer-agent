# Read-interface diagnostic — prepared, not launched

## Decision on submission

Do not submit S_temp based on temperature_v1. Both candidates produced four
ungraded outcomes and no patches. No verified performance improvement occurred.
The earlier S solve is one observed success that did not recur on its next attempt.
This does not establish population regression or a leaderboard score.

## New evidence

The independent audit verified all 65 temperature raw-file hashes before and
after inspection. See reference/temperature_review/argument_audit.json.
Across six traces, 162 read_file calls contain unknown argument names; 160 of
these return status ok. Some keys are start_line" and end_line", not the declared
start_line and end_line. Unknown optional parameters can therefore be silently
dropped rather than producing the rejected-call signal used in earlier reports.

test_shellread_candidate.py replays step 6 from S_temp/rich_3278 through the real
local ADK 1.36.1 FunctionTool with a signature-matched capturing function. Its
requested 1100–1357 range becomes None/None; correctly named keys retain the
range. This proves local argument filtering, not the origin of malformed output.
The historical trace records the malformed arguments and a successful default
read. Raw pre-parser output remains unavailable.

The prior A/S run records adk-submission 0.2.11; temperature records 0.2.12.
Other recorded package version strings match. This is a cross-session difference,
not proof of a compiler regression. The within-session temperature contrast
shares the same environment. Version strings alone are not binary identity.

## Candidate

S_shellread derives from frozen S. Its coder loses read_file and its prompt reads
focused ranges via run_command/sed, checking for the intended definition.
Only agent.yaml and prompts/system.md change. The analyzer, editing tools,
submission tool, all sampling and budgets remain unchanged. The analyzer still
has its original tools. This tests a coder read-interface package; it cannot
separate the removed tool from its necessary prompt adaptation.

Baseline archive: 8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07
Candidate archive: 8e3f9286ce0f2399c32dfa452e129a12fd48cdd657b88ea6c76d3c48c36956ae

No parser patch, harness behavior change, task solution, hidden test or new
anti-repetition rule is included. Shell calls can still be malformed or repeated.
This change is not a demonstrated cure for the seven no-edit trajectories.

## Offline checks completed

- Official local validation and compilation passed for S and S_shellread.
- Effective generation configs equal; root tool-set difference exactly read_file.
- All other package files byte-identical; both archives are deterministic.
- Real ADK malformed-key replay and corrected-key counterexample passed.
- Frozen notebook and evidence hashes rechecked after preparation.

The compiler used locally is 0.2.11. Before any GPU dispatch, compile both packages
with the actual runtime's 0.2.12 compiler, retain compiler/package hashes, and run
the existing baseline/reference/provenance gates. Refuse drift or failed controls.
Do not silently pin an older compiler to restore an earlier result.

## Proposed next measurement — needs a new GPU authorization

Four runs, two existing development tasks with observed malformed reads:
rich_3675 S, rich_3675 S_shellread, rich_3942 S_shellread, rich_3942 S.
Verify these remain outside the unchanged protected hold-out before generation.
Reuse existing tested dispatch/control machinery; preserve launched notebooks.
Same model, temperature 0.2, context settings and budgets as temperature_v1.
No experiment is armed or queued by this preparation.

Primary: verified solves, graded-unsolved, ungraded and not-attempted out of two
per candidate. Keep all paired outcomes visible. Reliability: valid source diff
and observed grade. Mechanism: read result coverage, malformed keys, repeats and
rejected edits. Neither fewer malformed calls nor more wrong patches is a solve.

At least one verified solve and no observed paired solve regression are necessary
to consider broader validation, not sufficient for submission or a score claim.
Two selected Rich tasks cannot validate general superiority, competition runtime,
or statistical non-inferiority. No access to protected tasks without a separately
specified final evaluation. If no gradeable patches appear, stop instead of
automatically expanding the GPU run.

## Reproduce offline

Run scripts/audit_temperature_arguments.py, scripts/prepare_shellread_candidate.py,
then scripts/test_shellread_candidate.py using Python 3.11 with the existing local
ADK dependencies. These scripts do not invoke a model or Kaggle.
