# V4 runtime evidence audit

Prepared 2026-10-17. Offline inspection only; no submission or inference run.

`archive_config.json` records hashes and root evaluation-config presence for the frozen V3 and V4 ZIPs. Neither contains `eval_config.yaml` or `eval_config.yml`. This does not establish the effective grader defaults, whether another configuration source is used, or the cause of the timeout.

The saved full submission response in `../submission_v4_error_2026-10-14/submissions.json` reports that V4 exceeded allowed runtime. Its missing score is not a zero score. The archive inspection is separate evidence, not a causal diagnosis.

`scenarios.json` contains explicit hypothetical serial-runtime calculations. Task counts, setup costs and per-task minutes are assumptions, not measurements or estimates of the hidden dataset. The 720-minute input is a scenario budget. Startup, per-task setup and reserve are charged separately. These examples neither certify a candidate nor establish an enforced runtime cap.

Next: verify how the supported submission format supplies effective limits, then measure a bounded candidate under those limits before another submission. Preserve the frozen packages as comparison evidence.
