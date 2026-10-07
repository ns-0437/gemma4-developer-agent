# Verification comparison: trace diagnosis

Reviewed 2026-10-03. This is an offline inspection of the four preserved traces, tool arguments/observations, source patches and grading outputs. No candidate, launched notebook, holdout or raw result was changed. No model, GPU or submission was invoked.

## Decision

Do not promote V. Both candidates have zero solves, one graded incorrect patch and one ungraded outcome. The prompt intervention was not reliably followed. This experiment does not show that verification is unhelpful; it shows that this instruction change failed to deliver it on these tasks.

## rich_3675: V did not implement the requested verification discipline

Evidence: pilot/V__rich_3675/traces/trace_rich_3675.json, ATIF step IDs.

- Step 1 records the instruction to keep assertions enabled, propagate failure, preserve before/after expectations and separate assumptions from requirements. This confirms the recorded instruction, not the exact outgoing HTTP request.
- Step 6 creates a reproduction with active assertions for values 0 and 1, but catches each AssertionError and prints a failure. The value-1 check fails, yet the command exits 0.
- Step 9 rewrites the reproduction, adds an unset case that only checks the result is a bool, and again swallows assertion failures. It exits 0 while printing a failed value-1 check. A bool check does not establish preservation of terminal detection.
- No command in this trace reads local documentation or neighboring test source to resolve the issue's unspecified semantics. Existing test execution later is not equivalent to that inspection.
- Step 11 sends edit_file syntax through run_command and receives command-not-found (127). Step 12 calls edit_file with malformed arguments and is rejected for missing old_string. Step 13 recovers with an accepted edit and a returned source diff. These transient errors did not stop this run.
- Step 14 reruns the same final reproduction: all three narrow checks print passed. There is no observed failing assertion here, but its exception handling would still mask a failure.
- Step 15 runs the existing test file: EXIT=0, 98 passed. Step 16 submits a 536-byte source patch.
- Grading adds the verification test: 98 passed, one failed. The observed first failure is the empty-value case: V returns False where terminal auto-detection should have occurred. The patch also places its check after FORCE_COLOR; this review does not claim an executed precedence failure, because pytest stopped within the earlier case.

The visible issue only asks to implement TTY_COMPATIBLE and links an external discussion. It does not spell out these expected values or precedence. Do not insert grader-derived answers into a candidate prompt.

The baseline is not better overall, but it actually propagates its reproduction failure: step 6 initially comments out the new-behavior assertion; step 7 enables it and re-raises AssertionError, returning 1; step 12 passes after editing. Its reproduction is still incomplete, and its 723-byte patch also fails the added test. Baseline failure first manifests as missing auto-detection invocation; V first fails the boolean result. Both are graded incorrect, not environment failures.

## rich_3942: both candidates loop on an empty history search

Visible task: 'Update to markdown styles' / 'Updates to Markdown styling'. It contains no detailed acceptance criteria. Controls validate a baseline/reference distinction, not whether the agent-facing prose uniquely specifies the intended change. Keep the task in this experiment's denominator; do not discard it retrospectively.

Both agents locate rich/markdown.py, read the element mapping, inspect a recent history entry, then open commit b4c04880 from 2020 after a broad title search. That is historical repository content, not established as the intended repair.

Dominant command: git log --grep="Update to markdown styles" --oneline

| Candidate | Requested calls with this exact payload | Completed empty-output/exit-0 responses | Final budget rejection |
|---|---:|---:|---:|
| V | 51 | 50 | 1 |
| S_shellread | 52 | 51 | 1 |

V additionally repeats a different empty search twice. Each run makes 60 run_command calls, with 9 distinct payloads; neither calls edit_file, write_file, the analyzer, or submit_patch. The final tracked patch is empty. No observed source-edit operation occurs; this does not prove absence of every possible transient or untracked filesystem change.

The CSV's repeated-identical counts (48 and 49) are not total frequencies: they count adjacent repeated payloads. All-call frequencies above include earlier occurrences interrupted by other searches. The step ranges 14-62 form the final repeated sequence; the last response is the budget error.

Recorded prompt token counts increase through the tail (V 11686,11747,11808; baseline 11597,11658,11719), below the configured 20480 compaction threshold. This is consistent with accumulating history. Exact request bodies and pre-parser output were not captured, so neither feedback delivery nor a specific model/parser cause is proved.

## Trace access audit and limits

All four trace JSON files are readable. An argument scan for tasks.jsonl, solution.parquet, FAIL_TO_PASS, test_patch, gold.patch, swegemma and adk_submission found no matches. Ordinary test execution and repository history access are present. The opened historical patch is reported explicitly; no claim that all Git history is harmless or inaccessible is made. This bounded scan is not proof of answer-key isolation, and subprocess execution is not a filesystem boundary.

## Deployment feasibility and next work

The inspected swegemma agent_runner.py compile_submission call supplies tool and model registries, but no callback registry. Compiler 0.2.12's callback resolver returns no callback kwargs when that registry is None. Merely adding before_tool/after_tool callback names to YAML therefore does not provide enforcement on this inspected path. A notebook-only guard must not be represented as a deployable score improvement.

The compiler schema supports SequentialAgent and per-agent tool lists. The next recommendation is an OFFLINE feasibility prototype of staged localization/coding/review with restricted tools, initially testing whether the stages actually advance and whether a reviewer receives the candidate patch. SequentialAgent alone does not prevent the first tool-using stage from exhausting the global budget; LoopAgent.max_iterations is not a per-model-call cap. Prove those properties with the actual compiled execution path before proposing a GPU experiment. If enforceable advancement cannot be expressed in the accepted submission format, report that limitation rather than hiding it behind simulation or a harness patch.

Do not add another generic anti-loop paragraph, expose protected holdout answers, or resubmit V based on its narrower reproduction. Any subsequent GPU comparison remains a separate decision. Goal: correct, graded patches; reduced repetition or compilation success alone is insufficient.
