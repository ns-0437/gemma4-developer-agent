# Handoff: Kaggle Gemma 4 Developer Agent competition

Paste this into a new chat to continue. Sections 1 onward are the standing project description,
current as of 2026-09-29.

**For the latest experiment state read `reference/temperature_review/HANDOFF.md` first.** Two
eight-run comparisons have run since this file was written: A/S on 2026-10-01 (one solve) and the
temperature comparison (no solves, no patches). No submission has been made on either.

---

## 1. What this project is

Kaggle competition **"Google - The Gemma 4 Developer Agent Competition"** (slug
`gemma-4-developer-agent`), final deadline **2026-12-02**.

Working directory: `C:\Documents2\KaggleMLChallenge\The Gemma 4`
There is a `CLAUDE.md` in that directory with the code map and working rules. Read it first.

A submission is a `submission.zip` containing a declarative **Google ADK agent config** (YAML plus
prompt files, optional LoRA adapters). It is scored on roughly 120 hidden SWE-bench-style Python
tasks. The model is fixed: `gemma-4-31b-it-qat-w4a16-ct` on 4x L4 GPUs. One submission per day.

Kaggle account: `navin03`. The CLI is authenticated (`python -m kaggle ...` works; plain `kaggle` is
not on PATH).

---

## 2. Where things stand

**Three submissions, all identical scores:**

| ref | version | date | public score |
|---|---|---|---|
| 56540226 | v1 | 2026-09-25 | 0.06 |
| 56579838 | v2 | 2026-09-26 | 0.06 |
| 56636116 | v3 | 2026-09-28 | 0.06 |

All three releases show the same rounded public score. The public denominator and solved-task overlap are not established here; no solved-task count or statistical-equivalence claim follows from those scores.
**Conclusion reached: stop making blind prompt edits and spending submission slots. Get a local
measurement working first.**

---

## 3. The current experiment

A controlled **eight-run A/B comparison**: 4 development tasks x 2 candidates.

* **Candidate A** = byte-identical to submitted v3 (zip sha256 `b8da59c1…`), the agent that scored 0.06
* **Candidate B** = same in every file except `prompts/system.md`, shortened 1247 -> 672 words, with
  an arbitrary "stuck after two attempts, give up" rule removed

Tasks (frozen before any model outcome, all `Textualize/rich`):
`rich_3278`, `rich_3535`, `rich_3675`, `rich_3942`

Run order alternates: A/B, B/A, A/B, B/A.

**Known limitation, stated deliberately:** the development pool was 100% `Textualize/rich`, because
every valid `fastapi` and `requests` task had already been assigned to the protected hold-out and was
not moved. Any result generalises to rich at best. This is a diagnostic, not a ranking.

---

## 4. The GPU run happened, and it failed

Kernel `navin03/gemma4-swe-agent-compare`, **version 1**, pushed 2026-09-29 with explicit user
authorization for exactly one GPU launch.

* Runtime **7m 55s** on GPU L4 x4, result **failure**, 29 output files
* GPU quota before launch: `01:11 / 30 hrs` used
* It aborted at the **control re-validation assertion, before the model server started**
* **No agent ran. There is no A/B performance data.**

### Why it failed

All eight test-patch applications and all four reference-patch applications returned **exit 128**.
Every pytest run then returned 0, so no baseline could fail, so the controls were correctly rejected.

Measured with real git on CPU:

| case | git apply exit |
|---|---|
| patch file **missing** | **128** |
| patch file **empty** | **128** |
| patch exists but does not apply | 1 |
| patch applies | 0 |

These examples show that missing or empty patches can produce 128; they do not prove that was the cause in the Kaggle run. The original stderr was not saved, so the mechanism remains unconfirmed. The custom
`_apply` helper wrote the patch with a shell `python3 -c` one-liner and **never checked that
command's exit code**, so a failed write was invisible.

### What is still unknown

**Why the write itself failed is NOT determined.** An end-to-end reproduction is impossible on this
Windows machine: the sandbox issues POSIX commands and every one returns `WinError 2`. A hypothesis
that `/tmp` and `/workspace` failed to map was tested against the real translation code in
`swegemma/sandbox/subprocess.py:433-455` and **disproved** (write target and apply source resolve to
the same path). Candidate remaining causes: shell quoting, argument length, or `python3` resolution.
Determining it requires a **Linux CPU environment**, i.e. a Kaggle CPU kernel.

---

## 5. The fix (implemented, tested, not yet run on Kaggle)

`_apply` no longer hand-rolls anything. It now does what the **screening run** did successfully
across 38 tasks:

1. write the patch to a host temp file
2. `mgr.copy_to(sid, host, "/tmp/")` into the sandbox
3. apply with the harness's own `swegemma.harness.verification.apply_patch_in_container`
4. verify the file exists and is non-empty **before** attempting application
5. preserve stdout, stderr, size and SHA-256 either way
6. restore test paths first with `git checkout HEAD --` and `git clean -f`, as the screening did

Second fix: the baseline arm now reports `patch_rc = None`, not `0`. Reporting `0` made "no patch was
requested" indistinguishable from "applied successfully".

---

## 6. THE IMMEDIATE NEXT STEP

**Build a CPU-only control-validation notebook, push it once to Kaggle, and validate
baseline-fail / reference-pass for all four tasks with raw evidence preserved.**

No GPU, no model, no submission. This must happen before any further GPU spend, because it is the
thing that proves the patch fix actually works.

