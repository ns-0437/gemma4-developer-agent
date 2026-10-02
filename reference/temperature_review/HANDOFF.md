# Handoff: temperature comparison analysed, read-interface experiment prepared

Written 2026-10-02. Paste this file as the first message of the new chat. It supersedes
`reference/ab_s_review/HANDOFF.md`; that session's artifacts and report remain on disk and remain valid.

## Status

Nothing is pending. No retry, repush, candidate edit or submission was made.

| | |
|---|---|
| last kernel | `navin03/gemma4-swe-agent-temperature`, version 1, **COMPLETE** (checked 2026-10-01T05:45:45Z) |
| its download | finished and preserved, 65 files, hashes re-verified before and after analysis, 0 mismatches |
| next experiment | `experiments/shellread_v1/`, **prepared, dispatch false, never launched** |
| standing decision | **no submission.** Three submissions have each scored 0.06; no verified solve stands |
| GPU quota | `04:26 / 30 hrs` read before the temperature launch; not re-read since |

## Result of the two 2026-10-01 sessions

Same four Rich development tasks both times: `rich_3278`, `rich_3535`, `rich_3675`, `rich_3942`.

| session | candidate | solved | graded unsolved | ungraded | decided pairs |
|---|---|---|---|---|---|
| A/S, adk-submission 0.2.11 | A | 0 | 1 (`rich_3675`) | 3 | 1 of 4 |
| | S | **1** (`rich_3675`) | 0 | 3 | |
| temperature, adk-submission 0.2.12 | S | **0** | 0 | 4 | **0 of 4** |
| | S_temp (0.7) | **0** | 0 | 4 | |

**The temperature session produced no patches at all.** S_temp also repeated itself more than S, 148
adjacent identical calls against 56, so the predeclared criteria failed in both clauses and S_temp is
not advanced. **`rich_3675` was carried as a regression check and did not re-solve under a
byte-identical S.** Sampling variation and the 0.2.11 to 0.2.12 change both differ between the sessions
and this evidence cannot separate them, so treat the one solve as a single observation that has already
failed to reproduce once.

## The finding that matters most

`read_file` silently drops undeclared argument keys and still returns `status: ok`. Across six
temperature traces there are **162 such calls, 160 of them successful**, with keys like `start_line"` and
`end_line"` carrying a trailing quote. The tool then answers with the default first window.

Verified: in `S_temp/rich_3675` the agent asked for lines 910-950, then 910-960, of `rich/console.py` and
received the same 4,023 bytes from line 1 every time. `scripts/test_shellread_candidate.py` replays the
recorded arguments through the real local ADK 1.36.1 `FunctionTool` and reproduces the drop.

**So a malformed call can present as benign repetition rather than as a rejected call**, and the
`repeated_identical_*` counters partly measure this defect. It is the same mis-paired-delimiter mechanism
as the PARSER SETTLED section of CLAUDE.md, surfacing on a tool whose optional parameters fail silently.

## Where the binding failure sits

Across the temperature session: **0 of 8 runs produced any accepted modifying operation and 7 of 8 never
attempted an edit.** Repetition is a symptom; failing to reach an edit is the thing to move.
`experiments/shellread_v1/` targets the read defect, not the no-edit problem, and its PLAN.md says so.

## Paths

| what | path |
|---|---|
| temperature raw artifacts, unmodified | `reference/temperature_run_2026-10-01/` |
| manifest recorded before analysis | `reference/temperature_review/raw_sha256.json` |
| report | `reference/temperature_review/TEMPERATURE_REPORT.md` |
| argument audit | `reference/temperature_review/argument_audit.json` |
| A/S raw artifacts and report | `reference/ab_s_run_2026-10-01/`, `reference/ab_s_review/` |
| A/S ungraded diagnosis | `reference/ab_s_review/ungraded_diagnosis/UNGRADED_DIAGNOSIS.md` |
| prepared next experiment | `experiments/shellread_v1/PLAN.md` |
| project working rules and history | `CLAUDE.md` |

## Hashes

| artifact | sha256 |
|---|---|
| launched temperature notebook | `ff22c79682ec29e90c795bc61cde205e2f2ddf3cce1aa52c1ee4d9c08bcb5f26` |
| candidate S, frozen baseline | `8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07` |
| candidate S_temp | `4f1ff61c1d8acf0287bc786c697e3ff4949a8624f3c49ec01b815cd6742f366c` |
| candidate S_shellread, prepared | `8e3f9286ce0f2399c32dfa452e129a12fd48cdd657b88ea6c76d3c48c36956ae` |
| prepared shellread notebook | `71ddec6ae5a66fadf037a27a1701ee2dd7870563dc93f11e4c10edff89afa768` |

Temperature identity was verified directly: launched notebook and both archive digests match, the
downloaded candidate trees are byte-identical to the frozen zips, and the only difference between the
arms is `configs/sampling.yaml` temperature.

## Caveat on the review script

`scripts/review_stage1.py` pins `FROZEN_TASK = "rich_3278"`, `FROZEN_CANDIDATE = "R"` and a one-entry
`FROZEN_ORDER`, and asserts `manifest tasks == ['rich_3278']`. It aborts on any multi-task two-candidate
set, including both 2026-10-01 sessions. **Do not loosen those checks silently.** Both sessions were
reviewed by direct hash and byte comparison plus a one-off read-only trace summarizer kept beside its
write-up in `reference/ab_s_review/ungraded_diagnosis/`.

## Evidence limits to restate in any report

Four selected Textualize/rich tasks say nothing about the repository generally or about the leaderboard;
the hidden mix is roughly 67 fastapi, 48 rich, 13 requests and 1 httpx. Exit `-1` means grading did not
run and is not a test verdict. An ungraded side makes a pair undecided, never an opponent win, and is
never dropped from the denominator. Grading-side provenance was unobserved on every ungraded run because
grading never ran, which is unexercised rather than faulty. The subprocess backend is not a filesystem
isolation boundary, so absence of answer-key hits in a trace does not prove isolation. Do not state that
past runs were unseeded; see the seed note in CLAUDE.md.

## Standing constraints

No GPU launch, Kaggle push, competition submission or continuous polling without explicit authorization
in the user's own words. Preserve raw artifacts and frozen releases; write analysis outside the raw
directories. **The user wants evidence of improved solves before another submission.**
