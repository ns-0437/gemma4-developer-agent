# V5 baseline measurement under V5's own budget, disabled

Prepared 2026-10-20, corrected the same day. Offline preparation only: no GPU launch, Kaggle push,
submission, hold-out consumption or Git push. Exact V5, earlier releases, all raw evidence and
`task_freeze.json` are preserved and verified unchanged.

## Corrections to the first version of this plan

1. **V4 had no packaged `eval_config`.** It shipped no evaluation section, so it carried no per-task
   budget and the harness default applied. **Ten minutes describes our development runs**, which set
   `max_time_minutes 10.0` in the notebook. It does not describe V4's submission.
2. **Trace timestamps are trace-relative, not agent-budget time.** `elapsed_s` is measured from
   `trace.start()`, which precedes task setup; the agent budget begins later at
   `start_agent_session()`. So "first accepted edit at 436 s" and "submit at 607 s" are positions on
   the trace clock and are **not** directly comparable to a 300 s agent budget. The direction may
   hold; the arithmetic as stated does not.
3. **Removed-call durations are descriptive, not counterfactual savings.** The 230 s around rejected
   calls is recorded inter-call time including model generation. It does not mean 230 s would be
   recovered if those calls vanished. No "591 minus 230" arithmetic is claimed.
4. **Historical 10-minute runs are context, not a matched control.** They differ in configured budget,
   and some differ in prompt, candidate and harness version. They may support diagnosis; they cannot
   serve as a control arm.
5. **One short-budget failure cannot establish a causal regression.** With one run per task and known
   run-to-run variance, including a solve that already failed to reproduce once, that inference is
   unavailable. The earlier regression criterion is withdrawn.
6. **Shell-reading results do not establish shell-editing effectiveness.** `S_shellread` removed
   `read_file` and routed reads through `sed`; it says nothing about shell-applied edits. The earlier
   dismissal of shell editing on that basis is withdrawn. Shell editing is untested in both
   directions.

What survives: V5's agent bytes are identical to frozen ON (`527acc54…`), and **we have never
measured V5's configuration on development tasks.** Every development datapoint we hold used a
10-minute budget and a 300 s command timeout.

**The only package change from V4 was evaluation limits. V4 timed out; V5 scored 0.13. Limits are
the leading explanation for completion, but their effect on patch quality and score is not
isolated.**

## Primary metric

**Verified solves divided by all attempted tasks**, reported with **total elapsed time**.

| outcome | in denominator | counts as solve |
|---|---|---|
| verified solve, graded and resolved | yes | yes |
| graded failure, patch graded but not resolved | yes | no |
| candidate no-patch or time-budget failure | **yes**, an unsuccessful end-to-end attempt | no |
| environment failure | **invalidates the comparison**; reported explicitly, never dropped | no |

Missing grades remain visible in end-to-end completion counts.

## Ranked bottlenecks from existing development evidence

Five V5-agent (ON) development runs, 2,150 s of recorded inter-call time. Shares are descriptive and
include model generation.

| phase | share | calls | recoverable opportunity | uncertainty |
|---|---|---|---|---|
| diagnosis, shell probes | **32.8%** (706 s) | 56 | unclear, much is informative | high |
| localization | 18.4% (395 s) | 38 | unclear; 272 s is one underspecified task | high |
| **editing, failed calls** | **16.5%** (354 s) | 24 | the clearest candidate for reduction; rejections returned an error rather than file content, though the agent's next action sometimes changed after one, so "no information gained" is not established | medium; content-dependent, concentrated in 2 runs |
| editing, accepted | 15.3% (328 s) | 16 | not measured; these produced the patches, but whether fewer or earlier edits would do as well is untested | medium |
| diagnosis, file reads | 12.1% (260 s) | 44 | some, paging re-reads | medium |
| verification | 2.9% (62 s) | 9 | none, and notably small | low |
| termination | 2.1% (46 s) | 6 | none | low |

Probing and localization dominate the recorded time. Verification is a small share; whether that is
too little verification or appropriately little is not established by these shares alone. No hidden verification requirement is used in any candidate instruction, and
none is proposed.

## The question chosen

**What is V5's verified-solve rate and elapsed time on development tasks under V5's own
configuration?**

This is not a re-demonstration that long trajectories exceed five minutes. It is **descriptive
baseline evidence**: the primary metric under the shipped configuration, which has never been
measured.

