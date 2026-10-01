# Launch packet, revision 4: eight-run A/B prompt-package comparison

Revised 2026-09-29 after a third review. **Nothing pushed, dispatched or submitted.** No GPU quota spent, no
watcher, no v4. `DISPATCH_CONFIRM = False` in the artifact as written.

Candidates were not redesigned and no held-out task was moved.

---

## 0. Corrections to revision 1

Four claims in the first packet were wrong or overstated. Each is corrected here and in the notebook
itself, not just in prose.

| revision 1 said | correct |
|---|---|
| implied a container/Docker execution model | **The backend is `subprocess` in both preconditions and evaluation**, all three `EvalConfig` sites. The notebook prints this before dispatch. The subprocess backend is not a filesystem isolation boundary. |
| "agent-side import provenance: UNAVAILABLE" without qualification | The *historical CPU controls* lack an agent phase, so no agent-side path was recorded for them. **The live per-run setup still probes both the agent and grading import views** in the actual sandbox, and the precondition cell does the same for every task before the server starts. The gap is in the saved evidence, not in the run. |
| "answer-key isolation is structural, stronger than filtering" | Prompt invariance under a sentinel substitution establishes that **the prompt** does not carry the answer keys. It establishes **nothing about filesystem access**, and under a subprocess backend there is no filesystem isolation boundary at all. |
| "four tasks cannot rank two prompts" (correct but under-stated) | Four tasks **from one repository** are a narrow diagnostic. Any result generalises to `Textualize/rich` at best. The report cell now says this in its own closing text. |

---

## 0b. Corrections to revision 2

| revision 2 said | correct |
|---|---|
| control acceptance was sound | **It could pass on missing evidence.** A missing report, an all-skipped reference arm, and a reference arm where only an unrelated test passed all returned `True`. Fixed and tested; see section 7. |
| `token_threshold` is "post-invocation only" | **Wrong.** `CompactionRequestProcessor` runs before contents are prepared for each model call (`single_flow.py:49`). It is driven by previously recorded token usage and is not a reservation; see section 6. |
| error classification was correct | **Two wrong verdicts**, both reproduced by the reviewer: a wrapped context error became an environment failure, and a persisted environment failure was hidden by an escaped candidate error. Fixed; see section 3. |
| control evidence written at the end | Now written **per arm, immediately**, so a later failure cannot erase completed arms. |
| "any single-task difference is within noise" | Removed. Results will be reported as observed paired outcomes, with no generalisation claim. |

---

## 0c. Correction to revision 3

| revision 3 said | correct |
|---|---|
| control arms recorded `teardown_error` | **They recorded it and then ignored it.** An arm whose `sandbox_stop` raised was still accepted if its test results looked right. Worse, the leaked sandbox would be snapshotted as *pre-existing* by the dispatch loop's own cleanup check, so nothing downstream would ever catch it. Fixed, gated and tested; see section 7b. |
| teardown returning implied teardown happened | It does not. Each arm now verifies its **own** sandboxes are gone, with a bounded grace period. |

While writing the test for this, the same unguarded teardown turned up in the **precondition probe**
(`_precondition` called `sandbox_stop` bare in a `finally`). A leak there has the identical
consequence, so it is now gated the same way. That was not in the review; it was found by the test.

---

## 1. Task selection, and the coverage problem

The dev-eligible pool is **entirely `Textualize/rich`**: 20 valid tasks minus 12 protected hold-out
leaves 8, and every valid `fastapi` and `requests` task sits in the hold-out.

| pool | rich | fastapi | requests |
|---|---|---|---|
| dev-eligible (8) | 8 | 0 | 0 |
| protected hold-out (12) | 5 | 5 | 2 |

No held-out task was moved. Adding coverage needs new screening, which is proposed and not executed.

**The four selected tasks**, frozen in `task_freeze.json`
(`76804a27cc2bbc5e73e84d9ee5fa5a6c4e6c78e5a536648fa6f0c21b0ccdce93`) before any model outcome exists:

