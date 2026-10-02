# Temperature-only comparison, S versus S_temp: eight runs on four Rich tasks

Written 2026-10-01. Kernel `navin03/gemma4-swe-agent-temperature` version 1, reported COMPLETE by
Codex at 2026-10-01T05:45:45Z. Downloaded to a fresh directory `reference/temperature_run_2026-10-01/`,
65 files. SHA-256 manifest recorded **before** any analysis at
`reference/temperature_review/raw_sha256.json`. Raw files unmodified; all reports are written here,
outside the raw directory. No GPU launch, repush, retry, submission, candidate change, hold-out access,
GitHub push or history rewrite was made.

**Headline: all eight runs exhausted the 60-turn budget. Zero patches, zero grading, zero solves for
either candidate. The previously observed `rich_3675` solve by candidate S did not reproduce.**

---

## 1. Experiment identity, verified

| check | result |
|---|---|
| launched notebook | `notebooks/temperature/temperature.ipynb` = `ff22c79682ec29e9…` **matches** the pinned launched hash; `ARMED.json` and `LAUNCH_RECORD.json` carry the same hash with `dispatch: true` |
| prepared versus armed | `PREPARED.json` pins `d17f234a34b1c44d…` with `dispatch: false`; the only recorded delta to the armed notebook is the dispatch flag |
| candidate archives | `S.zip` = `8bf9f72c5d7ac474…` **matches**; `S_temp.zip` = `4f1ff61c1d8acf02…` **matches** |
| downloaded candidate trees | 5 files each, **byte-identical** to the frozen archives; no extra or missing file on either side |
| the one intended difference | `configs/sampling.yaml` only, `temperature: 0.2` → `temperature: 0.7`. `agent.yaml`, `prompts/system.md`, `prompts/analyzer.md` and `sub_agents/code_analyzer.yaml` are byte-identical |
| manifest run order | `[3278 S, 3278 S_temp, 3535 S_temp, 3535 S, 3675 S, 3675 S_temp, 3942 S_temp, 3942 S]`, exactly the planned order |
| task content hashes | all four match `expected_task_hashes` |
| budgets | 10 agent minutes, 100 tool calls, 60 turns, 300 s command timeout |
| environment | 4x NVIDIA L4, swegemma 0.2.7, **adk-submission 0.2.12**, adk-eval-core 0.1.0, google-adk 1.36.1, vllm 0.19.1, litellm 1.82.4, transformers 5.13.1 |
| session wall clock | about 2,454 s (41 min) |

**One environment difference from the A/S session, and it matters for the S-versus-historical-S
contrast:** that session ran **adk-submission 0.2.11**, this one ran **0.2.12**. Candidate S is
byte-identical across both, the harness package is not.

---

## 2. All eight planned rows

None missing, none aborted, none not-attempted. `attempted=True` on all eight.

| # | task | cand | outcome | patch bytes | grading observed | exit | resolved | termination | tool calls | longest adjacent identical block | adjacent repeats | rejected calls | edit calls | agent loop s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | rich_3278 | S | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **20** (`cat > /tmp/repro.py` heredoc) | 52 | 0 | 0 | 410.9 |
| 2 | rich_3278 | S_temp | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **19** (`edit_file`, all rejected) | 43 | **21** | 21 | 202.8 |
| 3 | rich_3535 | S_temp | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **41** (`python3 -c "print(hex(ord(' ')))"`) | 40 | 0 | 0 | 70.5 |
| 4 | rich_3535 | S | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **0** (39 separated duplicates) | 0 | 0 | 0 | 87.4 |
| 5 | rich_3675 | S | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **2** (`read_file rich/console.py`) | 2 | 0 | 0 | 109.8 |
| 6 | rich_3675 | S_temp | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 60 | **11** (`read_file rich/console.py`) | 41 | 0 | 0 | 151.9 |
| 7 | rich_3942 | S_temp | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 59 | **10** (`read_file rich/markdown.py`) | 24 | 0 | 0 | 186.7 |
| 8 | rich_3942 | S | candidate, turns budget | 0 | **no** | -1 | false | turns budget (60) | 57 | **3** (`read_file rich/default_styles.py`) | 2 | 0 | 0 | 142.9 |

Exit `-1` is the harness sentinel meaning **grading did not run**. It is not a test verdict and is not
a failed test. `patch_touches_source` is false and `acknowledged_source_edit_calls` is 0 on all eight,
so there is no accepted modifying operation anywhere in this session, by file tool or by shell command.

### Source-patch validity and application evidence

Nothing to validate: `patch_bytes = 0` on all eight, no `patches/` directory was produced for any run,
and no `test_outputs/` directory exists. Seven of the eight runs **never attempted** a repository edit.
The eighth, S_temp on `rich_3278`, attempted 21 and had all 21 rejected before execution.

