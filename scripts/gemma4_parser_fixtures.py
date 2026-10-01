"""Drive the REAL vLLM 0.19.1 gemma4 tool parser over fixture inputs, offline.

The parser file is executed unchanged from the verified sdist extraction under
`reference/vllm_0.19.1_src/`, and its SHA-256 is checked against `PROVENANCE.json` before anything
runs. None of the parsing logic is reimplemented, simulated or replaced.

DEPENDENCY STUBS, and why each is safe (printed by --stubs so the list cannot drift silently):

  vllm.logger                                     init_logger -> stdlib logging
  vllm.tokenizers.TokenizerLike                   a typing alias only
  vllm.entrypoints.chat_utils.make_tool_call_id    id generator, streaming only, no parsing
  vllm.entrypoints.openai.*.protocol              plain dataclasses standing in for pydantic models:
                                                  FunctionCall, ToolCall, DeltaMessage,
                                                  DeltaToolCall, DeltaFunctionCall,
                                                  ExtractedToolCallInformation, requests
  vllm.tool_parsers.abstract_tool_parser.ToolParser  faithful stub of the real base: it sets five
                                                  attributes and exposes vocab via
                                                  model_tokenizer.get_vocab(). Verified against
                                                  the extracted source. Holds no gemma4 logic
  vllm.sampling_params / vllm.utils.*             imported by the base module only, never reached

NOT stubbed, because they are part of the logic under test:
  `regex` (the real package, the same one the parser imports)
  `vllm.tool_parsers.utils.find_common_prefix` (extracted from the real file by AST, byte-exact)
  every module-level function and the non-streaming regex in gemma4_tool_parser.py

Run:
  python scripts/gemma4_parser_fixtures.py            # run every case, write results
  python scripts/gemma4_parser_fixtures.py --stubs     # print the stub inventory and exit
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import logging
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reference" / "vllm_0.19.1_src"
PARSER_FILE = SRC / "vllm" / "tool_parsers" / "gemma4_tool_parser.py"
UTILS_FILE = SRC / "vllm" / "tool_parsers" / "utils.py"
BASE_FILE = SRC / "vllm" / "tool_parsers" / "abstract_tool_parser.py"
OUT = ROOT / "reference" / "parser_fixtures"
RECORDED = ROOT / "reference" / "compare_run2_malformed_calls.json"

STRING_DELIM = '<|"|>'
START, END = "<|tool_call>", "<tool_call|>"

STUBS = [
    ("vllm.logger", "init_logger -> stdlib logging.getLogger"),
    ("vllm.tokenizers", "TokenizerLike, a typing alias"),
    ("vllm.entrypoints.chat_utils", "make_tool_call_id, streaming-only id generator"),
    ("vllm.entrypoints.openai.chat_completion.protocol", "ChatCompletionRequest dataclass"),
    ("vllm.entrypoints.openai.engine.protocol",
     "FunctionCall / ToolCall / Delta* / ExtractedToolCallInformation dataclasses"),
    ("vllm.entrypoints.openai.responses.protocol", "ResponsesRequest dataclass"),
    ("vllm.tool_parsers.abstract_tool_parser",
     "Tool alias + faithful ToolParser base (5 attributes, vocab from get_vocab)"),
]


# ---------------------------------------------------------------- integrity
def verify_source() -> dict:
    prov = json.loads((SRC / "PROVENANCE.json").read_text(encoding="utf-8"))
    rel = "vllm/tool_parsers/gemma4_tool_parser.py"
    want = prov["files"][rel]["sha256"]
    got = hashlib.sha256(PARSER_FILE.read_bytes()).hexdigest()
    if got != want:
        raise SystemExit(f"parser file changed since extraction\n  expected {want}\n  got      {got}")
    return {"sdist_sha256": prov["published_sha256"],
            "digest_verified": prov["digest_verified"],
            "parser_file": rel, "parser_sha256": got,
            "parser_bytes": prov["files"][rel]["bytes"],
            "release_url": prov["release_url"]}


def extract_function(path: Path, name: str):
    """Compile ONE real function out of a real file, byte-exact, without importing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    mod = ast.Module(body=[node], type_ignores=[])
    ns: dict = {}
    exec(compile(ast.fix_missing_locations(mod), f"<{path.name}:{name}>", "exec"), ns)
    return ns[name]


