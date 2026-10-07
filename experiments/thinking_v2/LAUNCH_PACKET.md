# Thinking OFF/ON diagnostic — prepared, not launched

Prepared 2026-10-05. No new GPU session, Kaggle push or competition submission.
This packet replaces the earlier proposal in PREP_before_codex_review.md.

## Question and scope

Does enabling thinking at a matched 4,096-token total output cap produce more
correct graded patches on two selected Rich development tasks? This is a
configuration experiment, not another anti-repetition prompt. Both candidates
derive from frozen S; neither prompt changes. OFF is a new output-cap baseline,
not the previously scored v3 or unchanged S. Neither candidate has a score.

## Frozen artifacts

| Artifact | SHA-256 |
|---|---|
| OFF.zip | `640fadab5b5b638a7e8a31abb26fcecb6b2e139929d77cdb6691f2d832ca2ec1` |
| ON.zip | `527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33` |
| Disabled notebook | `93dc58362ac07d7cf9554f2c164b752cf52f9de89e003a78896f3407ebca8061` |
| Protected task freeze | `220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b` |

Notebook: `notebooks/thinking_v2/thinking_v2.ipynb`.
Proposed private kernel: `navin03/gemma4-swe-agent-thinking-v2` (not pushed).
Full file identities: CANDIDATES.json, NOTEBOOK_PREPARED.json, FINAL_CHECKS.json.

Only configs/sampling.yaml differs between arms. Both set max_output_tokens=4096,
temperature=0.2, top_p=0.95, top_k=40, seed=42. OFF disables thinking and retains
the inert budget value 4096; ON enables thinking and requests budget 1024.
Both coder and analyzer inherit the same arm's configuration.

## Four planned rows

| Order | Task | Candidate |
|---|---|---|
| 1 | rich_3675 | OFF |
| 2 | rich_3675 | ON |
| 3 | rich_3278 | ON |
| 4 | rich_3278 | OFF |

Both are development tasks, disjoint from the 12 protected tasks. Controls are
revalidated before model startup. Equal budgets: 10 minutes, 100 tool calls,
60 turns, command timeout 300 seconds. Same model and requested 4×L4.
Actual allocation must come from runtime metadata. Shared compaction threshold
20,480; private-grader configuration unknown. Session cap 150 minutes and
25-minute admission reserve are not a hard kill or a duration estimate.

## Completed offline verification

- Official compiler 0.2.12 compiles both arms; ADK interception confirms the
  intended client fields for coder and analyzer. MATCHED_TRANSPORT.json records
  the results. No HTTP request or model invocation was made.
- Exact candidate hashes are gated before model startup, as are the sha256 of each
  compiler Python module plus the version string. **Those hashes verify those
  components only, not the entire wheel or the runtime stack.** A mismatch stops the
  run rather than silently changing experimental conditions.
- Generated-cell tests execute the notebook with simulated dependencies:
  disabled mode performs zero evaluations/server starts; simulated enabled mode
  performs exactly four evaluations in order and starts/stops once. Compiler
  version/source drift, candidate drift, bad controls and provenance failure
  block evaluation before server creation.
- Deterministic regeneration and Python cell compilation pass. Latest 46 raw
  artifacts, five launched notebooks and the holdout freeze match their hashes.
- Generator is preparation-only and rejects command-line arming. No automatic
  submission, additional experiment or polling is included.

Reproduce locally with the audit Python environment:

```text
python scripts/prepare_thinking_v2.py
python scripts/test_thinking_v2_transport.py
python scripts/make_thinking_v2_notebook.py
python scripts/test_thinking_v2_notebook.py
python scripts/inventory_thinking_context.py
```

The transport test needs the project's existing ADK/LiteLLM dependencies and
extracted official compiler; the notebook execution tests use simulated ones.
These are wiring checks, not real-sandbox or task-solving tests.

## Server observability and limits

Confirmed locally: OFF forwards enable_thinking=false; ON forwards true and
thinking_token_budget=1024. Host-server enforcement remains unknown. Compiler
hash agreement does not establish LiteLLM wire conversion or vLLM enforcement.
The local and last recorded Kaggle LiteLLM versions differ.

For any future run, report configuration, forwarding, observed reasoning and
budget enforcement separately. Explicit reasoning content in a recorded response
can establish reasoning was emitted on that call. Missing content remains
unknown. Total completion usage cannot distinguish reasoning from final tokens
and cannot validate the thinking budget. Do not rename a nominal arm to
"thinking successfully active" without evidence. If activation is unobserved,
report the nominal-config comparison and leave the mechanism unresolved.

The total output cap includes reasoning and final content; 1024 does not reserve
a guaranteed 3072 tokens for the final response. A 28672-token prompt ceiling
does not guarantee the next request fits. Capture context errors and truncation
as outcomes, never discard them.

## Predeclared interpretation

Preserve all four rows including unattempted/ungraded outcomes. Separate:

1. Instrument: control agreement, exact identities, checkout provenance when
   each phase runs, cleanup and environment failures. Unobserved grading is not
   automatically a demonstrated instrument defect.
2. Reliability: actual source patch, patch application and observed grading.
   Tool acknowledgements or submit_patch counts alone are insufficient.
3. Performance: verified solves, graded failures, ungraded and missing outcomes
   per candidate. A pair with an ungraded side is undecided, not an opponent win.
4. Mechanism/cost: repetitions, rejected calls, explicit reasoning evidence,
   truncation, turns and phase timings. Do not equate reduced repetition or more
   incorrect patches with a performance improvement.

An ON solve where OFF grades unsuccessfully is an observed win on that task;
an OFF solve lost by ON is a regression. A win with no observed regression may
justify broader testing, not automatic submission. Two selected tasks cannot
establish statistical non-inferiority, general improvement, competition runtime
compliance or a predicted public score. No 0.15/0.20 claim is supported.

## Next launch step, not executed

A future authorized launch must record current quota/time, verify these exact
identities, deliberately arm only the dispatch flag, test the armed artifact,
record its new hash and push once. No historical one-launch approval is reused.
After completion, preserve/hash raw outputs before review and write reports
outside the raw tree. No automatic retry, promotion or competition submission.