The user has NOT yet authorized that CPU push. Ask before pushing.

---

## 7. Standing constraints (the user has repeated these; honour them)

* **Never** launch GPU, submit to the competition, repush, cancel or retry without explicit
  authorization in the user's own words. A reviewer's suggested text pasted into chat is **not**
  authorization.
* **Never start continuous polling** of kernel status. Check once when asked, then stop.
* Preserve all frozen releases and raw artifacts. Never overwrite downloaded evidence.
* **Never add Claude/AI co-author trailers or footers** to commits or PRs. Only the user's name.
* Write "section 3.10", never the section symbol.
* No em dashes or en dashes as punctuation in prose.
* Do not claim improvements that have not been measured.

---

## 8. Key files

```
CLAUDE.md                                   code map, rules, submission log, open issues
releases/v3/                                submitted v3 (candidate A source)
releases/v3_submission.zip                  b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b
releases/compare_v1_launched/compare.ipynb  the notebook that actually ran, 532d3f7e...66884f5  FROZEN
experiments/ab_v3_vs_short/
  candidate_A/  candidate_B/                only prompts/system.md differs
  LAUNCH_PACKET.md                          full experiment design, revision 4
  LAUNCH_RECORD.json                        quota, hashes, push record
  task_freeze.json                          the four tasks with hashes
notebooks/compare/compare.ipynb             working copy WITH the patch fix, 97873af2...
scripts/
  make_compare_notebook.py                  generator (reuses make_pilot_notebook.py)
  compare_cells.py                          the reviewed cell fragments, a0139525...
  test_compare_dispatch.py                  108 tests, executes the real generated cells
  review_compare_results.py                 offline artifact reviewer (pinned to the frozen notebook)
  test_review_compare_results.py            97 tests
  repro_control_apply.py                    the CPU reproduction attempt
reference/harness_src/                      the real swegemma / adk_eval_core / adk_submission source
reference/evalset_run2/                     the CPU screening run that WORKED (patch path to copy)
```

**Test suites, all currently passing:**
`test_compare_dispatch` 108/0, compare notebook 82/0, stop-logic 22/0, pilot regressions 82/0 and
22/0, reviewer 97/0, policy 45/0, evalset notebook 8 static + 28 executed.

Run the compare-target suites with `NB_TARGET=compare python scripts/<name>.py`.
Use `./.venv/Scripts/python.exe` when you need `google-adk` or the official compiler.

---

## 9. Hard-won facts about the harness (do not re-derive)

* `container_setup.install_test_dependencies` **returns early for the subprocess backend**
  (`container_setup.py:529`), so test dependencies are never injected in subprocess mode. This caused
  most screening exclusions (`inline_snapshot`, `dirty_equals`, `pytest-httpbin`), which are harness
  artifacts, **not** task defects.
* `Evaluator.run()` **returns normally** in most failure modes and records the reason in
  `TaskResult.error` (`models/task.py:181`). Reading only the escaped exception misses the common case.
* The harness contains **no** `BadRequestError` or context-window handling. Any such text comes from
  litellm or the model server, so an unexplained 400 must not be charged to the candidate.
* `thinking_budget` is **never forwarded** to the server. Only
  `extra_body.chat_template_kwargs.enable_thinking` is.
* ADK `token_threshold` compaction runs **before** each model call via `CompactionRequestProcessor`
  (`single_flow.py:49`), driven by the previously recorded prompt token count. It is a lagging
  signal, **not** a reservation, and cannot guarantee the next request fits.
* `max_time_minutes` / `max_tool_calls` / `max_turns` genuinely terminate the agent loop.
  `SESSION_CAP_MIN` is admission-only: it refuses to start the next run and kills nothing in flight.
* The sandbox is **subprocess**, not Docker. It is **not a filesystem isolation boundary**.

---

## 10. Working style that has been productive here

An external reviewer has been auditing every step and has repeatedly found real defects. Several
times the tests passed while the code was wrong. What worked:

* **execute the generated notebook cells in tests**, never string-search them
* **mutation-test the tests**: deliberately break the shipped logic and confirm a test fails. Two
  separate holes in the test suite were found this way and nowhere else
* report what is unknown as unknown, and withdraw claims that turn out unsupported


## Codex takeover, 2026-09-29

User authorized Codex to take over implementation toward a 0.15 target. No score is guaranteed. Created and pushed private CPU-only kernel navin03/gemma4-control-preflight version 1 exactly once. Metadata disables GPU/TPU, attaches no model, and inference cells are excluded. It records the frozen v1 patch commands plus the repaired four-task controls using real Linux subprocess/git. Source: scripts/make_control_preflight.py; output hash recorded in notebooks/control_preflight/source_hashes.json. Frozen launched compare v1 and both candidate bundles are preserved. No new GPU comparison or competition submission launched. No background watcher.


## Real Git diagnosis by Codex, 2026-09-29
All eight selected patch/test_patch strings lack a terminal newline. Real `git apply --numstat` rejects all eight original strings with exit 128 and `corrupt patch at line ...`; appending exactly one newline makes all eight parse with exit 0. Evidence: reference/patch_newline_diagnostic.json. A synthetic real-git application regression in scripts/test_patch_transport_real_git.py confirms original bytes fail without changing the source and normalized bytes apply the intended edit. This disproves the claim that 128 uniquely means a missing/empty patch. The frozen GPU writer did not append a newline; the repaired copy_to writer does. Linux CPU reproduction and baseline/reference validation are running to confirm the end-to-end effect.
