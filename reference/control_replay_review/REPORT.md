# CPU control replay: six controls reproduced

Kernel `navin03/gemma4-control-replay`, version 1, was pushed on
2026-10-07 at 04:18:37 UTC. The saved results contain six accepted control
arms. This report describes those artifacts; it is not a live status check.

| Task | Baseline exit | Reference exit | Nodes per arm | Skipped per arm | Workspace normalization |
| --- | --- | --- | --- | --- | --- |
| fastapi_15280 | 1 | 0 | 1 | 0 | Not needed |
| requests_7427 | 1 | 0 | 229 | 13 | One identity in each arm |
| rich_3894 | 1 | 0 | 46 | 4 | Not needed |

Both Requests arms contain a test parameter with their temporary workspace
path. Replacing each recorded workspace root preserves the relative path
and makes the complete expected and observed node/outcome maps agree.
Neither arm has a normalization collision. Targets retain the expected
baseline-fails/reference-passes outcomes, and cleanup passed on all six arms.

## Integrity and scope

- [raw_sha256.json](raw_sha256.json) records all 27 downloaded files.
- [Raw evidence](../control_replay_run_2026-10-07/) remains separate from this review.
- The compiler record reports version 0.2.12 with matching Python-file hashes.
- This CPU-only notebook has no model startup or candidate dispatch cell.
- No candidate run directories or exposure ledger were produced.

This verifies these controls under the replay environment. It does not
measure V3 or ON task-solving performance, establish private-grader parity,
or predict a leaderboard score. GPU quota readings are account-level
observations and must not be treated as this CPU run's duration or cost.

## Next experiment

The separately prepared `final_validation_v2` packet retains the same
three tasks, both frozen packages, the pinned image, and the six-run order.
Its control and compiler-check cells match the CPU-tested cells.
Its dispatch flag remains false in the prepared artifact. A GPU launch and
a competition submission are separate actions; this report authorizes neither.