| task | patch | targets | baseline | reference | task_sha256 |
|---|---|---|---|---|---|
| rich_3278 | 1 line, `ansi.py` | 16 | exit 1, 16 failed / 7 passed | exit 0, 23 passed | `8fb8127fdb3e069ae02db8a0e3d2e5306b96e7d42a1ab7c3185da2e269cd61bf` |
| rich_3535 | 8 lines, `cells.py`+`segment.py` | 1 | exit 1, 1 failed / 7 passed | exit 0, 8 passed | `3c70ac67cc8e78d329459615dd6db711e2715b92f6da4632cc4905f1faf0ad18` |
| rich_3675 | 41 lines, `console.py`+`diagnose.py` | 1 | exit 1, 1 failed / 98 passed | exit 0, 99 passed | `d651989d2710c16333584401276a29f5c36026b5fff3407204f53d550f3176fb` |
| rich_3942 | 70 lines, `default_styles.py`+`markdown.py` | 6 | exit 1, 6 failed / 2 passed | exit 0, 8 passed | `b626009683a3a55af3ad72e8a4cc9cd629cb24444a2c404c073a87778b8148b8` |

All four: `patch_rc = 0`, `test_patch_rc = 0`, `import_in_checkout = true`, zero errored nodes,
failed-set strictly inside the reference passed-set, and a first baseline failure that matches the
issue title (checked per task, not assumed).

---

## 2. The candidates

Only `prompts/system.md` differs. Diff: `system_md.diff`
(`348ba590679e1867a46b215c6a4f6dcc4b4ba57ed7c2cdf1c8a6c91f4d3f2e72`).

| | A (= submitted v3) | B (short) |
|---|---|---|
| `agent.yaml` | `8e890bec4c5e146402c6ef9ee22eb40388207ad8416cfd3405e040aa038ffb83` | identical |
| `configs/sampling.yaml` | `78eb4bf20538c713e6208d89743728dc70701c8e4ac2f2de91ad2bdb5d432c95` | identical |
| `prompts/analyzer.md` | `5011d37145d981e616d58fb56c5191ccbf336574fa01b3f65c2feab7d697b3a3` | identical |
| `sub_agents/code_analyzer.yaml` | `396b75ffd1315ef93f3d1806b814a49758b9f8dd8b8caef6a092bd6cb2c2d9bb` | identical |
| `prompts/system.md` | `4d42f2b7d48143cd06c31fe4c33b17a3f78da21ec2c53d9569cf6a336f6e5e79` | `f8bb0d4e32853bae6aa38c1a2278c39b4f6ed133bafd323495b74077c84ee5b1` |
| **bundle zip** | **`b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b`** | `33a5ec57db0dd482fd4f807206f2cbda45cdc5f14a28c836c88417305c6e3909` |

A's bundle hash equals the submitted v3 archive, so candidate A is the 0.06 agent bit for bit.

B: 1247 -> 672 words (compiled coder instruction 7729 -> 4246 chars). Removed the two-attempt
surrender rule as instructed, plus four redundant passages. Retained: issue-driven implementation,
`/tmp` heredoc scratch files, checkout-import verification, the never-edit-a-test-expectation rule,
exit-code-preserving verification, individual test-path restore, `submit_patch` last. Written without
reading any selected task's reference patch or verification tests.

Official compiler on both: `OFFICIAL COMPILE OK`, same model, tools, analyzer (1384 chars both) and
generation config; the coder instruction length is the only compiled difference. The notebook asserts
`sampling.yaml` is byte-identical and that `system.md` is the only file that differs, and aborts if
the two system prompts are ever equal.

---

## 3. Dispatch decisions now consume both error sources

The previous dispatch cell read only the **escaped exception**. `Evaluator.run()` returns an
`EvaluationResult` **normally** in most failure modes and records the reason in `TaskResult.error`
(`models/task.py:181`), persisted to `results_dir/task_results.jsonl`. The common case was therefore
invisible. The cell now reads both.

The persisted error vocabulary was taken from the installed harness source, not guessed:

| persisted error | class |
|---|---|
| `Agent exceeded session timeout (N min)` | candidate (budget) |
| `Failed to apply agent patch: ...` | candidate |
| `Failed to apply test_patch: ...` | environment |
| `Missing JUnit XML report (possible premature os._exit(0))` | unobserved grading |
| `Pytest stdout summary indicates zero or no passing tests` | **a result**, not a failure |
| `Sandbox execution error: ...` | environment |
| `Evaluation error: ...`, `Unexpected evaluation worker error: ...` | wrapper, cause inspected |

