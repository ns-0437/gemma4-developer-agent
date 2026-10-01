"""Compile a submission with the OFFICIAL compiler and print the EFFECTIVE model arguments per agent.

This exists because `thinking_budget: 4096` in sampling.yaml is not self-evidently an enforced
reasoning limit. adk_submission/resolvers/generation.py forwards only `enable_thinking` (and
`reasoning_effort` when a thinking_level is set) into LiteLlm._additional_args.extra_body; the numeric
budget is NOT forwarded anywhere. This script prints what is actually attached to each agent's model so
that claim can be checked rather than assumed.

Usage: .venv\\Scripts\\python.exe scripts/effective_settings.py releases/pilot_A releases/pilot_B
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml
from adk_submission import (
    GenerationConstraints, ModelRegistry, NumericRange, SubmissionLimits,
    compile_submission, validate_directory,
)
from google.adk.models.lite_llm import LiteLlm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_check import GEN, LIMITS, TOOLS  # noqa: E402  (same competition limits + tool stubs)


def walk(agent, depth=0, out=None):
    out = [] if out is None else out
    model = getattr(agent, "model", None)
    rec = {
        "agent": agent.name,
        "class": type(agent).__name__,
        "depth": depth,
        "model": getattr(model, "model", str(model)),
        "additional_args": getattr(model, "_additional_args", None),
    }
    gcc = getattr(agent, "generate_content_config", None)
    rec["generate_content_config"] = gcc.model_dump(exclude_none=True) if gcc is not None else None
    out.append(rec)
    for t in getattr(agent, "tools", []) or []:
        sub = getattr(t, "agent", None)
        if sub is not None:
            walk(sub, depth + 1, out)
    for sa in getattr(agent, "sub_agents", []) or []:
        walk(sa, depth + 1, out)
    return out


def report(path: Path) -> dict:
    validate_directory(path, LIMITS)
    models = ModelRegistry()
    models.register("gemma-4-31b-it-qat-w4a16-ct",
                    LiteLlm(model="openai/gemma-4-31b-it-qat-w4a16-ct",
                            api_base="http://localhost:8000/v1", api_key="EMPTY"))
    agent = compile_submission(submission_dir=path, tool_registry=TOOLS, model_registry=models,
                               limits=LIMITS, generation_constraints=GEN)
    rows = walk(agent)

    raw = (path / "configs" / "sampling.yaml").read_bytes()
    parsed = yaml.safe_load(raw.decode("utf-8"))
    files = sorted((p for p in path.rglob("*") if p.is_file()),
                   key=lambda p: p.relative_to(path).as_posix())
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.relative_to(path).as_posix().encode())
        digest.update(f.read_bytes())
    return {"dir": str(path), "content_sha256": digest.hexdigest(),
            "sampling_yaml_raw": raw.decode("utf-8"), "sampling_yaml_parsed": parsed,
            "agents": rows}


def main() -> int:
    paths = [Path(a) for a in (sys.argv[1:] or ["releases/pilot_A", "releases/pilot_B"])]
    reports = []
    for p in paths:
        r = report(p)
        reports.append(r)
        print("=" * 78)
        print(f"{p}   content_sha256={r['content_sha256']}")
        print("  sampling.yaml parses as real YAML:", isinstance(r["sampling_yaml_parsed"], dict))
        print("  parsed thinking_config:", r["sampling_yaml_parsed"].get("thinking_config"))
        for a in r["agents"]:
            print(f"  [{'  ' * a['depth']}{a['agent']}] model={a['model']}")
            print(f"      generate_content_config={json.dumps(a['generate_content_config'])}")
            print(f"      EFFECTIVE model args   ={json.dumps(a['additional_args'])}")
    if len(reports) == 2:
        a, b = reports
        print("=" * 78)
        print("A vs B effective differences:")
        for ra, rb in zip(a["agents"], b["agents"]):
            if ra["additional_args"] != rb["additional_args"]:
                print(f"  {ra['agent']}: {json.dumps(ra['additional_args'])}"
                      f"  ->  {json.dumps(rb['additional_args'])}")
            other = {k: (ra[k], rb[k]) for k in ("model", "generate_content_config")
                     if ra[k] != rb[k]}
            if other:
                print(f"  {ra['agent']} OTHER DIFFS: {other}")
        print("\nNOTE: `thinking_budget` appears in generate_content_config but is NOT present in the")
        print("effective model args, i.e. it is not forwarded to the inference server. Only")
        print("extra_body.chat_template_kwargs.enable_thinking (and reasoning_effort, unset here) is.")
        print("Treat the numeric budget as UNVERIFIED until observed in an outgoing request.")
    Path("reference/effective_settings.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print("\nsaved reference/effective_settings.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