### Provenance and cleanup

- **Agent-side setup provenance observed on all 8**; `preconditions.json` reports `ok: True` for all
  four tasks, with agent and grading import paths both inside the checkout.
- **Grading-side provenance is UNOBSERVED on all 8, because grading never ran.** `grading_phase_s` is
  empty for every run. `both_setup_imports_verified` is false everywhere for that reason. This is
  unexercised, not a demonstrated fault, and **not zero**.
- **Cleanup confirmed on 8 of 8.** No leaked sandbox. `server_stopped: true`.

### Candidate versus environment failures

**Candidate failures 8, environment failures 0, harness errors 0, provenance failures 0.** Every
termination is `failure_class: candidate` with `phase_status {agent: passed, grading: not_attempted}`.
The turns-budget message appears in the harness error field as the termination cause; it is attributed
to the candidate, not the instrument.

---

## 3. Three findings, kept separate

### 3a. Instrument validity: good, with one new reproducibility problem that is not the instrument's fault to prove

Controls re-validated on all 8 arms and agree: baseline pytest exit 1, reference exit 0, on every one
of the four tasks. Preconditions ok on 4 of 4. Cleanup 8 of 8. Identity fully verified above. Zero
environment failures. On its own terms the instrument behaved.

What the instrument cannot currently support is a **run-level reproducibility claim**. Candidate S is
byte-identical to the S that solved `rich_3675` in the A/S session roughly five hours earlier, and here
it did not reach an edit on that task at all. Two differences are present at once, session-to-session
sampling variation and adk-submission 0.2.11 versus 0.2.12, and this evidence cannot separate them.

### 3b. Candidate reliability: worse than the A/S session for both arms

| | A/S session, candidate S | this session, S | this session, S_temp |
|---|---|---|---|
| runs reaching `submit_patch` | 1 of 4 | **0 of 4** | **0 of 4** |
| runs attempting any edit | 2 of 4 | **0 of 4** | **1 of 4** (all 21 rejected) |
| runs with an accepted modifying operation | 1 of 4 | **0 of 4** | **0 of 4** |
| total adjacent identical repeats | 85 | **56** | **148** |

Both arms are unreliable here. S_temp is the worse of the two on the diagnostic measure: **148 adjacent
identical repeats against S's 56 in the same session, under the same controls and alternating order.**

### 3c. Verified task performance: nothing verified, for either candidate

| candidate | solved | graded, unsolved | ungraded | not attempted | denominator |
|---|---|---|---|---|---|
| **S** | **0** | **0** | **4** | 0 | 4 |
| **S_temp** | **0** | **0** | **4** | 0 | 4 |

Paired, all four tasks:

| task | S | S_temp | pair |
|---|---|---|---|
| rich_3278 | ungraded | ungraded | **undecided** |
| rich_3535 | ungraded | ungraded | **undecided** |
| rich_3675 | ungraded | ungraded | **undecided** |
| rich_3942 | ungraded | ungraded | **undecided** |

**0 decided pairs, 4 undecided.** No ungraded outcome has been converted into a test failure, and none
has been dropped from the denominator. There is no claimed solve in this session, so the instruction to
inspect the patch and grading evidence behind every claimed solve has nothing to act on.

**On the regression check:** `rich_3675` was carried specifically to re-observe the earlier solve. It
was not re-observed. That is an **observed failure to reproduce a previously observed solve by the
unchanged candidate**, which is a reliability finding about run-to-run variance, and it is not the same
thing as S_temp causing a regression. S_temp did not regress relative to S here; neither arm solved
anything.

---

## 4. Answer-key audit

Traces present for **8 of 8**. No hit in any trace on gold or verification patch filenames,
`tasks.jsonl`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `test_patch`, or `/kaggle/input/competitions`. Four runs
referenced repository test files under `tests/`, which is ordinary engineering.

**This does not prove isolation.** The subprocess backend runs `run_command` on the host, so answer-key
files remain reachable, and this audit sees only what the trace recorded. Traces being present and
showing no suspicious match is weaker evidence than a filesystem boundary would be.

---

## 5. Reuse of existing review code

`scripts/review_stage1.py` pins `FROZEN_TASK = "rich_3278"`, `FROZEN_CANDIDATE = "R"` and a one-entry
`FROZEN_ORDER`, and additionally asserts `manifest tasks == ['rich_3278']` and
`controls_present == {(rich_3278, baseline), (rich_3278, reference)}`. Against this eight-row
two-candidate set it aborts on experiment identity. **It was not run, not modified and not weakened**;
the file is unchanged in the working tree. Identity here was verified by the direct hash and byte
comparisons in section 1, and the trace diagnostics came from the same read-only summarizer used for
the A/S review, pointed at the new directory. Nothing was generalized.

