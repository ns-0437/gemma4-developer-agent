# Thinking off/on comparison: offline preparation

Written 2026-10-05. **Nothing is prepared for launch. No candidate archive, notebook or dispatch flag
exists yet.** No GPU run, Kaggle push, submission or candidate edit was made. Frozen candidates,
launched notebooks, raw artifacts and the holdout freeze are untouched.

This covers steps 1 to 4 of the handoff's recommended work, executed rather than read, and proposes the
step 5 design with one decision left open because it redefines the submitted baseline.

---

## 1. Disk and Git state, verified

| check | result |
|---|---|
| verification raw artifacts | **46 files, all hashes match** `reference/verification_review/raw_sha256.json` |
| repository sync | local `main` equals `origin/main`, working tree has uncommitted experiment work (below) |
| commit attribution | 28 commits on the remote: 19 authored `navin1282002@gmail.com`, 9 authored `navinkumar0437@gmail.com`, **all 28 linked to `ns-0437`** |

**Correction to the handoff.** It states that nine recent commits were "corrected and verified". No
history was rewritten: the commits I pushed on 2026-10-02 (`fc80271` and earlier) still carry their
original hashes and their original `navin1282002@gmail.com` author. The nine newer commits were simply
authored with a second address. Both addresses are verified on the account, so both already count.
Nothing needs fixing and nothing should be rewritten.

**Uncommitted at the time of writing:** `reference/verification_run_2026-10-03/`,
`reference/verification_review/`, `reference/shellread_run_2026-10-02/`,
`reference/shellread_review/review_summary.json`, `experiments/staged_workflow_v1/`, parts of
`experiments/verification_v1/`, `notebooks/verification/`, and four scripts. These are raw evidence and
reports that exist only on this disk. Committing them is not part of this task and was not done.

---

## 2. Thinking transport, measured on both compilers

`scripts/check_thinking_transport.py` derives two variants from frozen
`experiments/concise_workflow_v1/candidate_S`, differing **only** in the `thinking_config` block,
compiles each with the official compiler, and captures the kwargs ADK hands the LiteLLM client through
an intercepting client that raises before any HTTP. Instruction hashes are asserted equal across
variants. Run once per compiler in its own process.

Captured `client_parameters` for `swe_coder` (the `code_analyzer` sub-agent is identical in every case):

| | adk-submission 0.2.11 | adk-submission 0.2.12 |
|---|---|---|
| `seed` | **absent** | **42** |
| thinking off: `extra_body` | `{chat_template_kwargs: {enable_thinking: false}}` | `{chat_template_kwargs: {enable_thinking: false}}` |
| thinking on: `extra_body` | `{chat_template_kwargs: {enable_thinking: true}}` | `{chat_template_kwargs: {enable_thinking: true}, thinking_token_budget: 4096}` |
| `reasoning_effort` | absent | absent (only set for level low/medium/high) |
| `max_completion_tokens` | 8192 | 8192 |
| compiled `seed` / `thinking_config` | 42 / `{include_thoughts: false, thinking_budget: 4096}` | identical |

Outputs: `transport_0_2_11.json`, `transport_0_2_12.json` in this directory.

### Two stale claims to retire

**CLAUDE.md is wrong as written.** Lines near "Thinking is currently OFF in every candidate (verified
2026-09-26)" and the THINKING A/B PILOT section both assert that **`thinking_budget` is never
forwarded**. That holds for 0.2.11 and is false for 0.2.12, which forwards it as
`extra_body.thinking_token_budget` whenever thinking is enabled with a positive budget. The surrounding
conclusion still holds for the *current* config: `include_thoughts: false` sets `enable_thinking: false`
and the resolver then pops `thinking_token_budget`, so the 4096 in frozen S is inert and every shipped
candidate ran with thinking off.

