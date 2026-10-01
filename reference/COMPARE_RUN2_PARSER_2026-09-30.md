# The vLLM gemma4 tool parser: offline evidence packet

2026-09-30. Offline. No GPU launch, no Kaggle push, no submission. Frozen candidates, launched
notebooks, task selection and held-out data unchanged. `notebooks/compare/compare.ipynb` ships
`DISPATCH_CONFIRM = False`. Nothing was installed.

---

## 1. Verified version and source hashes

### Which build the evaluation actually ran

| | |
|---|---|
| recorded by the run | `pilot_manifest.json` -> `package_versions.vllm = "0.19.1"` |
| how it was recorded | `importlib.metadata.version("vllm")` in the notebook's install cell |
| how it got there | the install cell runs `pip install -q --no-deps --force-reinstall` over **41 wheels** symlinked from the host dataset `metric/gemma-4-developer-agent-wheelhouse` (kernel log: `installing 41 wheels...`) |

**So the running vLLM was a wheel from the host's Kaggle dataset, not from PyPI.** Its distribution
metadata reports `0.19.1`. That wheel is not available on this machine, so **byte equivalence with the
upstream release is NOT established**, and everything below is labelled as upstream behaviour. The two
published wheels for 0.19.1 are manylinux x86_64 and aarch64; if the host simply mirrored the x86_64
wheel then the parser file is identical, but nothing here demonstrates that.

Also worth recording, because it differs from the environment used for the client-side proof:
the run had **litellm 1.82.4**; this machine has **1.102.1**. google-adk matches at **1.36.1**, and the
conversion hop that matters (`json.loads` of `arguments`) is ADK code, not litellm code.

### The upstream source, fetched and verified

`scripts/fetch_vllm_parser_source.py`. PyPI's JSON metadata was read, the archive was fetched straight
from the release URL with `urllib`, and its digest was checked before the archive was opened. pip was
not used, so vLLM's `setup.py` and CUDA metadata preparation never ran.

| | |
|---|---|
| metadata | `https://pypi.org/pypi/vllm/0.19.1/json` |
| distribution | `vllm-0.19.1.tar.gz` (sdist), 31,105,401 bytes, uploaded 2026-04-18T05:50:15Z |
| published sha256 | `9fb88ce6b50991eba41d183584f65f51d7f6015d86a42cdabf79c1c8bd5d66fa` |
| computed sha256 | `9fb88ce6b50991eba41d183584f65f51d7f6015d86a42cdabf79c1c8bd5d66fa` **MATCH** |
| installed | **no** |
| extraction | allow-listed path prefixes only, 56 of 4,447 files; every member checked to be a regular file and to resolve inside the destination; links and escapes refused |
| parser file | `vllm/tool_parsers/gemma4_tool_parser.py`, 27,743 bytes, sha256 `682b2152b76c031df9c58c3ffbb5b243945be5d8957ebdce00faef1b9de6b889` |

Per-file hashes are in `reference/vllm_0.19.1_src/PROVENANCE.json`. Note the path: in 0.19.1 the tool
parsers live at `vllm/tool_parsers/`, not the `vllm/entrypoints/openai/tool_parsers/` of older
releases. My first allow-list guessed the old layout and extracted nothing relevant; the archive was
listed and the list corrected before extracting.

---

## 2. The parsing path our evaluation used

**Non-streaming `extract_tool_calls`.** Established, not assumed:

- `swegemma/harness/agent_runner.py:516` builds `RunConfig(max_llm_calls=remaining_turns)` and sets no
  `streaming_mode`;
- ADK's default is `streaming_mode: StreamingMode = StreamingMode.NONE`
  (`google/adk/agents/run_config.py:225`);
- `base_llm_flow.py:1294` derives `stream=` from that mode.

Both paths were inspected. They share `_parse_gemma4_args`, so the format findings apply to both, but
the streaming entry point (`extract_tool_calls_streaming`, accumulate-parse-diff with a withheld
trailing-character prefix) was never exercised by our run. Streaming results below are informational.

### The native format is not JSON

From the parser's own module docstring and constants:

```
<|tool_call>call:func_name{key:<|"|>value<|"|>,num:42}<tool_call|>
```

- `TOOL_CALL_START = "<|tool_call>"`, `TOOL_CALL_END = "<tool_call|>"`, `STRING_DELIM = '<|"|>'`
- keys are **unquoted**, pairs separated by `,`, key and value separated by the **first** `:`
- a string value is recognised **only** if it begins with the `<|"|>` token
- anything else is a "bare value" scanned until the next `,`, `}` or `]`
- non-streaming extraction is a single regex:
  `<\|tool_call>call:([\w\-\.]+)\{(.*?)\}<tool_call\|>`
