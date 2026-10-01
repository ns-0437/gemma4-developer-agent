"""Check candidate R's recovery steps against the ACTUAL tool signatures and the REAL parser.

Two independent sources of truth, neither of them this script's own opinion:

  signatures  read by AST from the installed harness source
              reference/harness_src/src_swegemma/swegemma/tools/{workspace,execution}.py
  parser      the verified vLLM 0.19.1 gemma4 parser, executed unmodified
              (loader and stub inventory in scripts/gemma4_parser_fixtures.py)

What the recovery order claims, and what it does not. It records that the three operations differ in
how many separate text arguments they require, in whether any argument must match existing file bytes,
and in whether the operation overwrites the whole file. Those are facts about the signatures.
**Nothing here claims that fewer required arguments serialise better, or that any step is more likely
to survive transport.** The reason to change operation after a rejection is narrower: re-sending a
rejected payload is known to return the same rejection. Which alternative works is not predicted.

`rejected_tool_calls` and `unparsed_tool_call_texts` stay descriptive diagnostic flags and are never
treated as proof of an encoding root cause.

Run:  python scripts/test_recovery_candidate.py
"""
from __future__ import annotations

import ast
import filecmp
import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "reference" / "harness_src" / "src_swegemma" / "swegemma" / "tools"
CAND_A = ROOT / "experiments" / "ab_v3_vs_short" / "candidate_A"
CAND_R = ROOT / "experiments" / "tool_recovery_v1" / "candidate_R"

spec = importlib.util.spec_from_file_location("g4fix", ROOT / "scripts" / "gemma4_parser_fixtures.py")
g4fix = importlib.util.module_from_spec(spec)
sys.modules["g4fix"] = g4fix
spec.loader.exec_module(g4fix)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  -> {detail}" if detail and not cond else ""))