**On `BadRequestError`:** grep over the installed harness finds **no** `BadRequestError` or
context-window handling anywhere in swegemma, so any such text originates in litellm or the model
server. A 400 is charged to the candidate only when its cause is identifiable as the request the
agent produced (context window, prompt length, malformed content). A 400 with no identified cause is
classified as **environment**, because treating it as a candidate result would let a broken server be
recorded as a candidate's score.

**Precedence, corrected in revision 3.** Revision 2 returned on the first source that matched a
marker, which produced two wrong verdicts that a reviewer reproduced:

| case | revision 2 | revision 3 |
|---|---|---|
| context-window error wrapped in `Unexpected evaluation worker error: ...` | environment (the wrapper matched first) | **candidate** (the cause inside the wrapper is examined first) |
| escaped context-window error **plus** a persisted sandbox failure | candidate (the second source was never read) | **environment** (a genuine environment failure is not hidden) |

`_classify_one` now checks result markers, then unobserved markers, then **candidate causes**, then
specific environment causes, then an unattributed BadRequest, and only then the generic wrappers
(`Unexpected evaluation worker error`, `Sandbox execution error`, `Evaluation error`), which carry the
real cause inside them. `classify_outcome` classifies **both** sources before deciding and combines
them worst-first: `environment > unobserved_grading > candidate > ok`. The recorded reason names
every source, so a combined verdict can be audited.

Four outcomes are distinguished, not two: `candidate`, `environment`, `unobserved_grading`, `ok`,
with `provenance` tracked separately and taking precedence in the report's `failure_class`. Grading
that never started is reported as an absence of observation, not as a provenance failure.

---

## 4. Cleanup verification is now a gate

Previously the cell globbed every `/tmp/swegemma_sandbox_*` on the machine and **printed** the count.
It now snapshots the sandbox set immediately before each run, and after the run counts only
directories **that run created**. It waits a bounded `CLEANUP_GRACE_S` for teardown, and if any
run-owned sandbox remains, dispatch **stops before the next candidate** with a recorded stop reason.
A pre-existing unrelated sandbox cannot be attributed to the run, and cannot mask a real leak. Both
directions are tested ([D5], [D5b]).

---

## 5. The report covers all eight planned runs

Rows are built from `ORDER`, not from `RUNS`. Each planned `(task, candidate)` pair appears **exactly
once**. A run that never happened becomes an `attempted: false` row with `attribution:
not_attempted` and the recorded `stop_reason`; its outcome fields stay `unavailable` rather than being
filled with a plausible value. The cell asserts no duplicate run records, no run outside `ORDER`, no
duplicate `ORDER` entries, and that every row matches a fixed `ROW_KEYS` schema. Partial artifacts
(`runs.json`, per-run directories) are preserved on every stop path.

---

## 6. Context headroom, corrected

The revision-2 claim that `token_threshold` is "post-invocation only" was **wrong**. Read from the
installed ADK 1.36.1 execution path:

```
flows/llm_flows/single_flow.py:49   wires compaction.request_processor into the processor chain
flows/llm_flows/compaction.py       CompactionRequestProcessor.run_async
                                    "Compacts session events before contents are prepared for
                                     model calls"                      -> runs PRE-model-call
apps/compaction.py:425              _run_compaction_for_token_threshold_config
apps/compaction.py:474              _run_compaction_for_token_threshold  (post-invocation helper)
runners.py:603                      sliding-window path
```

So token-threshold compaction runs **before** each model call through the request processor, and a
post-invocation path exists as well.

**What drives it:** `_latest_prompt_token_count(session.events)`, the most recently **recorded**
prompt token count from an earlier response's usage metadata. If that is `None` or below the
threshold, nothing is compacted (`apps/compaction.py:443-449`).

**What that means.** The threshold is a **lagging signal derived from prior usage**, not a hard
reservation of input or output space. Tool output produced since the last measurement is not counted,
so a request can still exceed the window while the threshold is respected. Lowering the threshold
widens the margin; **it cannot guarantee the next request fits**, and the revision-2 phrasing that
implied otherwise is withdrawn.

`20480` sits below `max_model_len - max_output_tokens` (32768 - 8192 = 24576), leaving room for the
retained raw events and for growth before the next measurement. That is the whole of the claim.

