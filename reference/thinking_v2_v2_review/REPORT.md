# thinking OFF/ON, four runs: ON produced a verified solve; OFF produced none

Kernel `navin03/gemma4-swe-agent-thinking-v2` **version 2**, status COMPLETE checked
2026-10-06T13:53:05Z. Downloaded to `reference/thinking_v2_run_v2_2026-10-06/`, **48 files**, hashed
into `reference/thinking_v2_v2_review/raw_sha256.json`. No retry, repush, candidate change or
submission.

**Download caveat, recorded for honesty:** the first `kernels output` call returned only 15 files and
no kernel log. It was refetched to completion. All 15 originally hashed files are **byte-identical** in
the complete set, so nothing was overwritten with different content; the first manifest was simply
partial.

## Version identity

| check | result |
|---|---|
| candidate hashes in `pilot_manifest.json` | OFF `640fadab…`, ON `527acc54…`, **both as pinned** |
| run order | `[(3675,OFF),(3675,ON),(3278,ON),(3278,OFF)]`, as planned |
| budgets | `max_turns 60, max_tool_calls 100, max_time_minutes 10.0, timeout_seconds 300` |
| environment | adk-submission **0.2.12**, swegemma 0.2.7, google-adk 1.36.1, vllm 0.19.1, transformers 5.13.1, litellm 1.82.4, 4x NVIDIA L4 |
| seed in sampling | 42 |

The image pin worked: this is the first session of this experiment to get past the wheelhouse install.

## All four planned rows

| Order | Task | Cand | Outcome | Grading observed | Exit | Resolved | Patch B | Touches source | Agent loop s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | rich_3675 | OFF | graded, unsolved | yes | 1 | false | 593 | yes | 256.0 | 309.0 |
| 2 | rich_3675 | ON | graded, unsolved | yes | 1 | false | 723 | yes | 145.5 | 198.5 |
| 3 | rich_3278 | ON | **SOLVED** | yes | **0** | **true** | 319 | yes | 566.6 | 618.7 |
| 4 | rich_3278 | OFF | ungraded, turns budget | **no** | -1 | false | 0 | no | 387.2 | 412.6 |

None missing, none aborted; `attempted=True` on all four.

### Categories

| | OFF | ON |
|---|---|---|
| **verified solves** | **0** | **1** (`rich_3278`) |
| graded, unsolved | 1 (`rich_3675`) | 1 (`rich_3675`) |
| ungraded | 1 (`rich_3278`, 60-turn budget) | 0 |
| environment failures | 0 | 0 |

`failure_class` is `none` on the three graded runs and `candidate` on OFF/`rich_3278`. Cleanup confirmed
4 of 4. Controls re-validated on all four arms and agree: baseline exit 1, reference exit 0 on both
tasks. `both_setup_imports_verified` true on the three graded runs, false on the ungraded one because
grading never ran, which is unexercised rather than faulty.

### Paired outcomes

| Task | OFF | ON | pair |
|---|---|---|---|
| rich_3675 | graded unsolved | graded unsolved | **tie, both incorrect** |
| rich_3278 | **ungraded** | **solved** | **undecided** |

Applying the predeclared rule exactly: a pair with an ungraded side is **undecided, not an opponent
win**. ON's solve on `rich_3278` is a verified solve on its own terms, but because OFF never produced a
patch there, the *pair* does not establish that thinking caused it. The packet's win condition was an ON
solve where **OFF grades unsuccessfully**; OFF did not grade at all.

### Regressions

**None observed.** OFF solved nothing that ON failed. On the one task both graded, neither solved.

## The verified solve, inspected

`ON/rich_3278`, 319 bytes, one character class in `rich/ansi.py`:

```diff
-(?:\x1b([(@-Z\-_]|\[[0-?]*[ -/]*[@-~]))
+(?:\x1b([(0-Z\-_]|\[[0-?]*[ -/]*[@-~]))
```

Widening the range start from `@` to `0` brings the private escape codes `0123456789:;<=>?` into the
pattern, which is exactly what the issue asked for. Grading: **23 passed, exit 0, resolved true**. This
is a minimal, correct fix, not a broad rewrite. Reached in 45 tool calls with **0 repeated identical
calls and 0 rejected calls**.

## Mechanism and cost, reported separately

| | OFF 3675 | ON 3675 | ON 3278 | OFF 3278 |
|---|---|---|---|---|
| tool calls | 43 | 24 | 45 | 60 |
| repeated identical | 22 | **0** | **0** | 8 |
| rejected calls | **24** | **0** | **0** | 0 |
| edit calls | 25 | 3 | 9 | 0 |
| completion tokens | 7,741 | 4,819 | 18,132 | 12,516 |

The two ON runs recorded **zero repeated identical calls and zero rejected calls**; OFF/`rich_3675` had
24 rejected calls and 22 repeats. That is a mechanism observation on two runs, not a demonstrated
property of thinking.

**Thinking activation: positively evidenced, not inferred from token totals.** The harness recorded
`extra.event_type == "thinking"` on **46 steps in ON/rich_3278 and 25 in ON/rich_3675**, and that event
type is **absent from both OFF traces**. That is a structural per-call record of the thinking path
being exercised. It does **not** establish that the server enforced the requested 1,024-token budget;
no recorded field reports an enforced budget, and completion-token totals cannot separate reasoning
from final content.

Runtime: ON's solve took the longest agent loop of the four, 566.6 s against OFF's 387.2 s on the same
task. Grading phases were uniform at roughly 27 s. Session GPU usage moved 0.01h to 1.46h.

## What this does and does not support

Established: the environment repair works; ON produced this project's **second verified solve overall
and the first on `rich_3278`**; no regression was observed; the instrument was clean on all four runs.

Not established: that thinking caused the solve (the pair is undecided), that the 1,024 budget was
enforced, non-inferiority, or anything about the leaderboard. **Two selected Rich development tasks
cannot predict public score**, and three submissions have each scored 0.06. OFF is a new
4,096-output baseline, so neither arm corresponds to submitted v3.

**No submission is recommended on this evidence.** One verified solve in an undecided pair is a reason
to test further, not to spend a daily slot. The natural next step is to re-run this same pair to see
whether either outcome reproduces, since the earlier `rich_3675` solve by candidate S did not.
