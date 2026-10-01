# A vs S, eight runs on four Rich development tasks

Checked 2026-10-01T00:31:24Z: kernel `navin03/gemma4-swe-agent-ab-s` status **COMPLETE**. Downloaded to
a fresh directory `reference/ab_s_run_2026-10-01/`, 69 files, SHA-256 manifest in
`reference/ab_s_review/raw_sha256.json` recorded before any analysis. Raw files unmodified. No retry,
no cancellation, no repush, no new run, no candidate edit, no submission.

**A notebook marked COMPLETE does not prove the agent runs succeeded, and here six of eight did not
produce a patch.**

---

## 1. Experiment identity

| | |
|---|---|
| launched notebook on disk | `86d1c83bb203a1000c205d8913df59abcf83f86c584e66eb2ceba1e3e5a5a649` **matches** |
| manifest tasks | `rich_3278, rich_3535, rich_3675, rich_3942` |
| manifest run order | A/S, S/A, A/S, S/A as planned |
| candidate A, recomputed from the downloaded files | `b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b` **matches** |
| candidate S, recomputed | `8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07` **matches** |
| downloaded prompts vs local | A and S both byte-identical |
| environment | 4x NVIDIA L4, swegemma 0.2.7, adk-submission 0.2.11, google-adk 1.36.1, vllm 0.19.1, litellm 1.82.4 |
| session wall clock | 2,898 s (~48 min) |

---

## 2. All eight planned rows

None missing, none aborted. Order as planned.

| # | task | cand | outcome | patch B | grading exit | resolved | tool calls | repeats | loop s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | rich_3278 | A | candidate, turns budget | 0 | -1 | false | 60 | **51** | 169 |
| 2 | rich_3278 | S | candidate, turns budget | 0 | -1 | false | 60 | **42** | 307 |
| 3 | rich_3535 | S | candidate, turns budget | 0 | -1 | false | 60 | **42** | 75 |
| 4 | rich_3535 | A | candidate, turns budget | 0 | -1 | false | 59 | **35** | 584 |
| 5 | rich_3675 | A | ok | 633 | **1** | false | 10 | 0 | 38 |
| 6 | rich_3675 | S | ok | 772 | **0** | **true** | 20 | 0 | 75 |
| 7 | rich_3942 | S | candidate, turns budget | 0 | -1 | false | 57 | 0 | 196 |
| 8 | rich_3942 | A | candidate, turns budget | 0 | -1 | false | 57 | 10 | 156 |

"repeats" counts identical consecutive tool calls. Exit `-1` is the harness sentinel meaning grading
did not run, not a verdict.

### Instrument, per run

- **Controls: all 8 arms re-validated and agree with the saved screen.** Baseline exit 1, reference
  exit 0, on every task. Node counts 23, 8, 99, 8; targets 16, 1, 1, 6. Cleanup confirmed on each arm.
- **Preconditions: `ok=True` for all four tasks.**
- **Provenance:** agent-side verified on all 8 runs. Grading-side observed on the two runs that
  reached grading (`rich_3675` A and S). On the other six the grading path was **unobserved because
  grading never ran**, which is unexercised, not a demonstrated fault.
- **Cleanup: 8 of 8 confirmed.** No leaked sandbox.
- **Environment failures: 0. Provenance failures: 0. Candidate failures: 6** (the six turns-budget
  terminations).

---

## 3. A versus S, all four tasks visible per candidate

| candidate | solved | graded, unsolved | ungraded | not attempted |
|---|---|---|---|---|
| **A** | **0** | 1 (`rich_3675`) | 3 | 0 |
| **S** | **1** (`rich_3675`) | 0 | 3 | 0 |

### Paired per task

| task | A | S | pair |
|---|---|---|---|
| rich_3278 | ungraded | ungraded | **undecided** |
| rich_3535 | ungraded | ungraded | **undecided** |
| **rich_3675** | graded, unsolved | **solved** | **S** |
| rich_3942 | ungraded | ungraded | **undecided** |

**1 decided pair, 3 undecided. An ungraded side makes the pair undecided, not an opponent win.**
Six of eight runs produced no patch at all, so three quarters of the comparison carries no signal.

