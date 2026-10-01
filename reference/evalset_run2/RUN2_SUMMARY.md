# evalset kernel version 2 — COMPLETED (manifest read via browser; artifacts NOT yet downloaded)

Run      : navin03/gemma4-swe-agent-evalset, version 2 of 2, Accelerator None (CPU)
Result   : "Successfully ran in 4403.6s" (1h 13m 24s), Output 6.6 MB
Notebook : sha256 536d4fafd2d8251b52c5ca0aed2af09ed0efb9c8f57a33d9d425fc8557338891 (verified pre-push)
Policy   : sha256 f59934c6b6369e97d529f821c0284cc666d708e340b3654aafd16dfe5f5e37ee (embedded, matches local)
Identity : notebook owner navin03 / "NAVIN KUMAR"; CLI username was navin03 -> identities MATCH.
           The CLI failure was credential expiry ("Authentication required"), not an identity or slug problem.

## The sampling fix worked
candidates to screen: 40 -> fastapi 18, rich 16, requests 5, httpx 1
(the defective version 1 produced requests 0)
repo quota: fastapi 12, requests 2, rich 9, httpx 1 ; quota_respected = true

## httpx: excluded, dependency limitation (not a task defect)
hatchling preflight failed both ways: with deps -> trove-classifiers unavailable;
--no-deps -> hatch_vcs unavailable; import check -> ModuleNotFoundError.

## Screening outcome
screened 38 | VALID 20 | EXCLUDED 18
valid by repo: rich 13, fastapi 5, requests 2

## Allocation produced a DEGENERATE development set
holdout (12, filled exactly, diverse): rich_3180, rich_3938, rich_3894, fastapi_15280, fastapi_14873,
  fastapi_13537, requests_7427, rich_3486, rich_3521, fastapi_15800, fastapi_14479, requests_6644
dev (4, shortfall 8, ALL rich): rich_3061, rich_3782, rich_3942, rich_3675
shortfall: dev_short 8, holdout_short 0, unused_valid 0

CAUSE: allocate() fills held-out FIRST. With only 16 tasks surviving the quota cap (rich 13 capped
to 9), held-out consumed 12 and left 4 for development - and all four are rich, so the development
set has no repository diversity at all. This is a policy flaw, not a data problem: filling held-out
first was meant to protect it from previously studied tasks, but it starves dev when the valid pool
is small. DO NOT USE THIS SPLIT.

## Dominant exclusion reason: fastapi collection errors
11+ fastapi tasks excluded with "baseline: collection error; baseline: pytest interrupted/internal
error" (fastapi_14953, 14512, 11355, 15661, 14246, 15030, 14349, 14962, 14266, 14099, 14605...).
Others: requests_7505 and requests_6592 "JUnit errors present" in BOTH arms;
rich_3772 "no JUnit report; pytest exit 124" (timeout); rich_3930 collection error.

## NOT DONE - required before accepting any task
The per-arm evidence (arm.json, junit.xml, stdout/stderr, failure_details) lives in the 6.6 MB
output and has NOT been downloaded or inspected. No task is accepted. The Kaggle CLI must be
re-authenticated before the artifacts can be fetched.

---

## Failure-evidence inspection (done after the full 6.9 MB output was downloaded)

Artifacts: `reference/evalset_run2/output/` — 311 files, `evalset/screen.json` (38 rows),
`evalset_manifest.json`, `evalset_policy.py`, and `evalset/evidence/<task>/<arm>/{arm.json,junit.xml,
stdout.txt,stderr.txt}` for 37 tasks.

**Provenance check passed.** The `policy_sha256` recorded in the manifest
(`f59934c6b6369e97d529f821c0284cc666d708e340b3654aafd16dfe5f5e37ee`) matches the SHA-256 of the
`evalset_policy.py` that came back in the kernel output, so the run used the policy that was pushed.

### Every exclusion traced to a cause

| n | cause | tasks |
|---|---|---|
| 11 | collection error: `ModuleNotFoundError: No module named 'inline_snapshot'` | fastapi_11355, _14099, _14246, _14266, _14349, _14482, _14512, _14605, _14953, _14962, _15030 |
| 3 | JUnit errors, ~185-197 nodes per arm: pytest fixture `httpbin` unavailable (`pytest-httpbin` not installed) | requests_6592, requests_7505, requests_6757 |
| 1 | collection error: `No module named 'scripts.prepare_release'` | fastapi_15661 |
| 1 | baseline pytest exit 124 (timeout, zero nodes collected); reference completed with 22 passed | rich_3772 |
| 1 | reference arm produced no `stdout.txt` | rich_3930 |
| - | preflight: `hatchling` could not be installed offline (`trove-classifiers`, `hatch_vcs` missing) | all `encode/httpx` |

**This changes the reading of the run.** The exclusions are overwhelmingly *defects in my offline
environment build*, not properties of the tasks. In both `fastapi` and `requests` arms the patches
applied cleanly (`patch_rc == 0`, `test_patch_rc == 0`) and grading imported from the checkout
(`import_in_checkout == true`) — the suites simply could not import a test-only dependency.

Two consequences worth stating plainly:
* 14 of the 18 exclusions are one of **two missing packages**. If `inline_snapshot` and
  `pytest-httpbin` are installable from the competition wheel mirror, the usable pool goes from 20 to
  roughly 34 and a full 12/12 split becomes reachable.
