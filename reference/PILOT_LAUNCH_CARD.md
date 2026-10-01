# Pilot launch card — prepared 2026-09-27, NOT dispatched

Authorization state: **GPU hold in force.** Nothing pushed, submitted, or polled.

## Artifact identity (verified by recomputation, not copied from notes)
| artifact | sha256 | score evidence |
| --- | --- | --- |
| submitted v1 | `1e265aab08f5671f7e4a4f4ce42f4a3d3c274205d84fb2b235d53fd8fd42fd1d` | 0.06 (ref 56540226) |
| **submitted v2** | `6918f2c4adccccd9cdcaf51f354cd04aefb7d08eebef5f04d6c1ccb148cd5324` | **0.06** (ref 56579838) |
| pilot A = v2_reviewed | `f6392b8207a91a521c2434e1b5ce9f3f8d68d881298615725230d678bf04b3e3` | **never submitted; no score** |
| pilot B | `194b420a487c48f475267bf2a35b33a813c13bd2e2410e23d0ea405835bf913d` | never submitted; no score |
Pilot A/B hashes recomputed from `releases/pilot_A` and `releases/pilot_B` match the review exactly.

## Launch-ready files
| file | sha256 |
| --- | --- |
| `scripts/make_pilot_notebook.py` | `8d7d18d111da630f4e1e44525a38e71e6c4bd9a0a6c21b630e0ee06763143f00` |
| `scripts/test_pilot_notebook.py` | `5821182563db087a042943fca4d61950ad0cef59f1aff7f2421fd5ba57c8adf0` |
| `notebooks/pilot/pilot.ipynb` | `30b500e01d762bee70ec406f47bbe7d690a8e5cdbe40a3aa430cf0b0d3147d24` |
| `notebooks/pilot/kernel-metadata.json` | `85b6ca2acacdbfd0bcc379d8ee34516556a2bd38b517c92f6bd4c6be89111344` |

## Verified invariants (re-checked, not assumed)
- `DISPATCH_CONFIRM = False`; the vLLM cell is guarded by it, so **no server starts while disabled**.
- `server_instance.stop()` present on the completion/failure paths.
- Timing wrappers patch `swegemma.evaluate` as well as the source modules (Evaluator holds its own bindings).
- Task drift guard: `EXPECTED_TASK_HASHES` over repo/base_commit/problem_statement/hints/patch/test_patch.
  Recomputed locally: `requests_7309` and `rich_3471` **both match**. It asserts before model startup.
- kernel-metadata: `is_private: true`, `enable_internet: false`, `enable_gpu: true`,
  `machine_shape: NvidiaL4`, model source `google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2`.

## Cost statement (corrected)
`SESSION_CAP_MIN = 150` is an **admission limit**: it prevents a NEW run from starting, it does not kill
a run in flight or end the Kaggle session. A GPU notebook consumes quota during CPU setup as well, so the
preconditions are not free. Stopping vLLM does not necessarily terminate the session.
**The earlier "conservative maximum 1.5 h" figure was unsupported and is withdrawn.** No total wall-clock
bound is claimed here; the four runs are bounded per task by `max_time_minutes=10` plus setup and grading,
and actual hardware must be confirmed from the notebook's own GPU check at run time.

## Exact intended command (run ONLY after explicit four-run authorization)
1. set `DISPATCH_CONFIRM = True` in `scripts/make_pilot_notebook.py` (config cell source);
2. `python scripts/make_pilot_notebook.py`   # candidates unchanged
3. `python scripts/test_pilot_notebook.py`   # rerun guard/order tests
4. record the new `notebooks/pilot/pilot.ipynb` sha256
5. `python -m kaggle kernels push -p notebooks/pilot`   # exactly once
Authorized design is ONLY {requests_7309, rich_3471} x {A,B}, order A/B then B/A, identical budgets.

## What remains unmeasured
No pilot solve results exist. Neither pilot candidate has any score. The 82 offline assertions establish
execution reliability only: no Gemma served, no real sandbox, no task solved, and no evidence about why
the Docker-graded submissions scored 0.06.


