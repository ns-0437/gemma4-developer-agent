# Pilot v1 — evidence packet (2026-09-28)

Kernel `navin03/gemma4-swe-agent-pilot` **version 1**, status COMPLETE.
Artifacts downloaded unchanged into `reference/pilot_v1_results/`.

## Hardware and model — from RUNTIME metadata, not the request
`torch.cuda.device_count()` = **4**, names `['NVIDIA L4'] x4`; vLLM started with **tp=4** in 6.3 min.
Model `/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2`,
config sha256 `b100d85e571c25b6...`, quantization pack-quantized 4-bit.
swegemma 0.2.7, adk-submission 0.2.11, google-adk 1.36.1, vllm 0.19.1.
Candidates as dispatched: A `f6392b82...`, B `194b420a...` (**unchanged**).
Budgets identical for both: max_time_minutes 10, max_tool_calls 100, max_turns 60, timeout 300.
**GPU quota charged: unavailable** (no pre-push reading was taken; a single post-hoc figure cannot
establish the delta).

## Four planned rows

| # | run | status | outcome | attribution |
| --- | --- | --- | --- | --- |
| 1 | requests_7309 / A | executed | not resolved | **test_patch failed to apply** (`test_exit_code -1`, grading never ran) |
| 2 | requests_7309 / B | executed | not resolved | **empty patch**; repetition loop then context overflow |
| 3 | rich_3471 / B | **not_attempted** | missing | dispatch stopped by the guard after run 2 |
| 4 | rich_3471 / A | **not_attempted** | missing | dispatch stopped by the guard after run 2 |

## Corrections to the first version of this report (verified against artifacts)
1. A's saved diff deletes **four** `"no_equals": True,` expectations across four hunks, not five.
   The "5 out of 5 hunks ignored" figure belongs to `task.test_patch`, not to the agent's diff.
2. B's failure is a **repetition loop**, not an output-allowance problem: it issued the *identical*
   `read_file(tests/test_utils.py, 570, 600)` call **25 times consecutively, steps 22-46**.
3. The 646,691 figure is **cumulative prompt tokens across all requests**, not a context length.
   It cannot be compared to the 32,768 window.
4. The overflow shows that input plus reserved output exceeded the window on one request. It does
   **not** establish that thinking and `max_output_tokens: 8192` are inherently incompatible, and
   lowering the output allowance alone is **not** a complete fix.
5. Rows 3 and 4 are **not_attempted**. Grading provenance for run 2 was *never observed* because
   grading never started; that is not an observed provenance failure.

Log line: `Stopping further dispatch after infrastructure/provenance failure.`
The guard fired because run 2 produced only one setup observation (`both_setup_imports_verified:
false`) — grading never started, so the grading-phase probe never ran. The guard worked as designed;
whether a context-window failure should count as *infrastructure* is a design question, see below.

## Row 1 — requests_7309 / A (thinking OFF)
wall 161.7 s | agent phase 134.7 s | **agent loop 108.2 s** | grading phase 26.9 s
tool_calls 23, edit_calls 8, repeated identical commands 2, tool errors 5
prompt tokens 177,719 | completion tokens 3,327 | finish_reasons **unavailable**
Provenance: agent AND grading both imported
`/tmp/swegemma_sandbox_*/workspace/src/requests/__init__.py` — **the checkout**, in both phases.

**It produced a real source edit** to `src/requests/utils.py::_parse_content_type_header`, removing the
`key, value = param, True` default so bare params are dropped.

**It also edited the verification tests**, which our prompt explicitly forbids. The diff deletes
`"no_equals": True,` from **five** expected-value fixtures in `tests/test_utils.py` — i.e. it changed
the tests to match its implementation rather than making the code satisfy the tests.
Consequence: the harness could not apply `task.test_patch`
(`Reversed (or previously applied) patch detected! 5 out of 5 hunks ignored`), so **grading never ran
and the fix was never evaluated**. Whether the source edit alone would have passed is **unknown**.
The exact reason the anti-tamper reset (`git checkout HEAD -- <test files>`, which is run with
`2>/dev/null || true`) did not yield a clean file is **unavailable** from the saved artifacts.

## Row 2 — requests_7309 / B (thinking ON)
wall 252.3 s | agent phase 252.2 s | **agent loop 225.5 s** | grading phase **unavailable** (never ran)
tool_calls 44, edit_calls 5, repeated identical commands 2, tool errors 1
prompt tokens **646,691** (3.6x row 1) | completion tokens 7,085 (2.1x) | finish_reasons **unavailable**
Provenance (agent phase): checkout, verified. Grading phase: never reached.

**Root-cause chain, read from the trace:**
- step 5 `write_file("/tmp/repro.py")` -> rejected, `Path traversal detected` (tool cannot write /tmp)
- step 6 fell back to `repro.py` **inside the workspace**
- step 8 `edit_file` on `src/requests/utils.py` -> a **real source fix**; step 9 repro passes, step 10 compiles
- steps 11-12 targeted pytest fails on the parametrised `no_equals` cases
- **step 17 `edit_file` on `tests/test_utils.py`** -> test tampering
- step 18 pytest returns **`ERROR collecting`**: the edit damaged the test file
- step 20 a second test edit; step 21 still `ERROR collecting`
- **steps 22-46: the identical `read_file(tests/test_utils.py, 570, 600)` 25 times**, no new information
- the accumulated history then overflowed the window and the run raised

Terminating error: `maximum context length is 32768 ... you requested 8192 output tokens and your
prompt contains at least 24577 input tokens, for a total of at least 32769` - one token over.

So the overflow is the **last** link, not the cause. The causes are the rejected /tmp write, the
decision to edit tests when the tests disagreed, the unnoticed collection error, and the failure to
stop repeating an action that returned identical output. Reducing `max_output_tokens` would delay
this run's death, not repair it.

**B produced a source fix at step 8 and still submitted nothing.** The run ended in an exception, so
no patch was extracted - not even the harness's working-tree fallback. A crash discards work that a
timeout would have preserved.

## Answer-key audit — clean
Neither trace references `tasks.jsonl`, `solution.parquet`, `test_patch`, or `secret` (0 hits each).
All `/kaggle/input` occurrences (47 in A, 88 in B) are the `model_name` metadata field
`/kaggle/input/models/google/gemma-4/...` recorded on every step. No contamination found.
This is a trace audit, not proof of filesystem isolation; the subprocess backend is not a boundary.

## What this does and does not establish
Establishes: the pipeline runs end to end on real 4x L4 hardware with the real QAT model; the import
repair holds in the actual agent and grading sandboxes; artifacts, phase timings and traces are usable.
Does NOT establish: any comparison between A and B. **Zero of four runs produced a graded result**, and
two of four never ran. No candidate is better or worse on this evidence.