**This remains an evaluation setting, applied identically to A and B, and it differs from the
submitted configuration.** `EvalConfig.events_compaction_config` defaults to `None` and
`agent_runner` forwards it only when set, so grading applies no compaction unless the graders
configure one. Neither candidate's artifact is touched.

## 7. Control re-validation, and the acceptance bug that was in revision 2

Equivalence between the screening environment and this one cannot be established in advance, so the
notebook re-runs all four controls, both arms, in fresh sandboxes using the same patched setup path,
on CPU before the model server starts. It re-issues the exact `pytest` command the screen recorded.

**Revision 2's acceptance logic could pass on missing evidence.** `nodes = got.get("nodes") or {}`
collapsed a missing report into an empty dict, and acceptance then compared only *failed* node sets.
For a reference arm, whose expected failure set is empty, three broken cases all returned `True`:
a missing JUnit report, every test skipped, and only an unrelated test passing. Comparing failure
sets also never proved that the tests failing at baseline actually **passed** in the reference arm.

Fixed. `_nodes_from_junit` now returns `(nodes, duplicates, parse_error)` and returns `nodes = None`
for a report that is absent, unparseable, empty, or contains no `testcase` elements. `None` stays
distinct from `{}` the whole way through. Acceptance requires **all** of:

* a usable report, with a non-empty set of collected nodes;
* the **complete expected node/outcome map** to match, with `missing`, `extra`, `changed` and
  `skipped` reported explicitly rather than summarised;
* every saved **target node** to be `failed` in the baseline arm and `passed` in the reference arm;
* **no duplicate node identities** (previously the later entry silently overwrote the earlier one);
* matching pytest exit code, `patch_rc == 0`, `test_patch_rc == 0`, and no errored nodes;
* no exception during the arm.

**Evidence is persisted per arm, immediately.** Each arm writes
`control_evidence/<task>__<arm>.json` plus the raw `.junit.xml` as soon as it completes, before the
next arm starts, so a later arm or a teardown failure cannot erase earlier results. Records carry
raw XML, truncated stdout and stderr, setup and patch return codes, package versions, and exception
and traceback text. When no report is readable the cell writes a `NO_JUNIT.txt` marker. **It never
synthesises XML.**

## 7b. Control sandbox cleanup

Three things changed.

**The gate.** An arm is rejected if `teardown_error` is set **or** if `cleanup_ok` is not `True`.
Revision 3 recorded the first and checked neither.

**Real verification, not a return value.** `sandbox_set()` is snapshotted immediately before the arm
creates anything; after teardown the arm re-checks and counts only directories it created, waiting up
to `CLEANUP_GRACE_S`. A sandbox that existed beforehand is never attributed to the arm, and **nothing
is ever deleted** — a leak is reported, not tidied away, and an unrelated sandbox is never touched.

**Stop before contamination spreads.** Evidence for the arm is written first, then
`CONTROL_STOP_REASON` is set and both loops break, so no further control arm runs and the model is
never started. A separate assertion requires all `2 x len(SELECTED)` arms to have run, so a partial
sequence cannot be mistaken for a clean one.

The helpers moved from the RUN cell into COMMON. They previously lived in the dispatch cell, which
executes *after* the controls, so the controls had no way to check their own teardown at all. Both
the controls and the dispatch loop now use one implementation.

## 8. Notebook and executed-test results

`notebooks/compare/compare.ipynb`, sha256
**`216f7d8c8a40323af1da60b752b6d5c6c6586a73c2347364aee8a783b66884f5`**, 13 cells, byte-identical
across repeated regeneration. `DISPATCH_CONFIRM = False`, `token_threshold = 20480`.
Candidate hashes unchanged: A `b8da59c1…`, B `33a5ec57…`.

| suite | target | result |
|---|---|---|
| `test_compare_dispatch.py` | compare | **94 passed, 0 failed** |
| `test_pilot_notebook.py` | compare | **82 passed, 0 failed** |
| `test_stop_logic.py` | compare | **21 passed, 0 failed** |
| `test_pilot_notebook.py` | pilot (regression) | **82 passed, 0 failed** |
| `test_stop_logic.py` | pilot (regression) | **22 passed, 0 failed** |
| `test_evalset_policy.py` | policy | 45 passed, 0 failed |
| `test_evalset_notebook.py` | evalset | 8 static + 28 executed, 0 failed |

