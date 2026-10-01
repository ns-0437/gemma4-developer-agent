"""Search for a constructed input that the REAL parser turns into the recorded run-2 dictionary.

Reuses the loader in `gemma4_parser_fixtures.py`, so the parser executed here is the same verified
file, unmodified.

WHAT A MATCH WOULD AND WOULD NOT SHOW. The model's raw completion for those 42 steps was never
recorded and is not recoverable. A constructed input that the parser maps onto the recorded
dictionary demonstrates **a possible mechanism**: it shows the recorded dictionary is reachable from
a single, plausible malformation. It is **not** proof that the model emitted that text, and no such
claim is made anywhere in the output.

Run:  python scripts/gemma4_reconstruct_run2.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reference" / "parser_fixtures"

spec = importlib.util.spec_from_file_location("g4fix", ROOT / "scripts" / "gemma4_parser_fixtures.py")
g4fix = importlib.util.module_from_spec(spec)
sys.modules["g4fix"] = g4fix   # dataclasses resolves cls.__module__ through sys.modules
spec.loader.exec_module(g4fix)

DELIM = '<|"|>'
START, END = "<|tool_call>", "<tool_call|>"

# The two regex blocks, written the way the recorded arguments carry them: DOUBLE-escaped relative to
# the file on disk (the file has r\"\"\" and \x1b; these carry r\\"\\"\\" and \\x1b). Whether the model
# or the transport doubled them is not established, so the recorded form is used as-is.
NEW_TEXT = (
    'e_ansi = re.compile(\n    r\\"\\"\\"\n'
    '(?:\\\\x1b\\\\](.*?)\\\\x1b\\\\\\\\)|\n'
    '(?:\\\\x1b([0-?@-Z\\\\\\\\\\\\\\\\-_]|\\\\\\\\[[0-?]*[ -/]*[@-~]))\n'
    '\\"\\"\\",\n    re.VERBOSE,\n)'
)
OLD_TEXT = (
    'e_ansi = re.compile(\n    r\\"\\"\\"\n'
    '(?:\\\\x1b\\\\](.*?)\\\\x1b\\\\\\\\)|\n'
    '(?:\\\\x1b([(@-Z\\\\\\\\\\\\\\\\-_]|\\\\\\\\[[0-?]*[ -/]*[@-~]))\n'
    '\\"\\"\\",\n    re.VERBOSE,\n)'
)


def candidates() -> list[tuple[str, str]]:
    """(label, raw args_str) hypotheses. Each is one self-consistent malformation."""
    new_v, old_v = "r" + NEW_TEXT, "r" + OLD_TEXT
    return [
        # The documented format, for contrast.
        ("H0_correct_both_delimited",
         f"filepath:{DELIM}rich/ansi.py{DELIM},new_string:{DELIM}{new_v}{DELIM},"
         f"old_string:{DELIM}{old_v}{DELIM}"),
        # Opens new_string with the delimiter token, closes it with a backtick, then the next
        # delimiter token appears where old_string's value starts.
        ("H1_open_delim_close_backtick",
         f"filepath:rich/ansi.py,new_string:{DELIM}{new_v}`,old_string:{DELIM}{old_v}"),
        # Same, with filepath also delimited.
        ("H2_filepath_delimited_too",
         f"filepath:{DELIM}rich/ansi.py{DELIM},new_string:{DELIM}{new_v}`,old_string:{DELIM}{old_v}"),
        # Backticks throughout, no delimiter token at all.
        ("H3_backticks_only",
         f"filepath:`rich/ansi.py`,new_string:`{new_v}`,old_string:`{old_v}`"),
        # No delimiters at all.
        ("H4_bare_only",
         f"filepath:rich/ansi.py,new_string:{new_v},old_string:{old_v}"),
        # new_string before old_string, both bare.
        ("H5_bare_new_then_old",
         f"filepath:rich/ansi.py,new_string:{new_v},old_string:{old_v}"),
    ]


def main() -> int:
    integrity = g4fix.verify_source()
    g4fix.install_stubs()
    ns: dict = {"__name__": "vllm.tool_parsers.gemma4_tool_parser"}
    exec(compile(g4fix.PARSER_FILE.read_text(encoding="utf-8"), str(g4fix.PARSER_FILE), "exec"), ns)
    parser = ns["Gemma4ToolParser"](g4fix.FakeTokenizer())
    request = sys.modules["vllm.entrypoints.openai.chat_completion.protocol"].ChatCompletionRequest()

    recorded = json.loads((ROOT / "reference" / "compare_run2_malformed_calls.json")
                          .read_text(encoding="utf-8"))["payloads"][0]["arguments"]

    print(f"parser {integrity['parser_file']} sha256 {integrity['parser_sha256'][:16]}")
    print(f"recorded keys ({len(recorded)}):")
    for k in recorded:
        print("   ", repr(k)[:90])

    rows = []
    for label, args_str in candidates():
        wire = f"{START}call:edit_file{{{args_str}}}{END}"
        ex = parser.extract_tool_calls(wire, request)
        got = json.loads(ex.tool_calls[0].function.arguments) if ex.tool_calls else None
        exact = got == recorded
        same_keys = got is not None and list(got) == list(recorded)
        rows.append({"label": label, "wire_len": len(wire), "tools_called": ex.tools_called,
                     "n_keys": len(got) if got else 0, "keys": list(got) if got else [],
                     "exact_match": exact, "same_key_sequence": same_keys, "args": got})
        print(f"\n{label}")
        print(f"  tools_called={ex.tools_called}  keys={len(got) if got else 0}"
              f"  exact_match={exact}  same_key_sequence={same_keys}")
        if got:
            for k, v in got.items():
                print(f"    {repr(k)[:70]:<72} -> {repr(v)[:60]}")
            if not exact:
                for k in recorded:
                    if k not in got:
                        print(f"    MISSING recorded key: {repr(k)[:70]}")
                for k in got:
                    if k not in recorded:
                        print(f"    EXTRA key not recorded: {repr(k)[:70]}")

    hits = [r for r in rows if r["exact_match"]]
    print(f"\nexact reproductions of the recorded dictionary: {len(hits)}")
    for h in hits:
        print("  ", h["label"])

    (OUT / "reconstruction.json").write_text(json.dumps({
        "integrity": integrity,
        "parsing_path": "non-streaming extract_tool_calls",
        "recorded_keys": list(recorded),
        "claim": ("A constructed input that reproduces the recorded dictionary demonstrates a "
                  "POSSIBLE MECHANISM. The model's raw completion was never recorded and is not "
                  "recoverable, so this is not evidence of what the model emitted."),
        "candidates": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT / 'reconstruction.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
