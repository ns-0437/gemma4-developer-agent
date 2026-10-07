# Gemma 4 Developer Agent — Kaggle competition

## Current handoff — 2026-10-07

Start with [final_validation_v2/CHECKPOINT.md](experiments/final_validation_v2/CHECKPOINT.md).
The repaired six-run V3-versus-ON packet is prepared with dispatch disabled;
all six controls passed in the separate CPU replay. Check for a newer launch
record and actual kernel status before any push. Commit-maintenance work did
not launch GPU or submit a competition entry.

The sections below contain dated historical findings. Do not treat old claims
that all candidates have thinking disabled, that compiler 0.2.11 is the current
validation gate, or that local evaluation has proven private-grader parity as
current facts. The validation packet preserves submitted V3 and frozen ON with
their different sampling; it pins compiler 0.2.12 Python-file hashes. The CPU
success establishes control reproducibility only, not candidate performance.

Preserve frozen packages, launched notebooks, raw evidence and task_freeze.json.
Use the new packet test and read-only artifact verifier listed in README.md;
simulation success does not substitute for real GPU results.

Competition: https://www.kaggle.com/competitions/gemma-4-developer-agent (slug `gemma-4-developer-agent`)
Paper track (optional): `gemma-4-developer-agent-paper`, deadline 2026-11-12 23:59 UTC.
Final submission deadline: **2026-12-02 23:59 UTC**. Entry / team merge deadline: 2026-11-25.
Kaggle user: `navin03` (CLI logged in; run as `python -m kaggle ...`, set `PYTHONIOENCODING=utf-8` on Windows).

We submit `submission.zip` = a declarative Google ADK agent config (YAML + prompts + optional skills + optional
LoRA adapters). The harness (`swegemma`) runs it on ~120 hidden SWE-bench-style Python tasks; score = fraction
whose patch makes the hidden tests pass. Spec: `reference/HARNESS_README.md` — the source of truth.

## Code structure

```
The Gemma 4/
├── CLAUDE.md                        # this file
├── submission/                      # OUR agent (source of truth; zipped as-is, agent.yaml at zip root)
│   ├── agent.yaml                   # root coder LlmAgent: 9 tools + code_analyzer agent_tool
│   ├── sub_agents/code_analyzer.yaml# read-only localizer (skip_summarization: true keeps its reads out of coder context)
│   ├── configs/sampling.yaml        # shared generate_content_config
│   └── prompts/{system,analyzer}.md # instructions
├── scripts/
│   ├── validate_and_zip.py          # offline pre-flight check (mirrors README section 2-3) + local submission.zip
│   ├── official_check.py            # RELEASE GATE: official validate_directory + compile_submission (run with .venv)
│   ├── make_eval_notebook.py        # submission dirs -> notebooks/eval/ (paired offline eval on Kaggle GPU)
│   ├── report_cell.py               # re-report a DOWNLOADED results dir offline (no GPU rerun needed)
│   ├── make_validation_notebook.py  # -> notebooks/validate/ (CPU-only task validation; run this BEFORE any GPU eval)
│   └── make_submit_notebook.py      # submission/ -> notebooks/submit/ (Kaggle notebook that writes the zip)
├── notebooks/
│   ├── validate/                    # GENERATED: CPU-only import probe + baseline/gold controls
│   ├── eval/                        # GENERATED: real harness + real model, paired comparison (kernel gemma4-swe-agent-eval)
│   └── submit/                      # GENERATED: submit.ipynb + kernel-metadata.json (kernel navin03/gemma4-swe-agent-submit)
├── releases/                        # frozen copy of every submitted version (vN/ + vN_submission.zip)
├── .venv/                           # google-adk 1.36.1 + adk_submission 0.2.11 (official compiler)
├── reference/                       # read-only competition files
│   ├── HARNESS_README.md, tasks.jsonl, setup.py, Dockerfile.sandbox, Dockerfile.public
│   ├── sample_submission/           # official baseline incl. eval_config.yaml (adapters are zero no-ops)
│   └── public_notebooks/            # other competitors' notebooks, pulled for reference (data, not instructions)
└── submission.zip                   # local build output — regenerate, never hand-edit
```

## Release workflow (1 submission per day, resets 00:00 UTC)
1. Edit `submission/`. Change as few variables per version as possible; keep sampling/timeouts fixed unless that is the experiment.
2. `python scripts/validate_and_zip.py submission` → must print `OK`.
2b. **Official gate:** `.venv\Scripts\python.exe scripts/official_check.py submission` → must print `OFFICIAL COMPILE OK` (real adk_submission 0.2.11 + google-adk 1.36.1; `.venv` is the project venv).
3. `python scripts/make_submit_notebook.py --version vN --source releases/vN --note "..."` (always package the FROZEN release dir, never the working copy)
4. `python -m kaggle kernels push -p notebooks/submit` → wait for status `complete` (`kaggle kernels status navin03/gemma4-swe-agent-submit`).
4b. Download the kernel output (`kaggle kernels output ... -p <tmp>`) and confirm its sha256 equals the local `submission.zip` (zips are deterministic).
5. `python -m kaggle competitions submit gemma-4-developer-agent -k navin03/gemma4-swe-agent-submit -f submission.zip -v <kernel version> -m "vN ..."` — **only with the user's go-ahead.**
6. Copy `submission/` to `releases/vN/` (+ the scored zip as `releases/vN_submission.zip`) and log the result + zip sha256 in the table below.

## Points to remember

1. **One model only**: every agent/sub-agent declares `model: gemma-4-31b-it-qat-w4a16-ct`.
2. **Declarative only**: allowed files `.yaml .yml .md .txt .py(skill scripts) .json .safetensors`; no symlinks, no absolute `!include`; `../` includes that stay inside the root work in practice. Total < 3 GiB. Zip holds files only (no directory entries).
3. **Submissions come from a notebook's output** (`/kaggle/working/submission.zip`), not a direct upload. **1 per day.** Every one counts — validate first.
4. **Tools**: the 9 harness tools by name + `agent_tool:` sub-agents; skills attach via `skills:` (`run_skill_script` / `load_skill_resource`).
5. **Context 32,768 tokens** total. Proven sampling: temp 0.2, top_p 0.95, top_k 40, max_output 8192, thinking_budget 4096, `include_thoughts: false`. Keep edits small so `<|tool_call>` isn't truncated.
6. **Time budgets — careful** (host Ryan Holbrook, discussion 743063): tasks run **sequentially**; the scorer reads only `evaluation: {timeout_seconds, max_tool_calls, max_time_minutes, max_turns}` from `eval_config.yaml`; **omitted = no limit**; **hitting 12 h currently errors the whole submission** (fix planned to score unfinished tasks as 0). ~120 tasks → ~6 min/task average including setup. The sample's 1 min/10 calls is a trap; a public 5-min run scored 0.00. Scoring public notebooks ship no eval_config. A timeout is not fatal to a task: the working-tree diff is still graded. Generation speed (thinking tokens) is the main time cost.
7. **Patch = `git add -N . && git diff HEAD`** in /workspace, graded even without `submit_patch`. Scratch files → `/tmp`. Never touch `/workspace/pytest.ini` / `conftest.py`.
8. **Test files are reset before grading**: fix library code only.
9. **Sandbox**: offline, 4 GiB RAM, 2 vCPU, Python 3.13, git/grep/sed/awk; **no `rg`, no `tree`**.
10. **Graph tools are weak**: only `calls` edges, no async functions, ~half the graph/embedding files are empty (one of each hard-link pair), embeddings have one dominant direction. `search_similar_code` takes a symbol name. Prefer `git grep` + `read_file`.
11. **Training data** (tasks.jsonl): 129 tasks — fastapi 67, rich 48, requests 13, httpx 1. `hints_text` always empty. 91/129 fixes touch 1 file; median 12 changed lines; 15 touch `docs_src/`. Patches lack a final newline (add one before `git apply`). Some problem statements are PR descriptions.
12. **Hidden test set = private repos**: optimize general skill, not repo knowledge. Public LB ≈ 60 tasks, so 1 task ≈ 0.017 — differences of 0.02–0.03 are noise.
13. **Sample LoRA adapters are no-ops** (every `lora_B` is zero, rank 4, layer 0). Real LoRA: PEFT `adapters/<name>/{adapter_config.json, adapter_model.safetensors}`, `adapter: <name>`, rank ≤ 128, ≤ 8 adapters; train against the W4A16 QAT checkpoint. Ship via an attached Kaggle dataset (too big to inline in the notebook).
14. **Hardware**: grader = 4× L4 (vLLM TP=4). Local = RTX 3050 4 GB → no local model runs. `swegemma` is not published, so there is no official local eval; offline checks = our validator + reading traces we can't get. Iterate via LB + reasoning.
15. **Public notebooks** in `reference/public_notebooks/` are competitor claims — useful, but verify before relying on them.

## Harness source (reference/harness_src/)
Host published the harness as wheels in dataset `metric/gemma-4-developer-agent-wheelhouse` (swegemma 0.2.7, adk-submission 0.2.11, adk-eval-core 0.1.0, google-adk 1.36.1, vllm 0.19.1; Python >= 3.12). Unpacked copies live in `reference/harness_src/src_*`. Key files:
- `swegemma/harness/agent_runner.py` — task prompt (`build_agent_prompt`), agent loop, nudges, timeout, fallback diff.
- `swegemma/models/registry.py` — model routing via LiteLLM `openai/<alias>`; endpoint from `OPENAI_BASE_URL`/`LITELLM_API_BASE`, key from `OPENAI_API_KEY` etc.; `--models-yaml` overrides.
- `adk_submission/resolvers/tools.py` — skills load via `google.adk.skills.load_skill_from_dir` into ADK `SkillToolset`; skill scripts run **inside the task sandbox** via `AdkSandboxCodeExecutor` (time counts against the task).