# ---------------------------------------------------------------- stubs
def install_stubs() -> None:
    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    @dataclasses.dataclass
    class FunctionCall:
        name: str
        arguments: str

    @dataclasses.dataclass
    class ToolCall:
        function: FunctionCall
        type: str = "function"
        id: str = "call_stub"

    @dataclasses.dataclass
    class DeltaFunctionCall:
        name: str | None = None
        arguments: str | None = None

        def model_dump(self, exclude_none=False):
            d = dataclasses.asdict(self)
            return {k: v for k, v in d.items() if not (exclude_none and v is None)}

    @dataclasses.dataclass
    class DeltaToolCall:
        index: int
        function: dict | None = None
        type: str | None = None
        id: str | None = None

    @dataclasses.dataclass
    class DeltaMessage:
        content: str | None = None
        tool_calls: list | None = None

    @dataclasses.dataclass
    class ExtractedToolCallInformation:
        tools_called: bool
        tool_calls: list
        content: str | None

    @dataclasses.dataclass
    class ChatCompletionRequest:
        tools: list | None = None
        tool_choice: str | None = None
        skip_special_tokens: bool = True

    @dataclasses.dataclass
    class ResponsesRequest:
        pass

    class ToolParser:
        """Faithful stand-in for vllm.tool_parsers.abstract_tool_parser.ToolParser.

        Mirrors the extracted source: five attributes plus `vocab` from get_vocab(). Asserted
        against that source in check_base_stub() so it cannot drift from the real base.
        """

        def __init__(self, tokenizer, tools=None):
            self.prev_tool_call_arr: list[dict] = []
            self.current_tool_id: int = -1
            self.current_tool_name_sent: bool = False
            self.streamed_args_for_tool: list[str] = []
            self.model_tokenizer = tokenizer
            self.tools = tools

        @property
        def vocab(self):
            return self.model_tokenizer.get_vocab()

        def adjust_request(self, request):
            return request

    for p in ("vllm", "vllm.entrypoints", "vllm.entrypoints.openai",
              "vllm.entrypoints.openai.chat_completion", "vllm.entrypoints.openai.engine",
              "vllm.entrypoints.openai.responses", "vllm.tool_parsers"):
        if p not in sys.modules:
            mod(p)
    mod("vllm.logger", init_logger=lambda name: logging.getLogger(name))
    mod("vllm.tokenizers", TokenizerLike=object)
    mod("vllm.entrypoints.chat_utils", make_tool_call_id=lambda: "call_stub_id")
    mod("vllm.entrypoints.openai.chat_completion.protocol",
        ChatCompletionRequest=ChatCompletionRequest)
    mod("vllm.entrypoints.openai.engine.protocol",
        DeltaFunctionCall=DeltaFunctionCall, DeltaMessage=DeltaMessage,
        DeltaToolCall=DeltaToolCall, ExtractedToolCallInformation=ExtractedToolCallInformation,
        FunctionCall=FunctionCall, ToolCall=ToolCall)
    mod("vllm.entrypoints.openai.responses.protocol", ResponsesRequest=ResponsesRequest)
    mod("vllm.tool_parsers.abstract_tool_parser", Tool=object, ToolParser=ToolParser)
    # the real find_common_prefix, lifted from the real utils.py
    mod("vllm.tool_parsers.utils",
        find_common_prefix=extract_function(UTILS_FILE, "find_common_prefix"))