### Runtime, agent loop seconds

| candidate | 3278 | 3535 | 3675 | 3942 | total | mean |
|---|---|---|---|---|---|---|
| A | 169 | 584 | 38 | 156 | 947 | 237 |
| S | 307 | 75 | 75 | 196 | 652 | 163 |

Both candidates stayed inside the 10-minute per-run budget. The four-task mean is **not** used to
project competition runtime.

---

## 4. The one decided pair, in detail

Both candidates found the same code location, `Console.is_terminal` in `rich/console.py`, and both
produced a syntactically valid source patch that graded. The difference is the fix itself.

**A, graded exit 1, not resolved.** Treats any value of `TTY_COMPATIBLE` as a terminal, and inserts
the check after the `FORCE_COLOR` branch:
`if tty_compatible is not None: self._force_terminal = True; return True`

**S, graded exit 0, resolved.** Distinguishes `"1"` from `"0"`, and inserts the check before
`FORCE_COLOR` so it takes precedence:
`if tty_compatible == "1": ... return True` and `if tty_compatible == "0": ... return False`

S handled the negative case and the precedence order; A handled neither. Both reached grading in a
short, non-repeating run: A used 10 tool calls, S used 20, neither repeated a call.

**S's run followed the prescribed workflow exactly:** localize with `git grep`, read the file, write
and run a reproduction, one `edit_file`, `py_compile`, locate and run the repo's own test file, then
`submit_patch`. That is the behaviour candidate S was written to produce, observed once.

---

## 5. Repetition

The failure mode from Stage 1 persisted and affected **both** candidates. On the three tasks neither
solved, consecutive identical calls ran to 51, 42, 42, 35 and 10. S on `rich_3278` is notable: 46 of
its 60 calls were `edit_file`, with 42 consecutive repeats, so it was looping on edits rather than
probes. `rich_3942` was the cleanest failure for both: 0 and 10 repeats, 47 and 39 distinct calls,
still no patch.

**The concise prompt did not eliminate repetition.** It coincided with a solve on one task.

---

## 6. Answer-key audit

Traces present for **8 of 8** runs, so the audit is available for every row.

No hit on gold or verification patch files, `tasks.jsonl`, or `FAIL_TO_PASS` / `PASS_TO_PASS` in any
run. The "harness internals" pattern matched in five runs, and inspecting every match shows they are
all sandbox paths echoed in ordinary output, for example
`/tmp/swegemma_sandbox_654225a7-d99_jcuz06qg/tmp/repro.py` in a traceback. **That pattern is too broad
and these are benign.** Four runs also read repository test files, which is ordinary engineering.

**Absence of a hit is not proof of isolation.** The subprocess backend runs `run_command` on the host,
so answer-key files remain reachable, and this audit sees only what the trace recorded.

---

## 7. Recommendation

**Do not submit S on this evidence, and do not treat one solve as a measured improvement.**

What is actually established, on four selected Textualize/rich development tasks:

- S produced the project's **first verified solve** of any kind, on `rich_3675`, with a correct fix and
  a clean workflow.
- A produced a graded but incorrect patch on the same task. **That is a real difference on one pair**,
  and it is one pair.
- Three of four pairs are undecided because both sides ran out of turns without a patch. **No
  regression was observed**, since A solved nothing that S did not.
- The instrument is in better shape than before: controls, provenance and cleanup clean on all eight,
  and grading demonstrably works end to end now that two runs reached it.

The binding problem is unchanged and is **not** candidate-specific: **six of eight runs exhausted 60
turns without producing a patch.** Until that falls, most of any comparison is undecided and the
sample cannot grow usefully.

Suggested next step, for your decision rather than my action: investigate the turns-budget failures
themselves on the three unsolved tasks, using the eight traces already in hand, before spending
another GPU session or preparing another candidate. Specifically, whether those runs ever reached an
edit at all, and what they were repeating. That is offline work on existing evidence.

**No leaderboard score is predicted. Four selected Rich tasks say nothing about the hidden set**,
which is roughly 67 fastapi, 48 rich, 13 requests and 1 httpx by the training mix, and the three
previous submissions each scored 0.06.