- the resulting dict is handed to `json.dumps(..., ensure_ascii=False)` and becomes `arguments`

---

## 3. Fixtures: inputs, outputs, failures

`scripts/gemma4_parser_fixtures.py` executes the parser file unchanged and runs 41 cases;
`scripts/test_gemma4_parser_findings.py` asserts the findings (**29 assertions, 0 failures**).
Full records in `reference/parser_fixtures/results.json` and `reconstruction.json`.

Dependency stubs are listed by `--stubs` and none of them touch the parsing logic: `vllm.logger`,
`TokenizerLike`, `make_tool_call_id`, the protocol dataclasses, and a faithful `ToolParser` base
(five attributes plus `vocab` from `get_vocab()`, asserted against the real source so it cannot drift).
`regex` is the real package. `find_common_prefix` is lifted from the real `utils.py` by AST rather than
stubbed. No parsing function is reimplemented.

### With correct delimiters, nothing breaks

All 12 corpus cases round-trip exactly in the `delim` rendering, including **p01, the real failing
content**: the `rich/ansi.py` regex with its backslashes, triple quotes, commas, colons and bracket
character classes. Also clean: Unicode with CJK brackets and an emoji, doubled backslashes, multi-line
values, and content that literally spells `old_string:`.

**The parser is not broken on this content.** That is the single most important fixture result.

### Without the delimiter token, content fragments into keys

`bare` and `backtick` renderings of p01 produce spurious keys that are slices of the regex body, cut at
a `]` and running to the next `(?`, and `old_string` is lost. This is the same damage shape as the
recording.

| rendering | outcome |
|---|---|
| `key:<|"|>value<|"|>` | exact round trip, every case |
| `key:value` (bare) | fine for content with no `,` `:` `}` `]`; fragments otherwise |
| `key:`value`` (backticks) | never round-trips: the backticks land inside the value, and commas still split |

### Delimiter damage

| input | result |
|---|---|
| start tag misspelled `<|tool_call` | no tool call, whole text returned as content |
| end tag misspelled `<tool_call>` | no tool call |
| no braces after the name | no tool call |
| unterminated `<|"|>` string | tool call with a single key, value takes the rest |
| **the real end-of-run text** | no tool call, whole text returned as content |

### Streaming, informational only

Correctly delimited input reassembles into valid JSON at chunk sizes 1, 3, 7 and 29. Not our path.

---

## 4. Established findings versus unresolved causes

### Established

1. **The native format is a custom `key:<|"|>value<|"|>` encoding, not JSON.** Any description of the
   payload as "JSON the model emitted" is wrong.
2. **The parser handles the real failing content correctly when the delimiters are right.** Content
   density in backslashes, quotes, commas, colons or Unicode is **not** the cause. My earlier
   content-dependence hypothesis is refuted for the correctly delimited case.