## Working copy vs releases (corrected 2026-09-26)
Every candidate is frozen before packaging; `--source releases/vN` is always used.
- `releases/v2` == `releases/v2_pre_review`, zip `6918f2c4…` — **this is what was submitted** (ref 56579838).
- `releases/v2_reviewed`, zip `f6392b82…` — same as the current working copy `submission/`. Adds to system.md:
  `git grep -n -F --`, PYTHONPATH-prefixed /tmp repro + assertion requirement, pytest exit code 5 = no tests collected
  (and skipped != pass), preserve behaviour for existing callers, inspect untracked new source files before submit.
  It passed the local validator, the official compiler and the notebook byte-comparison. It is **structurally validated
  but not yet evaluated for task-solving performance** — that is what the paired eval measures. (An earlier note in this
  file called it "unvalidated/unreviewed"; that was wrong.)

## Host guidance (2026-09-26)
- Host notebook `ryanholbrook/getting-started-gemma-4-developer-agent` (copy in reference/public_notebooks/host-getting-started):
  installs the wheelhouse, serves the real model with vLLM on Kaggle machine shape **`NvidiaL4`** (the grader's GPUs),
  runs `swegemma` Evaluator with `sandbox='subprocess'` on a few tasks, then zips. => **paired eval can run on Kaggle
  with the real model** (better than a Gemini-API proxy). Model source `google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2`.
- It avoids `thinking_level` in sampling (LiteLLM maps it to reasoning_effort). We don't use it.
- Host: "The only enforced constraint in this competition is a 12 hour inference runtime."
- Discussion 743683: failed-by-resources submissions get rerun on Monday. 743383: only LoRA adapters accepted (no full weights).
- Public LB = 58 tasks (competitor count, discussion) → 1 task ≈ 0.017.

## Thinking is currently OFF in every candidate (verified 2026-09-26)
`adk_submission/resolvers/generation.py::apply_thinking_config_to_model`: `include_thoughts: false` (or
`thinking_level: none`) sets `extra_body.chat_template_kwargs.enable_thinking = False`, and **`thinking_budget`
is never forwarded** — only `enable_thinking` and `reasoning_effort` are. Our `sampling.yaml` has
`thinking_budget: 4096` + `include_thoughts: false`, so v1, v2 and v2_reviewed all ran with thinking disabled;
the 4096 budget is inert. The host's own getting-started notebook uses `include_thoughts: true` (thinking ON).
Enabling it is a real, untested lever with a runtime cost -> `MODE="thinking"` in the eval notebook.

## Offline evaluation (notebooks/eval)
`python scripts/make_eval_notebook.py` embeds `releases/v2` + `releases/v2_reviewed` as base64 zips (verified
byte-identical to the frozen zips) and writes a Kaggle GPU notebook that runs the **real** harness + **real**
QAT weights. `MODE="smoke"` (1 task, requests_6589) is the default; `paired`/`thinking` also need
`FULL_RUN_CONFIRM=True`. Results go to `results/<MODE>/<candidate>/`; a non-empty existing dir is an error,
so stale/partial results are never silently reused.
Paired subset (14): fastapi 11194/14246/14361/14482/14794/15588, rich 2725/3105/3471/3676/3934,
requests 6589/7309, httpx 3672. Caveat: `fastapi_14794`'s statement is a PR description naming the fix.

### Result artifact schema (verified against swegemma/results.py — read this before writing report code)
`task_results.jsonl` rows contain **`instance_id`, `agent_patch_size` (int, characters), `error`,
`test_exit_code`, `duration_seconds`, `tool_calls`, `total_llm_calls`** — there is **no** `agent_patch`,
`test_output`, `status` or `error_message` field. The text lives in separate files, with inconsistent naming:
- `patches/<id with / -> __>.patch` — written only if the patch is non-empty
- `test_outputs/<id with / -> __>.log` — written only if grading produced output
- `traces/trace_<id with / -> __>.json`
- `logs/<id with / -> _>.log`  (**single** underscore, from agent_runner.py:221)
`test_exit_code == -1` is a sentinel meaning grading did not run; treat it as failure, not success.
`duration_seconds` covers setup + agent + Phase 2 grading, so it is **not** an inference-time projection.

### Evaluation caveats (do not overstate results)
- Prompt invariance (sentinel answer keys leave the prompt unchanged) proves the data flow, **not** filesystem
  isolation: the subprocess backend runs `run_command` on the host, where answer-key files stay reachable.
  Audit traces before trusting a pass.
- Same model + same GPU name is not proven equivalence with the grader.

## SMOKE RUN RESULT 2026-09-26 (kernel v2, artifacts in reference/smoke_run_2026-09-26/)
**Environment confirmed = grader:** 4x NVIDIA L4, tp=4, swegemma 0.2.7, adk-submission 0.2.11,
google-adk 1.36.1, vllm 0.19.1, transformers 5.13.1, `Gemma4ForConditionalGeneration` 4-bit
pack-quantized (group_size 32). vLLM startup ~6 min, agent run 2.5 min. All 6 smoke stages passed.

**THE EVAL ENVIRONMENT IS INVALID — fix before any comparison.** On requests_6589 the agent read
`total_length = len(o)` from `src/requests/utils.py` (no fix present) yet its reproduction printed
`super_len('🚀') = 4` and "Test passed!" **before any edit**. The executed package was NOT the
checkout. The subprocess sandbox builds its venv **without pip** (`ensurepip unavailable` warning),
so the editable install of /workspace cannot have worked. Any agent comparison run on top of this
measures reactions to contradictory evidence, not skill.

**Corrected reading of the 25 repeated commands** (an earlier note in this file blamed disabled
thinking — that was wrong, and remains only an untested hypothesis): the agent localised the bug
correctly on tool call 1, then re-ran the same check because source and runtime disagreed. Prompt/
completion token totals do NOT establish "no room to reason": short completions are normal for tool
calls and the prompt total is re-processed history. Test thinking on/off only after the environment
is valid.

**Scratch file leak was a TOOL-CAPABILITY error, not disobedience.** The trace shows
`write_file("/tmp/repro.py")` -> `FileWriteError: Path traversal detected: '/tmp/repro.py' escapes
workspace root`. The agent then fell back to `repro.py` in the workspace, which became the entire
731-char patch. **`write_file`/`edit_file` can only write inside /workspace**; /tmp scratch files
must be created via `run_command` + heredoc. Fixed in the working copy (v3 candidate).

**requests_6589 target tests error on the `httpbin` fixture** ("recursive dependency involving
fixture 'httpbin'", 187 ERRORs). Whether gold can pass there is **still unverified** — the gold
control has not been run yet, so "even the gold patch cannot pass" was premature.

**`display_mode="quiet"` leaves `logs/<id>.log` empty (0 bytes)** -> derive tool errors and
repeated-call counts from `traces/trace_<id>.json`, not the log.

## Task validation (notebooks/validate) — CPU only, no model, no GPU
`python scripts/make_validation_notebook.py` -> kernel `navin03/gemma4-swe-agent-validate`.
Per task, each in a fresh sandbox: (1) import probe — does `import <pkg>` resolve under /workspace
(handles src/ layouts), plus fixture-plugin probes (pytest_httpbin, pytest_asyncio, trio, anyio) and
a `--collect-only` check; (2) **negative control** — test_patch only, tests must FAIL; (3) **positive
control** — reference patch + test_patch, tests must PASS. `USABLE` needs all three. Gold-only
passing is not enough: the negative control catches tasks that already pass without a fix.
Infrastructure failures (collection errors, missing fixtures, sandbox exceptions) are a separate
`INFRA_FAILURE` verdict and every exclusion is printed, never silently dropped.

**Order of work (do not skip ahead):** validate imports + fixtures -> baseline-fail/gold-pass
controls -> derive metrics from traces -> thinking on/off on the usable subset -> paired prompt
comparison. The bottleneck is trustworthy evaluation, not a stronger prompt.

## VALIDATION RESULT 2026-09-27 (CPU run, artifacts in reference/validation_run_2026-09-27/)
Controls ran per task in two fresh sandboxes each (negative = test_patch only, positive = gold + test_patch),
with the harness's exact pytest command + `--junitxml`.

**USABLE (9)** — target tests FAIL at baseline and PASS with the gold patch, so the tests provably exercise
the checkout: `fastapi_11194, fastapi_14794, fastapi_15588, rich_2725, rich_3105, rich_3471, rich_3676,
rich_3934, requests_7309`.

**EXCLUDED (5), with cause:**
- `requests_6589` — both target tests **ERROR** at setup (`httpb   in` fixture recursion) in BOTH controls.
  Gold cannot pass. Confirms the earlier suspicion; the smoke run picked the one broken task.
- `fastapi_14246 / 14361 / 14482` — pytest **collection interrupted (exit 2)** on other test modules.
- `httpx_3672` — collection error: `module 'httpx' has no attribute ...` because the import resolved to
  the installed copy, and its test_patch adds no new test function.

**IMPORT PROVENANCE — mismatch confirmed for 3 repos.** `<pkg>.__file__` inside the control sandboxes:
- fastapi / rich -> `/tmp/swegemma_sandbox_*/workspace/<pkg>/__init__.py` (the checkout; `/workspace` is
  rewritten to the sandbox temp dir in subprocess mode)
- **requests / httpx -> `/usr/local/lib/python3.12/dist-packages/<pkg>/__init__.py`** (an installed copy).
  This is the mechanism behind the smoke run's contradiction: the released `requests` already contains the
  `super_len` fix, so the agent's reproduction printed 4 while the checkout source said `len(o)`.
  Editable-install logs: fastapi `No module named 'pdm'`, rich `No module named 'poetry'`,
  httpx `No module named 'hatchling'`; requests "Can't uninstall 'requests'... Successfully installed".

**Two bugs in my own validation code (fixed for future runs, results above already corrected offline):**
1. `in_checkout` compared against the literal `/workspace` prefix, but subprocess sandboxes rewrite it to
   `/tmp/swegemma_sandbox_*/workspace` -> false "not in checkout" for all 14 tasks.
2. Keying only on newly added `def test_*` mislabels tasks whose test_patch edits existing tests
   (rich_3105, requests_7309). Fall back to file-level: baseline exit 1 + gold exit 0.

**The behavioural pair is stronger evidence than the __file__ probe**: if baseline fails the target tests and
the gold patch makes them pass, the tests must be exercising the checkout whatever a side-probe reports
(the probe and pytest do not necessarily use the same interpreter/flags — pytest runs
`PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s`). Treat provenance as diagnostic, behaviour as decisive.

**CONFOUND IN MY OWN CONTROL CODE (found 2026-09-27, invalidates the verdicts above as final):**
`provenance()` recorded `<pkg>.__file__` and THEN re-ran the editable install, and pytest ran after that.
So the probe and the grading measured **different environment states**, and every "usable" verdict was
obtained in a sandbox my diagnostic had mutated with an extra install the real agent run never gets.
The `-s` flag only disables user site-packages; it does NOT imply a different interpreter, so my earlier
"different interpreter" explanation was wrong too.
Verdicts are therefore **provisional** — see `reference/validation_run_2026-09-27/provisional_verdicts.csv`
(the old `validation_results.csv` is renamed `*_SUPERSEDED_wrong_verdicts.csv`). 7 PROVISIONAL_USABLE,
2 PROVISIONAL_USABLE_FILE_LEVEL (rich_3105, requests_7309 — file-level fallback, needs failure review
before promotion), 5 EXCLUDED_INFRA.

## Provenance check (notebooks/provenance) — CPU only, 2 tasks
`python scripts/make_provenance_notebook.py` -> kernel `navin03/gemma4-swe-agent-provenance`.
Answers one question: **do the agent's commands AND the grading run both import the checkout?**
Tasks: `requests_7309` (disputed) + `rich_3471` (comparison). Design:
- control path does **no installs and no mutation**; install diagnostics get their own throwaway sandbox;
- provenance recorded under the **agent's** settings (plain `python3` via run_command, cwd /workspace);
- provenance ALSO recorded **inside the pytest process** by a plugin on `PYTHONPATH=/tmp/provplug`
  (outside the repo), loaded with `-p prov_plugin`, capturing `sys.executable`, `sys.path`, `__file__`;
- `pwd -P` gives the real workspace root, so the `/workspace` prefix bug cannot recur;
- full test identities, failure messages and raw JUnit XML preserved.
Decision gate: only if BOTH agent and pytest import the checkout on both tasks do we move to a small
thinking-on/off comparison. Recovering the 5 excluded tasks can wait.

## PROVENANCE RESULT 2026-09-27 — DECISION GATE FAILED (artifacts: reference/provenance_run_2026-09-27_norepair/)
Two tasks, no installs or mutation in the control path, provenance recorded under the agent's settings
AND inside the pytest process (plugin on PYTHONPATH outside the repo).

| task | agent imports | pytest imports | neg exit | pos exit |
| --- | --- | --- | --- | --- |
| requests_7309 | dist-packages | dist-packages | 1 | 1 (same 6 failures) |
| rich_3471 | **checkout** | **dist-packages** | 0 | 0 (0 failures) |

- `requests_7309`: gold patch changes **nothing** — identical failures in both controls, because neither
  the agent nor pytest ever loads the checkout. The earlier "gold passes" verdict was **entirely an
  artifact of the extra editable install my own diagnostic performed**. UNUSABLE.
- `rich_3471`: the agent sees the checkout but **pytest does not**; the installed released `rich` already
  contains the fix, so the negative control PASSES and the task cannot detect the bug. UNUSABLE.
- Therefore **all 9 "provisional usable" tasks were usable only because of that accidental reinstall.**

**ROOT CAUSE.** The sandbox venv carries `_host_env.pth`, which puts the Kaggle host's
`/usr/local/lib/python3.12/dist-packages` (with released fastapi/rich/requests/httpx) on `sys.path`, and
`install_editable_package` **silently fails** — no `.egg-info`, no `__editable__*` finder — because the
venv lacks the PEP 517 build backends (`No module named 'pdm' / 'poetry' / 'hatchling'`). Under
`PYTHONSAFEPATH=1` pytest does not add cwd, so the installed copy wins.
**This is a defect of our subprocess proxy, not evidence about the real grader**, whose Docker image
(`Dockerfile.sandbox`) preinstalls `setuptools wheel poetry-core hatchling flit-core pdm-backend editables`.

**REPAIR (feasible offline).** Those backends are in the competition's own `wheels/`
(`hatchling-1.30.1`, `poetry_core-2.4.1`, `pdm_backend-2.4.9`, `flit_core-3.12.0`, `editables-0.6`,
`setuptools`, `wheel`). `REPAIR_EDITABLE_INSTALL=True` installs them from `/wheels` and re-runs the
editable install inside `base_setup`, so it applies identically to every control and to any future agent
run, and is logged (`repair_log`) rather than silent. Diagnostic evidence it works: after a successful
editable install, `import requests` resolved to `/tmp/.../workspace/src/requests/__init__.py`.
Set the flag False to reproduce the broken baseline.

**STILL TRUE:** no agent performance has been measured, and no GPU comparison may start until both tasks
show the agent AND pytest importing the checkout.

## GATE PASSED 2026-09-27 with the repair (reference/provenance_run_2026-09-27_repaired/)
| task | agent imports | pytest imports | neg exit | pos exit |
| --- | --- | --- | --- | --- |
| requests_7309 | checkout | checkout | 1 (5 failures) | 0 |
| rich_3471 | checkout | checkout | 1 (1 failure: test_append_tokens) | 0 |
Both tasks: agent commands AND grading now load the task checkout, baseline fails, gold passes.
Compare with the un-repaired run (`*_norepair/`), where requests_7309 gave IDENTICAL failures in both
controls and rich_3471 passed its own negative control.

**Repair that works** (`repair_editable_install`): install each PEP 517 backend **separately** (pip aborts
the whole command on one unresolvable name) from BOTH `/wheels` (the sandbox stages only 41 of 124 wheels)
and the competition's full `DATA_DIR/wheels` (which the subprocess sandbox can read directly), then re-run
the editable install. `editables` and `poetry_core` exist only in the full directory.
**`hatchling` still fails to install** (missing transitive deps offline) -> httpx tasks remain broken.

**PORTING THE REPAIR TO THE GPU PATH IS MANDATORY BEFORE ANY AGENT RUN.** `notebooks/eval` calls
`Evaluator(cfg).run()`, which does its own setup, so the repair must be monkeypatched onto **all** of:
`swegemma.harness.agent_runner.install_editable_package` (Container A = the agent's own environment),
`swegemma.harness.verification.install_editable_package` (Container B = grading), and
`swegemma.harness.container_setup.install_editable_package` — each binds the name at import time.
Without this the agent's reproduction imports a released package again, which is exactly the smoke-run
failure, and the grade would be meaningless.

**The other 12 task verdicts are void** (produced in the broken environment); full 14-task CPU validation
re-running with the repair.

## VALIDATED TASK SET 2026-09-27 (repaired; reference/validation_run_2026-09-27_repaired/)
With the repair, **imports resolve to the checkout for 13 of 14 tasks** (only httpx_3672 fails, because
`hatchling` cannot be installed offline).

**USABLE (7)** — target tests fail at baseline, pass with gold, both sides on the checkout:
`fastapi_11194, fastapi_14794, fastapi_15588, rich_2725, rich_3471, rich_3676, rich_3934`
(rich_3471 agrees with the independent provenance run — the two methods cross-check.)

**+1 proven separately:** `requests_7309` is classified INFRA_FAILURE only because my verdict keys on
newly added `def test_*` and its test_patch edits existing tests. The provenance run measured it directly:
baseline 5 failures, gold 0 failures, both sides on the checkout. **Usable; 8 total.**

**`rich_3105`** — same file-level fallback case (neg exit 1, pos exit 0, no new test functions).
**Needs failure review before promotion**; not counted.

**EXCLUDED:** `fastapi_14246/14361/14482` (pytest collection interrupted, exit 2 both controls),
`requests_6589` (target tests ERROR on the httpbin fixture), `httpx_3672` (import still not in checkout).

Repo mix of the 8: fastapi 3, rich 4, requests 1.

## ROOT CAUSE, precisely (container_setup.py, verified in source)
Subprocess mode **skips setup by design**: `install_editable_package` returns immediately at line 512
and `install_test_dependencies` at line 529 when the manager is `SubprocessManager`/`SubprocessSandbox`.
So the checkout is never installed and the sandbox relies entirely on `_host_env.pth`, which exposes the
Kaggle host's dist-packages holding RELEASED fastapi/rich/requests/httpx. Under `PYTHONSAFEPATH=1`
pytest adds no cwd, so the released copy wins.
**The real grader runs `--sandbox docker` (the default), where both functions actually execute** — so
this is a property of the notebook proxy, not evidence about the leaderboard. Note the **host's own
getting-started notebook uses `sandbox='subprocess'`**, so anyone evaluating that way on Kaggle is
measuring against released packages unless they repair it.

## GPU eval path: repair ported + hard precondition (notebooks/eval)
`patched_install_editable_package` calls the original, then (subprocess only) installs the PEP 517
backends one-at-a-time from `/wheels` + the competition's full `wheels/`, then does a real editable
install. It is bound onto **all three** modules that hold the name:
`agent_runner` (Container A = the agent), `verification` (Container B = grading), `container_setup`.
Verified offline that all three bindings exist and rebind independently.
A **precondition cell runs before vLLM starts**: it builds one sandbox, applies the patched install, and
asserts that BOTH the agent view (`python3 -c "import pkg"`) and the grading view
(`PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -c ...`) resolve under the workspace. If either fails
the notebook stops before model serving starts; GPU quota is already consumed during CPU setup in a GPU session.
Task set = the validated 8; `MODE="smoke"` uses `rich_3471`.

## THINKING A/B PILOT — prepared 2026-09-27, NOT dispatched
Both submissions scored **0.06** (v1 ref 56540226, v2 ref 56579838). Equal aggregates do not mean the
same tasks were solved. Nothing measured so far demonstrates improved task-solving.

**Candidates** (`scripts/effective_settings.py` prints the compiled arguments):
| | dir | zip sha256 | effective |
| --- | --- | --- | --- |
| A | `releases/pilot_A` (= v2_reviewed, unchanged) | `f6392b82…` | `enable_thinking: false` |
| B | `releases/pilot_B` | `194b420a…` | `enable_thinking: true` |
Exactly one line differs (`include_thoughts`); the file length decreases by one byte. Verified: every other file is byte-identical,
and the compiled effective model args differ only in `extra_body.chat_template_kwargs.enable_thinking`
for BOTH `swe_coder` and `code_analyzer`.
**`thinking_budget: 4096` is NOT forwarded to the server** — the resolver passes only `enable_thinking`
(and `reasoning_effort`, unset here). Do not call the numeric budget an enforced limit.

**The archived competitor baselines reviewed here run with thinking OFF** (`reference/public_baselines.json`): the 0.12 top
baseline uses `include_thoughts: false`, and Black Cat sets `thinking_level: HIGH` **but**
`include_thoughts: false`, which the resolver resolves to OFF — its HIGH is inert. Only the host's own
demo notebook enables thinking. So thinking-off cannot by itself explain 0.06 vs 0.12, and B is
untested territory rather than a known win.

**Pilot design:** 4 runs = {requests_7309, rich_3471} x {A, B}, order alternated per task
(A,B then B,A), identical budgets, fresh workspaces/sessions, shared server.
`DISPATCH_CONFIRM=False` by default; `SESSION_CAP_MIN=150` stops new runs (worst case = cap + one run).
A two-task pilot establishes that the experiment executes; it cannot establish superiority.

**Execution defects found by review and fixed** (previous generator parsed fine yet would have crashed):
1. the repair cell used `ALL`/`TASK_IDS`/`run_sync` before definition -> `NameError`; a COMMON cell now
   defines them first and `ALL_BY_ID` is used consistently;
2. pip piped through `tail` discarded exit status -> rc is checked, output retained, and a failed
   REQUIRED backend or editable install raises;
3. the monkeypatch could wrap itself on re-execution -> `__wrapped_original__` makes it idempotent;
4. one precondition sandbox was generalised to all tasks -> every selected task is checked through the
   patched setup path;
5. `duration_seconds` bundles grading -> `run_agent_sandbox`/`verify_task` are wrapped for separate
   agent and grading timings;
6. quiet-mode logs are empty -> diagnostics come from structured traces, and missing values are
   reported as `unavailable`, never 0;
7. attribution keyed on `edit_file` -> it now keys on what the diff contains, so shell edits count.

**Tests:** `python scripts/test_pilot_notebook.py` — 22 assertions, all passing. It EXECUTES the
generated cells in notebook order in fresh namespaces with injected stubs, and covers install failure,
repair idempotency, required-install failure, precondition failure, and the report schema.
It is **not** a real Kaggle run: no model, no sandbox, no task solved.

## PILOT AUDIT + HANDOFF 2026-09-27 (see reference/PILOT_LAUNCH_CARD.md)
An external audit found P1 defects my 22-assertion suite missed and **repaired them in-project**:
disabled dispatch still started vLLM with no shutdown; the timing wrappers missed `swegemma.evaluate`,
which holds its own imported bindings; missing control evidence was skipped rather than fatal; the A/B
comparison only iterated A's files; and `reference/public_baselines.json` attributed **submitted v2's
0.06 to unsubmitted pilot A** (my error). All fixed; repaired suite = **78 assertions, 0 failures**.

**Verified by me on 2026-09-27** with the audit interpreter (codex-primary-runtime python.exe, since the
project `.venv` is Python 3.11 and swegemma needs >=3.12):
- `scripts/test_pilot_notebook.py` -> 78 passed, 0 failed.
- All artifact hashes recomputed and matching; frozen releases unchanged.
- `DISPATCH_CONFIRM=False`; the vLLM cell is guarded by it; `.stop()` on completion/failure paths.
- Task drift guard `EXPECTED_TASK_HASHES` recomputed locally: both pilot tasks match.
- kernel-metadata: private, internet off, NvidiaL4, correct model source.

**Corrections to my own earlier claims:**
- "conservative maximum ~1.5 h session wall time" was unsupported -> **withdrawn**. `SESSION_CAP_MIN=150`
  only blocks admitting a NEW run; it does not kill a run in flight or end the session, and GPU quota is
  consumed during CPU setup too.
- pilot A (f6392b82...) is **reviewed but never submitted and has no score**. Only 6918f2c4... (v2) and
  1e265aab... (v1) have scores, both 0.06.
- The 78 offline assertions use simulated dependencies; they are not a Kaggle run.

**Still unmeasured:** any pilot solve result, and why the Docker-graded submissions scored 0.06. The
subprocess import defect concerns local evaluation only.

## REPLAY RESULT 2026-09-28 — overturned my pilot conclusion (reference/replay_run_2026-09-28/)
CPU-only, four arms, controls valid (baseline exit 1 with the 5 `_parse_content_type_header` cases;
reference exit 0 over 220 tests).

| arm | test_patch rc | pytest | result |
| --- | --- | --- | --- |
| baseline | 0 | 1 | fails, as required |
| reference | 0 | 0 | passes, as required |
| **A_original** | 0 | **0** | **passes** |
| **A_source_only** | 0 | **0** | **passes** |

1. **Candidate A's saved patch passed the replay's 220 tests** (both as saved and with the tests/
   blocks stripped). That supports correctness **on this verification suite**; it does not establish
   why the original pilot run failed, and it is not a leaderboard result.
2. **The test edits did NOT cause the pilot's grading failure.** The harness reset worked exactly as
   designed: the tampered file hashed `0dfa40c1…` before reset and `749c36bc…` after — identical to
   `git show HEAD:` pristine — then test_patch applied rc 0 and the tests passed. `A_original` passes.
   **My earlier claim that "editing tests destroys the measurement" is not supported.**
3. The pilot's `test_patch` application failure **did not reproduce**; its mechanism is **unavailable**.
   Do not invent one. **This remains an OPEN ISSUE** and must not be written up as resolved.
What survives: candidate B's self-inflicted `ERROR collecting` -> 25 identical reads -> crash, losing a
source fix it had already made at step 8. That is what v3's guards actually target.

## LoRA status
Discussion 743116 (competitor, unanswered): pinned vLLM 0.19.1 either refuses `--enable-lora` for `Gemma4ForConditionalGeneration` or ignores adapters. Discussion 743508: adapters load but are silently wiped (Gemma4 decoder layers registered twice → reset_lora); host replied "I will address". **LoRA on hold** until fixed; prompts/skills/config are the levers now.

## Local eval plan (proposed)
Real swegemma harness in Docker (Docker Desktop is installed) + Docker task sandboxes + `gemma-4-31b-it` via the Gemini API's OpenAI-compatible endpoint (free tier ≈1,500 req/day). Proxy only: not the W4A16 QAT weights and not vLLM's gemma4 tool parser. Dev subset ≈24 tasks ≈3.2 GB of snapshots (fastapi snapshots ~250 MB each, rich ~94 MB, requests ~37 MB).

## Open questions
- **Screening exclusions are a subprocess-mode artifact, not task defects (run 2, evidence inspected 2026-09-28).**
  `container_setup.install_test_dependencies` returns early for `SubprocessManager`/`SubprocessSandbox`
  (container_setup.py:529), so `_ensure_container_site_packages` never runs and the repo's test-only
  dependencies are never injected. In real Docker grading that helper unpacks every base wheel (<16 MB)
  from the 1.7 GB wheels dir into site-packages, then resolves large wheels by scanning workspace imports.
  Consequences measured in run 2: 11 fastapi tasks died on `No module named 'inline_snapshot'`, 3 requests
  tasks errored ~190 nodes per arm on the missing `httpbin` fixture (`pytest-httpbin`), and httpx was
  excluded on a `hatchling` preflight -- yet `Dockerfile.sandbox:7` pre-installs hatchling in the real image.
  In all of these the patches applied (`patch_rc == 0`) and grading imported from the checkout. Open: extend
  the screening repair to inject the base wheels, then re-screen. Untested -- do not assume the packages
  are present in the wheel mirror until a run shows it.
- `requests_6592` has a clean fail->pass signal with 185 errored nodes IDENTICAL in both arms. The
  classifier rejects it on "JUnit errors present". Relaxing that to "errors identical across arms" would
  be a post-hoc loosening fitted to this data; not done.
- Whether an explicit `max_time_minutes` (~5-6) helps as a 12 h failsafe or hurts by cutting good runs short.
- Whether the analyzer sub-agent is worth its extra LLM calls vs. a single agent (0.12 vs 0.06 in public notebooks is ~3 tasks, near noise).
- Discussion 742807: whether distillation from proprietary LLMs (for LoRA training data) is allowed — host answer pending.

## CANDIDATE R rev3 + STAGE-1 PACKET, review items closed 2026-09-30

State check first: nothing had been reverted. Work had stopped after revision 2, so all four review
items were outstanding. They are now done.

**Item 1, exact anchor verification.** The `git grep -c -F` first-line count is REMOVED (it counted
matching lines, not occurrences of a multiline block) along with the contradictory instruction. The
scripted check is now `assert old and s.count(old) == 1` over the whole block, which also rejects an
empty anchor, and it runs before the write.

**Item 2, safe rollback.** Before a recovery write the agent copies the file's current bytes to a unique
`/tmp/bak.*` and restores THAT on a wrong attempt. `git checkout -- <path>` is gone from the recovery
path and the hazard is named: it would discard earlier valid edits to the same file. `read_bytes`/
`write_bytes` preserve encoding and line endings. The diff is reviewed in bounded sections until empty
rather than `head -40`. `py_compile` runs only for `.py`.

**Item 3, executed Stage-1 configuration.** `scripts/test_stage1_notebook.py`, **38 assertions 0
failures**, runs the GENERATED cells with simulated dependencies: disabled dispatch creates no server
and evaluates nothing; enabled simulation evaluates exactly `rich_3278`/R once; A is never evaluated
(only `R__rich_3278` is created); a failed precondition and a corrupted control each block model
startup; the server is stopped on success, evaluator failure and startup failure; no Stage-2 run exists.
This required one harness fix: `_control_maps()` only built control evidence for `NB_TARGET=compare`, so
stage1's controls came back empty. It now follows the notebook under test, and compare regenerates and
passes unchanged.

**Item 4, `scripts/review_stage1.py` written.** Pinned to the prepared notebook's full hash
`695cad7b6efb6edaa899b95cebc063bf8c934b0922ea247d4088212753c196a0`; **arming flips DISPATCH_CONFIRM and
changes those bytes, so the pin is updated deliberately with both values recorded.** It separates
instrument validity / candidate reliability / task performance and never sums them. Stage-1 success
needs a valid non-empty SOURCE patch (test-only and scratch-only patches do not count, and the patch
size must match the evaluator's record) plus observed grading. **An accepted tool call does not prove a
source change.** Recovery is "observed" only with a rejection, a later DIFFERENT accepted operation, and
an argument naming a path that actually changed; otherwise **"recovery unproven"**. Raw artifacts are
read-only and the reviewer refuses to write inside them.

`scripts/test_review_stage1.py`, **48 assertions 0 failures**: valid graded source patch, missing
submission, missing submission as the sole failing gate line, empty patch, failed controls, missing
trace, early termination with no run record, artifact hash mismatch, test-only patch, recovery observed,
same-tool retry, accepted-but-unlinked operation, and the write-inside-artifacts refusal.

**Two real reviewer bugs were found by its own tests:** `test_exit_code` and `resolved` were being read
from `runs.json` instead of `task_results.jsonl`, and a missing trace was reported as "no rejected call".
**Mutation testing (`scripts/mutate_stage1_guards.py`) then found two coverage holes** that 41 passing
assertions had missed: dropping the missing-submission gate line and dropping the recovery link
requirement both survived. Cases V2b and V9c close them; **all 7 mutations are now caught.**

**Hashes.** R rev3 `prompts/system.md` `74a12c7d241371f7e8a26aad9b061780bac2a5c8c5b8fd4fd9ed80f5eedea8c3`
(A `4d42f2b7...`, rev1 `a495b4ec...`, rev2 `c953913b...`, all preserved). `OFFICIAL COMPILE OK`;
generation config identical to A, only coder instruction length moves (7,729 to 10,917 chars). Stage-1
notebook `695cad7b...`. Frozen unchanged: `releases/compare_v1_launched` `532d3f7e...`,
`releases/compare_v2_prepared` `97873af2...`, working compare `029bb41f...`.

**REVIEWER FALSE POSITIVES FIXED 2026-09-30 (candidate R unchanged, `74a12c7d...`).** Codex reproduced
two, both real:
1. **Recovery over-attribution.** A successful `read_file` after a rejection became "recovery observed"
   whenever that path appeared in the final patch. Now: read-only tools never qualify; an explicitly
   successful **MODIFYING** operation is required; its target must match a changed source path
   **exactly** after normalisation (a same-basename match is refused and reported as such); and the
   tool's own change evidence (`edit_file`'s `diff`, or `write_file`'s `filepath` plus `size`) must tie
   it to the patch. Without that evidence the verdict is **"consistent with recovery; attribution
   unproven"**. Causal certainty is never inferred from the final diff.
2. **Patch over-acceptance.** `agent_patch_size` could be absent and a diff header alone passed as a
   source patch. Now the recorded size must exist, be an `int`, and equal the preserved text; header-only,
   malformed-hunk and count-mismatched patches are rejected; and **syntactic validity, application
   evidence and actual source change are three separate reported properties.**

Also: BOTH agent and grading provenance observations are required before the graded path is called
verified; duplicate control arms, off-plan runs and a mismatched manifest run order **abort** rather than
warn; a missing submission is reported as grading **UNOBSERVED**, separate from an instrument fault; a
refusal from the notebook's own REPORT cell is recorded as an artifact finding instead of crashing the
reviewer; and the synthetic `SOURCE_PATCH` fixture's inconsistent hunk counts were corrected.

`scripts/test_review_stage1.py` **98/0**, with independently load-bearing negatives for read-only after
rejection, same-basename file, exact match without evidence, absent and wrong-typed patch size,
header-only / malformed / count-mismatched patches, non-verdict exit codes, agent-only provenance,
duplicate controls, off-plan run and mismatched manifest. `scripts/mutate_stage1_guards.py`:
**22 mutations, 22 caught.** One earlier survivor was an equivalent mutant I had mis-targeted, and
retargeting it to the real routing branch made it load-bearing.

**Launch scope, not yet requested:** one Kaggle kernel, `navin03/gemma4-swe-agent-stage1` (private,
internet off, GPU), **one task `rich_3278`, one candidate R, one agent run**, `SESSION_CAP_MIN = 90`,
`DISPATCH_CONFIRM = False` as shipped. No automatic Stage 2. Estimated 35 to 45 minutes, an estimate and
not a bound.

## STAGE 1 RESULT + CANDIDATE S 2026-09-30 (read experiments/concise_workflow_v1/PROPOSAL.md)

**Stage 1 ran once (kernel version 1, armed notebook `775d88df...`) and FAILED to produce a patch.**
Kaggle: successful, 12m 7s, GPU L4 x4. Raw artifacts `reference/stage1_run_2026-09-30/` (25 files,
hashes in `reference/stage1_review/raw_sha256.json`, verified unchanged after analysis).

- **Instrument: GRADING_PATH_UNOBSERVED.** Both controls re-validated and agree with saved (baseline
  exit 1, reference exit 0, 23 nodes, 16 targets); agent provenance verified in the workspace; cleanup
  confirmed; one readable result record. The only unmet check is grading-phase provenance, which could
  not run **because grading never ran**. That is UNEXERCISED, not a demonstrated fault.
- **Candidate: 60 turns, 59 `run_command` + 1 `read_file`, 5 distinct payloads, one regex probe issued
  56 times, 54 repeated identical calls, 0 rejected calls, 0 acknowledged source edits,
  `submit_patch` called 0 times.** Terminated on the turns budget.
- **Performance: 0-byte patch, `test_exit_code` -1, not resolved.** Agent loop 158.3 s, wall 183.6 s.
- The recovery ladder was **never exercised**: there were no rejections.

**CORRECTION, important.** Candidate R ALREADY forbids identical calls against unchanged state and
already has a two-attempt escape rule (five separate instructions, verified). Describing repetition as
a missing instruction was WRONG. **Do not add another phrasing of that rule.**

**Reporting fixed in `scripts/review_stage1.py`:** instrument reporting now has three states,
`observed_checks_passed` / `grading_path_unobserved` / `demonstrated_failure`, so unobserved is never
reported as broken. The absence of a missing-submission message is no longer treated as evidence that
`submit_patch` was called: the observed call count is reported and is deliberately NOT gated on,
because `agent_runner` captures the working-tree diff as a fallback patch. Stage 1 remains NOT PASSED.
`test_review_stage1.py` **114/0**.

**FEEDBACK-PATH AUDIT (`reference/stage1_review/FEEDBACK_PATH_AUDIT.md`): no defect found.** Recorded:
prompt tokens grew 5,514 to 19,538 over 60 turns with **0 decreases in 59 transitions**, a constant
**+128 per turn** through the loop; compaction threshold 20,480 never reached; no rewind/retry/reset
event. Source: ADK rebuilds contents from `session.events` each turn (`contents.py:73`) and pairs calls
with responses (`contents.py:101,148`); removal needs a rewind, a branch mismatch or compaction, all
ruled out here. **NOT established: the outgoing request bodies were never captured, so this does NOT
prove the model saw the observations. No transport defect is claimed.**

**CANDIDATE S** = `experiments/concise_workflow_v1/candidate_S`, derived from **A (= releases/v3)**,
not from R. Only `prompts/system.md` changes: **1,247 to 413 words**, a concise
understand -> reproduce once -> edit -> verify -> submit workflow with a mid-run editing checkpoint.
Preserves the /tmp heredoc rule, tests-reset-before-grading, pytest exit-code capture, exit 5 is not
success, no rg/tree, the checkout-import check, unique `old_string`, and test-path restore. Twelve
checks assert no task or gold leakage. `OFFICIAL COMPILE OK: candidate_S`, coder instruction
7,729 -> 2,598 chars, generation config identical to A.
system.md `39b2541c2220cc7655c576bb4ae7ac7e03200a72f2f1e518313068fc93be3b91`,
zip `8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07`. Build:
`python scripts/make_candidate_s.py`. **A prompt-package experiment; it does NOT assert that length
caused the loop.**

**MY TASK PROPOSAL VIOLATED THE FREEZE, corrected.** `fastapi_14873` and `requests_7427` are in
`protected_holdout`, and so are ALL seven validated fastapi/requests tasks. `task_freeze.json` already
records `coverage_shortfall`: the dev-eligible pool is 100% Textualize/rich and those seven were
deliberately not moved. They are removed from the proposal; **the freeze is unchanged**
(`220869409441c04d...`). **New guard:** `make_compare_notebook.assert_tasks_not_held_out()` runs at the
top of `main()` and refuses to generate any notebook whose tasks intersect the hold-out, so every
notebook on this machinery inherits it. Verified to refuse a held-out task and accept the dev four.

**A vs S PREPARED, DISABLED:** `notebooks/ab_s/ab_s.ipynb` sha256
`92cb1f0b7fe6fdc9a5c14f1ccb0a7e33edf9a1ca6a6d8dbb3f664ff719599279`, kernel
`navin03/gemma4-swe-agent-ab-s`, private, internet off, `DISPATCH_CONFIRM = False`, built by
`scripts/make_ab_s_notebook.py` reusing the existing comparison machinery and controls. Order
alternates A/S then S/A: `rich_3278 A, rich_3278 S, rich_3535 S, rich_3535 A, rich_3675 A,
rich_3675 S, rich_3942 S, rich_3942 A`. **RICH-ONLY DIAGNOSTIC, not evidence of cross-repository
improvement.** Executed checks on the generated cells: 11/0 (disabled runs nothing; enabled dispatches
exactly eight in the right order with both candidates; a corrupted control still blocks the server; no
held-out task appears). ~130 min estimate, not a bound.

**Three measurements stay separate in the report:** RELIABILITY (valid non-empty source patch +
observed grading) / PERFORMANCE (paired solves, losses, ties, and **ungraded as its own category**) /
MECHANISM (repeats, turns, operation-level edit evidence). **A source patch counts whatever produced
it: a shell edit via `run_command` is as valid as `edit_file`, and no acknowledged edit call is
required.** **More graded but incorrect patches is progress on reliability and nothing on performance.**

**Open and unexplained:** why the agent repeated one command 56 times when the recorded token growth is
consistent with five prohibitions still being in context (the request bodies were not captured). The +24 min quota move (02:25 to 02:49) is NOT attributed to this run alone: other
usage and delayed accounting were not ruled out. **No score prediction; nothing supports 0.15 or 0.20.**

## Submission log
| Date | Version | Change | Public LB |
|---|---|---|---|
| 2026-09-25 | v1 | coder + code_analyzer (0.12-notebook structure), our prompts (git grep, no rg, graph caveats, exact-API emphasis, test conventions), proven sampling, no eval_config. Kernel version 1, submission ref 56540226, zip sha256 1e265aab… | **0.06** (top of LB 0.13) |
| 2026-09-28 | v3 (frozen in releases/v3) | prompt-only, from pilot v1 + replay evidence: /tmp heredoc scratch, checkout-import verification, diagnose-then-restore on `ERROR collecting`, no repeats against unchanged state, stuck-after-two exit, test-path revert before submit (not stash/reset). Sampling, tools, analyzer identical to v2_reviewed; thinking OFF. Kernel version 3, submission ref **56636116**, zip sha256 `b8da59c1c3a0671bb9b11b2fe4238a252ff792a63abf7ea4b5d555ceab57b24b`. **Exploratory, not a proven improvement.** Pre-correction freeze preserved as releases/v3_pre_correction (`301af87d…`) | **0.06** (COMPLETE, confirmed 2026-09-29) |
| 2026-09-26 | v2 (frozen in releases/v2) | prompt/workflow only, from two external reviews: coder searches directly; analyzer optional, gets issue + findings + focused question, sole owner of graph tools; reuse existing tests; baseline test run before editing; pytest exit code preserved via /tmp/test-output.txt + PYTEST_EXIT_CODE (no `| tail` masking); no stash/reset; unresolved-not-unrelated failures; bounded investigation. Sampling, timeouts, adapters identical to v1. Deterministic zip sha256 6918f2c4… (Kaggle output verified identical). Kernel version 2, submission ref 56579838 | **0.06** (user screenshot, 2026-09-27) |


## Latest source audit (supersedes contradictory notes above)

Implemented in the original Kaggle project; previous v2 preserved as releases/v2_pre_review.
New candidate: releases/v2_reviewed. Original releases/v2 remains unchanged.

Changes: assertion-based scratch reproduction with checkout import path; issue-related boundary and ordinary cases; explicit no-tests/skipped-test handling; review untracked source; exact ZIP bytes embedded in notebook; compiler prints effective thinking configuration.

Official compiler and local validator passed. Notebook cell executed locally and produced the identical archive. This is packaging validation, NOT a task-solving evaluation.

The compiler maps include_thoughts:false to enable_thinking:false. The 4096 thinking_budget does not establish 4096 reasoning tokens on this path. Sampling remains unchanged until measured model testing supports a change.

Docker responds outside the sandbox. GEMINI_API_KEY is absent from process and user environment. Project .venv references an unavailable Python executable. Validation used bundled Python 3.12 and an isolated work/check_deps installation of adk_submission 0.2.11 and google-adk 1.36.1.

No model tasks evaluated; no score improvement proven. Nothing pushed or submitted. Old 6918f2c4 hash is superseded for this candidate. Verify the actual Kaggle output against the full new hash before submission.

SHA256: f6392b8207a91a521c2434e1b5ce9f3f8d68d881298615725230d678bf04b3e3


## Evaluation report corrections (latest audit)

Live check: navin03/gemma4-swe-agent-eval remains QUEUED; submission 56579838 remains PENDING. No score or GPU allocation confirmed. No new notebook pushed and no GPU job launched by this review.

Fixed in scripts/make_eval_notebook.py and regenerated notebooks/eval/eval.ipynb:
- Parse the real JSONL schema: error and agent_patch_size; read patch and grading output from their saved files.
- Smoke checks accept real successful artifacts and reject the -1 grading sentinel. Empty-patch extraction remains explicitly unproven.
- Report only completed common task pairs and list missing pairs; reject duplicates.
- Reject stale/partial result reuse and separate output directories by mode.
- Remove inference projection: duration_seconds includes Phase 2 grading.
- Verify four L4 GPUs for full mode, not just GPU count.
- Validate requested task count and fail if the named smoke task is missing.
- Stop the vLLM server in finally after evaluation.
- Add prompt invariance test with sentinel reference/test patches; state that subprocess does not provide filesystem isolation.

All nine code cells parse. Both embedded archives match frozen releases. Both full-run guards fire. Regression fixtures use the real harness serializer and cover successful smoke, UTF-8 patch size, patch-apply failures, missing artifacts, negative grading sentinel, duplicates, and incomplete pairs.

The queued version has the old report code. Its final report may fail even after inference succeeded. Retrieve its raw JSONL, patches, test_outputs, traces and logs before considering another GPU run. report_cell.py can re-report those artifacts with RESULTS_ROOT, WORKING_DIR, CANDIDATE_DIRS, MODE and TASK_IDS set to the downloaded run.

Remaining limitations: prompt invariance is not an answer-key isolation guarantee. The subprocess shell runs on the host and can potentially reach attached answer-key files. Audit tool traces before trusting results and use genuine filesystem isolation for a stronger guarantee. Hardware/version metadata must be inspected after the queued job starts; no equivalence to grading is yet demonstrated. Statistical task-solving improvement remains unmeasured.


## Current pilot judge audit — 2026-09-27 (supersedes older pilot readiness claims)

Read reference/PILOT_JUDGE_REVIEW_2026-09-27.md and reference/CLAUDE_NEXT_EXECUTION.md.
Direct repairs applied to scripts/make_pilot_notebook.py, scripts/test_pilot_notebook.py and
notebooks/pilot/pilot.ipynb. Previous support files preserved in reference/pilot_pre_audit_2026-09-27/.

- DISPATCH_CONFIRM=False now prevents server construction/start and model evaluations. The notebook
  still requests a GPU session in metadata, so CPU setup is NOT quota-free.
- Server stop executes on run completion/failure/admission stop and partial startup failure.
- Phase instrumentation patches the actual swegemma.evaluate imports, preserving function signatures;
  agent-loop time is separate from agent phase setup and grading time.
- Saved controls fail closed; both controls must import the checkout, negative failed node IDs must
  explicitly pass under gold, and setup errors are rejected. Selected task-content drift aborts.
- Actual agent and grading setup paths repeat provenance probes, tie them to run IDs and persist them.
  These are fresh import probes with grading flags, NOT direct in-pytest instrumentation.
- Both candidate file sets and all unchanged bytes are checked. Report verifies record identity,
  duplicate results, patch character length and the -1 grading sentinel; heuristics are labelled.
- 78 offline assertions pass; logs: reference/pilot_judge_validation_2026-09-27.txt.
  The test uses simulated dependencies and the real Evaluator forwarding method, NOT a real GPU run.
- Both unchanged candidates compile; reference/pilot_compiler_audit_2026-09-27.txt.
  Local interpreter: bundled Python 3.12; the original .venv remains unusable on this host.
- Submitted v2 (6918f2c4...) scored 0.06. pilot_A/v2_reviewed (f6392b82...) is UNSCORED and
  unsubmitted. pilot_B (194b420a...) is also unscored. reference/public_baselines.json corrected.
- The 150-minute cap is an admission limit plus a planning reserve, not an OS-enforced deadline.
  The former 1.5-hour maximum estimate was unsupported. Stopping vLLM need not end the GPU session.

Live public browser review: leaderboard 0.15 first, 0.13 third; scored public notebooks shown top out
at 0.12. Exact top-team submitted code remains unverified. The public grader-audit author's no-edit
failure measurements are hypotheses for OUR trace audit, not our measured failure cause.

No Kaggle job, submission or watcher started in this audit. DISPATCH_CONFIRM remains False.
Existing hold on GPU spending remains. Next authorized measurement should be the four-run two-task
pilot, then review artifacts before any larger comparison. No score/rank improvement has been proven.


## Latest launch-transition review — 2026-09-27

Test-only fix after the launch card: explicitly simulate both dispatch states even with an enabled shipping notebook. 82 assertions pass; see reference/PILOT_LAUNCH_TRANSITION_REVIEW.md. Generator, notebook and frozen candidates unchanged; dispatch still False; no GPU or external actions. Original .venv fails because its base executable is absent, separately from swegemma requiring Python >=3.12.

## Result after three submissions (2026-09-29)

v1 0.06, v2 0.06, v3 0.06. Three prompt-only candidates, no measurable movement. At ~120 hidden tasks
0.06 is roughly 7 solved, and the gap between adjacent scores is a small number of tasks, so these are
not distinguishable from one another at this sample size. What this does establish is that further
blind prompt edits are not worth a submission slot: the local evaluation set has to start producing
signal first. The evalset screen is not yet usable for that (see reference/evalset_run2/RUN2_SUMMARY.md,
including the 2026-09-29 correction).


## Codex takeover correction, 2026-09-29
Equal displayed 0.06 scores do not prove identical solved tasks or statistical equivalence. Do not infer solved counts from the full hidden-task total; the public denominator is unverified. Exit 128 does not uniquely identify a missing patch. The CPU-only preflight now captures the actual command results to diagnose it. See HANDOFF.md latest entry.


## Real Git diagnosis by Codex, 2026-09-29
All eight selected patch/test_patch strings lack a terminal newline. Real `git apply --numstat` rejects all eight original strings with exit 128 and `corrupt patch at line ...`; appending exactly one newline makes all eight parse with exit 0. Evidence: reference/patch_newline_diagnostic.json. A synthetic real-git application regression in scripts/test_patch_transport_real_git.py confirms original bytes fail without changing the source and normalized bytes apply the intended edit. This disproves the claim that 128 uniquely means a missing/empty patch. The frozen GPU writer did not append a newline; the repaired copy_to writer does. Linux CPU reproduction and baseline/reference validation are running to confirm the end-to-end effect.

## Codex takeover: repaired comparison v2 launched
CPU preflight navin03/gemma4-control-preflight v1 COMPLETE; all 8 baseline/reference control arms agree with saved node outcomes, correct exit codes, cleanup and import preconditions. Exact original patch writer reproduced corrupt patch at line 20 despite successful file creation; missing final newline confirmed. Repaired eight-run comparison pushed exactly once as navin03/gemma4-swe-agent-compare version 2 with explicit user authorization after CPU passes. Notebook SHA256 97873af2210b0f26276efce30c14d1b4c0491320f008e983c20c174328bfdbbc. Frozen A/B unchanged. Launch record releases/compare_v2_prepared/LAUNCH_RECORD.json. Pre-push quota observed 01:27/30 hours. No competition submission and no watcher. Four Rich tasks only: no generalisation or leaderboard guarantee. Patch evidence bytes/sha256 fields represent pre-normalized text; created_bytes includes newline. Preserve frozen v1 and v2 for later review; do not apply reviewer v1 pin blindly to v2 artifacts.

## COMPARE RUN 2 + OFFLINE REPAIR 2026-09-30 (read reference/COMPARE_RUN2_REPAIR_2026-09-30.md)

Kernel `navin03/gemma4-swe-agent-compare` **version 2** completed. All eight baseline/reference
control arms passed and agreed with the saved screen. **Only 2 of 8 agent runs executed and neither
reached grading, so no candidate has a grade and neither won.** Evidence copied unmodified into
`reference/compare_run2/` (verified byte-identical to the Codex download), Codex's review into
`reference/compare_run2_review/`, this repair's outputs into `reference/compare_run2_analysis/`.
**The single authorized GPU launch has been used. Another run needs fresh authorization.**

**Corrected numbers (the launched report cell, replayed, reproduces the session CSV exactly first):**
`shell_edit_hints` A 54 -> 0 and B 2 -> 0; `first_source_edit_attempt_step` A 5 -> unavailable,
B 5 -> 8; `tool_errors` B 1 -> 43; `attribution` B empty_patch -> no_submission. New columns:
`acknowledged_source_edit_calls` **0 for both** (calls the tool accepted; no before/after file
comparison exists in these artifacts), `tmp_scratch_writes` A 54 / B 2, `rejected_tool_calls`
B 42, `repeated_identical_tool_calls` A 48 / B 39, `unparsed_tool_call_texts` B 4.
**No accepted edit-tool call was recorded for either candidate**, and B's final `git diff` against the
baseline came back empty (`agent_runner.py:766-780`). Together that establishes **no net tracked change
at the end of the run**, NOT that no file was ever written: an untracked file or a write-then-revert
leaves the same evidence.

**Established causes (do not re-derive):**
- The stop was an unmatched marker, not an observed fault: `"Agent completed execution without
  calling submit_patch."` fell through `_classify_one` to `'unclassified error'` -> environment.
  Setup provenance passed both probes, the sandbox was clean, and the same server had just carried A
  through 60 turns.
- B ended on the **nudge limit** (`max_nudges = 3`, `agent_runner.py:499,680`), not a budget.
- **WITHDRAWN 2026-09-30: the delimiters were NOT mismatched.** `<|tool_call>` and `<tool_call|>` are
  the correct tokens (verified in the real parser source). The four strings failed to parse because the
  non-streaming regex requires `call:<name>{<args>}` and the text carried a shell command with no
  braces. Call them **unparsed client-visible response text**, not pre-parser bytes. See
  `reference/COMPARE_RUN2_PARSER_2026-09-30.md`.
- The harness **misdiagnoses that as truncation**: `has_truncated_tool_call = '<|tool_call>' in
  last_assistant_text` (`agent_runner.py:695`) fires on the substring, while completions were 26-30
  tokens against `max_output_tokens: 8192`.
- The 42 rejections come from **google-adk, before `edit_file` runs**
  (`google/adk/tools/function_tool.py:170-188`): the argument dict is filtered to declared parameters,
  `old_string` is missing, and `{'error': ...}` is returned without invoking the tool. So they cost
  **no tool-call budget** (charged inside `@budget_gated`, `tools/base.py:62-92`) but **one LLM turn
  each**. The filter also discards the malformed extra keys, so the model is told only that
  `old_string` is missing. **That the uninformative text CAUSED the 41 identical retries is a
  hypothesis, not established**: low temperature on a near-identical prompt would look the same.
- `new_string` is **double-escaped** relative to the file (`r\"\"\"` and `\\x1b` where
  `rich/ansi.py` has `r"""` and `\x1b`), so even a correctly parsed call could not have matched.
- **A recorded no edit-tool call at all** and was not reacting to contradictory evidence: its
  reproduction exited 0 and its output **demonstrated the bug** (`Match: None` for all four private
  escape codes, the unfixed behaviour), which is not a passing fix. Stable from step 9, then 37 more
  identical runs.

**UNKNOWN, and not to be filled in:** whether the malformed arguments originate in the model or in
vLLM's `gemma4` tool parser. Raw completions are recorded only for steps that produced no parsed call,
and vLLM 0.19.1 is not in this project, so the parser cannot be read offline. `finish_reason` is
absent from every trace step, so the truncation branch cannot be audited from artifacts.

**Repair (diff: `reference/compare_run2_analysis/REPAIR_DIFF.patch`).** `compare_cells.py` gains a
one-entry `_CANDIDATE_NO_SUBMISSION_MARKERS` tier, checked **after** `_ENVIRONMENT_MARKERS` and before
the wrappers, returning a candidate outcome. Cleanup, provenance and unobserved-grading stops are
unchanged, and a candidate outcome still requires the server health probe. `make_pilot_notebook.py`
rewrites `trace_stats` around `observation_status()` (recognises a bare `{"error": ...}`, separates
rejected from failed) and `shell_write_targets()` (a `/tmp` heredoc is a scratch write, not a source
edit); `attribute()` gains `no_submission`. `ARM_FOR_LAUNCH = False`; the regenerated notebook
(`27b7f7aa...`) ships `DISPATCH_CONFIRM = False`.

**Suites, all executing generated cells:** compare dispatch **137/0** (was 108; six new tests use the
real termination string verbatim, D14 candidate outcome, D15 all 8 runs still dispatched, D16
environment still stops, D17 and D19 precedence across two sources and within one string, D18 cleanup
still stops with all eight rows intact), trace metrics **58/0** (new, runs the shipped cell over the
real traces), stop-logic 22/0 and 21/0, pilot 82/0 both targets, reviewer 97/0, policy 45/0, evalset
36/0, patch transport 1/0. **Mutation-tested:** six deliberate breakages, all six caught
(`reference/compare_run2_analysis/mutation_log_2026-09-30.txt`).

New test-harness capability: `make_env(server_healthy=True)` starts a real `ThreadingHTTPServer` on an
ephemeral port so the post-candidate health probe can genuinely succeed. Previously only the failing
branch was reachable, so no test could cover "continue to the next run".

**THE 2026-09-29 PROPOSAL IS WITHDRAWN. Read
`reference/COMPARE_RUN2_CAPTURE_PATH_2026-09-30.md`.** An ADK `after_model_callback` is a **post-parser**
capture point: it receives an `LlmResponse` whose `function_call.args` is already
`json.loads(tool_call.function.arguments)` (`lite_llm.py:1730`, invoked from `base_llm_flow.py:1270`).
It would have re-recorded the parsed dicts the run already has, for the price of a GPU session.

**Response path, proved by `scripts/capture_point_proof.py` (12/12):** the parse happens inside the
vLLM server process and the pre-parser text is never transmitted. ADK reproduces the recorded run-2
dict **byte-for-byte** from a JSON `arguments` string, so **the recorded dicts are the gemma4 parser's
output**, not raw completions, and ADK's own fallback parser (strict `raw_decode`, skipped whenever
structured `tool_calls` are present) cannot have produced them. The four raw texts at steps 51-57 are
the only pre-parser bytes the run preserved, and they exist precisely because nothing parsed them.

**Read the parser BEFORE requesting GPU.** vLLM is not on this machine and not in
`reference/harness_src/`, so its wire format is UNKNOWN and nothing assumes JSON.
`scripts/parser_fixture_harness.py --show-format` exits 2 and records that.
`reference/parser_fixtures/corpus.json` holds 12 content cases ready to run (p01 is the real failing
regex; p11 vs p12 discriminate "model omitted a parameter" from "transport ate one").
**Needs the user's go-ahead to download the `vllm==0.19.1` sdist from PyPI** (~10-40 MB, hash recorded,
unpacked read-only under `reference/vllm_0.19.1_src/`, never installed).

**Only if the source leaves it open:** the smallest GPU diagnostic is **one task, one candidate**
(`rich_3278` / B), capturing the server log via `VllmConfig.extra_args` if such a flag exists, plus
`litellm.log_raw_request_response` with header redaction; ~35-45 min, an estimate not a bound. Never an
eight-run rerun to discover a hook records parsed data.

## PARSER SETTLED 2026-09-30 (read reference/COMPARE_RUN2_PARSER_2026-09-30.md)

**The gemma4 tool-call format is NOT JSON.** `<|tool_call>call:name{key:<|"|>value<|"|>,n:42}<tool_call|>`:
unquoted keys, pairs split on `,`, key/value on the first `:`, and a value is a string only if it opens
with the `<|"|>` token; anything else is a bare value scanned to the next `,` `}` `]`. Non-streaming
extraction is one regex, `<\|tool_call>call:([\w\-\.]+)\{(.*?)\}<tool_call\|>`.

**Source, verified:** upstream sdist `vllm-0.19.1.tar.gz`, sha256
`9fb88ce6b50991eba41d183584f65f51d7f6015d86a42cdabf79c1c8bd5d66fa` (matches PyPI metadata), fetched
from the release URL without pip, **not installed**, 56 of 4,447 files extracted under
`reference/vllm_0.19.1_src/` with path-escape checks. Parser file sha256
`682b2152b76c031df9c58c3ffbb5b243945be5d8957ebdce00faef1b9de6b889`. In 0.19.1 the parsers live at
`vllm/tool_parsers/`, not `vllm/entrypoints/openai/tool_parsers/`.
**CAVEAT: the run used a wheel from the host dataset (`pip install --no-deps --force-reinstall`, 41
wheels), reporting version 0.19.1. Byte equivalence with upstream is NOT established.** The run also had
litellm 1.82.4 while this machine has 1.102.1; google-adk matches at 1.36.1.

**Path used: non-streaming `extract_tool_calls`.** `RunConfig(max_llm_calls=...)` sets no
`streaming_mode` (`agent_runner.py:516`), ADK defaults to `StreamingMode.NONE` (`run_config.py:225`),
and `base_llm_flow.py:1294` derives `stream` from it. Streaming was inspected and is informational only.

**Fixture results** (`scripts/gemma4_parser_fixtures.py`, 41 runs; `scripts/test_gemma4_parser_findings.py`,
**29 assertions 0 failures**, executing the real parser with documented non-parsing stubs):
- **With correct delimiters every case round-trips**, including the real `rich/ansi.py` regex with its
  backslashes, triple quotes, commas, colons, and Unicode/CJK/emoji. **The parser is not broken on this
  content, so content density is NOT the cause.** My content-dependence hypothesis is refuted for the
  correctly delimited case.
- Without the `<|"|>` token, values fragment on their own `,` `:` `]` and `old_string` is lost.
- **One mis-paired closing delimiter reproduces the recorded dictionary byte-for-byte**, keys and order:
  `new_string` opened with `<|"|>` and closed with a backtick, so the next `<|"|>` is eaten as its
  closing delimiter. **A possible mechanism, NOT proof of the model's output**, which was never recorded.

**Corrections:** [C1] shows only that ADK preserves a supplied `arguments` object through its
conversion; it does not identify the producer. `--enable-log-outputs` logs the PARSED form in `output:`,
but `entrypoints/logger.py::log_outputs` emits `output_token_ids` in full at INFO
(`chat_completion/serving.py:1622-1652`), and those ids decode to pre-parser text. `extra_args` does
reach the command line (`server.py:736`). `litellm.log_raw_request_response` is post-parser.

**No fix is justified yet.** A parser change is the grader's stack, not ours. A prompt rule against a
reconstruction is premature: the model emits `<|"|>` as a special token via the chat template
(`examples/tool_chat_template_gemma4.jinja`, extracted), so prompt-level leverage is unknown. Offline and
unblocked: (1) flag `rejected_tool_calls > 0` with `unparsed_tool_call_texts > 0` as a distinct
tool-call-encoding failure class; (2) read the chat template.

**Smallest pre-parser diagnostic, NOT requested and NOT authorized:** one task one candidate
(`rich_3278`/B), `extra_args=["--enable-log-requests","--enable-log-outputs"]`, decode `output_token_ids`
from `server_instance.log_path`. Prompts are logged only at DEBUG so INFO does not write them. ~35-45
min, an estimate not a bound.

**Also noted:** `pilot_manifest.json` does not record `STOP_REASON`; the re-derivation had to read it
from the session CSV. Worth adding to the MANIFEST block before the next run.

## A/S + TEMPERATURE RESULTS 2026-10-01 — still zero verified solves standing

Two GPU sessions ran on the same four Rich development tasks (`rich_3278`, `rich_3535`, `rich_3675`,
`rich_3942`), eight runs each. Raw artifacts and manifests:
`reference/ab_s_run_2026-10-01/` + `reference/ab_s_review/`, and
`reference/temperature_run_2026-10-01/` + `reference/temperature_review/`.

**Session 1, A vs S (adk-submission 0.2.11).** S solved `rich_3675`, A produced a graded-but-wrong patch
on it, and the other six runs exhausted the 60-turn budget with no patch. One decided pair, three
undecided. A's patch failed because `if tty_compatible is not None` short-circuits on
`TTY_COMPATIBLE=""`, so `isatty()` was never called; S special-cased `"1"` and `"0"` before the
`FORCE_COLOR` branch and passed 99 tests.

**Session 2, S vs S_temp, temperature 0.2 vs 0.7, nothing else changed (adk-submission 0.2.12).**
**All eight runs hit the turn budget. Zero patches, zero grading, zero solves on both sides, all four
pairs undecided.** S_temp repeated itself *more*, 148 adjacent identical calls against S's 56, so the
predeclared criteria failed in both clauses and S_temp is not advanced. See
`reference/temperature_review/TEMPERATURE_REPORT.md`.

**`rich_3675` did not re-solve.** Candidate S is byte-identical across both sessions. Two things differ
at once, ordinary sampling variation and adk-submission 0.2.11 vs 0.2.12, and the evidence cannot
separate them. **Treat the one solve as a single observation that has already failed to reproduce once.**

### The read_file argument defect (this changes how earlier "repetition" counts should be read)

`scripts/audit_temperature_arguments.py` compares recorded argument keys against the tool signatures in
`official_check.py`. Across six temperature traces, **162 `read_file` calls carry undeclared argument
names, 160 of them returning `status: ok`** — keys such as `start_line"` and `end_line"`, carrying the
trailing quote. **Unknown keys are dropped and the call still succeeds**, so the tool returns the default
first window instead of the requested range.

Verified in `S_temp/rich_3675`: the agent requested lines 910-950, then 910-960, of `rich/console.py` and
received the same 4,023 bytes from line 1 on every call. `scripts/test_shellread_candidate.py` replays
step 6 of `S_temp/rich_3278` through the real local ADK 1.36.1 `FunctionTool` and the malformed keys
arrive as `start_line=None, end_line=None` while correct keys keep the 1100-1357 range.

**Consequence: a malformed call can look like benign repetition rather than a rejected call.** The
`repeated_identical_*` counters and the "repeated read/reproduction calls" category in
`reference/ab_s_review/ungraded_diagnosis/UNGRADED_DIAGNOSIS.md` partly measure this defect, not idle
looping. This is the same mis-paired-delimiter mechanism as PARSER SETTLED above, surfacing on a tool
whose optional parameters fail silently instead of rejecting.

### Seed: do not overstate

A local interception showed the inspected ADK path omitting `seed` from the LiteLLM client kwargs, and
`lite_llm.py`'s generation mapping lists temperature, top_p, top_k and penalties without seed.
**That does not establish the historical runs' complete wire requests or the server's defaults.** Do not
write that those runs were unseeded. `pilot_manifest.json` records `seed_in_sampling: 42`, which is the
configured value, not an observation of inference.

### Where the binding failure actually sits

Across the temperature session: **0 of 8 runs produced any accepted modifying operation, and 7 of 8 never
attempted an edit.** That, not repetition, is the thing to move. `experiments/shellread_v1/` is prepared
(dispatch false, never launched) and targets the read defect, not the no-edit problem; its own PLAN.md
says so. **No submission on this evidence. The user wants verified solves first.**


## 2026-10-05 transport correction (supersedes historical generalisations)
Compiler 0.2.11 omitted seed and thinking_token_budget from client parameters;
0.2.12 forwards seed and a positive thinking budget when thinking is enabled.
Statements above saying these fields are never forwarded are version-specific,
not current universal claims. Frozen submitted v3/S disable thinking; the old
pilot B enabled it, and the new thinking_v2 ON package requests it. The new OFF
and ON packages have not been run. Forwarding is not server enforcement.
Private-grader compaction remains unknown. See experiments/thinking_v2/PREP.md.