---

## 6. Correction to my earlier seed claim

I previously wrote that the earlier runs "were never seeded inference". **That overstated the
evidence.** What `check_temperature_transport.py` demonstrated is narrower: in a local interception of
the inspected google-adk non-streaming path, the compiled config carried `seed: 42` while the captured
LiteLLM client kwargs did not, and the installed `lite_llm.py` generation mapping lists temperature,
top_p, top_k and penalties without seed. That is one local code path under locally installed versions.
It does **not** establish the historical runs' complete wire requests, nor the host server's defaults,
and it must not be stated as proof that those runs were unseeded. `pilot_manifest.json` for this
session still records `seed_in_sampling: 42`, which is the configured value, not an observation of
inference behaviour.

A consequence worth keeping: because seeding is unestablished either way, the large S-to-S behavioural
difference between sessions is **compatible with** ordinary sampling variance, and the "fixed seed plus
near-greedy decode gives a decoding fixed point" story from my earlier diagnosis is not supported by
this session. Higher temperature was predicted to break identical-call loops; measured, it coincided
with **more** of them (148 against 56). That weakens the sampling hypothesis. It does not identify the
real mechanism.

---

## 7. Evidence limitations

- Four selected Textualize/rich development tasks. **No population or leaderboard extrapolation is
  justified**, and none is offered. The hidden set is roughly 67 fastapi, 48 rich, 13 requests, 1 httpx
  by the training mix; three previous submissions each scored 0.06.
- Zero graded rows this session, so the comparison carries **no task-performance signal at all**, only
  reliability and diagnostic signal.
- Two variables differ between this session and the A/S session (sampling variation and
  adk-submission 0.2.11 → 0.2.12), so the lost `rich_3675` solve cannot be attributed to either.
- One shared model server and alternating order reduce but do not eliminate ordering effects.
- Budgets here (10 min, 100 calls, 60 turns) are the comparison's, not an unrestricted competition
  submission's. A real submission ships no such turn cap unless `eval_config.yaml` sets one.
- The subprocess backend is not a filesystem isolation boundary and this is not private-grader
  equivalence.
- `thinking_budget` is not forwarded to the server; only `enable_thinking` is.

---

## 8. Decision against the predeclared criteria, and one recommended next action

The plan's criterion was: **more verified solves with no observed solve regression would support broader
evaluation**, and explicitly, reduced repetition alone would not count. Measured: **S_temp produced
zero verified solves, and its repetition increased rather than fell.** The criterion is not met in
either clause.

**Do not advance S_temp. Do not submit. Keep candidate S as the current best, noting its solve is one
observation that has now failed to reproduce once.** Temperature 0.7 is not supported by this evidence
and should not be carried forward as an improvement.

**Recommended next action, one only, and it is evaluation work rather than a submission change:**

Target the largest observed failure, which is no longer repetition but **failure to reach an edit at
all: 7 of 8 runs this session never attempted one, and 0 of 8 produced an accepted modifying
operation.** The single highest-value change is a `prompts/system.md` edit that puts a hard turn
discipline on the investigation phase, for example requiring that an edit be attempted by a stated turn
number and that the agent commit to its best available fix rather than continue probing, with
`run_command` plus a heredoc named as an acceptable way to apply a change since the working-tree diff
is graded either way. One variable, prompts only, fully inside the declarative-only submission rules.

Second priority, not to be bundled into the same experiment: the `edit_file` argument malformation has
now reproduced in **two independent sessions and at both temperatures** (46 rejected calls in A/S
S/`rich_3278`, 21 here in S_temp/`rich_3278`, same missing `old_string` signature). That is the most
reproducible defect in hand and is separately addressable, also by prompt, by directing shell-applied
edits for content containing quotes or backslashes.

**Both are prompt changes requiring a GPU session to measure, and neither is prepared or launched
here.** Running either needs your explicit authorization, a quota reading, an armed freeze and a single
push, per the standing constraints. Before any further submission the user wants evidence of improved
solves, and this session produced none.

---

## 9. Report paths

| what | path |
|---|---|
| raw artifacts, unmodified | `reference/temperature_run_2026-10-01/` |
| SHA-256 manifest, recorded before analysis, 65 files | `reference/temperature_review/raw_sha256.json` |
| this report | `reference/temperature_review/TEMPERATURE_REPORT.md` |
| prior A/S diagnosis this builds on | `reference/ab_s_review/ungraded_diagnosis/UNGRADED_DIAGNOSIS.md` |
| experiment plan and launch state | `experiments/temperature_v1/` |
