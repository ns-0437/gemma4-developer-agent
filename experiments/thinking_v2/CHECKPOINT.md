# CHECKPOINT — thinking_v2 LAUNCHED and ERRORED; comparison unmeasured

Updated 2026-10-06. **The experiment WAS launched:** armed with `DISPATCH_CONFIRM = True`, pushed
once as kernel version 1 at 2026-10-05T16:56:29Z, and it reached **ERROR** before any evaluation ran.
No competition submission was made. The local armed notebook remains armed
(`38644eb6...`); the preserved disabled copy remains `93dc5836...`.

Environment repair is prepared, **disabled**, in `experiments/thinking_v3_env/`.

## State

The pre-launch review found no launch blockers and the launch itself was clean. The failure was an
environment one: the wheelhouse install could not run under the image this kernel received.

## Verified this session (all re-derived, not taken from the packet)

| check | result |
|---|---|
| OFF.zip / ON.zip / notebook sha256 | match the three pinned values exactly |
| zip members | 5 each, identical sets; **only `configs/sampling.yaml` differs** |
| the difference | `thinking_budget 4096 -> 1024`, `include_thoughts false -> true`; both arms `max_output_tokens: 4096`, temp 0.2, top_p 0.95, top_k 40, seed 42 |
| `candidate_OFF/` and `candidate_ON/` dirs | byte-identical to their zips |
| embedded notebook payloads | 2 base64 blobs, decoding to exactly the two pinned zip hashes, no extras |
| `ORDER` in notebook | `[(rich_3675,OFF),(rich_3675,ON),(rich_3278,ON),(rich_3278,OFF)]`, matches plan |
| dispatch | `DISPATCH_CONFIRM = False` present; no `= True` anywhere |
| compiler gate | per-file sha256 of every compiler module + version `0.2.12`, enforced by `assert record['matches'], 'Runtime compiler drift: refuse model startup'` (hard stop before server startup). The wheel sha256 is not the gate; per-file hashes are, which is equivalent or stronger |
| budgets in notebook | `max_turns=60`, `max_tool_calls=100`, `max_time_minutes=10.0`, `SESSION_CAP_MIN=150`, `RUN_RESERVE_MIN=25`, `token_threshold=20480` |
| kernel metadata | `navin03/gemma4-swe-agent-thinking-v2`, private, GPU, NvidiaL4, internet off, correct dataset/competition/model sources |
| frozen artifacts | 6 of 6 re-verified: five launched notebooks + holdout freeze `2208694094...` |
| verification raw artifacts | 46 of 46 match `reference/verification_review/raw_sha256.json` |
| existing notebook check | `scripts/test_thinking_v2_notebook.py` PASS (disabled mode, four-run order, lifecycle, compiler/candidate drift, controls, provenance; simulated dependencies) |

Not re-run: the transport test, already recorded in `MATCHED_TRANSPORT.json`. No dependency was
installed. No test battery was re-run beyond the one notebook check.

## Evidence paths

- packet: `experiments/thinking_v2/LAUNCH_PACKET.md`, `NOTEBOOK_PREPARED.json`, `FINAL_CHECKS.json`
- transport: `experiments/thinking_v2/MATCHED_TRANSPORT.json`, `transport_0_2_1{1,2}.json`
- notebook: `notebooks/thinking_v2/thinking_v2.ipynb` + `kernel-metadata.json`
- prior session: `reference/verification_review/REPORT.md`, `TRACE_DIAGNOSIS.md`

## Next action

**Kernel version 1 = ERROR at 2026-10-06T01:58:33Z, before any run.** Kaggle's image moved from
Python 3.12 to 3.13 and the host wheelhouse's cp312-only `apache_tvm_ffi` wheel cannot install, so
cell 2 raised `SystemExit: wheelhouse install failed rc=1` at t=11 s. All four rows unattempted; no
solves, no graded failures, no ungraded outcomes. GPU spent 0.01 h. Report:
`reference/thinking_v2_review/REPORT.md`, raw log hashed in that directory's `raw_sha256.json`.

Identity confirmed at content level (armed flag, both candidate payloads, ORDER). The pulled notebook
is not byte-identical to `38644eb6...` because Kaggle re-serializes notebook JSON; the local armed file
still hashes `38644eb6...` and the preserved disabled copy `93dc5836...`.

**Decision needed from the user before anything else.** The candidate fix is
`docker_image_pinning_type: "original"` in `notebooks/thinking_v2/kernel-metadata.json` (valid values
`original`/`latest`, confirmed against the installed Kaggle API). That edits a launched artifact and
needs a fresh single authorization and a re-verified armed hash. The alternative is to wait for the
host to publish a cp313 wheel, which is outside our control. **Nothing was changed, retried or
resubmitted.**

## Standing limits

Total completion tokens cannot prove thinking-budget enforcement; absent recorded reasoning does not
prove thinking was off. The 4,096 cap covers reasoning plus final content, so 1024 reserves nothing.
Private-grader compaction is unknown. Two selected Rich tasks cannot predict leaderboard performance.
Protected holdout untouched.
