# Candidate R, revision 2: recovery from rejected tool calls

2026-09-30. Offline. `DISPATCH_CONFIRM = False`. No GPU launch, no Kaggle push, no submission. No score
is promised and no leaderboard movement is predicted. Revision 1 is preserved unchanged as
`candidate_R_rev1`; frozen A/B releases and launched notebooks are untouched.

---

## 0. The two bounded checks

### Chat template (`reference/vllm_0.19.1_src/examples/tool_chat_template_gemma4.jinja`, 331 lines)

- Tool calls render as `'<|tool_call>call:' + function['name'] + '{'` then, per argument, `key:` and
  `format_argument(value, escape_keys=False)` (lines 232-243).
- `format_argument` for a string emits `'<|"|>' + argument + '<|"|>'` (line 112) with no escaping of the
  delimiter and none of `,` or `:`. Delimited strings need no comma or colon escaping; a string
  containing the literal delimiter sequence has no representation.
- Tool responses use the same encoding (line 153).

**What this does and does not imply.** It shows the template applies the encoding on the prompt side
and that there is no text-level escape sequence in the format. It does **not** establish that
prompt-level influence over the model's own emission is impossible: the model was trained on this
format and prompts demonstrably change which tools it reaches for. That remains an open empirical
question, and candidate R does not depend on the answer. What the prompt influences here is **which
operation the agent performs after a rejection**, not how any value is encoded.

### Host wheel versus upstream

`kaggle datasets files metric/gemma-4-developer-agent-wheelhouse`, metadata only, nothing downloaded:

| | bytes |
|---|---|
| host `vllm-0.19.1-cp38-abi3-manylinux_2_31_x86_64.whl` | **433,132,506** |
| PyPI, same filename | **433,132,101** |

**They differ by 405 bytes, so they are not the same file.** Whether
`vllm/tool_parsers/gemma4_tool_parser.py` itself differs is **not** established; the delta could be
re-zipping or `RECORD` metadata. Settling it needs the 433 MB wheel or HTTP range reads of its central
directory, neither of which was done and neither of which the candidate depends on. Parser findings
therefore describe **upstream** behaviour and are indicative for the host build.

---

## 1. The candidate

`experiments/tool_recovery_v1/candidate_R`. Baseline `candidate_A`, byte-identical to `releases/v3`,
the submitted agent that scored 0.06.

**One file changes:** `prompts/system.md`, 1247 -> 1655 words, one block inserted before `## Rules`.
`agent.yaml`, `configs/sampling.yaml`, `sub_agents/code_analyzer.yaml` and `prompts/analyzer.md` are
byte-identical, verified by `scripts/test_recovery_candidate.py` [R6]. Model, sampling, budgets, tool
list, analyzer and task selection unchanged.

| | sha256 |
|---|---|
| A `prompts/system.md` | `4d42f2b7d48143cd06c31fe4c33b17a3f78da21ec2c53d9569cf6a336f6e5e79` |
| R rev1 `prompts/system.md` (preserved) | `a495b4ece2ee384c0bfe058e15088c84ac6f42a757289850c282a169ba59195b` |
| **R rev2 `prompts/system.md`** | **`c953913bc5d8e7ba3add982b3385f048646b2b981b0edc942c6bf3a62cff80e5`** |
| R rev2 packaged zip | `4d283b8c020bc3a12c2a44a1aa7b4f392a096cc613c3c266bdb8dec5512b85f8` |

Diffs: `system_md.diff` (A to R rev2) and `system_md_rev1_to_rev2.diff`.

### What revision 2 changed, and why

Revision 1 let the agent fall back to `write_file` without qualification. `write_file` overwrites the
whole file, and `read_file` returns at most 150 lines, so an agent working from one read of a longer
file would have silently deleted everything it had not seen. Revision 2:

- allows `write_file` **only** after every line has been read (`cat -n`, in ranges, cross-checked
  against `wc -l`) and everything unaffected can be reproduced; if there is any doubt it routes
  straight to the scripted edit;
- requires the scripted edit to `assert s.count(old) == 1` **before** writing, so a non-unique or
  absent anchor changes nothing, then to read `git diff` and run `python3 -m py_compile`, with
  `git checkout --` named as the way back;
- requires step 1's shorter anchor to be checked for uniqueness with `git grep -c -F` first;
- drops any suggestion that fewer required arguments serialise better.

### What the ordering rests on

Facts about the signatures, read by AST from `swegemma/tools/{workspace,execution}.py`:

| tool | required | of which `str` | must match existing bytes | overwrites whole file |
|---|---|---|---|---|
| `edit_file` | `filepath, old_string, new_string` (+ optional `allow_multiple`) | 3 | yes, `old_string` | no |
| `write_file` | `filepath, content` | 2 | no | **yes** |
| `run_command` | `command` | 1 | no | no |

