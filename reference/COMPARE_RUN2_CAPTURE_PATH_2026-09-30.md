# Response path, capture points, and the smallest useful GPU diagnostic

2026-09-30, offline. No GPU launch, no Kaggle push, no submission. Frozen candidates, launched
notebooks, task selection and held-out data unchanged. `notebooks/compare/compare.ipynb` ships
`DISPATCH_CONFIRM = False`.

This replaces the "raw-completion capture via `after_model_callback`" proposal, which was wrong.

---

## 1. The actual response path, with what each hop holds

Proof script: `scripts/capture_point_proof.py`, **12 assertions, 0 failures**, run against the
installed google-adk **1.36.1** and litellm **1.102.1** (the competition versions).

| # | Hop | Representation at this point | Reference |
|---|---|---|---|
| 1 | model decodes tokens | the raw completion text | inside the vLLM server process |
| 2 | vLLM `--tool-call-parser gemma4` extracts tool calls from that text | **the parse happens here**; input is the step-1 text, output is an OpenAI `tool_calls` list | server launched as `python -m vllm.entrypoints.openai.api_server` with `--enable-auto-tool-choice --tool-call-parser gemma4` (`adk_submission/server.py:665-693`) |
| 3 | HTTP response to the client | `choices[].message.tool_calls[].function.arguments` is a **JSON string**. The step-1 text is **not** transmitted | OpenAI schema; `VllmConfig` at `server.py:95-147` |
| 4 | litellm deserialises | `ChatCompletionMessageToolCall` with `function.arguments` still a string | litellm 1.102.1 |
| 5 | ADK `_split_message_content_and_tool_calls` | structured `tool_calls` present, so ADK's own inline-JSON fallback is **skipped** | `google/adk/models/lite_llm.py:1367`, short-circuit at `1378-1381` |
| 6 | ADK `_message_to_generate_content_response` | `args = json.loads(tool_call.function.arguments or "{}")` -> a Python dict | `lite_llm.py:1730` |
| 7 | `after_model_callback` | an `LlmResponse` containing that dict | `flows/llm_flows/base_llm_flow.py:247`, invoked at `1270` with the converted response |
| 8 | ADK `FunctionTool.run_async` | filters the dict to declared parameters, then rejects if a mandatory one is missing, **without invoking the tool** | `google/adk/tools/function_tool.py:170-188` |

### What this settles

**An `after_model_callback` is a post-parser capture point.** [C3] builds a response, runs a callback
on it, and observes a `dict` with no accompanying text. Calling it pre-parser capture would be false.

**[C1] establishes that ADK preserves a supplied `arguments` object, and nothing more.** It takes
the recorded dictionary, serialises it to a JSON string, puts that string in `function.arguments`, and
runs the real ADK conversion: ADK reproduces the dictionary **byte-for-byte**, including both
content-fragment keys. That shows no ADK-side mangling is *needed* to explain the recording. It does
**not** on its own identify the upstream producer. Identifying it required the server-side parser, and
that is settled separately in `COMPARE_RUN2_PARSER_2026-09-30.md`.

**ADK's own text parser cannot be the culprit.** [C2] shows the fallback is skipped whenever
structured `tool_calls` are present, and that it uses `json.JSONDecoder().raw_decode`, which is strict
JSON. Fed the real end-of-run text `<|tool_call>call:git grep ... <tool_call|>` it returns **no** tool
call and passes the text through as content. That is why trace steps 51/53/55/57 carry text at all:
nothing parsed them into a tool call. Call these four **unparsed client-visible response text**. They
are not established to be the original pre-parser bytes; that would need the server code to show the
text is passed through unmodified.

### Capture points, ranked by what they can actually see

| Candidate point | Sees | Verdict |
|---|---|---|
| ADK `after_model_callback` | step 6's dict | **post-parser. Useless for this question.** Would re-record what the run already has |
| vLLM `--enable-log-requests --enable-log-outputs` | **verified 2026-09-30: the logged `output:` field is the PARSED form (`[tool_calls: name(arguments)]`), but `output_token_ids` is logged in full at INFO** | the token ids decode to the pre-parser text. See `COMPARE_RUN2_PARSER_2026-09-30.md` section 5 |
| litellm `log_raw_request_response` / `model_call_details["original_response"]` (`litellm/__init__.py:208`; `litellm_core_utils/litellm_logging.py:1461-1472`) | step 3's HTTP body: the `arguments` **string** | post-parser, but it rules litellm and ADK in or out and confirms the string that arrived. Cheap. Logs the full request too, so prompts and the `Authorization: Bearer EMPTY` header must be redacted |
| vLLM server log | step 1/2 | **the only pre-parser point, and it exists.** Verified in the 0.19.1 source: see the row above and `COMPARE_RUN2_PARSER_2026-09-30.md` section 5 |
| Serving with the parser disabled | step 1 text as `content` | pre-parser, but it changes execution semantics completely: the agent would receive no tool calls and could not work. A separate probe, never instrumentation of a comparison |

