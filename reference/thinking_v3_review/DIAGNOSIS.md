# Focused diagnosis of the two failed ON runs and the 3278 submit tail

Offline only. Raw evidence unchanged (60 files, manifest re-verified, 0 mismatches). No GPU launch,
rerun or submission. Frozen ON remains the reference candidate; OFF was not rerun.

## 1. Corrections applied to REPORT.md

- ON/`rich_3278`'s final regex `[ (0-Z\-_]` **already contains `@-Z`**, so step 50 removed nothing. Verified by enumeration: against the original
  class it adds space and `0123456789:;<=>?`; against step 47's class the **only** addition is the
  **space**, which is the unintended part. The solve verdict is preserved (graded exit 0, resolved true,
  twice); correctness is established **against the suite only**.
- ON/`rich_3535` verified ASCII examples and the existing visible tests, and still failed grading.
- ON/`rich_3942`'s visible requirement is vague. **No grader-specific style values or answer-key detail
  are to be put in any prompt.**
- The kernel log spans **about 50 minutes (3,013 s)** and records roughly **6 minutes of vLLM startup**.
  The **1.67h quota change is a separate account-level observation**, not the session wall clock.

## 2. Evidence table for the two failed ON tasks

| | ON / rich_3535 | ON / rich_3942 |
|---|---|---|
| **Visible requirement** | "Regex error. Fixes an issue with the regex used to select the fast path for strings with single-width characters." No ranges, no characters named. | "Update to markdown styles / Updates to Markdown styling." 75 characters, no target styles or values. |
| **Agent hypothesis** | The range end `\u006f` is truncated and should cover ASCII printable, so `\u0020-\u006f` becomes `\u0020-\u007e` (step 21, from reading `rich/cells.py` at step 7 and probing `CELL_WIDTHS` at steps 11-18). | Unclear from the issue; after ~30 exploratory calls it settled on **removing** the `"markdown.h7"` entry from `DEFAULT_STYLES` (step 39/44), having reverted an earlier attempt with `git checkout` at step 42. |
| **Verification performed** | Step 22 custom repro: `'hello','world','python','rich','p','z',' '` all True. Step 24 visible suite `tests/test_cells.py -q -x` **EXIT=0, 7 passed**. | Steps 30/32/41/45 ran `tests/test_markdown.py` and `tests/test_markdown_no_hyperlinks.py`; step 45 passed on the visible suite; step 54 `git diff` reviewed. |
| **Remained untested / unknowable** | **Box-drawing characters.** Grading's `test_is_single_cell_widths` adds `BOX = "┌─┬┐│ ││├─┼┤…"` and asserts single-cell width for each; `'┌'` (U+250C) lies outside every range in the regex before **and** after the patch. Nothing in the issue text or the visible test mentioned them. | **The intended styling itself.** Grading fails 6 tests on rendered output (`test_markdown_render`, `test_markdown_table`, `test_inline_styles_in_table`, `test_inline_styles_with_justification`, `test_partial_table`, plus the no-hyperlinks variant). A one-line deletion cannot produce the expected rendering. |
| **Information boundary** | Agent-visible: issue text, source, `CELL_WIDTHS`, the visible test file (no BOX loop). **Revealed only at grading:** the BOX requirement. | Agent-visible: issue text, source, visible tests, git history. **Revealed only at grading:** every expected style value. |

**Evidence-specific uncertainty, stated per task.** A green visible suite does not establish that a
requirement was unknowable.

- `rich_3535`: the deciding requirement (box-drawing characters accepted by the fast path) is **absent
  from the issue text and from the visible `tests/test_cells.py` the agent ran**. The evidence does
  **not** establish that it was unreachable: section 5 shows the repository carries its own width
  table, so a gap of this kind was discoverable in principle from files the agent had already opened.
  Whether *closing* that particular gap was required remains unknowable from visible material.
- `rich_3942`: the expected style values appear nowhere the agent read, and the trace shows about 30
  exploratory calls that did not converge. The evidence is consistent with the requirement being
  underdetermined by visible material, but it does not rule out that a more systematic reading of
  `rich/markdown.py` and the visible tests would have narrowed it. Unresolved.

## 3. Why ON/3278 kept editing, and the "600 s, completed" timing

Recorded sequence, with `elapsed_s` from the trace:

| step | t (s) | action | result |
|---|---|---|---|
| 46 | 441.4 | `pytest tests/test_ansi.py -q -x` | **EXIT=1**, `test_decode_issue_2688` fails: its earlier `[0-Z…]` edit had dropped `(`, which ESC-`(` sequences need |
| 47 | 474.5 | `edit_file` → `[(@-Z0-Z\-_]` | ok |
| 48 | 478.9 | `pytest` again | **EXIT=0, 7 passed** |
| 50 | 512.8 | `edit_file` → `[ (0-Z\-_]` | ok. **This is the space insertion, and it drops `@-Z`. No check was run after it.** |
| 51 | 545.3 | `edit_file`, `old_string == new_string` | rejected: "No changes to apply. old_string and new_string are identical." |
| 52 | 577.3 | identical no-op `edit_file` again | rejected, same message |
| 53 | 607.2 | `submit_patch` | ok |
| 54 | 621.0 | one further `run_command` | ok |

