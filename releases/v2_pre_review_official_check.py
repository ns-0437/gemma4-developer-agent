"""Release gate: run the OFFICIAL adk-submission validator + compiler on a submission dir.

Uses the host's adk_submission 0.2.11 wheel with google-adk 1.36.1 (the grader's versions), the competition
limits copied from swegemma/config.py::build_submission_limits, stub versions of the 9 harness tools with the
real signatures, and the same model-registry shape swegemma builds. No model is called.

Run with the project venv:  .venv\\Scripts\\python.exe scripts/official_check.py submission
"""
from __future__ import annotations

import sys
from pathlib import Path

from adk_submission import (
    GenerationConstraints,
    ModelRegistry,
    NumericRange,
    SubmissionLimits,
    compile_submission,
    validate_directory,
)
from google.adk.models.lite_llm import LiteLlm

ALLOWED = frozenset({".yaml", ".yml", ".md", ".txt", ".py", ".json", ".safetensors"})
LIMITS = SubmissionLimits(
    max_total_size_bytes=3 * 1024**3,
    max_yaml_size_bytes=50 * 1024 * 1024,
    max_skill_size_bytes=50 * 1024 * 1024,
    max_file_count=10_000,
    max_yaml_files=1_000,
    max_instruction_chars=1_000_000,
    max_total_instruction_chars=10_000_000,
    max_agents=500,
    max_sub_agent_depth=50,
    max_skills=1_000,
    max_loop_iterations=500,
    allowed_file_extensions=ALLOWED,
    adapter_extensions=frozenset({".safetensors"}),
)
GEN = GenerationConstraints(
    allowed_fields=None,
    max_output_tokens=NumericRange(1, 32768),
    thinking_budget=NumericRange(0, 32768),
    defaults={"max_output_tokens": 16384, "thinking_config": {"thinking_budget": 4096}},
)


# Stubs with the same names/signatures as swegemma.context.SwegemmaContext.create_tools().
def run_command(command: str) -> str:
    """Executes a shell command in /bin/bash -c inside /workspace."""
    return ""


def submit_patch() -> str:
    """Stages untracked files and captures git diff HEAD."""
    return ""


def get_status() -> str:
    """Returns live budget consumption and patch status."""
    return ""


def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Reads a file from /workspace."""
    return ""


def edit_file(filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> str:
    """Replaces old_string with new_string in a file."""
    return ""


def write_file(filepath: str, content: str) -> str:
    """Creates or overwrites a file."""
    return ""


def get_code_neighbors(node: str, edge_type: str | None = None, max_neighbors: int = 50) -> str:
    """Finds graph neighbors of a symbol."""
    return ""


def search_similar_code(query: str, k: int = 10) -> str:
    """Finds similar graph nodes."""
    return ""


def get_code_subgraph(nodes: list[str]) -> str:
    """Extracts the induced subgraph."""
    return ""


TOOLS = {f.__name__: f for f in (run_command, submit_patch, get_status, read_file, edit_file, write_file,
                                 get_code_neighbors, search_similar_code, get_code_subgraph)}


def describe(agent, depth: int = 0) -> None:
    pad = "  " * depth
    tools = []
    for t in getattr(agent, "tools", []) or []:
        name = getattr(t, "name", None) or getattr(t, "__name__", None) or type(t).__name__
        sub = getattr(t, "agent", None)
        tools.append(f"agent_tool:{sub.name}" if sub is not None else name)
    model = getattr(agent, "model", None)
    model = getattr(model, "model", model)
    gcc = getattr(agent, "generate_content_config", None)
    instr = getattr(agent, "instruction", "") or ""
    print(f"{pad}- {agent.name} [{type(agent).__name__}] model={model} instr={len(instr)} chars")
    print(f"{pad}  tools={tools}")
    if gcc is not None:
        print(f"{pad}  gen={gcc.model_dump(exclude_none=True)}")
    for t in getattr(agent, "tools", []) or []:
        if getattr(t, "agent", None) is not None:
            describe(t.agent, depth + 1)
    for sa in getattr(agent, "sub_agents", []) or []:
        describe(sa, depth + 1)


def main() -> int:
    sub = Path(sys.argv[1] if len(sys.argv) > 1 else "submission").resolve()
    validate_directory(sub, LIMITS)
    models = ModelRegistry()
    models.register("gemma-4-31b-it-qat-w4a16-ct",
                    LiteLlm(model="openai/gemma-4-31b-it-qat-w4a16-ct", api_base="http://localhost:8000/v1",
                            api_key="EMPTY"))
    agent = compile_submission(submission_dir=sub, tool_registry=TOOLS, model_registry=models,
                               limits=LIMITS, generation_constraints=GEN)
    print(f"OFFICIAL COMPILE OK: {sub.name}")
    describe(agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
