# Pilot review — 27 September 2026

Verdict: the previous notebook was not ready for an unattended GPU launch. The defects below are now fixed in the original project. The revised notebook passes 78 offline assertions and both unchanged candidates compile with the official compiler. It is ready for a limited, explicitly authorized four-run pilot, not a performance claim or a competition submission.

Project: `C:\Documents2\KaggleMLChallenge\The Gemma 4`.

## Findings and repairs

| Priority | Finding in the supplied implementation | Applied repair |
|---|---|---|
| P1 | `DISPATCH_CONFIRM=False` still started vLLM; no shutdown followed the runs. | Do not instantiate/start the server when disabled. Stop it after normal completion, evaluation failure, admission stop, and partial startup failure. |
| P1 | Timing wrappers patched the source modules, but `Evaluator` had imported its own function bindings. | Patch `swegemma.evaluate` as well as the source modules, preserve signatures, capture phase timings and the context's agent-loop timer separately. |
| P1 | Missing saved controls were printed and skipped. Only the negative control's import paths were checked. | Require evidence for each selected task; verify both controls' paths, a nonempty set of failed nodes, and explicit passes of those same nodes under gold. Reject setup errors. |
| P1 | A clean precondition sandbox was described as evidence for every actual agent/grading sandbox. | Observe and save imports inside each actual patched setup path; tie observations to task, candidate and phase; stop additional dispatch after failure. These are fresh import probes using grading flags, not direct in-pytest observations. |
| P2 | Checkout containment used string prefixes and could accept sibling paths. | Normalize paths and compare path components. |
| P2 | Candidate comparison only iterated A's files. | Require matching A/B file sets and exact sampling replacement, with every other file byte-identical. |
| P2 | Report logic could misclassify root-level source modules, miss compact JSON/nonzero command errors, and silently accept duplicate/wrong results or mismatched patch sizes. | Mark scratch attribution as suspected; keep termination errors separately; parse structured errors; validate task identity, result count, character length and grading sentinel. First-edit metrics are explicitly attempts. |
| P2 | The idempotency test replaced the modules before asserting on an old reference. | Re-execute the repair against the same modules and confirm all bindings really changed to the new wrapper with the same original. |
| P2 | The fake backend installer mistook `/wheels` for installation of `wheel`. | Match the actual final package argument. Test optional and required failures separately. |
| P2 | The public baseline table assigned submitted v2's 0.06 to unsubmitted pilot A. | Split the submitted release from the unscored reviewed candidate. |
| P2 | A prepared task could silently change in the live competition data. | Embed selected-task content fingerprints and fail before model startup on drift. Fingerprints match the local preparation; they are not retroactive proof of every old control's inputs. |

The session setting is an admission limit, not a hard wall-clock kill. The earlier “maximum 1.5 hours” claim is unsupported. A GPU notebook consumes quota during CPU setup too. Stopping vLLM does not necessarily terminate the Kaggle session itself.

## Verification actually performed

- Executed all generated code cells in notebook order with dependency stubs.
- Exercised disabled dispatch and enabled four-run dispatch, startup failure, evaluator failure, grading import failure, missing/invalid controls, changed task data, stale results and the admission limit.
- Executed the real harness `Evaluator._run_agent_sandbox` forwarding method, extracted from the local source, against instrumented simulated dependencies. This tests the imported-binding defect directly.
- Tested non-ASCII patch character counts, the `-1` sentinel, duplicates, wrong task identity, missing/mismatched patch content, command errors and scratch attribution.
- **78 assertions passed, 0 failed.** Log: `reference/pilot_judge_validation_2026-09-27.txt`.
- Recompiled both candidates with `adk_submission 0.2.11` / `google-adk 1.36.1`. Log: `reference/pilot_compiler_audit_2026-09-27.txt`; settings: `reference/effective_settings.json`.

These tests do not serve Gemma, create real Kaggle sandboxes, prove subprocess/Docker equivalence, or measure task-solving quality. The actual model run is still necessary.