**The order is not justified by a serialization claim, and none is made.** The justification is
narrower and does not depend on why a call was rejected: re-sending a rejected payload returns the same
rejection, so the agent must do something *different*; `edit_file` uniquely carries a value that must
match file bytes, so it can fail for a second, independent reason; `write_file` is destructive when the
file is not fully known, which is why revision 2 gates it; and the scripted edit is the only step that
can verify its own precondition and its own result. Which alternative actually gets through is **not
predicted here**.

All operations use tools the compiled candidate has: the official compiler prints
`tools=['run_command', 'read_file', 'edit_file', 'write_file', 'get_status', 'submit_patch', 'agent_tool:code_analyzer']`.

### How it avoids repeating the rejected payload

The rule forbids re-sending outright, and each step changes the operation, so the payload changes with
it. A's existing "do not repeat a call when nothing has changed" rule was already in force in run 2 and
candidate B still re-sent one byte-identical payload 41 times; R names the next operation instead of
asking for judgement.

**Corrected claim about the payoff.** A rejection consumes no tool-call budget but one LLM turn
(budget charged inside `@budget_gated`, `tools/base.py:62-92`; ADK rejects before the tool body runs,
`function_tool.py:170-188`). Candidate B spent 42 of its 60 turns on rejected calls. Stopping after one
retry would have left roughly 40 turns unspent. **That is a hypothetical maximum of repetition
avoided, not measured useful work.** Nothing shows those turns would have produced a fix, and B had
already failed to make an accepted edit in the turns it did use.

### What this candidate does not claim

No delimiter is mentioned, no escaping prescribed, no encoding fix hard-coded, the grader's parser
untouched. [R7] asserts the block contains none of `<|"|>`, `tool_call`, `delimiter`, `escape`,
`backtick`, `JSON`, `serial` or `fewer argument`. `rejected_tool_calls`, `unparsed_tool_call_texts` and
the `tool_use_flags` column are **descriptive diagnostics** and assert no cause.

---

## 2. Results already in hand

| check | result |
|---|---|
| local validator | `OK: 5 files, 0.01 MB, model={'gemma-4-31b-it-qat-w4a16-ct'}` |
| **official compiler** | **`OFFICIAL COMPILE OK: candidate_R`** (adk_submission 0.2.11, google-adk 1.36.1) |
| effective generation config | identical to A: temp 0.2, top_p 0.95, top_k 40, max_output 8192, seed 42, `enable_thinking: False` |
| coder instruction length | A 7,729 chars -> R rev2 10,159 chars, the only compiled difference |
| `scripts/test_recovery_candidate.py` | **66 assertions, 0 failures** |
| parser findings / trace metrics / dispatch / stop-logic / pilot / reviewer / policy | 29 / 77 / 137 / 22 / 82 / 97 / 45, all 0 failures |

[R4] renders every step in the native format, runs it through the **real** vLLM 0.19.1 parser, and
confirms ADK would find every mandatory parameter. That covers the well-formed case only and predicts
nothing about what the model will emit.

---

## 3. Three questions, kept apart

Conflating these is what produced run 2's wrong stop. Every report below reports them separately.

**Instrument validity.** Do the controls re-validate, does provenance resolve inside the workspace on
both the agent and grading sides, does grading machinery run, are this run's sandboxes cleaned up?
Evidence: `control_recheck.json`, `setup_provenance`, `grading_observed`, `cleanup_ok`.

**Candidate reliability.** Rejected calls, identical repeats, unparsed response text, missing
submissions. Evidence: `rejected_tool_calls`, `repeated_identical_tool_calls`,
`unparsed_tool_call_texts`, `attribution == no_submission`, `tool_use_flags`.

**Task performance.** Verified solves and regressions, from graded results only. Evidence: `resolved`,
`test_exit_code`, and `comparison_eligible`.

**A candidate that ends without submitting is an ungraded candidate outcome.** It belongs to candidate
reliability, not to instrument validity, and it is never counted as a solve or a loss. Paired graded
results and operational failure counts are reported in separate tables and never summed together.

---

## 4. Stage 1: one task, one candidate

`notebooks/stage1/`, kernel `navin03/gemma4-swe-agent-stage1`, notebook sha256
`19e63c4582cde3a679586b4e20d07757ae0ca40964b9e41bbd79f62d0d7af06c`, 13 cells, private, internet off,
GPU on, **`DISPATCH_CONFIRM = False`**. `ORDER = [(tid, 'R') for tid in TASK_IDS]` with
`TASK_IDS = ["rich_3278"]`: **A is embedded for the isolation check and is not dispatched.** There is
no Stage 2 in this artifact.

`SESSION_CAP_MIN = 90`, `RUN_RESERVE_MIN = 25`, budgets unchanged
(`max_time_minutes=10, max_tool_calls=100, max_turns=60, timeout_seconds=300`).

Cost: roughly 35 to 45 minutes, made of ~17 min CPU setup and controls, 6 to 10 min vLLM startup, one
run bounded by `max_time_minutes=10`, plus grading. **An estimate, not a bound**: startup has varied 6
to 9.6 minutes and grading time for this task is unmeasured.

### Stage 1 gate

All of these, or Stage 1 has not succeeded:

| # | criterion |
|---|---|
| 1.1 | **instrument:** both control arms re-validate and agree with the saved screen |
| 1.2 | **instrument:** agent-side and grading-side provenance both resolve inside the workspace |
| 1.3 | **instrument:** `grading_ran: true`, `test_exit_code` in {0, 1}, exactly one result record |
| 1.4 | **instrument:** `cleanup_ok: true`, no sandbox this run created left behind |
| 1.5 | **candidate:** a **valid non-empty patch that touches at least one source file**, `patch_touches_source: true`, and the patch bytes match `agent_patch_size` |
| 1.6 | **candidate:** `attribution` is not `no_submission` |

An acknowledged edit call is **not** sufficient for 1.5, and 1.5 is not satisfied by a scratch-only or
test-only diff.

### What Stage 1 can and cannot conclude

A pass means **the path produces a grade**. It does not mean the recovery rule helped, and it is not a
performance result: one task, one arm, no pairing.

**Recovery is claimed only if all three appear in the same trace:** at least one rejected call, then a
**different** operation that was accepted, then a verified change to a source file in the final diff.
`scripts/review_stage1.py` is not written yet and will assert exactly that sequence. Absent any of the
three, the run is reported as "no recovery observed", whatever the grade.

If 1.5 or 1.6 fails while 1.1 to 1.4 pass, that is an **ungraded candidate outcome with a valid
instrument**. Report it as such. Do not run anything broader on it, and do not conclude the instrument
is broken.

**If the gate fails, stop.** No broader run on an unproven path.

---

## 5. After Stage 1, if and only if it passes

A bounded development comparison, A against R, on the frozen four `rich` tasks, eight runs, order
alternated, budgets and controls unchanged. Roughly 130 minutes, an estimate and not a bound. It is a
**separate artifact requiring separate review and separate authorization**; nothing in the Stage-1
notebook triggers it.

Four selected tasks from one repository cannot support a general superiority claim, and cannot support
a statistical non-inferiority claim either: the sample is too small and the tasks were chosen, not
drawn. What eight runs can do is surface a large effect and produce per-task paired outcomes.

---

## 6. Promotion criteria, predeclared

Two distinct verdicts, never conflated:

- **Mechanically eligible for broader testing.** The instrument is valid and the candidate is reliable
  enough that a larger run would produce interpretable data.
- **Suitable for submission.** A separate, higher bar requiring evidence of task performance.

### Eligible for broader testing

| # | criterion |
|---|---|
| E1 | Stage 1 gate passed in full |
| E2 | across the four-task comparison, every run graded and every row comparable by `comparison_eligible`; any non-comparable row voids the comparison rather than being reinterpreted |
| E3 | R introduces no `tool_use_flags` value absent from A's runs |
| E4 | R's `attribution == no_submission` count is 0 |

### Suitable for submission

| # | criterion |
|---|---|
| S1 | **at least one verified paired solve by R**. Zero solves against zero solves is never a promotion, whatever the operational counts show |
| S2 | **no regression**: no task A solves that R does not. A single regression rejects R outright |
| S3 | per-task outcomes preserved and reported individually. Equal solve counts on four tasks are reported as **"no difference observed at this sample size"**, never as non-inferiority established |
| S4 | recovery observed on at least one task by the three-part definition in section 4 |
| S5 | runtime: **the four-task mean is not used to certify the competition runtime.** Report per-task `agent_loop_s` and the maximum, note that all four tasks are `rich` and that the hidden set is 67 fastapi / 48 rich / 13 requests / 1 httpx by the training mix, and state the projection as a range with the assumptions named. R is rejected if any run hits `max_time_minutes` that A did not |

A one-task paired solve lead is **real observed evidence** and is reported as exactly that: one task, on
`rich`, paired. It is not a general superiority claim and is not presented as one.

### Stop conditions

- Stage 1 gate unmet: nothing broader runs.
- E2 breached: the comparison is void; fix the instrument.
- S2 breached: R rejected regardless of solve count.
- S5's `max_time_minutes` clause breached: R rejected even if it solves more, because a 12-hour overrun
  currently errors the whole submission.

### Exploratory decisions

Any decision to submit on evidence weaker than S1 to S5 is an **explicit exploratory decision**. It
must be recorded as such, with the criterion it fails, the reason, and the slot cost, in
`CANDIDATE_RECORD.json` before the submission. It is never described as a measured improvement.

---

## 7. Pre-parser capture: still deferred

Not part of Stage 1. Before it is proposed again it must be demonstrated that, on the **actual** server
build and tokenizer, `--enable-log-requests --enable-log-outputs` writes `output_token_ids` and that
those ids decode back to the text. The host wheel is known to differ from upstream by 405 bytes, so the
upstream reading of `entrypoints/logger.py` is not sufficient. Logging stays private: `log_inputs`
writes prompts only at DEBUG, the default level is INFO, and any saved excerpt passes a redactor
dropping `Authorization`, `api-key` and `x-api-key` with an assertion that no `Bearer` string survives.
