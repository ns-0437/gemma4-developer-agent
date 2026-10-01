# Candidate S: a concise coder prompt, derived from scored v3/A

2026-09-30. Offline. Dispatch disabled. No GPU, no push, no submission. Candidate R, the launched
Stage-1 notebook and the raw run artifacts are unchanged; held-out tasks untouched.

---

## 1. Correction accepted

**Candidate R already forbids repeating identical calls against unchanged state, and already carries a
two-attempt escape rule.** Verified in `candidate_R/prompts/system.md`, five separate instructions:

- "Do not repeat a call when nothing relevant has changed since you last ran it."
- "Re-issuing an identical call against unchanged state is not: it will return what you already have."
- "If you are stuck after two attempts at the same sub-problem, submit the best source change you have."
- "Avoid repeating equivalent searches."
- "do not re-run the same command hoping for a different answer."

My earlier description of repetition as a missing instruction was wrong. **No sixth phrasing of that
rule is proposed, and candidate S does not add one.**

---

## 2. Feedback-path audit

Full write-up: `reference/stage1_review/FEEDBACK_PATH_AUDIT.md`.

**Recorded during this run**, from the artifacts only: prompt tokens grew from 5,514 to 19,538 across
all 60 model turns with **zero decreases in 59 transitions**, at a constant **+128 tokens per turn**
through the repeat loop, consistent with one call plus one response appended each time. The configured
compaction threshold was 20,480 and the peak was 19,538, so **compaction never fired**. No rewind,
retry or reset event appears anywhere in the trace.

**Source-level reconstruction**, kept separate: `agent_runner.py:521` passes only the new message;
ADK rebuilds the whole request from `session.events` every turn (`contents.py:73`), pairing function
calls with their responses (`contents.py:101, 148`). History can be removed only by a rewind action, a
branch mismatch, or compaction. All three are ruled out for this run by the recorded facts above.

**What this does not establish.** The outgoing HTTP request bodies were **not captured**. Token counts
evidence request SIZE and growth, not the internal ordering or association of call and response. **This
audit does not prove the model saw the observations**, and **no transport defect is claimed or
invented.** No concrete feedback-path defect was found, so the next step is a prompt-package
experiment, as instructed.

---

## 3. Candidate S

`experiments/concise_workflow_v1/candidate_S`, derived from **candidate A (= `releases/v3`, the scored
0.06 agent)**, not by expanding R.

**Only `prompts/system.md` changes.** `agent.yaml`, `configs/sampling.yaml`,
`sub_agents/code_analyzer.yaml` and `prompts/analyzer.md` are byte-identical; model, sampling, analyzer
and budgets unchanged.

| | A | S |
|---|---|---|
| system.md words | 1,247 | **413** (-834) |
| system.md chars | 7,729 | 2,598 |
| compiled coder instruction | 7,729 chars | **2,598 chars** |
| system.md sha256 | `4d42f2b7d48143cd06c31fe4c33b17a3f78da21ec2c53d9569cf6a336f6e5e79` | **`39b2541c2220cc7655c576bb4ae7ac7e03200a72f2f1e518313068fc93be3b91`** |
| package zip sha256 | `b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b` | **`8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07`** |

Diff: `experiments/concise_workflow_v1/system_md.diff`. Regenerate with
`python scripts/make_candidate_s.py`.

**Workflow:** understand -> localize -> reproduce **once** -> edit -> verify -> submit. The one novel
line is a budget instruction with a checkpoint: most turns belong to editing and verifying, and if
source editing has not begun by roughly halfway, edit the best current hypothesis and verify it.

**Preserved from A**, because they are environment facts the agent cannot discover cheaply:
`/tmp` scratch with a heredoc and the write tools' refusal of `/tmp`; test files reset before grading
so only source counts; pytest exit code preserved rather than piped away; exit 5 is not success and a
skipped test verifies nothing; `rg` and `tree` unavailable; the checkout-import check; a short unique
`old_string`; restoring test paths before submitting.

**Generic only.** Twelve checks in `scripts/make_candidate_s.py` assert no leakage of `rich_3278`,
`rich/ansi`, `re_ansi`, the escape-sequence details, `Textualize`, `FAIL_TO_PASS` or gold data, and
that each preserved constraint survives. All pass.

**Gate results:** local validator `OK: 5 files, 0.01 MB`; **`OFFICIAL COMPILE OK: candidate_S`**;
effective generation config identical to A (`temperature 0.2, top_p 0.95, top_k 40, max_output 8192,
seed 42`, `enable_thinking: False`); same tool list; analyzer instruction unchanged at 1,384 chars.

**This is a prompt-package experiment.** It does **not** assert that prompt length caused the loop. The
evidence is only that the anti-repetition instructions were present, retained in context, and not
followed. Whether a shorter prompt is followed more reliably is the hypothesis under test.