**My own earlier claim was version-specific and I overstated it.** I previously reported that the ADK
path omits `seed`. That is 0.2.11 behaviour. Under 0.2.12 `seed: 42` **is** forwarded as a client
parameter. This also means the two 2026-10-01 sessions differed in more than I credited: the A/S session
ran 0.2.11 with no seed reaching the client, the temperature session ran 0.2.12 with `seed: 42`
reaching it. That is a further confound on the "byte-identical S did not re-solve `rich_3675`" contrast,
and it is an additional reason not to read that as a candidate property. Forwarding still does not
establish server enforcement.

---

## 3. Context and output budgeting, measured

The earlier thinking arm did not merely underperform, it **died at the request boundary**.
`reference/pilot_v1_results/pilot_results.csv`, candidate B on `requests_7309`:

```
litellm.ContextWindowExceededError: This model's maximum context length is 32768 tokens.
However, you requested 8192 output tokens and your prompt contains at least 24577 input tokens,
for a total of at least 32769 tokens.
```

So the hard constraint is **`prompt_tokens + max_completion_tokens <= 32768`**, checked per request
before generation. With `max_output_tokens: 8192` the prompt ceiling is **24,576**.

I measured recorded `prompt_tokens` across every trace on disk, 29 runs over seven sessions:

| | tokens |
|---|---|
| observed peak prompt_tokens (B/`requests_7309`, last successful call) | **24,425** |
| prompt ceiling at `max_completion_tokens: 8192` | 24,576 |
| **headroom at the observed peak** | **151 tokens** |
| runs peaking above 20,000 | 15 of 29 |
| next highest peaks | 22,742, 22,160, 21,847, 21,747, 21,606 |

Two conclusions follow, and the second is the one that matters most.

**Compaction lags and cannot reserve space.** The comparison notebooks set
`token_threshold=20480`, yet 15 of 29 runs recorded peaks above it, up to 24,425. The trigger reads the
most recently *recorded* prompt token count from an earlier response, so tool output produced since that
measurement is uncounted. `scripts/make_compare_notebook.py` already documents this. Lowering the
threshold widens the margin and guarantees nothing. Do not state that compaction makes a request fit.

**Grading very likely applies no compaction at all.** Verified in harness source:
`swegemma/config.py` declares `events_compaction_config: EventsCompactionConfig | None = None`, and
`swegemma/harness/agent_runner.py` lines 410-411 add it to `app_kwargs` **only when it is not None**. It
is a field of the harness `EvalConfig`, not of the submission, so a submission cannot set it. Our
experiments therefore run with a protection the scored runs do not have, while already peaking 151
tokens short of the ceiling. **A plausible and so far untested contributor to the three 0.06 scores is
long hidden-set runs terminating on `ContextWindowExceededError` with whatever diff happened to exist.**
This is a hypothesis, not a measurement; nothing on disk records a hidden-set run.

The deployable lever is `max_output_tokens` in `configs/sampling.yaml`, which is submission-side and
directly sets the reserved output. Compaction is not available to us.

---

## 4. Verifying the server side: what is and is not establishable offline

From the extracted upstream source, **54 of vLLM 0.19.1's 4,447 files**, so absence of a reference here
is not absence in the shipped wheel, and the run used a host-dataset wheel whose byte equivalence with
upstream is not established:

- `enable_thinking` **is consumed**: `examples/tool_chat_template_gemma4.jinja` branches on it at lines
  171, 174 and 328, and `vllm/reasoning/gemma4_reasoning_parser.py` documents that
  `enable_thinking=True` in chat-template kwargs injects the thinking section.
- `thinking_token_budget` **is a recognised top-level request field**:
  `entrypoints/openai/chat_completion/protocol.py:183` declares it and line 519 threads it into the
  constructed `SamplingParams`. Since LiteLLM merges `extra_body` into the top-level request body for
  OpenAI-compatible endpoints, 0.2.12's `extra_body.thinking_token_budget` should arrive in the field
  vLLM expects.
- **Engine enforcement is not established.** No code that acts on that sampling param is present in the
  extracted subset.