3. **A single mis-paired closing delimiter reproduces the recorded dictionary byte-for-byte**, keys and
   order included. Two constructed inputs do it (`H1`, `H2`), differing only in whether `filepath` is
   delimited. The malformation: `new_string` is opened with `<|"|>` and closed with a backtick, so the
   next `<|"|>` (intended as `old_string`'s opening delimiter) is consumed as `new_string`'s closing
   one. Everything downstream, including the loss of `old_string` and both fragment keys, then follows
   deterministically. **This demonstrates a possible mechanism. It is not proof of the model's output**,
   which was never recorded and is not recoverable.
4. **Our run used the non-streaming path.** Chunk-boundary behaviour is irrelevant to it.
5. **My "mismatched delimiters" claim was WRONG and is withdrawn.** `<|tool_call>` and `<tool_call|>`
   are the correct tokens and the four end-of-run strings spell both correctly. They failed to parse
   because the regex requires `call:<name>{<args>}` and the text carries a shell command with no
   braces: `call:git grep -n -F -- "re_ansi" -- '*.py' | head -30`. The model emitted a shell command
   where a function call belonged.
6. **The harness's truncation nudge is still misdirected, for a different reason than I gave.**
   `has_truncated_tool_call = '<|tool_call>' in last_assistant_text` (`agent_runner.py:695`) fires
   because the token really is present. The response was not truncated (26 to 30 completion tokens
   against `max_output_tokens: 8192`), and the advice to "split the change into smaller incremental
   edits" does not address a missing `{`.
7. **`--enable-log-outputs` does NOT log pre-parser text, but `output_token_ids` does reach the log.**
   Verified in `chat_completion/serving.py:1622-1652`: the `output:` field is the parsed form
   (`[tool_calls: name(arguments)]`). `entrypoints/logger.py::log_outputs` emits at `logger.info` and
   includes `output_token_ids` in full unless `--max-log-len` is set. Those ids decode to the
   pre-parser text.
8. **`litellm.log_raw_request_response` is post-parser.** The parse happens server-side; the raw HTTP
   body already carries `tool_calls[].function.arguments`.
9. **[C1] was overclaimed and is corrected.** It establishes that ADK preserves a supplied `arguments`
   object through its conversion, not who produced it. The producer question needed section 3.
10. **The four strings are "unparsed client-visible response text."** Whether they are byte-identical
    to the model's output would need the server code to show pass-through, which was not checked.

### Unresolved

| Question | Why it is still open |
|---|---|
| What the model actually emitted | never recorded; `tool_calls` are stored only post-parse. `H1`/`H2` show a reachable path, not the actual one |
| Whether the host's 0.19.1 wheel matches upstream | the wheel is on Kaggle, not here |
| Who doubled the escaping (`\\x1b` for `\x1b`) | the recorded `filepath` has no escapes, so it cannot discriminate |
| Whether the uninformative rejection text caused the 41 identical retries | still a hypothesis |
| Whether any file was written during either run | only the end-of-run diff and acknowledged-call counts are known |
| Why v1, v2 and v3 all scored 0.06 | untouched |

---

## 5. Is an offline compatibility fix justified?

**No parser fix, and no prompt fix yet.**

A parser change is out of the question: it would be a change to the grader's own serving stack, which
we do not control and cannot ship. The submission carries YAML, prompts, skills and adapters only.

A prompt rule is **tempting and still premature**. The finding narrows the target sharply: the failure
is delimiter discipline in the tool-call encoding, not content escaping. But the model does not write
`<|"|>` as text; it emits a special token, and the encoding is applied by the chat template
(`examples/tool_chat_template_gemma4.jinja` is in the extraction). Whether a system-prompt instruction
can influence token-level delimiter pairing at all is unknown, and a rule written against a
reconstruction rather than an observation is exactly the "fitted to an artifact" risk flagged earlier.

What **is** justified offline, and needs no authorization:

1. **A guard, not a fix.** Extend the trace metrics to flag `rejected_tool_calls > 0` together with
   `unparsed_tool_call_texts > 0` as a distinct failure class, so a future run reports "tool-call
   encoding failure" rather than "candidate error". Cheap, and it makes the next run's evidence legible.
2. **Reading the chat template** already extracted, to see where `<|"|>` is emitted and whether any
   prompt-level lever exists at all. No download, no GPU.

---

## 6. The smallest pre-parser capture diagnostic, if one is still wanted

The question this packet leaves open is what the model emitted. One task, one candidate
(`rich_3278` / B), one arm.

**Capture.** `VllmConfig.extra_args = ["--enable-log-requests", "--enable-log-outputs"]`
(`server.py:736` appends `extra_args` verbatim; `cli_args.py:365` requires the pair). Read
`server_instance.log_path` afterwards, which `VllmServer` already writes
(`server.py:180, 272-277`). Take `output_token_ids` from each `Generated response ...` line and decode
them with the model's tokenizer to obtain the pre-parser text.

**Why this and not a client hook.** The parse is server-side; every client-visible representation is
already post-parse. The `output:` field in the same log line is post-parse too. Only the token ids are
upstream of the parser.

**What it does not change.** No request field is added, no sampling parameter moves, no client code
runs differently. `--max-log-len` is deliberately left unset so ids are not truncated.

**Credentials and privacy.** `log_inputs` logs the prompt only at DEBUG; at INFO it logs sampling
params and the LoRA request. Default logging level is INFO, so prompts are not written. The only
secret-shaped value in the system is `api_key="EMPTY"`. Before saving, the log excerpt passes a
redactor dropping `Authorization`, `api-key` and `x-api-key`, and the saved file is asserted not to
contain `Bearer`.

**Limitations, stated up front.** The token ids come from the host's wheel, whose equivalence to
upstream is unverified, so decoding is interpreted against upstream behaviour rather than proven
identical. Logging adds per-request I/O, so timings from this run must not feed the 12-hour projection.
One task, one repository, subprocess backend, which is not a filesystem isolation boundary and is not
the grader's Docker path.

**Cost.** ~17 min CPU setup and controls, ~6 to 10 min vLLM startup, one run bounded by
`max_time_minutes=10` plus grading. Roughly **35 to 45 minutes, an estimate and not a bound.**

**No authorization is requested here, and none is implied by this message.** Items 1 and 2 of
section 5 are offline and can proceed without any.