---

## 4. Prepared comparison, A against S

`notebooks/ab_s/`, kernel `navin03/gemma4-swe-agent-ab-s`, notebook sha256
`92cb1f0b7fe6fdc9a5c14f1ccb0a7e33edf9a1ca6a6d8dbb3f664ff719599279`, 13 cells, private, internet off,
GPU, **`DISPATCH_CONFIRM = False`**. Generated by `scripts/make_ab_s_notebook.py`, which reuses the
existing comparison machinery and controls rather than adding any.

### Correction: my earlier task list violated the freeze

I proposed `fastapi_14873` and `requests_7427` as development tasks. **Both are in
`protected_holdout`, and so are all five other validated fastapi and requests tasks.** The freeze
already records this: `coverage_shortfall` says the dev-eligible pool is 100% Textualize/rich and that
all seven valid fastapi/requests tasks were deliberately not moved. They are removed from the
proposal, and `task_freeze.json` is **unchanged**.

**New launch check.** `make_compare_notebook.assert_tasks_not_held_out()` reads the freeze and refuses
to generate any notebook whose task set intersects the hold-out, naming the overlap and stating that
editing the freeze to free a task is not the remedy. It runs at the top of `main()`, so every notebook
built on this machinery inherits it. Verified: it refuses `['rich_3278', 'fastapi_14873',
'requests_7427']` and accepts the development four.

### Tasks and order

The four frozen development tasks, alternating A/S then S/A:

| # | task | candidate |
|---|---|---|
| 1 | `rich_3278` | A |
| 2 | `rich_3278` | S |
| 3 | `rich_3535` | S |
| 4 | `rich_3535` | A |
| 5 | `rich_3675` | A |
| 6 | `rich_3675` | S |
| 7 | `rich_3942` | S |
| 8 | `rich_3942` | A |

**This is a Rich-only diagnostic. It is not evidence of cross-repository improvement.** All four tasks
are Textualize/rich because the hold-out holds every validated task from the other repositories. A
result here generalises to rich at best, and no screening pipeline is being built to widen it.

### Three measurements, kept separate

**Reliability.** Per run: a valid non-empty **source** patch, and observed grading with a verdict exit
code. This is the thing no run has yet produced.

**Performance.** Paired per task, reported as four categories and never collapsed into one number:
solve, loss, tie, and **ungraded**. An ungraded outcome is its own category; it is not a loss.

**Mechanism.** Repeated identical calls, turns used, whether the run ended on the turns budget, and
operation-level edit evidence. Reported alongside the other two, never merged into them.

### Two rules for reading it

**A source patch counts whatever produced it.** A shell edit through `run_command` is as valid as an
`edit_file` call: the harness grades `git diff`, not the tool that produced it. **No acknowledged
`edit_file` or `write_file` call is required** for reliability or performance. Operation-level edit
evidence is recorded under mechanism only, as a description of how the change was made.

**More graded but incorrect patches is not an improvement.** If S produces patches that grade and fail
where A produced none, that is progress on reliability and **nothing at all** on performance. The two
are reported separately precisely so that improvement in the first is not presented as the second.

### Cost

~17 min CPU setup, controls and preconditions; 6 to 10 min vLLM startup; eight runs at the 10-minute
agent budget plus grading. **Roughly 130 minutes. An estimate, not a bound**: startup has varied 6 to
9.6 minutes across past sessions, grading time for three of these four tasks is unmeasured, and
`SESSION_CAP_MIN = 300` is an admission limit that does not stop work in flight.

**Not authorized, and not armed.** The generator never arms; arming would change the notebook bytes
and would be recorded with both hashes, as it was for Stage 1.

---

## 5. Remaining unknowns

1. Whether the model's outgoing requests correctly associated each tool call with its response. The
   request bodies were not captured, and token growth cannot answer it.
2. Why the agent re-issued one command 56 times when five explicit prohibitions were in the prompt and
   the recorded growth is consistent with them still being in context. **Unexplained.**
3. Whether prompt length affects that at all. Untested, and the reason S exists.
4. Whether the host's vLLM wheel matches upstream (405 bytes apart, established earlier).
5. The Stage-1 quota reading moved from 02:25 to 02:49. **Attributing all 24 minutes to this run would
   require ruling out other account usage and delayed accounting, and I have not done that.** The
   session itself was 12m 7s by Kaggle's own page.
6. Nothing here speaks to the other repositories. The development pool cannot, by construction.
7. **No score prediction is made. There is no evidence supporting 0.15 or 0.20.** The immediate target
   is an agent that reliably gets from finding the bug to a graded patch, which no run has yet shown.
