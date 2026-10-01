# Diagnosis of the six ungraded runs, offline

Written 2026-10-01. Inputs: `reference/ab_s_run_2026-10-01/pilot/*/traces/*.json`, `summary.json`,
`task_results.jsonl`, `patches/`, `test_outputs/`. All 69 raw files re-hashed against
`reference/ab_s_review/raw_sha256.json` before and after this analysis: **0 mismatches, nothing in the
raw directory was written.** The two one-off summarizers used are copied beside this file. No change was
made to `scripts/review_stage1.py` and no new testing framework was built.

Budget, as printed in every task prompt: 10 min wall, 100 tool calls, **60 loop turns**. Turns were the
binding limit in all six runs; a turn carrying prose and no tool call still consumes one.

## Six-row diagnosis

| run | first localization | first edit attempt | what consumed the turns | exact rejection / error | accepted writes vs change evidence | last useful action | termination |
|---|---|---|---|---|---|---|---|
| **A / rich_3278** | turn 3, `git grep -n -F "ANSI" -- '*.py'` | **never** | **52 byte-identical adjacent `run_command` calls** (turns 11-62) of one `python3 -c` regex probe; observation identical (`['7', '8']`) for 51 of them, no interleaved nudge | 2 earlier probes returned a `re.error` traceback (unbalanced paren); final turn `Turn budget exhausted (60 turns)` | 0 attempted, 0 accepted, 0 change | turn 11, the probe that first returned the correct match list | turns budget; no patch file |
| **A / rich_3535** | turn 3, `git grep -n -F "single-width" -- '*.py'` | **never** | two adjacent blocks of **18 identical `cat > /tmp/repro.py` heredoc-plus-python calls** (turns 26-43 and 46-63), each `status: ok` with unchanged stdout; 35 duplicate calls, all adjacent | 4x `CommandError exit_code=1` with empty stdout and stderr; final turn turns-budget | 0 attempted, 0 accepted; repro scripts went to `/tmp`, repository untouched | turns 44-45, `git grep single_cell_widths` then `read_file rich/cells.py`, the correct location | turns budget; no patch file |
| **S / rich_3535** | turn 3, `git grep -n -F -- "single-width" -- '*.py'` | **never** | **43 byte-identical adjacent calls** of `python3 -c "print(hex(ord(' ')))"` (turns 20-62), every one `status: ok` returning `0x20` | 7x `exit_code=1` with empty output, 1 python traceback; final turn turns-budget | 0 attempted, 0 accepted, 0 change | turns 18-19, the two preceding `ord()` probes that were still informative | turns budget; no patch file |
| **S / rich_3278** | turn 3, `grep -rn "ANSI" .` | turn 11, `edit_file rich/ansi.py` | **46 of 60 turns are rejected `edit_file` calls**, in adjacent blocks of 5, 28 and 11. Every one carries the same malformation: the argument object was split on its own content, producing junk keys such as `"re_ansi = re.compi…"` and `"](.*?)\\x1b\\\\)|\n"`, leaving `old_string` absent. Two key-shape variants, 33 + 13 calls | `Invoking edit_file() failed as the following mandatory input parameters are not present: old_string` (46x); also 1x `FileWriteError: Path traversal detected: '/tmp/repro.py' escapes workspace root` on `write_file` | **47 edits attempted, 0 accepted, 0 change evidence.** No `git diff` was ever run | turn 49, a `/tmp` repro via `run_command` that correctly showed `\x1b7` and `\x1b8` surviving tokenization | turns budget; no patch file |
| **A / rich_3942** | turn 3, `git grep -n -F -- "Markdown" -- '*/markdown.py'` | **never** | not a tight loop: 39 distinct signatures, 10 adjacent and 8 separated duplicates. Turns went to **`git log` archaeology** (`--grep="markdown"`, `-p <sha>`, `-S`, varying `-n`), 3 prose-only turns that drew system nudges, and re-running `pytest tests/test_markdown.py` (7 passed, i.e. it confirmed the unmodified tree) | 2x `fatal: unrecognized argument` from a malformed `git log -n 20 --rich/markdown.py`, 3x `exit_code=1` empty; final turn turns-budget | 0 attempted, 0 accepted, 0 change | turn 24, `git log -n 1 --patch 072150a7 -- rich/markdown.py`, the one commit genuinely about markdown styling | turns budget on yet another `git log`; no patch file |
| **S / rich_3942** | turn 4, `find rich -name "*markdown*"` | **turn 65, the final turn** | **zero identical adjacent repeats, 47 distinct signatures.** Turns went to 12 paged `read_file rich/markdown.py` calls (legitimate, 150-line limit) plus 3 re-reads from line 1, roughly 25 `git log` / `git grep` turns hunting the intended style values, 3 `code_analyzer` sub-agent calls, 3 prose-only turns each answered by `Please continue your work using the available tools`, and 2 repro heredocs (the first died on an unterminated quote, the second rendered fine) | 1x `git: fatal: unrecognized argument`, 1x `/bin/bash: unexpected EOF while looking for matching '"'`, then on turn 65 the `edit_file` itself returned `Turn budget exhausted (60 turns)` | 1 attempted, **0 accepted** — and that call was *well-formed*, with a plausible `old_string` on `rich/default_styles.py`. It was killed by the budget, not rejected on its merits | turn 55, `tail -n 50 rich/default_styles.py`, which located the `markdown.*` style block it then tried to edit | turns budget, one turn before its only edit could execute; no patch file |