All of these drive the **actual generated cells**.

New in revision 4, all executing cells 0..10 so that "the model never started" is a real assertion
rather than a consequence of not running the server cell:

| id | fixture | required behaviour |
|---|---|---|
| C10 | control `sandbox_stop` raises | arm rejected, evidence persisted, no further arms, server count 0 |
| C10b | teardown removes the sandbox and *then* fails | rejected on `teardown_error` alone, with `cleanup_ok` true |
| C11 | `sandbox_stop` returns but leaves the arm's sandbox | rejected, the leaked path named, no further arms |
| C12 | an unrelated pre-existing sandbox | controls accepted, all eight arms run, stranger never deleted or blamed |
| C13 | the precondition probe's own teardown fails | rejected as an assertion, not a raw exception; server count 0 |

Revision 3: C1 missing report, C2 malformed XML, C3 empty and zero-testcase, C4 all-skipped
reference, C5 unrelated-test-only, C6 missing target, C7 duplicate identities, C8 evidence survives a
later failure, C9 target absent from the saved map, E1 wrapped context error, E2 environment not
hidden by candidate. Revision 2: D1-D8.

**Mutation check.** The shipped logic was broken ten ways and the suite re-run:

| mutation | caught |
|---|---|
| any `BadRequestError` -> candidate | 3 failures |
| read only the escaped exception | 14 failures |
| `confirm_cleanup` always reports clean | 4 failures |
| missing report accepted | 4 failures |
| duplicate node identities ignored | 1 failure |
| classifier returns on the first source again | 2 failures |
| target nodes not verified | 1 failure (needed C9, see below) |
| acceptance ignores `teardown_error` | 1 failure (needed C10b, see below) |
| acceptance ignores `cleanup_ok` | 1 failure |
| a dirty control arm does not stop the next | 2 failures |
| control arm blames pre-existing sandboxes | 4 failures |

**Two mutations initially survived, and both exposed holes in my tests rather than in the code.**

*Targets not verified.* Every degraded report I had written also removed an expected node, so the
full-map comparison rejected it and nothing exercised the target check alone. C9 covers the case
where it is load-bearing: a target the **saved map itself** omits, where observed equals expected
while the target was never verified.

*`teardown_error` ignored.* In my fixture a raising teardown always leaked as well, so `cleanup_ok`
rejected the arm and masked the mutation. C10b covers the realistic case the review actually
described: teardown that **removes the sandbox and then fails**, where `cleanup_ok` is true and only
`teardown_error` can disqualify. A further assertion on the arm's own persisted
`agrees_with_saved` separates the acceptance verdict from the stop-reason gate, which otherwise
overlaps it.

Every mutation was reverted and the notebook regenerated to the hash above.

**Defects caught by executing rather than searching**, across all revisions:

1. `CONTROL_EVIDENCE` substituted with `json.dumps`, putting `true` into Python source: `NameError`.
2. The pilot's isolation assertion required A and B to differ in `sampling.yaml`; here they must not.
3. The control fixture built JUnit XML by string formatting, malformed for `rich_3278`, whose
   parametrised node names contain `<` and `>`. Rebuilt with `ElementTree`.
4. The precondition probe's unguarded teardown (section 0c), found while writing C10.
5. Two holes in my own test suite, found by mutation rather than by reading.

## 9. Run order and limits

```
1. A  rich_3278      5. A  rich_3675
2. B  rich_3278      6. B  rich_3675
3. B  rich_3535      7. B  rich_3942
4. A  rich_3535      8. A  rich_3942
```

Identical for both candidates:

```
max_time_minutes = 10.0     max_tool_calls = 100      max_turns = 60
timeout_seconds  = 300      SESSION_CAP_MIN = 300     RUN_RESERVE_MIN = 25
CLEANUP_GRACE_S  = 45       token_threshold = 20480 (evaluation setting, see section 6)
```

**Actual termination:** `max_time_minutes`, `max_tool_calls`, `max_turns` are enforced inside the
harness agent loop, which raises `Agent exceeded session timeout (N min)`
(`agent_runner.py:585,644,744`). `timeout_seconds` is a real per-command timeout.

