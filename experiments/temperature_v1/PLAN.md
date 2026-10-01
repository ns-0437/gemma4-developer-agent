# Temperature-only comparison: S versus S_temp

Prepared October 1, 2026. **Not launched. Dispatch disabled.**

## Evidence and hypothesis

The previous contemporaneous A/S comparison produced one graded solve for S,
one graded-unsolved result for A, and three ungraded runs per candidate. Three
of the six ungraded runs repeated successful read/reproduction calls; one
repeated rejected malformed edits; two exhausted their budget investigating.
These are distinct observed behaviors, not a demonstrated common mechanism.

This experiment asks whether a temperature change yields more correct patches
under the same evaluation conditions. Reduced repetition alone is insufficient.
A result may support or weaken the sampling hypothesis; it cannot establish the
cause of a decoding loop or rule out parser/transport effects.

## Frozen candidate difference

Only `configs/sampling.yaml` differs: `temperature: 0.2` becomes `temperature: 0.7`.
Both the coder and analyzer include that file, so both agents' temperature changes.
All prompts, model names, tools, thinking configuration, top_p, top_k, output
limit, configured seed and penalties remain byte-identical. No penalty is added.
The temperature is an experimental setting, not a claimed optimum.

| Artifact | SHA-256 |
| --- | --- |
| S archive | `8bf9f72c5d7ac4747e10c53637393bd7b18a6b66aae1879ddf4a62f4e4a6dc07` |
| S_temp archive | `4f1ff61c1d8acf0287bc786c697e3ff4949a8624f3c49ec01b815cd6742f366c` |
| Disabled temperature notebook | `d17f234a34b1c44d8f85461c7563504cf5a5977a3836acf12122081f6a7e5ef7` |

The notebook unpacks the archives, validates them, compares complete file sets,
and asserts the exact temperature-only byte substitution before model startup.
Existing control, provenance, teardown, dispatch and reporting logic is reused.

## Transport evidence: do not call this a fixed-seed experiment

`TRANSPORT.json` is produced by `scripts/check_temperature_transport.py`.

1. **Schema:** the official adk-submission 0.2.11 compiler accepts both candidates.
2. **Effective configuration:** coder and analyzer compile at 0.2 versus 0.7;
   all other compiled fields and instruction hashes agree.
3. **ADK forwarding:** executing google-adk 1.36.1's real non-streaming generation
   method with an intercepted LiteLLM client captures temperature 0.2 versus 0.7.
   No HTTP request is sent. The exact client dictionaries differ only in temperature.
4. **Server behavior:** NOT tested offline. This does not prove the actual host
   server's sampling behavior or byte equivalence with upstream vLLM.

The compiled configuration contains seed 42, but the captured ADK client kwargs
do not contain seed. Thus unchanged YAML seed does not establish seeded inference.
The generation mapping in installed `google/adk/models/lite_llm.py` lists temperature,
top_p, top_k and penalties, but not seed. This experiment does not repair or change
that behavior. Local LiteLLM is 1.102.1; the earlier Kaggle manifest reported 1.82.4.
The interception is before LiteLLM's HTTP conversion, so the check does not test
either version's wire serialization. Record actual runtime versions on launch.

## Plan and protection

| Task | First | Second |
| --- | --- | --- |
| rich_3278 | S | S_temp |
| rich_3535 | S_temp | S |
| rich_3675 | S | S_temp |
| rich_3942 | S_temp | S |

The held-out freeze remains unchanged and generation rejects overlap. These are
four selected Rich development tasks; no population or leaderboard extrapolation
is justified. rich_3675 retains the previously observed solve as a regression check.
Historical S results are background, not a replacement for contemporaneous S runs.
One shared model server and alternating order do not eliminate all ordering effects.

Budgets remain 10 agent minutes, 100 tool calls, 60 turns, command timeout 300 seconds;
compaction retains the comparison's 20480 setting. This differs from an unrestricted
competition submission. The repaired subprocess environment is not private-grader
equivalence or a filesystem isolation boundary; audit traces for answer-key access.

## Measures and decision

- Main: verified solved, graded-unsolved, ungraded, not-attempted counts, out of all
  four planned tasks per candidate. Show all eight rows even after early stopping.
- Pairing: wins/losses/ties only where both have valid grading; otherwise undecided.
- Reliability: valid nonempty source patches and grading completion, irrespective
  of whether edits came through a file tool or a shell command.
- Diagnostic: longest adjacent identical-call block, total repeated calls,
  rejected calls, distinct calls, turns and runtime. A repeated call after a state
  change is not automatically waste. A write acknowledgment is not a byte change.

No automatic promotion. More graded-but-incorrect patches or less repetition does
not establish improvement. More verified solves with no observed solve regression
would support broader evaluation, not a guaranteed public score. Mixed outcomes
require reporting the tradeoff. Missing grades are never silently dropped.

## Runtime and launch boundary

The most recent eight-run A/S session took 2,898 seconds (about 48 minutes). That is
one observed run, not a bound for higher-temperature behavior. Reserve roughly
130 minutes provisionally; grading and generated trajectories may vary. The
300-minute session admission setting is NOT a hard stop, and an admitted run can
outlast it. GPU quota and wall-clock time are separate observations.

No GPU authorization has been consumed by this preparation. Before launch, obtain
authorization for this one experiment, record quota/time, freeze an armed copy,
verify only the dispatch flag changed, rerun focused execution checks and push once.
No retry, submission or subsequent experiment is authorized here.

## Verification commands

`python scripts/make_temperature_notebook.py`

`python scripts/check_temperature_transport.py` (uses the existing compiler packages)

`python scripts/test_temperature_notebook.py` (simulated dependencies, not solve evidence)

The shared generator's default compare output was regenerated in a temporary
directory and matched `029bb41f7405aabee2d96a928651c87a11f698f4fddc65cf1e00186d76cc3796`
byte-for-byte. Previous launched notebooks and frozen S are not overwritten.
