# Shell-read comparison review — 2026-10-02

Decision: do not submit this candidate on these results. No verified solves.
One observed improvement in reaching a graded source patch, but that patch is wrong.

## Identity and evidence

44 downloaded files hashed before inspection; full tree reverified unchanged afterwards.
Raw evidence: ../shellread_run_2026-10-02/.
Hashes: raw_sha256.json. Machine-readable checks and rows: review_summary.json.
Local launched notebook hash: 5722594505e407387a00567e39d78ddd00570384a32893f5c6223664de72f6a3.
Downloaded manifest candidate digests/order match the frozen launch record;
downloaded candidate file trees match the local frozen candidates byte-for-byte.
Notebook hash verification is of the local launched artifact, not a downloaded notebook.

Compiler 0.2.12 source hashes match the pinned competition wheel's Python files.
Runtime reports four NVIDIA L4 devices. Quota charged is not established here.

## All four planned outcomes

| Task | Candidate | Patch bytes | Grade exit | Outcome | Agent loop seconds |
|---|---|---:|---:|---|---:|
| rich_3675 | S | 0 | -1 | Ungraded, 60-turn budget | 93.7 |
| rich_3675 | S_shellread | 723 | 1 | Graded unsolved | 49.0 |
| rich_3942 | S_shellread | 0 | -1 | Ungraded, 60-turn budget | 89.9 |
| rich_3942 | S | 0 | -1 | Ungraded, 60-turn budget | 125.7 |

S: 0 solved, 0 graded-unsolved, 2 ungraded, 0 not attempted.
S_shellread: 0 solved, 1 graded-unsolved, 1 ungraded, 0 not attempted.
Two solve comparisons undecided because at least one side lacks a grade.
No observed solve regression is not a non-inferiority result.

## Verification

All four baseline/reference arms agree with saved controls and have raw readable
JUnit reports. rich_3675: baseline 1 failure, reference 99 passing cases.
rich_3942: baseline 6 failing cases, reference 8 passing cases. Neither arm has
JUnit errors. Test patches apply; reference patches apply. Both preconditions pass.
Every observed setup probe passes provenance; agent setup observed on all four
runs, grading setup only on the one graded run. Other grading paths are unobserved,
not demonstrated infrastructure failures. All four run cleanup checks pass.

## Patch and trace findings

S_shellread/rich_3675 locates Console.is_terminal, uses sed to retrieve the relevant
implementation, then makes one accepted edit and submits. The 723-byte preserved
patch matches the result's recorded size and touches rich/console.py only.
Grading executes and reports 98 passed, 1 failed. The failure is
test_tty_compatible: empty TTY_COMPATIBLE must preserve isatty auto-detection.
The patch instead treats any non-None value as true; it also cannot implement
explicit false correctly. Only the empty-string failure is directly observed in
the grading log, which stops at that assertion.

S's contemporaneous rich_3675 trace has malformed read_file range keys, then
repeats a grep pipeline returning empty output 50 times. The intervention changed
the workflow on this pair; this single realization does not establish causality
or repeatability. S_shellread also briefly calls edit_file as a shell executable,
gets command-not-found, then correctly invokes the tool and proceeds.

Both rich_3942 traces fail to produce a patch. The visible issue description is
only 'Update to markdown styles / Updates to Markdown styling'; its required
styling choices are underspecified in that text. S_shellread makes 47 git-log
requests, including reading a historical 2020 diff referencing an older symbol.
Do not turn hidden expected styling values into candidate instructions. Review
this task's specification adequacy separately; retain it in this result and do
not change the existing frozen split retrospectively.

All four traces readable. Scan of tool arguments found no tasks.jsonl,
FAIL_TO_PASS, PASS_TO_PASS, test_patch or solution.parquet references. History
access is explicitly retained in review_summary.json; the inspected 2020 diff
is not evidence of access to this task's answer key. This bounded audit does not
prove isolation or absence of indirect access. Subprocess is not a filesystem
security boundary. Tool observations can include nested sub-agent events, so
trace call counts and harness budget counts are not interchangeable.

## Recommended next step

Keep the submitted release unchanged. Before another GPU run, audit specification
coverage: does the agent extract explicit value cases, defaults and precedence
from the supplied issue and turn those into independent checks before submitting?
Use only user-visible task text for candidate-facing changes, never grading answers.
The reader intervention can remain a research candidate; do not stack an edit
policy onto it and call the combined result a read-only ablation.

No new GPU run, repush, competition submission or hold-out evaluation was performed.