## Against the five categories asked for

| category | runs |
|---|---|
| 1. repeated read / reproduction calls | **A/3278, A/3535, S/3535** — 3 runs, 127 wasted turns |
| 2. rejected malformed tool calls | **S/3278** — 46 turns. Minor instances only elsewhere: 1-2 bad `git` arguments or shell quotes each in A/3942 and S/3942 |
| 3. executed edits that failed | **none in any of the six.** No edit ever reached the filesystem and failed on its own terms |
| 4. accepted writes without a surviving patch | **none.** Accepted modifying operations = 0 across all six. The only writes attempted were repro scripts under `/tmp`, and S/3278's `write_file` attempt at one was refused for path traversal |
| 5. investigation that never reached an edit | **A/3942** (never attempted) and **S/3942** (attempted on the last turn, never executed) |

On `rich_3942` / S specifically: its zero repeat count does not mean it made progress. Its turns went to
search over an underspecified issue, not to a loop. That problem statement is 75 characters, "Update to
markdown styles / Updates to Markdown styling", naming no target values, so the run spent roughly half
its budget trying to recover the intended styling from git history and only reached the file it needed
to change at turn 55.

## Contrast with the one successful run, S / rich_3675

20 tool calls, 0 duplicates, strictly forward: `git grep is_terminal` (turn 3) → paged
`read_file rich/console.py` → repro via `run_command` → **one** `edit_file` (turn 16) → `py_compile` →
run the repo's own `tests/test_console.py` → `submit_patch` (turn 22). A/rich_3675 has the same shape in
10 calls. The two runs that produced a patch are exactly the two that attempted an edit early (turn 8 and
turn 16), on the one task whose statement named the thing to implement. None of the six ungraded runs
reached an accepted edit at all.

## Issue-relative correctness of the two graded patches

`rich_3675`'s problem statement is one line, "Implement new `TTY_COMPATIBLE` environment variable", plus
a link the offline sandbox could not fetch. Correctness is therefore judged against grading evidence
already downloaded, not against the statement.

- **A, `test_exit_code: 1`, `resolved: false`.** `if tty_compatible is not None: self._force_terminal = True; return True`,
  placed after the `FORCE_COLOR` branch. The graded test, visible in
  `A__rich_3675/test_outputs/rich_3675.log` as `tests/test_console.py::test_tty_compatible`, builds
  `Console(file=FakeTTY(), _environ={"TTY_COMPATIBLE": ""})` and asserts `console.file.called_isatty`.
  A's `is not None` short-circuits on the empty string, `isatty()` is never called, the assertion fails.
  **1 failed, 98 passed.** The defect is precisely the empty-value case.
- **S, `test_exit_code: 0`, `resolved: true`, 99 passed.** `"1"` forces terminal, `"0"` forces
  non-terminal, any other value falls through to `FORCE_COLOR` and `isatty()`, and the block sits before
  the `FORCE_COLOR` branch so it takes precedence. That satisfies all three cases the visible test
  exercises and leaves the 98 pre-existing tests passing.

