# Compare run 2: verification, repair, and one proposed next step

2026-09-30. Offline only. No GPU launch, no Kaggle push, no submission, no polling. Frozen candidates,
launched notebooks, the four-task selection and the held-out set are unchanged; the regenerated
working notebook is dispatch-disabled.

Evidence used, copied unmodified from the Kaggle download and verified byte-identical to the source
directory at copy time:

- `reference/compare_run2/` (raw artifacts, 906 KB)
- `reference/compare_run2_review/` (Codex's report, CSV, review summary, console log)
- `reference/compare_run2_analysis/` (this repair's outputs, written outside the evidence tree)

---

## 1. Verification of the reported findings

Every claim below was checked against the raw traces and `runs.json`, reading the actual tool-call
arguments and observations rather than the summary CSV.

| Reported | Verdict | Evidence |
|---|---|---|
| Kernel version 2 completed | confirmed | session log ends at t=1739 s with nbconvert output; no exception |
| All eight control arms passed | confirmed | `pilot/control_recheck.json`: 8 arms, every one `agrees_with_saved: true`, `cleanup_ok: true` |
| Only two of eight agent runs executed | confirmed | `pilot/runs.json` holds 2 records; 6 rows are `attempted=False` |
| Neither reached grading | confirmed | both records: `grading_phase_s: []`, `phase_status.grading: "not_attempted"`, `test_exit_code: -1` |
| A exhausted 60 turns re-running a reproduction | confirmed | 60 tool calls, 10 distinct; one `/tmp/repro.py` heredoc repeated **38** times byte-identically, a second **13** times |
| B made 42 rejected `edit_file` calls missing `old_string` | confirmed | steps 8-49, 42 calls, **41 byte-identical** payloads plus 1 variant at step 33; every observation is the ADK missing-parameter rejection |
| B ended without `submit_patch` | confirmed | `persisted_error: "Agent completed execution without calling submit_patch."` |
| The controller called that an environment failure and stopped | confirmed | `outcome: "environment"`, `outcome_reason: "persisted: unclassified error"` |
| Neither candidate won | confirmed | no grade exists for either run; the two attempted rows are non-comparable |
| The patch-loading repair held | confirmed | all 8 arms show `apply_rc: 0` with `bytes`/`created_bytes`/`sha256` recorded per patch |

Two of Codex's cautions are also confirmed as real defects, and are the metric repairs in section 3:
the `tool_errors` column undercounted, and `/tmp` reproduction writes were counted as repository
source edits.

### Corrections to the run's own numbers

The launched report cell, replayed here over the same artifacts, reproduces the session's own
`pilot_results.csv` **exactly** (`scripts/recheck_compare_run2.py` asserts this before comparing
anything). Against that baseline:

| | A/rich_3278 | B/rich_3278 |
|---|---|---|
| `shell_edit_hints` | 54 -> **0** | 2 -> **0** |
| `first_source_edit_attempt_step` | 5 -> **unavailable** | 5 -> **8** |
| `tool_errors` | 1 -> 1 | 1 -> **43** |
| `attribution` | empty_patch | empty_patch -> **no_submission** |
| `acknowledged_source_edit_calls` (new) | **0** | **0** |

That column is named for what it measures: edit calls the tool **accepted**. It is not a claim that a file changed, and there is no before/after file evidence in these artifacts.
| `tmp_scratch_writes` (new) | **54** | **2** |
| `rejected_tool_calls` (new) | **0** | **42** |
| `repeated_identical_tool_calls` (new) | **48** | **39** |
| `unparsed_tool_call_texts` (new) | **0** | **4** |

**No accepted edit-tool call was recorded for either candidate**, and for B the harness's final
`git diff` against the baseline commit came back empty (`agent_runner.py:766-780` sets the "without
calling submit_patch" message only in that case). Those two facts are independent of each other, and
together they establish **no net tracked change at the end of the run**. They do NOT establish that no
file was ever written: an untracked file, a write followed by a revert, or a change outside the diff's
scope would leave the same evidence. The metric counts calls the tool acknowledged; nothing anywhere
in this run compared a file's bytes before and after.

The corrected eight rows, the original eight rows, and every changed cell with both values are in
`reference/compare_run2_analysis/`.

---

## 2. Root-cause table

### Established

| Finding | Evidence |
|---|---|
| The stop was caused by an unmatched marker, not by an observed environment fault. `"Agent completed execution without calling submit_patch."` matched nothing in `_classify_one` and fell through to `return 'environment', 'unclassified error'`. | `scripts/compare_cells.py` pre-repair; `runs.json` `outcome_reason` |
| Nothing about the environment had failed. Four L4s, tp=4, sandbox cleaned, both setup provenance probes resolving to the workspace, and the same server had just carried A through 60 turns. | `runs.json` `setup_provenance[0].provenance_ok: true`, `cleanup_ok: true`; session log |
| B's run ended on the nudge limit, not a budget. `max_nudges = 3`; the loop breaks at `consecutive_nudges >= max_nudges`. B's trace shows 4 unparsed agent texts with 3 `continuation_nudge` entries between them. | `agent_runner.py:499,680`; trace steps 51-57 |
| The model's raw tool-call delimiters are wrong. The four saved raw texts are `<\|tool_call>call:git grep ... <tool_call\|>`. The harness's own nudge string names the correct token as `<\|tool_call\|>`. Opening and closing tokens are both malformed, and the payload is `call:` plus a bare shell command rather than a structured argument list. | trace steps 51/53/55/57; `agent_runner.py:700` |
| The harness misdiagnoses that as token-limit truncation. `has_truncated_tool_call = '<\|tool_call>' in last_assistant_text` fires on the literal substring, so the nudge tells the model its response was cut off and to "split the change into smaller incremental edits." Completion length was 26-30 tokens against `max_output_tokens: 8192`. | `agent_runner.py:695-703`; trace `metrics.completion_tokens`; `candidate_B/configs/sampling.yaml` |
| The 42 rejections were produced by google-adk, before `edit_file` ran. `FunctionTool.run_async` filters the argument dict to declared parameters, finds `old_string` missing, and returns `{'error': ...}` without invoking the function. | `.venv/.../google/adk/tools/function_tool.py:170-188`; observation text matches verbatim |
| Therefore the rejections cost **no** tool-call budget but one LLM turn each. The budget is charged inside `@budget_gated`, which decorates the tool body the rejection never reaches. B spent 42 of its turns this way (budget: `max_turns=60`, `max_tool_calls=100`). | `swegemma/tools/base.py:62-92`; `swegemma/context.py:542` |
| The `new_string` value is double-escaped relative to the file on disk. It carries `r\"\"\"` and `\\x1b` where `rich/ansi.py` has `r"""` and `\x1b`. Even a correctly parsed call could not have matched `old_string`. | payload vs the `read_file` observation at trace step 4 |
| A recorded no edit-tool call at all, and was not reacting to contradictory evidence. Its reproduction **ran** successfully (`exit_code: 0`) and its output **demonstrated the bug**: `Match: None` for all four private escape codes, which is the unfixed behaviour the issue describes. It is not evidence of a passing fix. That output was stable from step 9, and the identical command then ran 37 more times. | A's trace, step 9 observation |

### Plausible, not established

| Hypothesis | What supports it | What is missing |
|---|---|---|
| The 42 malformed argument dicts are the residue of splitting a non-JSON, backtick-quoted `key:value` payload on characters inside the content. | `new_string`'s value ends with a backtick followed by the literal text `,old_string:`; two further keys are fragments of the same replacement text. No JSON parser produces that from valid JSON. | The raw completion for those steps is not recorded, so the exact bytes are unknown. A naive comma/colon split of the intended text does not reproduce the observed four pairs exactly, so the splitting rule is not identified. |
| The failure is content-dependent: payloads dense in backslashes, quotes, colons and commas are the ones that break. | Both candidates failed on a regex task; the earlier smoke run's simpler `write_file("repro.py")` call was accepted. | One task, two runs. No controlled comparison across content shapes. |
| The identical retries are caused by uninformative feedback. | ADK filters the argument dict to declared parameters (`function_tool.py:171`), so the error names only `old_string` and never mentions that the payload was mangled; attempt 1 and attempt 41 receive the same text. | **Established: what the model was told. Hypothesis: that this is why it repeated.** A model can repeat identical output for other reasons (low temperature on a near-identical prompt, a decoding attractor). Nothing here rules those out, and no intervention on the feedback text has been tried. |
| The prompt difference between A and B produced the different failure modes (never editing vs 42 malformed edits). | Only `prompts/system.md` differs. | n=1 task, no grade, and both outcomes are zero-patch. Not attributable. |

### Unknown

- Whether the malformation originates in the model's output or in vLLM's `gemma4` tool parser. The
  trace records `tool_calls` only after parsing; no raw completion is stored for a step that produced
  a parsed call. vLLM 0.19.1 is not present in this project, so the parser's splitting rules cannot be
  read offline. **Not reconstructed, and not guessed.**
- Whether the server reported `MAX_TOKENS`. `finish_reason` is absent from every trace step
  (`finish_reasons: unavailable` for both runs), so the harness's truncation branch cannot be
  confirmed from the artifacts, only judged implausible from the 26-token completions.
- Why v1, v2 and v3 all scored 0.06 under Docker grading. Nothing here speaks to that.

---

## 3. The repair

Five files changed, four added. Full unified diff:
`reference/compare_run2_analysis/REPAIR_DIFF.patch`.

**Stop classification** (`scripts/compare_cells.py`). A new single-entry tier,
`_CANDIDATE_NO_SUBMISSION_MARKERS`, recognises the exact termination text and returns
`('candidate', 'agent ended without submitting a patch (no environment cause found)')`. It is checked
**after** `_ENVIRONMENT_MARKERS` and before the generic wrappers, so a real environment cause named in
the same string still wins. Because `classify_outcome` classifies each source separately and combines
worst-first, a genuine environment failure in the escaped exception also still wins. Cleanup,
provenance and unobserved-grading stops are untouched. A candidate outcome still requires a healthy
server probe before the next run starts.

**Metrics** (`scripts/make_pilot_notebook.py`). `trace_stats` is rewritten around two new helpers:

- `observation_status(step)` returns `ok | rejected | error | none`, recognising a bare
  `{"error": ...}` as well as `status == "error"` and a non-zero `exit_code`, and separating calls the
  tools *rejected* from calls that ran and failed.
- `shell_write_targets(cmd)` returns `(source_targets, scratch_targets)`, so `> /tmp/repro.py` is a
  scratch write and `sed -i ... rich/ansi.py` is a source edit. Only `.py` targets count.

New columns: `successful_tool_calls`, `rejected_tool_calls`, `acknowledged_source_edit_calls`
(named for what it measures: calls the tool accepted, not files proven to have changed),
`tmp_scratch_writes`, `repeated_identical_tool_calls`, `unparsed_tool_call_texts`. A source edit is
counted as *applied* only when the observation was accepted. `attribute()` gains `no_submission`, so a
run that never submitted is not labelled `empty_patch`.

`ARM_FOR_LAUNCH` in `scripts/make_compare_notebook.py` is now `False`; the regenerated notebook
(`27b7f7aa6c483b2934d22ba182c25dbf411b100595f164577b43bb21ae68a8a3`) ships `DISPATCH_CONFIRM = False`.

### Test results

All suites execute generated notebook cells, not string searches.

| suite | result |
|---|---|
| `NB_TARGET=compare test_compare_dispatch.py` | **137 passed, 0 failed** (was 108; +29 assertions in 6 new tests) |
| `NB_TARGET=compare test_trace_metrics.py` | **75 passed, 0 failed** (new) |
| `NB_TARGET=compare test_stop_logic.py` | 21 passed, 0 failed (S1 is skipped for this target) |
| `test_pilot_notebook.py` | 82 passed, 0 failed |
| `NB_TARGET=compare test_pilot_notebook.py` | 82 passed, 0 failed |
| `test_review_compare_results.py` | 97 passed, 0 failed |
| `test_evalset_policy.py` | 45 passed, 0 failed |

The six new dispatch tests use the real termination string verbatim:

- **D14** it is a candidate outcome, reported as ungraded, attributed `no_submission`
- **D15** it lets every other planned run go ahead: 8 of 8 dispatched, both candidates, no stop reason
- **D16** a genuine environment failure still stops
- **D17** environment wins when both occur as separate sources
- **D18** a leaked sandbox still stops, and all eight rows survive the early stop
- **D19** environment wins when both appear in **one** string, which pins the tier's position

D15 required a change to the test harness rather than the notebook. The suite could previously only
make the post-candidate server health probe *fail*; nothing could reach the "continue" branch. Rather
than stub out the probe and delete the code under test, `make_env(server_healthy=True)` starts a real
`ThreadingHTTPServer` answering `/v1/models` with 200 on an ephemeral port.

### Mutation testing

Tests passing is not evidence of coverage. `scripts/mutate_compare_repairs.py` breaks one thing at a
time, regenerates the notebook, and requires the suite to go red. Log:
`reference/compare_run2_analysis/mutation_log_2026-09-30.txt`.

| mutation | caught |
|---|---|
| classification tier removed entirely | yes, 10 failures |
| tier moved before the environment markers | yes, 2 failures |
| `no_submission` attribution removed | yes, 1 failure |
| plain-`error` observations no longer counted | yes, 9 failures |
| `/tmp` writes counted as source edits again | yes, 11 failures |
| rejected calls credited as applied source edits | yes, 2 failures |

All six caught; both suites returned to baseline after restore.

### Offline regression fixture

`reference/compare_run2_malformed_calls.json` holds both distinct payloads verbatim, the 42-step
replay sequence, the ADK rejection text and the source trace's SHA-256. `test_trace_metrics.py` [M5]
replays it through the shipped counter and asserts 42 rejected, 0 applied, 39 identical repeats, and
that the `old_string` residue is present inside `new_string`.

[M7] runs the reviewer's own `comparison_eligible` over the corrected rows: all eight remain
non-comparable, and a `candidate` failure class alone does not confer comparability. Reclassifying who
a failure belongs to must not turn an ungraded run into a win or a loss.

---

## 4. Proposed next experiment: WITHDRAWN and replaced

The 2026-09-29 version of this section proposed an eight-run GPU comparison with "raw-completion
capture" implemented as an ADK `after_model_callback`. **That proposal was wrong and is withdrawn.**

An `after_model_callback` receives an `LlmResponse` whose `function_call.args` is already
`json.loads(tool_call.function.arguments)` (`google/adk/models/lite_llm.py:1730`, invoked from
`flows/llm_flows/base_llm_flow.py:1270`). It is a **post-parser** capture point. It would have
recorded the same parsed dictionaries the run already recorded, at the cost of a GPU session.

The parse that matters happens inside the vLLM server process and its input is never transmitted to
the client, so no client-side hook can reach it. The replacement plan, the proof for each capture
point, and the smallest GPU diagnostic that is actually worth running are in
**`reference/COMPARE_RUN2_CAPTURE_PATH_2026-09-30.md`**. The short version: the decisive question can
probably be settled **with no GPU at all**, by reading the vLLM 0.19.1 `gemma4` tool parser, because
the observed argument dictionaries are that parser's output.

## 5. What still prevents a trustworthy comparison

1. **No grade has ever been produced for any candidate on any task.** Two runs reached the agent loop;
   neither reached grading. There is nothing to compare.
2. **Neither candidate has been observed making an accepted source edit.** Until one does, the
   comparison has no dependent variable.
3. **The model-versus-parser question is open,** and it sits upstream of every prompt decision. Raw
   completions are not recorded for parsed calls, and the parser is not readable offline.
4. **`finish_reason` is not recorded anywhere in the traces,** so the harness's own truncation
   branch cannot be audited from artifacts.
5. **The dev pool is 100% `rich`.** Every valid `fastapi` and `requests` task sits in the protected
   hold-out. A result here cannot speak to the hidden set's repo mix.
6. **Controls come from subprocess-mode screening; the comparison runs the same backend.** The grader
   runs Docker, where `install_editable_package` and `install_test_dependencies` actually execute.
   Equivalence is assumed, not demonstrated.
7. **`pilot_manifest.json` does not record `STOP_REASON`.** The re-derivation had to read it from the
   session's own CSV. Worth adding to the MANIFEST block before the next run.
8. **Nothing here improves the score,** and no score or rank improvement is claimed or implied.
