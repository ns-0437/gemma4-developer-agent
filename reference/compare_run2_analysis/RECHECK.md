# Compare run 2, re-derived

Artifacts: `reference/compare_run2/` (unmodified). Original report cell: `releases/compare_v2_prepared/compare.ipynb` (`97873af2210b...`). Corrected cell: `notebooks/compare/compare.ipynb`.

Replay of the launched cell reproduces the session's own `pilot_results.csv`: **True**.

## Corrected eight rows

| candidate | task | attempted | outcome | reclassified_outcome | would_have_continued | attribution | grading_ran | tool_calls | successful_tool_calls | rejected_tool_calls | successful_source_edits | tmp_scratch_writes | repeated_identical_tool_calls | unparsed_tool_call_texts | tool_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | rich_3278 | True | candidate | candidate | True | empty_patch | False | 60 | 59 | 0 | 0 | 54 | 48 | 0 | 1 |
| B | rich_3278 | True | environment | candidate | True | no_submission | False | 48 | 5 | 42 | 0 | 2 | 39 | 4 | 43 |
| B | rich_3535 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| A | rich_3535 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| A | rich_3675 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| B | rich_3675 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| B | rich_3942 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| A | rich_3942 | False | not_attempted | not_attempted | unavailable | not_attempted | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## What changed, and why

- `attribution`: a run that never submitted is no_submission, not empty_patch
- `first_source_edit_attempt_step`: was set by a /tmp scratch write, not by a repository edit
- `reclassified_outcome`: new: the repaired classifier's verdict on the same saved error strings
- `reclassified_reason`: new: why
- `rejected_tool_calls`: new: calls rejected before execution for unusable arguments
- `repeated_identical_tool_calls`: new: identical consecutive calls to ANY tool, not just run_command
- `shell_edit_hints`: was matching `> /tmp/repro.py`, which the prompt tells the agent to write
- `successful_source_edits`: new: accepted edits to a repository .py file
- `successful_tool_calls`: new: calls the tools accepted
- `tmp_scratch_writes`: new: scratch reproduction writes, counted apart from source edits
- `tool_errors`: was counting only {'status':'error'}; a rejected call carries a bare {'error':...}
- `unparsed_tool_call_texts`: new: agent turns whose text never became a parsed tool call
- `would_have_continued`: new: whether the repaired rule would have allowed the next planned run

`outcome` is what the GPU session recorded while running and is preserved unchanged. `reclassified_outcome` is what the repaired classifier says about the same saved error strings, and `would_have_continued` is whether the repaired rule would have let the next planned run start.

Original rows are preserved in `original_rows.csv`; every changed cell with both values is in `column_diff.csv`. No grade exists for either attempted run, so neither candidate is comparable and neither won.