No protected held-out task was inspected. Both of these are graded development tasks whose outputs were
already in hand.

## Facts, explanations, unknowns

**Observed.** All six hit the 60-turn limit with 0 accepted modifying operations and no patch file. Three
ended inside a byte-identical adjacent call block (52, 43, 18+18) whose observation never changed and
which no harness nudge interrupted. One burned 46 turns on a single reproducible `edit_file` argument
malformation. Two did unbounded history search on the shortest problem statement of the four, and one of
those got a well-formed edit in only on the turn the budget ended. Both candidates ship identical
`configs/sampling.yaml`: `temperature 0.2, top_p 0.95, top_k 40, seed 42`, no penalties.

**Plausible, not established.** (a) The identical-call loops look like a decoding fixed point: with a near
greedy decode, a fixed seed and an observation that does not change, the next context is nearly the one
that produced the call, so the same call is again the most likely continuation. (b) S/3278's malformation
plausibly comes from `edit_file` arguments whose content is an escaping-hostile Python raw-string regex
containing triple quotes and `\x1b\\`; the same model produced a clean `old_string` for a plain dict
literal in `rich/default_styles.py` (S/3942, turn 65). (c) The 3942 pair's cost plausibly follows from
the 75-character problem statement rather than from either prompt.

**Unknown.** Whether `seed: 42` is applied per LLM call or once per session. Whether the vLLM and litellm
path honors `presence_penalty` and `frequency_penalty` at all. Whether any loop would have broken itself
given more turns. Whether S/3942's turn-65 edit would have graded. Why both 3535 runs stayed in probing
after locating `rich/cells.py`. Nothing above is attributed to a single common cause: three distinct
mechanisms are visible, and the only thing all six share is the budget that stopped them.

## Recommended next experiment, one only

**Target: category 1, the degenerate identical-call loop.** It is the largest observed category by runs
(3 of 6) and by turns (127 of the 353 tool calls those six runs made, 36 percent), and it appears under
both prompts.

**Change exactly one variable, sampling.** Hold `system.md` for A and S byte-identical to the frozen
versions. Edit only `configs/sampling.yaml`: raise `temperature` from 0.2 to about 0.7, drop the fixed
`seed`, set `presence_penalty` and `frequency_penalty` above 0. Re-run the same four frozen tasks and read
one number per run: the longest adjacent identical-call block. The criterion is mechanical, not a solve
count. If the 52 / 43 / 18 blocks collapse, the fixed-point explanation survives and turns become
available for work; if they persist at comparable length, that explanation is dead and the next place to
look is the harness's turn accounting and nudge policy. `rich_3675` stays in the set only as the guard
that the two runs which currently reach `submit_patch` still do.

**Permitted in a competition submission: yes, fully.** `generate_content_config` is part of `agent.yaml`,
and `adk_submission/limits.py` lists `temperature`, `top_p`, `top_k`, `presence_penalty`,
`frequency_penalty` and `seed` among its recognized, range-constrained fields. No new file type, no
custom tool, no code, so it stays inside the declarative-only rule (allowed `.yaml .yml .md .txt`,
`.py` skill scripts, `.json .safetensors`; the 9 harness tools by name plus `agent_tool:` sub-agents).

**What would be evaluation-only, and so is not what is recommended:** an actual loop breaker, for example
suppressing a tool call byte-identical to its predecessor and returning a directive observation instead.
That lives in the turn loop and the tool implementations, which belong to the host's `swegemma` and
`adk-eval-core`, not to our package. It could be instrumented locally to size the problem, but it cannot
ship. The shippable approximation is a `system.md` rule, which is a prompt change, a different variable,
and a separate experiment.

**No launch was prepared.** No GPU run, Kaggle push, submission, polling or candidate edit was made.

## Correction to the record

The `rich_3675` S result is **the first graded solve in this A/S comparison**, not the project's first
evidence of a correct patch. And what these four tasks support is **no observed solved-task regression on
these four tasks**, since A solved nothing S did not, rather than non-regression in general.