So the **last verified state was step 48**, and the **submitted state is step 50's**, which was never
re-tested. It passed grading, so the solve stands, but it passed unverified. The two no-op edits at 51
and 52 are the agent attempting an edit it had already made; each consumed roughly 30 s of generation
for no state change.

**Timing, with the two clocks separated.** Trace `elapsed_s` values are **trace-relative**, not
agent-loop-relative: `agent_runner.py:215` calls `trace.start()` before task setup, while the agent
budget begins much later at `context.start_agent_session()` (`agent_runner.py:495`), immediately before
`async with timeout_context`. Setup, control re-validation and prompt recording fall between them. The
budget is enforced by **`asyncio.timeout(timeout_sec)`** (`agent_runner.py:440`, `timeout_sec =
time_minutes * 60`) as well as by elapsed checks.

`agent_loop_s` is 600.0051 s against a 600 s budget, so ON/`rich_3278` did reach the agent time budget.
**The earlier explanation for the calls at trace-time 607.2 s and 621.0 s is withdrawn.** Those are
trace-relative timestamps on a clock that starts before the budget clock, so they do not show calls
running past the deadline, and nothing recorded establishes a mid-call versus between-turn enforcement
boundary. Agent-relative timestamps and the termination path would be needed; the trace does not carry
them. What remains supported: ON/`rich_3278` has `termination_error: unavailable` with a patch and
observed grading, while ON/`rich_3942` has `Agent exceeded session timeout (10.0 min)` and never called
`submit_patch`.

## 4. One general intervention, and its honest limits

**Proposed: a submit-ordering invariant.** Require that `submit_patch` be immediately preceded by a
verification command on the current file state, and that any edit made after the last passing check be
followed by re-running that check before submitting.

- **How the supported format implements it:** text in `prompts/system.md` only. It is a sequencing rule
  over tools the agent already has (`run_command`, `edit_file`, `submit_patch`), needs no new tool, no
  callback and no framework, and stays inside the declarative-only submission rules.
- **What an offline test can actually prove:** only that the candidate still compiles under the official
  0.2.12 compiler and that the prompt bytes changed. Behaviour cannot be tested offline. What *is*
  measurable on existing traces, as a baseline metric rather than a prediction, is the defect rate: in
  this session 1 of 3 ON runs submitted a state newer than its last passing check, and 2 of 3 spent
  turns on no-op edits.
- **Benefit: no evidence establishes a solve benefit.** The recorded defect is real, one run submitted
  a state newer than its last passing check, but nothing here shows re-verification would have changed a
  graded outcome. No counterfactual is claimed in either direction.

I am not proposing a second intervention. The sharpest contrast in the data, OFF reaching grading 0 of 3
while ON reached 3 of 3 and solved 1, is a **configuration** observation about the frozen arms, not an
intervention, and all three pairs remain undecided so it does not establish causation either.

**Decision taken: frozen ON is unchanged and the submit-ordering rule was NOT added.**

## 5. Bounded retrospective investigation of rich_3535

*Retrospective diagnosis only. Not independent candidate validation. No candidate was edited.* Inputs
restricted to what the agent had already opened: the visible issue text, pre-edit `rich/cells.py`
(trace step 7), `rich/_cell_widths.py` (step 10), and the visible `tests/test_cells.py`.

**Does the repository provide an independent oracle? Yes.** `cells.py` carries two paths for the same
question. `_is_single_cell_widths` is a regex fast path; `get_character_cell_size` ->
`_get_codepoint_cell_size` is an authoritative lookup, a binary search over `CELL_WIDTHS` that
**returns 1 for any codepoint absent from the table**. The fast path is therefore checkable against the
repository's own slow path, with no external reference and no grader input.

**Correctness and performance point in different directions, and only one is a bug.**

| direction | meaning | status |
|---|---|---|
| regex **accepts** a character whose oracle width is not 1 | **unsoundness**, a correctness bug | zero found, before and after the patch |
| regex **rejects** a character whose oracle width is 1 | **coverage gap**, a performance matter | many, before and after |

An intentional subset fast path need not accept every single-width character, so a coverage gap is not
by itself a defect. That distinction is what makes the oracle usable without over-claiming.

**Demonstration without hard-coded grader characters or ranges.** Probe points are derived
*structurally* from the table: for every `(start, end, width)` entry take `start-1, start, end, end+1`,
then compare regex acceptance against the oracle. On a modelled subset of the table this reports **0
unsound accepts** for both the pre-edit and the patched regex and enumerates coverage gaps whose
boundaries are discovered rather than named. Nothing in the method mentions box drawing; that block
surfaces only because it is absent from the table and so defaults to width 1.

**The concrete, generalizable finding.** When a repository contains a fast path and a slow path for the
same predicate, the slow path is an oracle, and a differential probe over structurally derived boundary
points can (a) prove or refute soundness of the fast path and (b) enumerate its coverage gaps, using
only in-repo material. Applied here it would have shown the agent that its patch was sound yet still
rejected whole blocks of width-1 characters, turning an invisible requirement into a visible, ranked
list of candidate gaps. **It still cannot supply which gaps the project requires closing**; that
judgement stayed outside visible material, and the patch was sound but incomplete.

**No task-specific fix, no grader-derived value, no new warning paragraph and no framework is proposed.**