# ------------------------------------------------------------ real signatures
def tool_signatures() -> dict:
    out = {}
    for f in ("workspace.py", "execution.py"):
        tree = ast.parse((TOOLS / f).read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            a = node.args
            names = [x.arg for x in a.args]
            annots = {x.arg: (ast.unparse(x.annotation) if x.annotation else None) for x in a.args}
            n_def = len(a.defaults)
            required = names[: len(names) - n_def] if n_def else names[:]
            optional = names[len(names) - n_def:] if n_def else []
            required = [n for n in required if n != "ctx"]
            out[node.name] = {
                "required": required,
                "optional": optional,
                "required_text": [n for n in required if annots.get(n) == "str"],
            }
    return out


def new_block() -> str:
    """Only the text candidate R adds to candidate A's system prompt."""
    added = io.open(CAND_R / "prompts" / "system.md", encoding="utf-8").read()
    base = io.open(CAND_A / "prompts" / "system.md", encoding="utf-8").read()
    head = base.split("\n## Rules\n")[0]
    return added.replace(head, "", 1).split("\n## Rules\n")[0]


# ------------------------------------------------------------ recovery examples
SCRIPTED_EDIT = "\n".join([
    "python3 - <<'PY'",
    "from pathlib import Path",
    "p = Path('rich/ansi.py'); s = p.read_text()",
    "old = " + "'''" + "[(@-Z" + "'''",
    "new = " + "'''" + "[0-?@-Z" + "'''",
    "n = s.count(old)",
    "assert n == 1, f'anchor occurs {n} times, expected exactly 1'",
    "p.write_text(s.replace(old, new, 1))",
    "print('written')",
    "PY",
])

VERIFY_EDIT = ("git diff -- rich/ansi.py | head -40; "
               "python3 -m py_compile rich/ansi.py && echo COMPILE_OK")

LADDER = [
    ("step1_edit_file_short_anchor", "edit_file", {
        "filepath": "rich/ansi.py",
        "old_string": "re_ansi = re.compile(",
        "new_string": "re_ansi = re.compile(  # widened",
    }),
    ("step1_uniqueness_precheck", "run_command", {
        "command": "git grep -c -F -- \"re_ansi = re.compile(\" -- rich/ansi.py",
    }),
    ("step2_write_file_whole_file", "write_file", {
        "filepath": "rich/ansi.py",
        "content": "import re\n\nre_ansi = re.compile(\n    r'''\n(?:\\x1b\\](.*?))\n''',\n    re.VERBOSE,\n)\n",
    }),
    ("step2_read_every_line_first", "run_command", {
        "command": "cat -n rich/ansi.py | head -150; wc -l rich/ansi.py",
    }),
    ("step3_scripted_edit_with_assert", "run_command", {"command": SCRIPTED_EDIT}),
    ("step3_diff_and_syntax_check", "run_command", {"command": VERIFY_EDIT}),
]


def main() -> int:
    sigs = tool_signatures()
    print("tool signatures read from the harness source")
    for n in ("edit_file", "write_file", "run_command", "read_file", "submit_patch"):
        s = sigs[n]
        print(f"  {n:<13} required={s['required']}  optional={s['optional']}  "
              f"required_text={len(s['required_text'])}")

    print("\n[R1] signature facts (no reliability or serialization claim is made or tested)")
    counts = {n: len(sigs[n]["required_text"]) for n in ("edit_file", "write_file", "run_command")}
    check("edit_file requires 3 text arguments", counts["edit_file"] == 3, str(counts))
    check("write_file requires 2", counts["write_file"] == 2, str(counts))
    check("run_command requires 1", counts["run_command"] == 1, str(counts))
    check("only edit_file requires a value that must match existing file bytes",
          "old_string" in sigs["edit_file"]["required"]
          and "old_string" not in sigs["write_file"]["required"]
          and sigs["run_command"]["required"] == ["command"])
    check("write_file's own docstring says it takes the FULL file content",
          "Full content of the file" in (TOOLS / "workspace.py").read_text(encoding="utf-8"))
    check("read_file caps what one read returns, so one read need not be the whole file",
          "start_line" in sigs["read_file"]["optional"]
          and "end_line" in sigs["read_file"]["optional"])
    print("  NOTE: signature facts only. Nothing asserts that a step with fewer arguments serialises")
    print("  better or is likelier to survive transport.")

    print("\n[R2] every step uses a tool the compiled candidate actually has")
    agent_yaml = (CAND_R / "agent.yaml").read_text(encoding="utf-8")
    for tool in sorted({t for _l, t, _a in LADDER}):
        check(f"{tool} is declared on the coder agent", tool in agent_yaml, tool)

    print("\n[R3] each example satisfies its tool's required parameters")
    for label, tool, args in LADDER:
        s = sigs[tool]
        missing = [p for p in s["required"] if p not in args]
        unknown = [k for k in args if k not in s["required"] + s["optional"]]
        check(f"{label}: no missing required parameter", missing == [], str(missing))
        check(f"{label}: no unknown parameter", unknown == [], str(unknown))
        check(f"{label}: every supplied value is a str", all(isinstance(v, str) for v in args.values()))

    print("\n[R4] each example survives the real parser and would not be rejected")
    integrity = g4fix.verify_source()
    g4fix.install_stubs()
    ns: dict = {"__name__": "vllm.tool_parsers.gemma4_tool_parser"}
    exec(compile(g4fix.PARSER_FILE.read_text(encoding="utf-8"), str(g4fix.PARSER_FILE), "exec"), ns)
    parser = ns["Gemma4ToolParser"](g4fix.FakeTokenizer())
    req = sys.modules["vllm.entrypoints.openai.chat_completion.protocol"].ChatCompletionRequest()
    print(f"  parser sha256 {integrity['parser_sha256'][:16]}  path: non-streaming extract_tool_calls")
    for label, tool, args in LADDER:
        wire = g4fix.render(tool, args, "delim")
        ex = parser.extract_tool_calls(wire, req)
        got = json.loads(ex.tool_calls[0].function.arguments) if ex.tool_calls else None
        check(f"{label}: parses to the intended arguments", got == args,
              json.dumps({"got": got}, ensure_ascii=False)[:160])
        if got is not None:
            missing = [p for p in sigs[tool]["required"] if p not in got]
            check(f"{label}: ADK would find every mandatory parameter", missing == [], str(missing))
    print("  This covers the well-formed case only. It does not predict what the model will emit.")

    print("\n[R5] the prompt's safety requirements are present and specific")
    block = new_block()
    # The prompt is hard-wrapped, so phrase checks run against a whitespace-normalised copy.
    flat = " ".join(block.split())
    check("write_file is gated on holding the file's complete text",
          "complete text" in flat and "150 lines" in flat and "cat -n" in flat)
    check("the prompt warns that a partial copy destroys the rest",
          "silently deletes the rest" in flat)
    check("uncertainty routes to the scripted edit, not to write_file",
          "skip this step entirely and go to step 3" in flat
          and "not certain you have every unaffected line" in flat)

    # Item 1: the anchor check must count the WHOLE block, and must not count matching lines.
    check("the exact full-block assertion is present",
          "assert old and s.count(old) == 1" in flat)
    check("an empty anchor is rejected by that assertion", "assert old and" in flat)
    check("no first-line uniqueness count remains", "git grep -c -F" not in flat)
    check("no line-count uniqueness instruction remains",
          "a line count is not a count of the whole block" in flat)
    check("the assertion precedes the write",
          flat.index("assert old and s.count(old) == 1") < flat.index("p.write_bytes"))

    # Item 2: rollback must restore the agent's own backup, not HEAD.
    check("a unique /tmp backup is taken before a recovery write", "/tmp/bak." in flat)
    check("rollback restores that backup", "cp /tmp/bak.<name> <path>" in flat)
    check("the git checkout hazard is named",
          "would also throw away every earlier correct" in flat)
    check("git checkout is NOT offered as the recovery undo",
          "restore the file with `git checkout" not in flat)
    check("bytes are read and written, preserving line endings",
          "read_bytes()" in flat and "p.write_bytes(" in flat)
    check("the diff is reviewed in bounded sections, not truncated",
          "sed -n '1,80p'" in flat and "until no output remains" in flat and "head -40" not in flat)
    check("py_compile is applied only to Python files", "case <path> in *.py)" in flat)

    print("\n[R6] candidate R differs from A only in prompts/system.md")
    diffs = []
    for p in sorted(CAND_A.rglob("*")):
        if p.is_file():
            rel = p.relative_to(CAND_A)
            q = CAND_R / rel
            if not q.exists() or not filecmp.cmp(p, q, shallow=False):
                diffs.append(rel.as_posix())
    extra = [p.relative_to(CAND_R).as_posix() for p in CAND_R.rglob("*")
             if p.is_file() and not (CAND_A / p.relative_to(CAND_R)).exists()]
    check("exactly one file differs", diffs == ["prompts/system.md"], str(diffs))
    check("no files added or removed", extra == [], str(extra))
    check("agent.yaml byte-identical",
          (CAND_A / "agent.yaml").read_bytes() == (CAND_R / "agent.yaml").read_bytes())
    check("sampling.yaml byte-identical",
          (CAND_A / "configs" / "sampling.yaml").read_bytes()
          == (CAND_R / "configs" / "sampling.yaml").read_bytes())
    check("analyzer prompt byte-identical",
          (CAND_A / "prompts" / "analyzer.md").read_bytes()
          == (CAND_R / "prompts" / "analyzer.md").read_bytes())

    print("\n[R7] the added block names no delimiter and hard-codes no encoding fix")
    for forbidden in ('<|"|>', "tool_call", "delimiter", "escape", "backtick", "JSON",
                      "serial", "fewer argument"):
        check(f"the new block does not mention {forbidden!r}", forbidden not in block, forbidden)
    check("the new block names all three operations",
          all(t in block for t in ("edit_file", "write_file", "run_command")))
    check("the new block forbids re-sending a rejected payload", "never re-send" in block.lower())

    print("\n[R8] earlier revisions are preserved and distinct")
    revs = {"rev1": ROOT / "experiments" / "tool_recovery_v1" / "candidate_R_rev1",
            "rev2": ROOT / "experiments" / "tool_recovery_v1" / "candidate_R_rev2"}
    seen = {}
    for name, d in revs.items():
        check(f"candidate_R_{name} exists", d.is_dir())
        if d.is_dir():
            seen[name] = (d / "prompts" / "system.md").read_bytes()
            check(f"{name} differed from A only in system.md",
                  all(filecmp.cmp(q, d / q.relative_to(CAND_A), shallow=False)
                      for q in CAND_A.rglob("*")
                      if q.is_file() and q.relative_to(CAND_A).as_posix() != "prompts/system.md"))
    current = (CAND_R / "prompts" / "system.md").read_bytes()
    check("the current revision differs from both preserved ones",
          all(current != v for v in seen.values()), str(list(seen)))
    check("the two preserved revisions differ from each other",
          len(set(seen.values())) == len(seen))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