## Launch-transition review (2026-09-27, latest)
Codex reproduced and fixed a test-harness defect: when the saved notebook was enabled,
tests requesting dispatch=False did not force it off. They now set either Boolean explicitly
in the simulated namespace. Four new assertions cover both paths with an enabled artifact.
82 passed, 0 failed; reference/pilot_launch_transition_validation_2026-09-27.txt.
This is a test-only change. The generator, notebook, metadata and frozen candidates are unchanged.
The pre-launch test command now works after enabling the shipping notebook. Separately inspect
the saved notebook's flag before pushing: tests intentionally override it in their namespaces.
The current saved flag remains False; GPU hold respected; no external actions.
See reference/PILOT_LAUNCH_TRANSITION_REVIEW.md and reference/CLAUDE_PILOT_LAUNCH_NEXT.md.

## DISPATCH RECORD — four-run pilot, 2026-09-27
Authorized by the user in chat (explicit confirmation, after I declined to treat a forwarded template
as authorization). Scope: ONLY {requests_7309, rich_3471} x {A,B}, order A/B then B/A.

| item | value |
| --- | --- |
| kernel | `navin03/gemma4-swe-agent-pilot` **version 1** (single push; no pre-existing kernel) |
| enabled notebook sha256 | `1321f80539a68bb8e7c35629a8b0960d26045fb7acd77d0959b8fe161019c322` |
| kernel-metadata sha256 | `85b6ca2acacdbfd0bcc379d8ee34516556a2bd38b517c92f6bd4c6be89111344` (unchanged by enabling) |
| generator sha256 | `1a95dd0d4cd6f1b4b4241413bc8356f4eae0907d0116d725d23934b48d76390b` |
| test suite sha256 | `5821182563db087a042943fca4d61950ad0cef59f1aff7f2421fd5ba57c8adf0` |
| candidate A | `f6392b8207a91a521c2434e1b5ce9f3f8d68d881298615725230d678bf04b3e3` (unchanged) |
| candidate B | `194b420a487c48f475267bf2a35b33a813c13bd2e2410e23d0ea405835bf913d` (unchanged) |
| disabled-notebook sha256 (pre-flip) | `30b500e01d762bee70ec406f47bbe7d690a8e5cdbe40a3aa430cf0b0d3147d24` |

Pre-push verification: notebook diff disabled->enabled touched **exactly one line in one cell**
(`DISPATCH_CONFIRM False -> True`); the saved notebook's shipping flag was read directly as `True`
(independent of the tests, which override it in their simulated namespaces); repaired suite
**82 passed, 0 failed**.

Environment note (factual, differs from the review): on this disk `.venv/Scripts/python.exe` **exists and
runs** (Python 3.11.9), and the suite passes 82/82 under BOTH it and the audit interpreter. What the venv
cannot do is `import swegemma` (requires >=3.12), which is why the official-compiler work used the
unpacked harness source. I could not reproduce a missing-executable failure.

Status at record time: QUEUED. No submission, no expanded comparison, no automatic rerun.

## QUEUE INVESTIGATION 2026-09-27 (read-only) + two corrections
Observed, signed-in via the browser extension, on the pilot's own page:
Logs "Queued...", Accelerator "GPU L4 x4", Environment "Latest Container Image", Output 0 B,
**no warning, no error, no scheduling message**. Account settings: Kaggle GPU 00:39 / 30 hrs,
TPU 00:00 / 20 hrs, storage 0 B. No other session running (12 notebooks, only the pilot active).
The "draft" label in the notebook list is expected until a version completes a run.

**Two claims of mine were stronger than the evidence:**
1. "GPU L4 x4" on the page is the **configured/requested** accelerator. It is **not** proof that four
   GPUs were allocated. Actual allocation will be established only from runtime metadata
   (`torch.cuda.device_count()`, device names, and the `tensor_parallel_size` vLLM really starts with),
   which the notebook's VERIFY cell captures.
2. I wrote that the 39-minute reading "shows the queued pilot has consumed no GPU time". **Withdrawn.**
   A single quota reading shows headroom, not what any particular run was charged. Establishing the
   charge needs a before/after delta, and no pre-push reading was taken.

External corroboration (not proof): two competitors report multi-hour L4x4 queues in the same window,
discussion/743600. No official host statement on L4 capacity. **Cause unknown**; no blocker is
attributable to our notebook. No evidence that repushing or changing code would help, so the run stays
untouched.

**v3 position:** this investigation produced **no performance evidence**. The working copy
`submission/` holds unmeasured prompt reliability fixes (heredoc /tmp scratch files after the observed
`write_file` path-traversal rejection; verify `<pkg>.__file__` before trusting a reproduction). They are
structurally validated by the official compiler but **not frozen, not measured, and not a proven
improvement**. Freezing is deliberately deferred so the pilot's findings can redirect them.