**Admission-only:** `SESSION_CAP_MIN` and `RUN_RESERVE_MIN` are checked before starting a new run.
They refuse to begin run N+1 and kill nothing in flight.

**Not a limit at all:** `thinking_budget: 4096` appears in the compiled config but is never forwarded
to the server.

---

## 10. GPU and session estimate

From two weak observations: vLLM startup ~6 min (smoke run, one observation), and pilot v1 wall time
161.7 s = agent 134.7 s + grading 26.9 s (**one run, terminated early on a patch-apply failure**).

| scenario | 8 runs | + startup, install, controls | total |
|---|---|---|---|
| fast (runs resemble the pilot) | ~22 min | ~20 min | **~42 min** |
| budget-bound (every run exhausts 10 min) | ~84 min | ~20 min | **~104 min** |

The control re-validation adds CPU time before the server starts; the four rich suites ran in 0.07 to
1.2 s each during screening, so the cost is dominated by sandbox setup rather than pytest. Per-run
time for this configuration is **unmeasured**, and remaining GPU quota is **unread**.

---

## 11. Unresolved risks

1. **Development coverage is single-repository.** Four `Textualize/rich` tasks. Any result generalises
   to rich at best. The largest threat to the experiment's usefulness, with no fix that does not break
   the hold-out or add screening.
2. **No filesystem isolation.** The backend is `subprocess`; `run_command` executes on the host. Prompt
   invariance under sentinel substitution shows the answer keys are not in the prompt, and nothing more.
3. **The saved controls lack an agent phase**, so the guard over *historical* evidence checks
   grading-side provenance only. Live runs and preconditions probe both views. Section 7's
   re-validation narrows but does not eliminate the gap, since it likewise runs no agent.
4. **Four tasks cannot rank two prompts.** Eight runs can show the experiment produces gradeable
   evidence. Results will be reported as the observed paired outcomes per task, A against B, with no
   claim that they generalise beyond these four `Textualize/rich` tasks and no inference about which
   prompt is better overall.
5. **One shared vLLM process across eight runs.** Alternating order does not control session drift.
6. **Per-run time unmeasured, GPU quota unread.**
7. **Confounded prompt package.** B changes several things at once by design; a difference cannot be
   attributed to one removal.
8. **The compaction threshold now differs from the previous notebook and from grading's default of no
   compaction.** Applied identically to A and B, but it is a deviation, and its effect on agent
   behaviour is unmeasured.
9. **The access-failure cause from the earlier session remains unresolved** (credential expiry versus
   wrong kernel slug); the logs to settle it are not in hand.

---

## 12. Files

```
experiments/ab_v3_vs_short/
  candidate_A/  candidate_B/          only prompts/system.md differs
  system_md.diff    348ba590679e1867a46b215c6a4f6dcc4b4ba57ed7c2cdf1c8a6c91f4d3f2e72
  task_freeze.json  76804a27cc2bbc5e73e84d9ee5fa5a6c4e6c78e5a536648fa6f0c21b0ccdce93
  LAUNCH_PACKET.md  this file
notebooks/compare/
  compare.ipynb     216f7d8c8a40323af1da60b752b6d5c6c6586a73c2347364aee8a783b66884f5
  kernel-metadata.json   navin03/gemma4-swe-agent-compare, private, 4x L4, internet off
scripts/
  make_compare_notebook.py   generator (reuses make_pilot_notebook.py)
  compare_cells.py           the reviewed cell fragments
  test_compare_dispatch.py   the six required fixtures, executing the real cells
```

Frozen releases, run-2 raw artifacts and the recorded hold-out assignment are untouched.

## 13. Still outstanding, deliberately not a prerequisite

The dependency wheel inventory and CPU preflight for the excluded tasks are unchanged from revision 1
and remain **not executed**: the wheel mirror is only visible from a Kaggle kernel, so whether
`inline_snapshot`, `dirty_equals`, `pytest-httpbin` and `hatchling` are present is unverified. The
bounded three-task preflight is specified, including the requirement to check that injected wheels do
not shadow the checkout or change dependency versions before any broad injection. It is not a
prerequisite for this comparison, and no recovered-task count is predicted.