A GPU run can establish enforcement without any new instrumentation, from evidence the harness already
records: compare `completion_tokens` per call between arms, which must rise materially on the thinking
arm if thinking is generating, and check that no call's completion count approaches
`max_completion_tokens` in a way that implies the budget was ignored. A stronger check needs
`extra_args=["--enable-log-requests","--enable-log-outputs"]` on the server and decoding
`output_token_ids` from the server log, which is the pre-parser diagnostic already described in
CLAUDE.md and is **not** requested here.

Incidental finding, recorded because it is relevant to the repetition problem and easy to misread as a
fix: vLLM 0.19.1's request protocol also carries a `repetition_detection` sampling param
(`protocol.py` line 523 region). It is **not reachable from a submission**, because 0.2.12 writes only
specific keys into `extra_body` and our sampling goes through a constrained `GenerateContentConfig`.
Do not propose it as a candidate change.

---

## 5. Proposed matched design, with one open decision

Both arms derive from frozen S, identical prompts, identical tool lists, identical analyzer, same tasks,
alternating order. The only intended difference is the thinking block.

```yaml
# arm OFF                         # arm ON
thinking_config:                  thinking_config:
  thinking_budget: 4096             thinking_budget: <B>
  include_thoughts: false           include_thoughts: true
```

`max_output_tokens` must be the same in both arms. **That value is the open decision, because it
changes the baseline relative to submitted v3.**

| option | prompt ceiling | headroom over observed 24,425 peak | cost |
|---|---|---|---|
| keep `8192` | 24,576 | **151 tokens** | repeats the exact condition that killed the earlier thinking arm; a context error on either arm voids that run |
| **`4096` both arms** (recommended) | 28,672 | 4,247 tokens | halves the output allowance; thinking budget must then be well under 4096, suggesting `<B> = 1024`, leaving about 3,072 for the visible answer |
| `6144` both arms | 26,624 | 2,199 tokens | middle ground, still thin against unbounded growth |

I recommend **4096 for both arms with `<B> = 1024`**, and documenting it as a new baseline that is no
longer v3's sampling. The reason is that at 8192 the comparison is not merely risky, it is likely to be
undecidable again: a request-boundary death produces an ungraded row, and two ungraded rows would leave
the thinking question exactly where it is now. The cost is real and should be stated plainly: a 4096
output cap is itself an untested change to the candidate, so this experiment would measure thinking
on/off *at a new output budget*, not thinking on/off at v3's budget.

An alternative worth considering instead of either: run the **output-budget change on its own first**,
thinking off on both arms, `8192` against `4096`. That tests the context-exhaustion hypothesis from
section 3 directly, is fully deployable, and does not entangle it with thinking. Given that no candidate
has produced a verified solve since `rich_3675`, and that section 3 identifies a mechanism that could
be costing graded rows on the hidden set, this may be the better use of the next authorized session.

**Not decided here, and not to be decided without you:** which of those two experiments runs first, and
what `max_output_tokens` the eventual submitted baseline carries.

---

## 6. Limitations to carry into any request for GPU authorization

- Everything above is transport, source reading and recorded-token arithmetic. **No model, GPU, server
  or network was invoked.** Forwarding a field does not mean the server honours it.
- Local LiteLLM is 1.102.1; the Kaggle runtime recorded 1.82.4. The interception happens before
  LiteLLM's HTTP conversion, so neither version's wire serialization was tested. No parity claim.
- The installed compiler is 0.2.11; 0.2.12 was exercised from extracted source, not from an installed
  wheel. Wheel sha256 `077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10`.
- The 24,425 peak is the highest *recorded* prompt count, taken from a successful call. Peaks are not
  bounded by anything measured, so no configuration here is proved safe, only safer.
- The no-compaction-in-grading finding is read from harness source. It states what the code does when
  the graders leave the field unset; it is not an observation of a scored run.
- Four selected Rich development tasks remain the development pool. The holdout freeze
  (`220869409441c04d7c8f32ef5ab141df02f754cce352495deeb48995a7483b4b`, twelve protected tasks including
  all seven validated FastAPI and Requests tasks) is untouched, and no cross-repository claim is made.
- Measure correct graded patches, regressions, ungraded outcomes and runtime. No score is predicted and
  nothing here supports predicting 0.15 or 0.20.
