# Feedback-path audit: did the repeated command's observations reach later model requests?

2026-09-30, offline. Raw artifacts under `reference/stage1_run_2026-09-30/` are unmodified; hashes in
`raw_sha256.json`. No GPU, no push, no submission.

**The question.** Candidate R issued one `python3 -c` regex probe **56 times**. A trace that records an
observation does not by itself prove that observation entered the next outgoing model request. This
audit separates what this run RECORDED from what the installed source says the code DOES.

---

## A. Facts recorded during this run

These come from the downloaded artifacts and from nothing else.

| fact | value | source |
|---|---|---|
| model turns | 60 | `trace_rich_3278.json`, 62 steps minus system and task prompts |
| tool calls | 59 `run_command`, 1 `read_file` | trace |
| distinct payloads | 5 | trace |
| dominant repeat | one `python3 -c` regex probe, **56 times** | trace |
| rejected calls | 0 | trace |
| `submit_patch` calls | **0** | trace |
| prompt tokens, first turn | 5,514 | trace `metrics.prompt_tokens` |
| prompt tokens, last turn | 19,538 | trace |
| **decreases between consecutive turns** | **0 of 59 transitions** | trace |
| per-turn growth during the repeat loop | **exactly +128 tokens**, every turn | trace, e.g. 12,626 -> 12,754 -> 12,882, and 18,642 -> ... -> 19,538 |
| configured `token_threshold` | 20,480 | armed notebook |
| threshold crossed | **no**, peak 19,538 | trace vs notebook |
| compaction or nudge events in the trace | none (`event_type` is only `system_instruction`, `task_prompt`, and 60 plain agent turns) | trace |

**What the recorded numbers support.** The request context **grew monotonically** across all 60 turns
and never shrank, which is consistent with history being retained. The growth during the repeat loop is a constant +128 tokens per turn, which is
consistent with one tool call plus one tool response being appended each time. Compaction was
configured but its threshold was never reached, so it cannot have removed anything on this run. No
rewind, retry or reset event appears anywhere in the trace.

This is consistent with history being retained rather than truncated, reset or compacted. It does not
prove what the request bodies contained. On the evidence available, the agent re-issued an identical
call 56 times while the context was growing in a way consistent with that call and its result already
being present.

---

## B. Source-level reconstruction, kept separate

Read from the installed packages, not from this run.

| hop | what the source does | reference |
|---|---|---|
| the agent loop passes only the newest message | `runner.run_async(..., session_id=session.id, new_message=current_message)` | `swegemma/harness/agent_runner.py:521-524` |
| ADK rebuilds the whole request from session events every turn | `llm_request.contents = _get_contents(..., invocation_context.session.events, ...)` | `google/adk/flows/llm_flows/contents.py:73` |
| function calls and their responses are paired and re-ordered, not dropped | `_rearrange_events_for_async_function_responses_in_history`, `_rearrange_events_for_latest_function_response`, `_merge_function_response_events` | `contents.py:101, 148` |
| history can be removed only by an explicit rewind action | events between a `rewind_before_invocation_id` marker and its target are filtered out | `contents.py:445-460` |
| or by branch filtering | `_should_include_event_in_context` | `contents.py:466` |
| or by events compaction | `EventsCompactionConfig(token_threshold=20480)`, driven by the most recently recorded prompt token count | `flows/llm_flows/compaction.py`, wired at `single_flow.py:49` |

Section A gives no indication that any of those three paths was taken: no rewind event appears in the
trace, the run used a single agent branch, and the recorded peak stayed below the threshold. That is
absence of evidence for removal, from the records this run kept. It is not a proof of exclusion, since
the requests themselves were not captured.

---

## C. What this audit does NOT establish

Stated plainly, because the distinction is the point of the exercise.

1. **The actual outgoing HTTP requests were not captured.** Nothing in this run recorded the request
   bodies sent to the vLLM server. The prompt token counts come from the server's usage metadata as
   ADK recorded it, which is strong evidence about request SIZE and growth, and no evidence at all
   about the internal ORDERING or ASSOCIATION of call and response inside those requests.
2. **This audit therefore does not prove the model saw the observations.** It proves the context was
   not shrinking and that the code path has no unconditional drop. Those are different claims.
3. **No transport defect is claimed, and none was found.** The obvious hypothesis, that feedback was
   being lost so the agent could not know it had already run the command, is **not supported** by the
   recorded growth pattern. Inventing one would be unfounded.
4. The +128 tokens per turn is consistent with call-plus-response being appended, but the token
   accounting alone cannot confirm the response TEXT was the observation the trace records.

**Conclusion: no concrete feedback-path defect was found.** Under the review's own instruction, that
means the next step is a prompt-package experiment, not a transport fix.

---

## D. What the run does show about the behaviour

Candidate R's prompt already contains **five** separate instructions against exactly this behaviour,
verified in `experiments/tool_recovery_v1/candidate_R/prompts/system.md`:

- "**Do not repeat a call when nothing relevant has changed since you last ran it.**"
- "Re-issuing an identical call against unchanged state is not: it will return what you already have."
- "If you are stuck after two attempts at the same sub-problem, submit the best source change you have
  rather than continuing."
- "Avoid repeating equivalent searches."
- "do not re-run the same command hoping for a different answer."

The agent repeated one command 56 times. The recorded token growth is consistent with those
instructions and the full history still being in context, though the request contents were not
captured and so cannot be confirmed.

**The correction this forces:** describing repetition as a missing instruction was wrong. The
instructions were present in the prompt, the recorded growth is consistent with them remaining in
context, and the behaviour did not follow them. Adding a sixth phrasing of the same rule has no
evidential support and is not proposed.

The remaining candidate-side hypothesis, untested and explicitly labelled as such, is that a long
procedural prompt competes for attention with the task, and that a shorter one may be followed more
reliably. **That is a hypothesis about prompt packaging, not a demonstrated cause of the loop.**
Candidate S tests it; it does not assume it.