---

## 2. The parser: status, and why it comes first

`scripts/parser_fixture_harness.py --show-format` records the environment and exits **2**:

```
vllm_importable: false
import_error: ModuleNotFoundError: No module named 'vllm'
```

vLLM is nowhere on this machine (searched; only `litellm`'s unrelated `llms/vllm` adapter exists) and
not among the three wheels kept in `reference/harness_src/`. **The parser's expected wire format is
therefore UNKNOWN, and nothing here assumes it is JSON.** The harness simulates no parser and
fabricates no expected output; the corpus carries content only, and the rendering will come from the
parser's own source once read.

**This is the decisive point.** Because the recorded dictionaries are the parser's output, reading the
parser source can settle model-versus-parser **with no GPU run at all**:

- if the `gemma4` parser builds `arguments` by splitting a delimited `key:value` payload, then content
  containing `,` `:` `` ` `` can produce exactly the observed four-pair object, and the loss of
  `old_string` is a parser transformation;
- if the parser only extracts a JSON blob verbatim and passes it through, then the model emitted that
  JSON object, and the defect is upstream of the parser.

Either answer changes which lever to pull next, and neither needs a GPU.

### Fixtures, built and waiting on the parser

`reference/parser_fixtures/corpus.json` holds 12 cases, each isolating one character class:

| id | shape | question |
|---|---|---|
| p01 | the real `rich/ansi.py` regex, taken from the agent's own `read_file` observation | does `old_string` survive? |
| p02 | plain ASCII | baseline |
| p03 / p04 | commas / colons in values | is either a separator? |
| p05 / p06 | double quotes / backticks | is either a delimiter? The run-2 residue ended with a backtick |
| p07 / p08 | single / doubled backslashes | who doubles the escaping, parser or model? |
| p09 | multi-line values | is a newline significant? |
| p10 | Unicode incl. the CJK brackets from the run-2 variant | does Unicode survive, and can it appear where the model did not put it? |
| p11 | `old_string` omitted by construction | control: a genuinely missing parameter, distinct from one lost in transit |
| p12 | content literally containing the text `old_string:` | can content spell a parameter name and be split on it? This is the residue's signature |

Recorded against the parser, each case yields: the rendered input, the parser's `tool_calls` output,
`json.loads` of `arguments`, and whether ADK would then reject the call. p11 versus p12 is the pair
that discriminates "the model forgot a parameter" from "the transport ate one".

### What I need from you

The parser must come from an official source with a recorded hash. That means a download, so I am
asking rather than doing it:

- **`vllm==0.19.1` source distribution from PyPI**, `pip download --no-deps --no-binary :all: vllm==0.19.1`, roughly 10-40 MB compressed. I would record the sdist's SHA-256 and the `gemma4` parser file's SHA-256, unpack it read-only under `reference/vllm_0.19.1_src/`, and **not install it** (it needs Linux and CUDA and would not install here anyway).
- A large archive of ML source may attract attention from antivirus on unpack. Flagging that before, not after.
- If you would rather not download anything, say so: the fallback is to treat the parser as permanently unknown, which leaves the question open and makes the GPU diagnostic in section 4 the only route.

---

## 3. Report corrections applied

| Point | Change |
|---|---|
| A's exit-0 reproduction | now reads: it **ran** successfully and its output **demonstrated the bug** (`Match: None` for all four private escape codes, the unfixed behaviour). Explicitly not evidence of a passing fix |
| Repeated feedback causing repeated calls | moved from **Established** to **Plausible**. What is established is *what the model was told*: ADK's argument filter (`function_tool.py:171`) means the error names only `old_string` and never mentions the mangling. That this *caused* the repetition is a hypothesis; low temperature on a near-identical prompt or a decoding attractor are not ruled out, and no intervention on the feedback text has been tried |
| `successful_source_edits` | renamed **`acknowledged_source_edit_calls`** in code, notebook, tests, mutation suite, CSVs and both write-ups. It counts calls the tool accepted. No before/after file comparison exists anywhere in these artifacts |
| Empty final `git diff` | now reads: it establishes **no net tracked change at the end of the run**. An untracked file, a write followed by a revert, or a change outside the diff's scope would leave identical evidence |
| Runtime estimate | now labelled **an estimate, not an upper bound**, with the reasons: vLLM startup varied 6-9.6 min across runs, grading time for these tasks is unmeasured, `SESSION_CAP_MIN` is an admission limit that does not kill work in flight, and a run thrashing on tool errors spends wall clock without spending tool budget |

Suites after the rename: trace metrics **75/0**, compare dispatch **137/0**, pilot **82/0**,
capture-point proof **12/0**. Regenerated notebook `7abdc6786e867832ffe209731a8eacc4ae4a80850370a7e1690ff9ea8f37b606`, dispatch disabled.

---

## 4. The smallest useful GPU diagnostic

Only if the parser source leaves the question open. **Not an eight-run comparison**, and explicitly
not a run whose purpose is to discover that a hook records already-parsed data.

**Shape.** One task, one candidate, one arm. `rich_3278` with candidate B, the run that produced the
42 rejections. Success is a recording, not a score.

**Capture, in order of preference:**

1. **Server-side, if a flag exists.** Add the output-logging flag via `VllmConfig.extra_args` and read
   `server_instance.log_path` afterwards. Requests, sampling and client code are untouched; only the
   server's log verbosity changes. Whether such a flag exists in 0.19.1 is unknown until the source is
   read, and the flag name must come from that source, not from a newer vLLM's documentation.
2. **Client-side, always available.** `litellm.log_raw_request_response = True` plus a success callback
   storing `model_call_details["original_response"]`, keyed to the turn. This does not reach step 1,
   but it pins down the exact `arguments` string that arrived, which is the parser's output, and it
   removes litellm and ADK from suspicion by observation rather than by argument.

**Correlation.** Each captured record carries `(task, candidate, run_id, llm_call_index)` taken from
the harness's own counters, plus the SHA-256 of the rendered prompt, so a captured raw record can be
matched to a trace step without relying on wall-clock ordering under continuous batching.

**Preserving request and parser behaviour.** The capture must not alter the outgoing request. Before
any run I would assert offline that: the compiled agent's `generate_content_config` is byte-identical
with and without the capture attached; `scripts/effective_settings.py` prints the same effective model
arguments; and enabling `log_raw_request_response` adds no request field. **If any of those differ, the
experiment is invalid and does not run.**

**Credentials.** `api_key="EMPTY"` is the only secret-shaped value in play, but raw request logging
captures headers and full prompts. Every record passes a redactor that drops `Authorization`,
`api-key` and `x-api-key` headers and any `sk-`-prefixed token before anything is written, and the
capture file is asserted not to contain the string `Bearer` before it is saved.

**Known limitations, stated in advance.** Option 2 is post-parser and cannot by itself answer
model-versus-parser; it narrows the answer rather than settling it. Option 1's existence is unverified.
Raw logging adds I/O per turn, which perturbs timing, so timing numbers from this run must not be used
for the 12-hour projection. One task from one repository. Subprocess backend, which is not a filesystem
isolation boundary and is not the grader's Docker path.

**Cost.** ~17 min CPU setup and controls, ~6-10 min vLLM startup, one run bounded by
`max_time_minutes=10` plus grading: **roughly 35-45 min, an estimate rather than a bound.**

**This needs a fresh authorization in your own words, and I have not prepared a push.** It should not
be requested until the parser source has been read and has failed to settle the question.

---

## 5. Remaining unknowns

1. **The `gemma4` parser's wire format and splitting rules.** Blocks the central question. Needs the
   download in section 2.
2. **Whether vLLM 0.19.1 can log generated text**, and under what flag. Same blocker.
3. **The raw completions for the 42 rejected steps.** Permanently unavailable; the trace records
   `tool_calls` only after parsing. Not reconstructable, and not reconstructed.
4. **Whether the over-escaping (`\\x1b` for `\x1b`, `r\"\"\"` for `r"""`) comes from the model or the
   transport.** The clean `filepath` value does not discriminate, because it contains no escapes.
5. **Whether the repetition was caused by the uninformative error text.** Hypothesis only.
6. **Whether any file was ever written during either run.** Only the end-of-run diff and the
   acknowledged-call count are known.
7. **`finish_reason` is absent from every trace step**, so the harness's truncation branch cannot be
   audited from artifacts; the 26-token completions make it implausible, which is not the same as
   refuted.
8. **Why v1, v2 and v3 all scored 0.06 under Docker grading.** Untouched by any of this.