## Artifact identity

| Artifact | SHA-256 | Score evidence |
|---|---|---|
| Submitted v2 | `6918f2c4adccccd9cdcaf51f354cd04aefb7d08eebef5f04d6c1ccb148cd5324` | 0.06 in the user's screenshot |
| Pilot A = v2_reviewed | `f6392b8207a91a521c2434e1b5ce9f3f8d68d881298615725230d678bf04b3e3` | Unsubmitted; no measured score |
| Pilot B | `194b420a487c48f475267bf2a35b33a813c13bd2e2410e23d0ea405835bf913d` | Unsubmitted; no measured score |

The only candidate content change is the `include_thoughts` line. It maps to `enable_thinking` for both coder and analyzer; file length decreases by one byte, which does not mean only one byte changes. The compiled additional model arguments do not contain an enforced 4096-token thinking budget. Wire-level behavior has not been observed in this audit.

Changed project files: `scripts/make_pilot_notebook.py`, `scripts/test_pilot_notebook.py`, regenerated `notebooks/pilot/pilot.ipynb` and metadata, `reference/public_baselines.json`, compiler settings/logs, and the latest audit note in `CLAUDE.md`. Original pre-audit support files are preserved in `reference/pilot_pre_audit_2026-09-27/`. Frozen candidate content is unchanged. No GPU job, submission, or polling was started.

## Live public research

Read through Kaggle's browser on 27 September, signed out:

- [Public leaderboard](https://www.kaggle.com/competitions/gemma-4-developer-agent/leaderboard): Makus 0.15; second and third 0.13, with further ties. Approximately half the test data is public and the rest determines final standings. This does not establish any particular future prize threshold.
- [Public notebooks sorted by score](https://www.kaggle.com/competitions/gemma-4-developer-agent/code?competitionId=149921&sortBy=scoreDescending&excludeNonAccessedDatasources=true): the highest displayed scored notebooks were Roman Rozen and Pathfinder at 0.12. No verified implementation of the 0.15 leader was found in that view.
- [Pathfinder](https://www.kaggle.com/code/mizeroluckygall/pathfinder-gemma-4-agent-eda-baseline): public code uses coder plus analyzer, full issue input to the analyzer, exact API names, source examples, small edits and verification. Sampling is 8192 output tokens, temperature 0.2 and `include_thoughts:false`. It overlaps substantially with our design. Its narrative says v2 pending while the listing shows 0.12; pin exact versions before attributing a score to extracted code.
- [Busya PRIME's grader audit](https://www.kaggle.com/code/busyaprime/119-of-129-sound-the-gemma-4-grader-rebuilt), version 22: the author reports that many failures had already located relevant source and 42/68 runs made no successful edit and produced no patch. These are the author's measurements, not ours; the notebook describes substantial reproduction limits and an independently implemented grader. Use it to motivate a trace question, not to claim our failure cause or to adopt its 119-task validity count.

## Remaining limitations that affect the next decision

1. No pilot solve results exist. Equal public scores do not prove v1/v2 solved the same tasks. The subprocess import defect does not establish why the Docker-graded submission scored 0.06.
2. A and B compare thinking settings on a reviewed, unsubmitted candidate. They are not a paired evaluation of submitted v2 versus v3.
3. The two-task pilot is for execution and behavioral diagnosis. Eight screened tasks remain development data and are dominated by a few repositories.
4. Prompt invariance is not filesystem isolation. Audit traces for reference/test-patch or other answer-key access; invalidate contaminated runs.
5. Metrics such as first edit attempt, shell-edit hints and suspected scratch patches require human trace review. They do not prove causal failure attribution.
6. Fixed seeds, a shared server and alternating order do not eliminate run variability. A later paired comparison needs enough tasks, explicit wins/losses and a held-out check.

No rank guarantee is possible. The immediate objective is to obtain trustworthy failures, then improve the highest-frequency recoverable failure without changing several variables at once.
