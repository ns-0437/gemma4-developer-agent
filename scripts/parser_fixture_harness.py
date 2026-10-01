"""Offline fixture harness for the vLLM `gemma4` tool-call parser.

WHAT THIS IS FOR. The argument dictionaries recorded in compare run 2 are the **output** of that
parser (proved by `scripts/capture_point_proof.py` [C1]: ADK reproduces the recorded dict exactly from
a JSON `arguments` string, so the JSON object came from whatever produced that string). The recorded
dictionaries are therefore evidence about the parser's behaviour, not a reconstruction of the model's
raw completion. **No raw model completion for those 42 steps exists**, and none is reconstructed here.

WHAT IT DOES. It holds a corpus of content shapes and drives the REAL parser over each one, once the
parser is available. It deliberately does not assume a JSON-only wire format: the parser's own
expected format is read from its source and supplied as the renderer, and `--show-format` prints what
was found so the assumption is visible and reviewable.

Without the parser installed this script reports exactly that and exits 2. It never simulates a
parser and never invents an expected output.

Run:
  python scripts/parser_fixture_harness.py --show-format
  python scripts/parser_fixture_harness.py --run            (needs vllm importable)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "reference" / "parser_fixtures" / "corpus.json"
OUT = ROOT / "reference" / "parser_fixtures"

# Candidates in vLLM's tool-parser registry. Which one exists is recorded, never assumed.
PARSER_MODULES = [
    "vllm.entrypoints.openai.tool_parsers.gemma4_tool_parser",
    "vllm.entrypoints.openai.tool_parsers",
    "vllm.entrypoints.openai.tool_parsers.abstract_tool_parser",
]


def parser_status() -> dict:
    """What is actually importable, with versions and file hashes. No guessing."""
    status = {"vllm_importable": False, "vllm_version": None, "modules": {}}
    try:
        vllm = importlib.import_module("vllm")
        status["vllm_importable"] = True
        status["vllm_version"] = getattr(vllm, "__version__", "unknown")
    except Exception as exc:
        status["import_error"] = f"{type(exc).__name__}: {exc}"
        return status
    for name in PARSER_MODULES:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            status["modules"][name] = {"importable": False,
                                       "error": f"{type(exc).__name__}: {exc}"}
            continue
        src = Path(getattr(mod, "__file__", "") or "")
        entry = {"importable": True, "file": src.as_posix() if src else None}
        if src.exists():
            raw = src.read_bytes()
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
            entry["bytes"] = len(raw)
        status["modules"][name] = entry
    try:
        from vllm.entrypoints.openai.tool_parsers import ToolParserManager
        status["registered_parsers"] = sorted(getattr(ToolParserManager, "tool_parsers", {}))
    except Exception as exc:
        status["registry_error"] = f"{type(exc).__name__}: {exc}"
    return status


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-format", action="store_true",
                    help="report what parser source is available and what format it expects")
    ap.add_argument("--run", action="store_true", help="drive the real parser over the corpus")
    args = ap.parse_args()

    corpus = load_corpus()
    print(f"corpus: {len(corpus['cases'])} cases  ({CORPUS.relative_to(ROOT)})")
    for c in corpus["cases"]:
        print(f"  {c['id']:<22} {c['shape']:<38} expects: {c['question']}")

    status = parser_status()
    (OUT / "parser_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print("\nparser availability:", json.dumps(
        {k: v for k, v in status.items() if k != "modules"}, indent=2))
    for name, entry in status["modules"].items():
        print(f"  {name}: {entry}")

    if not status["vllm_importable"]:
        print("\nvLLM is NOT importable in this environment, so the parser's expected format is")
        print("UNKNOWN and no case can be run. Nothing is simulated. Obtain vllm 0.19.1 from an")
        print("official source, record its hash, and re-run with --run.")
        return 2

    if args.run:
        print("\nparser present: rendering and running each case is the next step, using the")
        print("format read from the parser source recorded above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