**It does not supply the matched control for a later A/B.** A control must be contemporaneous, so any
future candidate test should run exact V5 **in the same session** as the candidate. These four rows
are context for designing that test, not a substitute for its control arm.

**No candidate intervention is proposed.** The evidence ranks bottlenecks but identifies no minimal
change with a supported mechanism: the largest reducible category is content-dependent and
concentrated,
`write_file` cannot carry large files inside the 4,096-token output cap, shell editing is untested in
both directions, and a prompt warning is excluded and unsupported.

## Design

Single arm, **exact V5 as baseline**:

- Candidate: the V5 package with `eval_config.yaml` removed as submission-side, re-bundling to
  `527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33`.
- Budgets from V5's own `eval_config.yaml`: `max_time_minutes 5`, `max_turns 60`,
  `max_tool_calls 100`, **`timeout_seconds 60`**. The command timeout is part of V5's shipped
  configuration, so it takes V5's value rather than the development default of 300.
- Same runtime, pinned image, compiler gate, controls, sampling and all non-experimental limits as
  the existing machinery. No new framework.
- Four development tasks, one run each, declared order `rich_3278, rich_3535, rich_3675, rich_3942`.
  With one arm there is nothing to counterbalance; that is a limitation of a baseline measurement
  rather than a comparison.
- Hold-out remains protected; no hold-out task is touched.

When a candidate comparison is later justified it must run **exact V5 contemporaneously** as its own
control, counterbalanced and matched on runtime, compiler, image, tasks, sampling and
non-experimental limits. This run does not stand in for that.

## Cost assumptions

Four runs at a 5-minute agent cap plus grading, with roughly 6 minutes of vLLM startup observed on
the pinned image: **35 to 50 minutes expected**. Session admission cap 90 minutes, 20-minute reserve.
The cap is an admission limit, not a hard kill; this range is an expectation, not a bound.

## Follow-up rules

**No outcome count alone identifies the bottleneck.** Whatever the solve rate, the follow-up is
determined by evidence inspected per attempted row:

| evidence to inspect, every row | what it distinguishes |
|---|---|
| termination cause and remaining time at stop | time budget reached, turn budget reached, completed, or environment fault |
| actual patch state on disk and whether it was graded | reached an edit versus produced nothing |
| grading output and which tests failed first | patch correctness versus incompleteness |
| edit rejections, with their error category | tool-encoding failures versus wrong edits |
| repeated identical calls, adjacent and separated | degenerate loops versus genuine re-probing |
| phase time shares, as measured for the 10-minute runs | which phase consumed the budget |

Every attempted row is preserved with its failure category: verified solve, graded failure, candidate
no-patch, candidate time-budget, candidate turn-budget, environment failure. Environment failures
invalidate the affected row for comparison purposes and are reported, never dropped. Per-task
outcomes and elapsed time are reported individually, with variability stated; no statistical
superiority or inferiority is claimed from four selected tasks in one repository.

Only after that inspection does a next action follow, and it is chosen from the evidence rather than
from the count. If the inspection does not localize a bottleneck, the honest report is that it did
not, and the next step is a further diagnostic rather than a candidate change.

## Runtime deviations from a private submission run

This run is **the V5 agent and budgets in the public development harness**, not
private-grader-equivalent execution. The following development-harness settings are left exactly as
the existing machinery sets them; documenting them here changes none of them:

| setting | development value | note |
|---|---|---|
| **evaluation event compaction** | `EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=20480, event_retention_size=5)` | the private grader applies compaction **only if its own config sets it**; `EvalConfig.events_compaction_config` defaults to `None`. This is the largest known deviation. |
| context cache | `ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10)` | development setting; private configuration unknown |
| sandbox backend | `sandbox='subprocess'` | not a filesystem isolation boundary |
| `eval_config.yaml` | **absent from the candidate directory** | submission-side file; the notebook supplies the same four budget values |
| session admission cap | `SESSION_CAP_MIN 90`, `RUN_RESERVE_MIN 20` | admission limit, not a hard kill |
| control re-validation | runs before model startup | development instrument; no private equivalent |

## Remaining uncertainty

No hidden-task traces exist, so why V5 scored 0.13 is unknown, and completion is not separated from
patch quality. Run-to-run variance is large: the one twice-solved task also failed to reproduce once.
Four Rich development tasks cannot predict the hidden set. **No score is predicted, and nothing in
this packet is itself a score improvement.**
