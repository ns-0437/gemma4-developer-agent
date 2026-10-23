# V5 GPU baseline (kernel navin03/gemma4-v5-budget-v2, version 1): ERROR before dispatch

Checked terminal 2026-10-23T16:54:08Z. Downloaded into a fresh directory; 27 files hashed
before/after analysis via `raw_sha256.json`. Download completeness: the Kaggle CLI's log fetch
first failed silently (empty file) due to a Windows console codepage mismatch on a progress-bar
character; re-fetched under a UTF-8 codepage recovered the full 47,678-byte log. All 26 non-log
output files downloaded cleanly on the first pass; the log is the 27th.

## Identity verified against the launch record

| check | result |
|---|---|
| notebook_sha256 (armed, as pushed) | `066b5fb7...` matches `LAUNCH_RECORD.json` |
| compiler identity gate | version 0.2.13, matches=True |
| swegemma identity gate | version 0.2.11, 34 modules, matches=True |
| control arms | 8/8 agree with saved evidence, 8/8 cleanup confirmed |
| preconditions | 4/4 tasks ok |

Both runtime identity gates and the fresh control replay — the exact checks the CPU replay
validated two days earlier — reproduced identically on the GPU kernel. The repair held.

## Where it stopped

After preconditions and controls (identical to the successful CPU replay), the kernel proceeded
to vLLM server startup. The server began loading the quantized model's safetensors checkpoint
and did not become healthy within the server's own `startup_timeout` of 1200s (20 minutes):

    ServerStartupError: Inference server did not become healthy within 1200s.

This is **upstream of all four candidate tasks**: `server_instance.start()` runs once, before any
task dispatch. No candidate code, no agent turn, no tool call for rich_3278/3535/3675/3942 ever
executed. Log span: 1775.5s (~29.6 min) total session time, consistent with the 20-minute
server-startup ceiling plus setup/control overhead.

**This is not attributable to the V5 repair or the compiler/swegemma version bump.** `server.py`
is byte-identical between the extracted adk-submission 0.2.12 and 0.2.13 sources (`diff` returns
nothing), and the `startup_timeout=60*20` literal is unchanged, shared template code
(`scripts/make_pilot_notebook.py`) used by every prior GPU notebook, not something introduced by
this packet.

## All four planned rows

| Task | Candidate | Outcome | Grading | Patch | Agent-budget time | Trace-relative time |
|---|---|---|---|---|---|---|
| rich_3278 | V5 | **environment failure** (never dispatched) | not run | none | not applicable — the per-task 5-minute agent budget was never entered | n/a |
| rich_3535 | V5 | **environment failure** (never dispatched) | not run | none | not applicable | n/a |
| rich_3675 | V5 | **environment failure** (never dispatched) | not run | none | not applicable | n/a |
| rich_3942 | V5 | **environment failure** (never dispatched) | not run | none | not applicable | n/a |

Verified solves: 0. Graded failures: 0. Ungraded candidate failures: 0. Missing runs: 4 of 4
(none reached dispatch). **Environment failures: 1, session-level**, invalidating all four rows
identically. There is no agent-budget clock to report for any row, because
`start_agent_session()` (the agent-budget clock origin) is reached only after server start,
which this session never completed; the only clock available is the harness's trace/wall time
(1775.5s total), which is explicitly **not** agent-budget time.

## Evidence for the proposed change

| session | server startup time | ceiling |
|---|---|---|
| thinking_v3, 2026-10-07 | 6.0 min | 20 min (33% used) |
| thinking_v2 v2, 2026-10-06 | 12.1 min | 20 min (60% used) |
| v5-budget-v2, 2026-10-22/23 | **did not complete** | 20 min (100%, exhausted) |

Three observations spanning 6.0 to >20.0 minutes already show meaningful variance well before
this run exhausted the ceiling entirely. The server log tail captured at the moment of timeout
shows checkpoint loading still at "0% Completed" for the harness's own truncated 2000-character
tail — consistent with either a slow load or a near-complete one; the full server log is not
retrievable from the notebook's own evidence, so which is unknown.

## Single best-supported next improvement

**Raise the vLLM server's `startup_timeout` from 1200s to 1800s (30 minutes).** This is the only
change supported by actual evidence from this run: the failure occurred entirely before any
candidate code ran, is reproducible across package versions (identical `server.py`), and is
bounded by directly observed startup-time variance (6.0–12.1 min successful, now exceeding 20
min). It is not a V5 agent, prompt, sampling, or budget change, so it cannot be mistaken for a
candidate-performance claim. 1800s is 2.5x the longest previously observed successful startup
(12.1 min), leaving headroom without being unbounded; it stays well inside the packet's 90-minute
session admission cap for a 4-task run.

**No candidate behavior was measured by this run.** This report establishes nothing about V5's
patch quality, solve rate, or score; it is a pure infrastructure diagnosis.
