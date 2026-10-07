# Verification comparison: initial results

Checked COMPLETE at 2026-10-03T02:19:05Z (07:49 IST). Download completed successfully. All 46 raw files hashed before analysis and reverified unchanged afterwards.

| Task | Candidate | Patch bytes | Grading exit | Result |
|---|---|---:|---:|---|
| rich_3675 | S_shellread | 723 | 1 | Graded, unsolved |
| rich_3675 | V | 536 | 1 | Graded, unsolved |
| rich_3942 | V | 0 | -1 | Ungraded, 60-turn budget exhausted |
| rich_3942 | S_shellread | 0 | -1 | Ungraded, 60-turn budget exhausted |

Zero solves for both candidates. One graded unsolved tie; one undecided pair. No measured solve improvement supports submission of V.

All four control arms agree with saved outcomes and cleaned up; both preconditions passed. Run CSV records cleanup for all runs and both setup probes for the two graded runs. Grading unobserved for the two ungraded runs. Server stopped.

Downloaded candidate files match frozen local files byte-for-byte. Manifest package hashes match the launch record. Local launched notebook remains 7ea8397683c47beaeb9302036a18546deb8ed642dcc4c900f61eba4b0c754919.

V's rich_3675 patch changes handling of TTY_COMPATIBLE but fails the empty-string auto-detection case: 98 tests pass, one fails. This is diagnostic evidence only, not an instruction to add the grader's answer to the candidate prompt. Detailed trace and answer-key-access audits have not yet been performed in this review.

No new launch, retry, candidate edit or competition submission.
