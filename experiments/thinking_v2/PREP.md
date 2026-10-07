# Matched thinking OFF/ON: reviewed preparation

Updated 2026-10-05. Supersedes PREP_before_codex_review.md, preserved unchanged as
historical evidence. Packages and a disabled notebook are prepared. No GPU launch,
Kaggle push, competition submission or performance measurement was made in this step.
See LAUNCH_PACKET.md for the exact proposal and NOTEBOOK_PREPARED.json for identity.

## What the offline checks establish

The official compiler 0.2.12 compiles both frozen S derivatives. The real ADK
client interception confirms equal prompts, tools, temperature, top_p, top_k,
seed 42 and max_completion_tokens 4096 for both coder and analyzer. OFF sends
chat_template_kwargs.enable_thinking=false. ON sends true plus
thinking_token_budget=1024. Only configs/sampling.yaml differs between packages.
MATCHED_TRANSPORT.json records the evidence. The interception stops before HTTP.

The earlier transport_0_2_11.json and transport_0_2_12.json remain unchanged.
They tested the earlier 8192/4096 settings, not the newly prepared 4096/1024 arms.
Compiler 0.2.11 omitted seed and thinking_token_budget at this boundary; 0.2.12
forwards both. The historical A/S and temperature sessions used different
compiler versions, so comparisons across those sessions have that confound.
Forwarding a field does not establish the host server enforces it.

## Context findings and corrections

The pilot's rejected request had at least 24,577 prompt tokens plus 8,192 reserved
output tokens: 32,769 against a 32,768 context. Its last successful recorded
prompt was 24,425. Successful usage records do not bound rejected requests.

CONTEXT_INVENTORY.json has an explicit 29-trace, seven-session scope, every trace
hash, recorded maxima, configuration sources and exclusions. Fifteen recorded
peaks exceed 20,480; that is descriptive, NOT evidence all 29 used that threshold.
For five sessions the notebook matches its recorded launch hash and configures
20,480. The pilot and compare notebooks are not launch-pinned in this inventory;
their current source thresholds are shown separately, with historical settings
left unknown. In particular the current pilot source says 32,768, not 20,480.
Compaction depends on earlier recorded usage; it cannot reserve space for the
next request or guarantee the context fits.

The public harness defaults events_compaction_config to None. The private
competition grader's actual setting is UNKNOWN. We cannot infer hidden-run
context failures or explain the 0.06 scores from this default.

Latest verification loops peaked at 11,719 and 11,808 input tokens, far below
the 24,576 ceiling at an 8,192 output reservation. A cap-only experiment does
not directly address those observed loops and is not proposed as a GPU run.

## Why the matched settings

Both new arms use 4,096 total completion tokens, giving a 28,672 prompt ceiling
at context 32,768. OFF is a new output-budget baseline, NOT frozen S or submitted
v3 unchanged. ON requests 1,024 thinking tokens. The 4,096 total includes
reasoning and final content; it does not reserve a guaranteed 3,072-token final
answer. Thinking-budget enforcement is unverified. Neither the cap nor the
shared 20,480 compaction threshold guarantees a request fits.

## Server-side unknowns

Upstream vLLM source recognises enable_thinking and thinking_token_budget.
The host wheel differs from the upstream release file; upstream inspection is
not proof of the host engine's enforcement. Local LiteLLM is 1.102.1; recorded
Kaggle LiteLLM was 1.82.4. Client interception does not verify either HTTP body.

Aggregate completion-token usage mixes reasoning with final content: increased
usage does not prove thinking activated, and shorter output does not prove the
thinking budget was enforced. Explicit recorded reasoning content, if present,
can establish reasoning was emitted on that call. Absence remains unknown.
Strict budget enforcement needs attributable reasoning-token accounting or a
validated server-side capture; this preparation does not provide it. Report
configured/forwarded/observed/enforced as separate facts.

## Interpretation

Two selected Rich development tasks cannot predict a leaderboard score or
cross-repository improvement. Preserve all four planned rows, grade availability,
verified solves, regressions, runtime, and environment/candidate failures.
More incorrect patches or fewer repetitions alone do not justify promotion.
Protected holdout and all launched notebooks remain untouched. No candidate is
recommended for competition submission on this offline evidence.
