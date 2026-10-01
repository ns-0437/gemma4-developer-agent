"""Executable proof of what each proposed capture point actually receives.

The question this settles: can an ADK `after_model_callback` observe the model's PRE-PARSER output?
It cannot, and the proof is run here rather than asserted, by driving the real installed google-adk
1.36.1 conversion path with a response shaped exactly as vLLM's OpenAI endpoint returns one.

Response path, with the reference for each hop:

  1. model generates tokens                      (inside the vLLM server process)
  2. vLLM `--tool-call-parser gemma4` extracts    (vllm.entrypoints.openai.*; NOT inspected here,
     tool calls from that text                    the source is not present in this project)
  3. OpenAI-compatible response over HTTP:        choices[].message.tool_calls[].function.arguments
     `arguments` is a JSON **string**             is a string, per the OpenAI schema litellm parses
  4. litellm returns a ModelResponse              litellm 1.102.1
  5. ADK `_split_message_content_and_tool_calls`  google/adk/models/lite_llm.py:1367
     trusts structured tool_calls and SKIPS its
     own inline-JSON fallback parser              lite_llm.py:1378-1381
  6. ADK `_message_to_generate_content_response`  lite_llm.py:1730
     builds args via `json.loads(arguments)`
  7. `_handle_after_model_callback(ctx,           flows/llm_flows/base_llm_flow.py:247, called at
     llm_response, ...)` receives the LlmResponse  base_llm_flow.py:1270 with the converted response

Step 2 happens in a separate OS process and its input is never transmitted to the client. Steps 5-7
are all downstream of `json.loads`. Therefore:

  * an `after_model_callback` observes step 6's output: a parsed Python dict;
  * a litellm raw-response hook observes step 3: the `arguments` JSON **string**, which is still the
    parser's OUTPUT;
  * only the vLLM server's own log stream can carry step 1/2's input.

Run:  python scripts/capture_point_proof.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv" / "Lib" / "site-packages"
if str(VENV) not in sys.path:
    sys.path.insert(0, str(VENV))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


def recorded_payload() -> dict:
    """The argument dict the harness actually received, as recorded in the trace.

    This is the tool call as OBSERVED AFTER parsing. It is not, and is nowhere treated as, a
    reconstruction of the model's raw completion.
    """
    f = json.loads((ROOT / "reference" / "compare_run2_malformed_calls.json")
                   .read_text(encoding="utf-8"))
    return f["payloads"][0]["arguments"]


def main() -> int:
    import litellm  # noqa: F401  (ADK imports it lazily)
    from google.adk.models import lite_llm as L

    import google.adk as adk
    import importlib.metadata as _md
    print(f"google-adk {adk.__version__}   litellm {_md.version(chr(108)+chr(105)+chr(116)+chr(101)+chr(108)+chr(108)+chr(109))}")
    print(f"conversion:  {Path(L.__file__).as_posix()}")

    print("\n[C1] the observed dict is exactly json.loads of an `arguments` JSON string")
    observed = recorded_payload()
    arguments_string = json.dumps(observed, ensure_ascii=False)
    L._ensure_litellm_imported()   # ADK imports litellm lazily
    # Built with litellm's own types, which is what a real response deserialises into.
    tool_call = L.ChatCompletionMessageToolCall(
        type="function", id="call_12",
        function=L.Function(name="edit_file", arguments=arguments_string))
    message = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
    resp = L._message_to_generate_content_response(message)
    parts = [p for p in resp.content.parts if p.function_call]
    check("one function_call part produced", len(parts) == 1, str(len(parts)))
    got = dict(parts[0].function_call.args)
    check("ADK reproduces the observed dict byte-for-byte", got == observed,
          json.dumps({"got": got, "want": observed}, ensure_ascii=False)[:300])
    check("the two content-fragment keys survive ADK unchanged",
          sorted(got) == sorted(observed), str(sorted(got)))
    print("  -> C1 establishes ONE thing: ADK preserves a supplied `arguments` JSON object through")
    print("     this conversion unchanged. It does NOT by itself establish who produced that object.")
    print("     Identifying the producer needs the server-side parser, which is done separately in")
    print("     scripts/test_gemma4_parser_findings.py against the verified vLLM 0.19.1 source.")

    print("\n[C2] ADK's own inline-JSON fallback CANNOT have produced it")
    # _parse_tool_calls_from_text only runs when the server returned no structured tool_calls, and
    # it uses json.JSONDecoder().raw_decode, which is strict JSON.
    content, calls = L._split_message_content_and_tool_calls(message)
    check("structured tool_calls short-circuit the fallback parser", len(calls) == 1 and content is None,
          f"{content!r} {len(calls)}")
    client_text = "<|tool_call>call:git grep -n -F -- \"re_ansi\" -- '*.py' | head -30<tool_call|>"
    fallback_calls, remainder = L._parse_tool_calls_from_text(client_text)
    check("the real end-of-run client-visible text yields NO tool call from ADK",
          fallback_calls == [], str(fallback_calls))
    check("ADK passes that text through as content", remainder == client_text.strip(), repr(remainder)[:120])
    print("  -> this is why trace steps 51/53/55/57 carry text: nothing parsed it into a tool call,")
    print("     so it survived as message content. Call these four UNPARSED CLIENT-VISIBLE RESPONSE")
    print("     TEXT. They are not established to be the original pre-parser bytes: that needs the")
    print("     server code to show the text is passed through unmodified.")

    print("\n[C3] a callback placed after the model sees the parsed form, not the text")
    seen = {}

    def after_model_callback(callback_context, llm_response):
        parts = [p for p in (llm_response.content.parts or []) if p.function_call]
        seen["args_type"] = type(parts[0].function_call.args).__name__ if parts else None
        seen["has_raw_text"] = any(
            getattr(p, "text", None) for p in (llm_response.content.parts or []))
        return None

    after_model_callback(None, resp)
    check("the callback receives a dict, already parsed", seen["args_type"] == "dict", str(seen))
    check("no raw completion text accompanies it", seen["has_raw_text"] is False, str(seen))
    print("  -> an after_model_callback is a POST-parser capture point. Describing it as pre-parser")
    print("     capture would be wrong.")

    print("\n[C4] the only capture point upstream of the parser is the server's own log")
    src = (ROOT / "reference" / "harness_src" / "src_adk_submission" / "adk_submission"
           / "server.py").read_text(encoding="utf-8")
    check("the server subprocess writes stdout to a log file",
          "stdout=self._log_file_handle" in src and "stderr=subprocess.STDOUT" in src)
    check("that log file's path is exposed as .log_path", "self.log_path: str" in src)
    check("VllmConfig accepts extra vLLM flags without patching adk_submission",
          "extra_args: list[str] = field(default_factory=list)" in src)
    check("the parser runs in a separate OS process",
          "vllm.entrypoints.openai.api_server" in src)
    prov = ROOT / "reference" / "vllm_0.19.1_src" / "PROVENANCE.json"
    check("the verified vLLM 0.19.1 source is present for the server-side question",
          prov.exists() and json.loads(prov.read_text(encoding="utf-8"))["digest_verified"] is True)
    print("  -> the model's pre-parser text exists only inside that process. Reaching it means a")
    print("     server-side log flag, not a client callback. Which flag, and what it actually logs,")
    print("     is settled in scripts/test_gemma4_parser_findings.py and section 5 of")
    print("     reference/COMPARE_RUN2_PARSER_2026-09-30.md.")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
