"""Offline capture of what thinking-off vs thinking-on actually sends to the LiteLLM client.

Compiles candidates derived from frozen S with the OFFICIAL compiler and captures the
kwargs ADK hands to the LiteLLM client. Never performs HTTP and never calls a model, so
it shows transport only and says nothing about whether the host server enforces anything.

Run once per compiler so each version is imported cleanly in its own process:

    python scripts/check_thinking_transport.py 0.2.11 <out.json>
    python scripts/check_thinking_transport.py 0.2.12 <out.json>

0.2.11 is the version installed in .venv; 0.2.12 is the host wheel extracted under
experiments/shellread_v1/compiler_0_2_12/src.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.metadata as md
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILER_0_2_12 = ROOT / "experiments/shellread_v1/compiler_0_2_12/src"
FROZEN_S = ROOT / "experiments/concise_workflow_v1/candidate_S"

# Only the thinking block differs. Everything else is frozen S's sampling verbatim.
VARIANTS = {
    "thinking_off": {"thinking_budget": 4096, "include_thoughts": False},
    "thinking_on": {"thinking_budget": 4096, "include_thoughts": True},
}


def _bootstrap(version: str) -> None:
    if version == "0.2.12":
        sys.path.insert(0, str(COMPILER_0_2_12))
    sys.path.insert(1 if version == "0.2.12" else 0, str(ROOT / ".venv/Lib/site-packages"))
    sys.path.insert(0, str(ROOT / "scripts"))


def _check_compiler(version: str) -> str:
    import adk_submission

    where = Path(adk_submission.__file__).resolve()
    under_extracted = where.is_relative_to(COMPILER_0_2_12.resolve())
    if version == "0.2.12":
        assert under_extracted, f"expected the extracted 0.2.12 source, imported {where}"
    else:
        assert not under_extracted, f"expected the installed compiler, imported {where}"
    return str(where)


def _make_variant(dst: Path, thinking: dict) -> None:
    shutil.copytree(FROZEN_S, dst)
    sampling = dst / "configs/sampling.yaml"
    kept = [
        line
        for line in sampling.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(("thinking_config:", "  "))
    ]
    body = "\n".join(kept) + "\nthinking_config:\n"
    for key, value in thinking.items():
        body += f"  {key}: {json.dumps(value)}\n"
    sampling.write_text(body, encoding="utf-8")


class _Captured(Exception):
    pass


def _capture(agent) -> dict:
    from google.adk.models.lite_llm import LiteLLMClient
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types

    seen: list[dict] = []

    class CaptureClient(LiteLLMClient):
        async def acompletion(self, **kwargs):
            seen.append(kwargs)
            raise _Captured()

    agent.model.llm_client = CaptureClient()
    request = LlmRequest(
        model=agent.model.model,
        contents=[types.Content(role="user", parts=[types.Part(text="Offline probe")])],
        config=agent.generate_content_config,
    )

    async def drive():
        try:
            async for _ in agent.model.generate_content_async(request, stream=False):
                raise AssertionError("the capturing client must stop before any response")
        except _Captured:
            return
        raise AssertionError("transport capture was never reached")

    asyncio.run(drive())
    sent = seen[-1]
    return {
        "compiled": agent.generate_content_config.model_dump(exclude_none=True),
        "client_parameters": {
            k: v for k, v in sent.items() if k not in ("messages", "tools", "api_key")
        },
        "instruction_sha256": hashlib.sha256(agent.instruction.encode()).hexdigest(),
    }


def main() -> None:
    version, out_path = sys.argv[1], Path(sys.argv[2])
    _bootstrap(version)
    compiler_file = _check_compiler(version)

    import official_check as O
    from google.adk.models.lite_llm import LiteLlm

    report = {
        "compiler_requested": version,
        "compiler_file": compiler_file,
        "compiler_version_metadata": md.version("adk-submission"),
        "versions": {k: md.version(k) for k in ("google-adk", "litellm")},
        "frozen_source": str(FROZEN_S.relative_to(ROOT)),
        "boundary": (
            "ADK kwargs at the LiteLLM client boundary. No HTTP, no server, no model. "
            "Forwarding does not establish that the host server recognises or enforces any field."
        ),
        "variants": {},
    }

    with tempfile.TemporaryDirectory() as tmp:
        for name, thinking in VARIANTS.items():
            src = Path(tmp) / name
            _make_variant(src, thinking)
            O.validate_directory(src, O.LIMITS)
            registry = O.ModelRegistry()
            registry.register(
                "gemma-4-31b-it-qat-w4a16-ct",
                LiteLlm(
                    model="openai/gemma-4-31b-it-qat-w4a16-ct",
                    api_base="http://127.0.0.1:9/v1",
                    api_key="EMPTY",
                ),
            )
            agent = O.compile_submission(
                submission_dir=src,
                tool_registry=O.TOOLS,
                model_registry=registry,
                limits=O.LIMITS,
                generation_constraints=O.GEN,
            )
            agents = [agent] + [
                t.agent for t in agent.tools if getattr(t, "agent", None) is not None
            ]
            assert len(agents) == 2, f"expected coder + analyzer, got {len(agents)}"
            report["variants"][name] = {
                "sampling_yaml": (src / "configs/sampling.yaml").read_text(encoding="utf-8"),
                "agents": {a.name: _capture(a) for a in agents},
            }
            print(f"compiled and captured: {name}")

    # What actually differs between the two variants, per agent.
    diff = {}
    for agent_name in report["variants"]["thinking_off"]["agents"]:
        off = report["variants"]["thinking_off"]["agents"][agent_name]
        on = report["variants"]["thinking_on"]["agents"][agent_name]
        assert off["instruction_sha256"] == on["instruction_sha256"], agent_name
        changed = {}
        for field in ("compiled", "client_parameters"):
            a, b = off[field], on[field]
            keys = sorted(set(a) | set(b))
            changed[field] = {
                k: {"thinking_off": a.get(k, "<absent>"), "thinking_on": b.get(k, "<absent>")}
                for k in keys
                if a.get(k, "<absent>") != b.get(k, "<absent>")
            }
        diff[agent_name] = changed
    report["difference_off_to_on"] = diff

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")
    for agent_name, changed in diff.items():
        print(f"  {agent_name}: client_parameters delta = {changed['client_parameters']}")


if __name__ == "__main__":
    main()