def check_base_stub() -> list[str]:
    """Confirm the ToolParser stub matches the real base's observable surface."""
    src = BASE_FILE.read_text(encoding="utf-8")
    notes = []
    for needle in ("self.prev_tool_call_arr: list[dict] = []",
                   "self.current_tool_id: int = -1",
                   "self.current_tool_name_sent: bool = False",
                   "self.streamed_args_for_tool: list[str] = []",
                   "self.model_tokenizer = tokenizer",
                   "return self.model_tokenizer.get_vocab()"):
        if needle not in src:
            notes.append(f"base stub may be stale: {needle!r} not found in the real source")
    return notes


class FakeTokenizer:
    """Only `get_vocab` is used, and only to look up the two special-token ids."""

    def get_vocab(self):
        return {START: 51, END: 53, STRING_DELIM: 52}


# ---------------------------------------------------------------- renderings
def render(tool: str, args: dict, style: str) -> str:
    """Render a call in the native format, or in a deliberately wrong variant.

    delim   : the documented format, key:<|"|>value<|"|>
    backtick: values wrapped in backticks instead of the string-delimiter token
    bare    : values with no delimiter at all
    """
    parts = []
    for k, v in args.items():
        if style == "delim":
            parts.append(f"{k}:{STRING_DELIM}{v}{STRING_DELIM}")
        elif style == "backtick":
            parts.append(f"{k}:`{v}`")
        elif style == "bare":
            parts.append(f"{k}:{v}")
        else:
            raise ValueError(style)
    return f"{START}call:{tool}{{" + ",".join(parts) + f"}}{END}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stubs", action="store_true")
    args = ap.parse_args()

    if args.stubs:
        print("dependency stubs:")
        for name, why in STUBS:
            print(f"  {name:<52} {why}")
        print("\nNOT stubbed (part of the logic under test): regex, find_common_prefix,")
        print("every module-level function and the non-streaming regex in gemma4_tool_parser.py")
        return 0

    integrity = verify_source()
    print("source integrity")
    for k, v in integrity.items():
        print(f"  {k:<18} {v}")

    install_stubs()
    for note in check_base_stub():
        print("  WARNING:", note)

    ns: dict = {"__name__": "vllm.tool_parsers.gemma4_tool_parser"}
    exec(compile(PARSER_FILE.read_text(encoding="utf-8"), str(PARSER_FILE), "exec"), ns)
    Gemma4ToolParser = ns["Gemma4ToolParser"]
    _parse_gemma4_args = ns["_parse_gemma4_args"]
    print(f"\nloaded real parser: STRING_DELIM={ns['STRING_DELIM']!r} "
          f"START={ns['TOOL_CALL_START']!r} END={ns['TOOL_CALL_END']!r}")
    print(f"non-streaming regex: {ns['Gemma4ToolParser'].__doc__ is not None}")

    parser = Gemma4ToolParser(FakeTokenizer())
    request = sys.modules["vllm.entrypoints.openai.chat_completion.protocol"].ChatCompletionRequest()
    print(f"non-streaming regex pattern: {parser.tool_call_regex.pattern}")

    corpus = json.loads((OUT / "corpus.json").read_text(encoding="utf-8"))
    results = []
    for case in corpus["cases"]:
        for style in ("delim", "backtick", "bare"):
            wire = render(case["tool"], case["args"], style)
            extracted = parser.extract_tool_calls(wire, request)
            row = {"id": case["id"], "style": style, "shape": case["shape"],
                   "wire_len": len(wire), "tools_called": extracted.tools_called}
            if extracted.tool_calls:
                tc = extracted.tool_calls[0]
                parsed = json.loads(tc.function.arguments)
                row["name"] = tc.function.name
                row["keys"] = list(parsed)
                row["args"] = parsed
                row["roundtrip_ok"] = parsed == case["args"]
                row["missing_required"] = [k for k in ("filepath", "old_string", "new_string")
                                           if k in case["args"] and k not in parsed]
                row["spurious_keys"] = [k for k in parsed if k not in case["args"]]
            else:
                row["args"] = None
                row["roundtrip_ok"] = False
                row["content_returned"] = (extracted.content or "")[:80]
            results.append(row)

    # -------- delimiter damage cases, which no corpus rendering covers
    damage = {
        "d01_start_tag_malformed": "<|tool_call>call:edit_file{filepath:<|\"|>a.py<|\"|>}<tool_call|>"
                                   .replace("<|tool_call>", "<|tool_call"),
        "d02_end_tag_malformed": f"{START}call:edit_file{{filepath:{STRING_DELIM}a.py{STRING_DELIM}}}<tool_call>",
        "d03_run2_end_of_run_text": "<|tool_call>call:git grep -n -F -- \"re_ansi\" -- '*.py' | head -30<tool_call|>",
        "d04_no_braces": f"{START}call:edit_file filepath:{STRING_DELIM}a.py{STRING_DELIM}{END}",
        "d05_unterminated_string": f"{START}call:edit_file{{filepath:{STRING_DELIM}a.py}}{END}",
    }
    for name, wire in damage.items():
        extracted = parser.extract_tool_calls(wire, request)
        row = {"id": name, "style": "delimiter-damage", "shape": "malformed delimiters",
               "wire_len": len(wire), "tools_called": extracted.tools_called}
        if extracted.tool_calls:
            tc = extracted.tool_calls[0]
            row["name"] = tc.function.name
            row["args"] = json.loads(tc.function.arguments)
            row["keys"] = list(row["args"])
        else:
            row["args"] = None
            row["content_returned"] = (extracted.content or "")[:100]
        results.append(row)

    (OUT / "results.json").write_text(json.dumps(
        {"integrity": integrity, "parsing_path": "non-streaming extract_tool_calls",
         "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    # -------- summary
    print(f"\n{len(results)} fixture runs -> {OUT / 'results.json'}")
    print(f"\n{'case':<24}{'style':<18}{'called':<8}{'roundtrip':<11}keys")
    for r in results:
        rt = r.get("roundtrip_ok")
        print(f"{r['id']:<24}{r['style']:<18}{str(r['tools_called']):<8}"
              f"{('-' if rt is None else str(rt)):<11}{str(r.get('keys'))[:60]}")

    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))["payloads"][0]["arguments"]
    print("\nrecorded run-2 dictionary, for comparison:")
    print("  keys:", list(recorded))
    hits = [r for r in results if r.get("args") == recorded]
    print(f"  fixture runs reproducing it exactly: {len(hits)}")
    for h in hits:
        print("   ", h["id"], h["style"])
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ------------------------------------------------------------------ streaming
def run_streaming(parser_cls, tokenizer, request, wire: str, chunk: int) -> dict:
    """Feed `wire` through extract_tool_calls_streaming in fixed-size chunks.

    Our evaluation did NOT use this path: swegemma builds RunConfig(max_llm_calls=...) with no
    streaming_mode (agent_runner.py:516), ADK defaults to StreamingMode.NONE (run_config.py:225),
    and base_llm_flow.py:1294 derives `stream` from it. These runs are informational only.
    """
    p = parser_cls(tokenizer)
    prev = ""
    args_accum = ""
    name = None
    for i in range(0, len(wire), chunk):
        cur = wire[: i + chunk]
        delta = cur[len(prev):]
        msg = p.extract_tool_calls_streaming(prev, cur, delta, [], [], [], request)
        if msg is not None and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                fn = tc.function or {}
                if fn.get("name"):
                    name = fn["name"]
                if fn.get("arguments"):
                    args_accum += fn["arguments"]
        prev = cur
    parsed, err = None, None
    try:
        parsed = json.loads(args_accum) if args_accum else None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    return {"chunk": chunk, "name": name, "streamed_json": args_accum[:200],
            "parsed": parsed, "json_error": err}
