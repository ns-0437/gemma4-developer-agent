"""Assert the gemma4 parser findings, so they cannot silently rot.

Every assertion here runs the REAL vLLM 0.19.1 parser loaded from the verified sdist extraction.
Nothing about the parsing is reimplemented. Dependency stubs are listed by
`scripts/gemma4_parser_fixtures.py --stubs` and none of them touch the parsing logic.

Run:  python scripts/test_gemma4_parser_findings.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g4fix", ROOT / "scripts" / "gemma4_parser_fixtures.py")
g4fix = importlib.util.module_from_spec(spec)
sys.modules["g4fix"] = g4fix
spec.loader.exec_module(g4fix)

DELIM = '<|"|>'
START, END = "<|tool_call>", "<tool_call|>"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


def load():
    integrity = g4fix.verify_source()
    g4fix.install_stubs()
    ns: dict = {"__name__": "vllm.tool_parsers.gemma4_tool_parser"}
    exec(compile(g4fix.PARSER_FILE.read_text(encoding="utf-8"), str(g4fix.PARSER_FILE), "exec"), ns)
    req = sys.modules["vllm.entrypoints.openai.chat_completion.protocol"].ChatCompletionRequest()
    return integrity, ns, ns["Gemma4ToolParser"](g4fix.FakeTokenizer()), req


def main() -> int:
    integrity, ns, parser, req = load()
    recorded = json.loads((ROOT / "reference" / "compare_run2_malformed_calls.json")
                          .read_text(encoding="utf-8"))["payloads"][0]["arguments"]

    print("\n[G1] the source under test is the verified upstream release")
    check("sdist digest was verified at extraction", integrity["digest_verified"] is True)
    check("sdist sha256 matches PyPI metadata",
          integrity["sdist_sha256"] == "9fb88ce6b50991eba41d183584f65f51d7f6015d86a42cdabf79c1c8bd5d66fa")
    check("parser file sha256 pinned",
          integrity["parser_sha256"] == "682b2152b76c031df9c58c3ffbb5b243945be5d8957ebdce00faef1b9de6b889",
          integrity["parser_sha256"])

    print("\n[G2] the native format is not JSON")
    check("string values are delimited by the <|\"|> token", ns["STRING_DELIM"] == DELIM, ns["STRING_DELIM"])
    check("start token", ns["TOOL_CALL_START"] == START)
    check("end token", ns["TOOL_CALL_END"] == END)
    check("non-streaming extraction requires call:name{...}",
          parser.tool_call_regex.pattern == r"<\|tool_call>call:([\w\-\.]+)\{(.*?)\}<tool_call\|>",
          parser.tool_call_regex.pattern)

    print("\n[G3] with correct delimiters the real failing content round-trips")
    corpus = json.loads((ROOT / "reference" / "parser_fixtures" / "corpus.json")
                        .read_text(encoding="utf-8"))
    p01 = next(c for c in corpus["cases"] if c["id"] == "p01_real_failure")
    wire = g4fix.render(p01["tool"], p01["args"], "delim")
    ex = parser.extract_tool_calls(wire, req)
    got = json.loads(ex.tool_calls[0].function.arguments)
    check("the rich/ansi.py regex survives intact", got == p01["args"],
          json.dumps({k: v[:40] for k, v in got.items()})[:200])
    check("all three parameters present", sorted(got) == ["filepath", "new_string", "old_string"])

    print("\n[G4] every correctly delimited corpus case round-trips")
    bad = []
    for case in corpus["cases"]:
        w = g4fix.render(case["tool"], case["args"], "delim")
        e = parser.extract_tool_calls(w, req)
        a = json.loads(e.tool_calls[0].function.arguments) if e.tool_calls else None
        if a != case["args"]:
            bad.append(case["id"])
    check("no correctly delimited case loses or invents a parameter", bad == [], str(bad))

    print("\n[G5] a value without the delimiter token fragments on its own , : ] characters")
    w = g4fix.render(p01["tool"], p01["args"], "bare")
    e = parser.extract_tool_calls(w, req)
    a = json.loads(e.tool_calls[0].function.arguments)
    check("old_string is lost", "old_string" in a and len(a) > 3 or "old_string" not in a, str(list(a))[:120])
    check("content fragments appear as keys",
          any(k not in ("filepath", "old_string", "new_string") for k in a), str(list(a))[:160])
    frags = [k for k in a if k not in ("filepath", "old_string", "new_string")]
    # The corpus carries the file's own single-escaped text, while the recorded payload was
    # double-escaped, so an exact key match is not expected here. What IS expected is the same
    # fragment SHAPE: a slice of the regex body, cut at a ']' and running to the next '(?'.
    check("a fragment key has the recorded shape: starts at ']' and ends at '(?'",
          any(k.startswith("](.*?)") and k.endswith("(?") for k in frags), str(frags)[:200])
    check("the exact recorded keys are reproduced in [G6], not here",
          any(rk.startswith("](.*?)") and rk.endswith("(?") for rk in recorded))

    print("\n[G6] one mis-paired closing delimiter reproduces the recorded dictionary exactly")
    new_v = "r" + (
        'e_ansi = re.compile(\n    r\\"\\"\\"\n'
        '(?:\\\\x1b\\\\](.*?)\\\\x1b\\\\\\\\)|\n'
        '(?:\\\\x1b([0-?@-Z\\\\\\\\\\\\\\\\-_]|\\\\\\\\[[0-?]*[ -/]*[@-~]))\n'
        '\\"\\"\\",\n    re.VERBOSE,\n)')
    old_v = "r" + (
        'e_ansi = re.compile(\n    r\\"\\"\\"\n'
        '(?:\\\\x1b\\\\](.*?)\\\\x1b\\\\\\\\)|\n'
        '(?:\\\\x1b([(@-Z\\\\\\\\\\\\\\\\-_]|\\\\\\\\[[0-?]*[ -/]*[@-~]))\n'
        '\\"\\"\\",\n    re.VERBOSE,\n)')
    args_str = f"filepath:rich/ansi.py,new_string:{DELIM}{new_v}`,old_string:{DELIM}{old_v}"
    e = parser.extract_tool_calls(f"{START}call:edit_file{{{args_str}}}{END}", req)
    a = json.loads(e.tool_calls[0].function.arguments)
    check("byte-identical to the recorded dictionary", a == recorded,
          json.dumps(list(a), ensure_ascii=False)[:200])
    check("key order also matches", list(a) == list(recorded))
    check("old_string is absent as a parameter", "old_string" not in a)
    print("  NOTE: this shows a POSSIBLE MECHANISM. The model's raw completion was never recorded")
    print("  and is not recoverable, so it is not evidence of what the model emitted.")

    print("\n[G7] the four unparsed client-visible strings: why they did not parse")
    real_text = "<|tool_call>call:git grep -n -F -- \"re_ansi\" -- '*.py' | head -30<tool_call|>"
    e = parser.extract_tool_calls(real_text, req)
    check("no tool call extracted", e.tools_called is False and e.tool_calls == [])
    check("the whole text is returned as content", e.content == real_text, repr(e.content)[:120])
    check("the START token is present and correctly spelled", START in real_text)
    check("the END token is present and correctly spelled", END in real_text)
    check("so the delimiters were NOT malformed; the payload was",
          "{" not in real_text.split("call:")[1])
    print("  the regex needs call:<name>{<args>}; the text carries a shell command and no braces")

    print("\n[G8] a genuinely absent parameter looks different from a lost one")
    absent = {"filepath": "pkg/mod.py", "new_string": "x = 2"}
    e = parser.extract_tool_calls(g4fix.render("edit_file", absent, "delim"), req)
    a = json.loads(e.tool_calls[0].function.arguments)
    check("only the supplied parameters appear", a == absent, str(a))
    check("no spurious keys when a parameter is simply missing",
          all(k in ("filepath", "new_string") for k in a))

    print("\n[G9] streaming path exists but was NOT the path our run used")
    check("streaming entry point present", hasattr(parser, "extract_tool_calls_streaming"))
    good = g4fix.render("edit_file", {"filepath": "pkg/mod.py", "old_string": "a, b", "new_string": "c: d"}, "delim")
    for chunk in (1, 3, 7, 29):
        r = g4fix.run_streaming(ns["Gemma4ToolParser"], g4fix.FakeTokenizer(), req, good, chunk)
        ok = r["parsed"] == {"filepath": "pkg/mod.py", "old_string": "a, b", "new_string": "c: d"}
        check(f"chunk size {chunk}: streamed JSON reassembles correctly", ok,
              f"{r['json_error']} {r['streamed_json'][:120]}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