* `requests_6592` is the sharpest example: baseline `{passed 134, failed 1, errored 185}`, reference
  `{passed 135, errored 185}`. The fail->pass signal is clean and the 185 errors are **identical in
  both arms**, so they are environmental noise rather than patch effects. The classifier's blanket
  "JUnit errors present" rejection is the right conservative default, but here it discards a task
  whose signal is intact. Not changing that rule without a re-run: relaxing it to "errors identical
  across arms" would be a post-hoc loosening fitted to this data.

### `allocate()` defect fixed

The degenerate dev=4 / holdout=12 split was my policy's fault, now corrected in
`scripts/evalset_policy.py`. `allocate()` used to fill held-out to its full capacity before
development saw the pool; when the pool is smaller than both capacities the whole shortfall landed
on development. New `_proportional_targets()` computes both targets up front and splits the
shortfall between them; unfillable held-out slots (too few unstudied tasks) now spill to
development rather than being wasted. Regression tests `[E9]`/`[E10]` pin both behaviours —
`scripts/test_evalset_policy.py` is now 45 assertions, all passing, and the generated notebook's
executed tests are 8/8 static + 28/28 executed.

Recomputed offline against the real run-2 rows, with the quota the run actually recorded
(`fastapi 12, rich 9, requests 2, httpx 1`), pool 16 after the cap:

```
dev  8  rich 5, fastapi 2, requests 1
hold 8  rich 4, fastapi 3, requests 1
```

Both sets now span all three repositories. Without the quota the same allocator yields 10/10.

### Status: no task accepted

This split is *not* adopted. It rests on 20 valid tasks of which 14 more were lost to two missing
packages, and a development set of 8 — 5 of them from one repository — is thin for iteration. The
recorded dev=4 split remains marked **DO NOT USE**. Deciding between (a) adopting the corrected 8/8
and (b) re-screening after adding the two packages is a call for the next session; option (b) needs
a fresh CPU kernel run and is not started.

---

## CORRECTION (2026-09-29): the exclusion table above is wrong

An external review caught it and the review is right. The table was built by a sweep that classified
tasks by *environment fault*, and I then presented it as the *exclusion* taxonomy. Those are two
different sets, and the mismatch hid real cases. Rebuilt below from `evalset/screen.json`, which is
the authoritative record of why each task was rejected.

**38 screened, 20 valid, 18 excluded.** Grouped by the reasons the classifier actually recorded:

| n | exclusion reasons | tasks | first cause in stdout |
|---|---|---|---|
| 10 | collection error both arms, exit 2 | fastapi_11355, _14099, _14246, _14266, _14349, _14482, _14512, _14953, _14962, _15030 | `No module named 'inline_snapshot'` |
| 1 | collection error both arms, exit 2 | fastapi_14605 | `No module named 'dirty_equals'` |
| 1 | baseline collection error, exit 2 | fastapi_15661 | `No module named 'scripts.prepare_release'` |
| 1 | baseline collection error, exit 2 | rich_3930 | `No module named 'rich._unicode_data'` |
| 1 | baseline exit 124, no JUnit report | rich_3772 | none recorded |
| 1 | JUnit errors both arms, reference exit 1 | requests_7505 | `httpbin` fixture |
| 1 | JUnit errors both arms, reference exit 1 | requests_6592 | `httpbin` fixture |
| 1 | baseline collection error exit 2, **plus** reference failing nodes and reference exit 1 | requests_6757 | mixed |
| 1 | **baseline pytest exit 0** | fastapi_14077 | none: baseline already passes |

### What I got wrong, specifically

* **"11 fastapi tasks, one cause" was wrong.** It is 10 on `inline_snapshot` and 1 on `dirty_equals`.
  Three distinct missing packages across the run, not two.
* **`fastapi_14077` was omitted entirely.** Baseline `3 passed`, reference `3 passed`, identical.
  The verification suite passes *without* the fix. That is not an environment gap. The likely cause is
  in my own control design: the control runs the whole test file rather than the task's declared
  FAIL_TO_PASS node list, so a discriminating parametrisation elsewhere would never be exercised.
  Unresolved, and it is the most important of these because it questions the control, not the sandbox.
* **`rich_3930` was described as "reference arm produced no stdout".** That was an artifact of my
  reading partial files while the download was still running. The real reason: baseline collection
  fails on `No module named 'rich._unicode_data'`, a module the reference patch *creates*. This is a
  legitimate property of a new-module task, not an environment defect, and no package install fixes
  it. It marks a structural limit of the classifier: for any task whose fix introduces a new module,
  the baseline can never collect, so `baseline exit 1` is unreachable.
* **`requests_6757` is not a clean `httpbin` case.** Baseline has a collection error (exit 2) *and*
  the reference arm has failing nodes and exits 1. Installing `pytest-httpbin` may not clear it.
* **"These tasks are fine under real grading" was unsupported and is withdrawn.** The Docker
  provisioning difference explains a plausible environment gap. It does not demonstrate that any of
  these tasks grade successfully. Nothing here has been graded under the real path.
* **"20 to roughly 34 usable" is withdrawn.** It assumed one fix resolves a class cleanly. Fixing the
  first missing dependency can expose a second, as `dirty_equals` already shows inside the group I
  had called uniform. No recovered-task count is predicted.
* **The access-failure cause is unresolved.** The earlier summary attributed it to credential expiry;
  the later note attributed it to a wrong kernel slug. The command logs from that session are not in
  hand to settle it, so it stays unresolved rather than being written up either way.
