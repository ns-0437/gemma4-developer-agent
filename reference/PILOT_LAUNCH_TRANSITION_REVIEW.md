# Launch-transition review — 27 September 2026

Verdict: ready for the limited four-run pilot once the user explicitly authorizes GPU use.

All eight file hashes from the prior audit initially matched. The handoff accurately preserved
the candidate distinction, quota caveats and GPU hold. No repeat compiler check was needed.

One test defect was found in Codex's previous changes: run_cells only changed False to True.
When the shipping notebook was already True, tests requesting disabled dispatch instead ran
the enabled path. Reproduction failed three disabled-server assertions using simulated dependencies.
This was a pre-launch test failure, not evidence that the notebook ignored its actual False flag.

Fixed run_cells to set the requested Boolean explicitly in either direction. Added four checks
for disabled/enabled behavior with an enabled artifact. The full suite now passes 82 assertions.
No Gemma model, real sandbox or GPU was used. Test results do not establish performance.

Updated script SHA-256:
5821182563db087a042943fca4d61950ad0cef59f1aff7f2421fd5ba57c8adf0

Generator, notebook, metadata, compiler evidence and candidates are unchanged. Existing audit
manifest remains a historical snapshot; pilot_launch_transition_manifest_2026-09-27.json records
the current state. Updated PILOT_LAUNCH_CARD.md contains the new test hash. Previous test script
is preserved in reference/pilot_pre_dispatch_test_fix_2026-09-27/.

Environment correction: invoking .venv/Scripts/python.exe --version fails with 'No Python at ...'
for its configured WindowsApps executable. This is a missing base interpreter. Independently,
swegemma metadata requires >=3.12 and adk_submission metadata requires >=3.11. The former
requirement is not the cause of that launch error.

No Kaggle commands, polling, submissions or GPU launches occurred in this review. Dispatch remains
False. Stop expanding the local review unless new evidence warrants it. Obtain the real four-run
trace packet next, then decide on one measured improvement.
