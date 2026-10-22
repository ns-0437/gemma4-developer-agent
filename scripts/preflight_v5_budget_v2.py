"""CPU-only preflight for the repaired V5 baseline. No model, server or agent evaluation.

Covers, against the CURRENT wheelhouse stack recorded in the failed run (swegemma 0.2.11,
adk-submission 0.2.13):

  1. every import the notebook performs, including the removed-symbol replacement;
  2. candidate validation and official compilation of the exact V5 agent;
  3. effective budget mapping for V5's four values;
  4. all eight control arms from saved evidence, through the real comparison code;
  5. recorded package versions, module paths and dependency identities.

CPU success here does NOT verify GPU inference, vLLM startup or any agent behaviour.

    python scripts/preflight_v5_budget_v2.py
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILER_SRC = ROOT / "experiments/v5_budget_v2/compiler_0_2_13/src"
SWEGEMMA_SRC = ROOT / "experiments/v5_budget_v2/swegemma_0_2_11/src"
# adk-eval-core is 0.1.0 in the failed run, unchanged from our extracted copy.
EVALCORE_SRC = ROOT / "reference/harness_src/src_adk_eval_core"
CAND = ROOT / "experiments/v5_budget_v1/candidate_V5"
CAND_SHA = "527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33"
BUDGET = {"max_time_minutes": 5.0, "max_turns": 60, "max_tool_calls": 100, "timeout_seconds": 60}
OUT = ROOT / "experiments/v5_budget_v2/PREFLIGHT.json"


def declared_model(agent_dir: Path) -> str:
    """Replacement for the removed swegemma.models.discovery.validate_single_declared_model.

    swegemma 0.2.11 no longer ships swegemma/models/discovery.py and exposes no equivalent
    helper, so the single declared model is read from the candidate's own agent.yaml and
    sub-agent configs. Those files are already hash-pinned byte-for-byte by the notebook's
    candidate-drift gate, so this reads verified bytes. It raises on no model or on more than
    one distinct model, which is the contract the removed helper enforced.
    """
    import yaml

    class _Loader(yaml.SafeLoader):
        """SafeLoader that keeps unknown tags (notably !include) as plain scalars."""

    _Loader.add_multi_constructor(
        "", lambda loader, suffix, node: getattr(node, "value", None))

    models: set[str] = set()
    for p in sorted(agent_dir.rglob("*.yaml")) + sorted(agent_dir.rglob("*.yml")):
        doc = yaml.load(p.read_text(encoding="utf-8"), Loader=_Loader) or {}
        if isinstance(doc, dict) and isinstance(doc.get("model"), str):
            name = doc["model"].strip()
            if not name:
                raise AssertionError(f"blank model string declared in {p.name}")
            models.add(name)
    if not models:
        raise AssertionError("no model declared in the candidate configuration")
    if len(models) > 1:
        raise AssertionError(f"ambiguous model declaration: {sorted(models)}")
    return models.pop()


def main() -> None:
    assert len(sys.argv) == 1, "preflight takes no arguments"
    report: dict = {"harness": "public development harness, CPU only",
                    "claim_boundary": "CPU preflight; does NOT verify GPU inference, vLLM "
                                      "startup or agent behaviour"}

    # 1. imports, with the 0.2.13 compiler source ahead of site-packages
    sys.path.insert(0, str(EVALCORE_SRC))
    sys.path.insert(0, str(SWEGEMMA_SRC))
    sys.path.insert(0, str(COMPILER_SRC))
    sys.path.insert(1, str(ROOT / ".venv/Lib/site-packages"))
    sys.path.insert(0, str(ROOT / "scripts"))

    mods = {}
    for name in ("adk_submission", "swegemma", "swegemma.config", "swegemma.models",
                 "google.adk", "litellm", "yaml"):
        m = importlib.import_module(name)
        mods[name] = getattr(m, "__file__", "(namespace)")
    report["module_paths"] = mods

    import adk_submission
    where = Path(adk_submission.__file__).resolve()
    assert where.is_relative_to(COMPILER_SRC.resolve()), f"wrong compiler imported: {where}"

    report["versions"] = {}
    for p in ("adk-submission", "swegemma", "google-adk", "litellm"):
        try:
            report["versions"][p] = md.version(p)
        except Exception as exc:
            report["versions"][p] = f"metadata unavailable: {type(exc).__name__}"
    report["compiler_source_version_declared"] = "0.2.13"
    pinned = json.loads((ROOT / "experiments/v5_budget_v2/compiler_0_2_13_hashes.json")
                        .read_text(encoding="utf-8"))
    root = COMPILER_SRC / "adk_submission"
    found = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob("*.py"))}
    report["compiler_identity_matches_pinned"] = (found == pinned["python_files"])
    report["compiler_wheel_sha256"] = pinned["wheel_sha256"]
    assert report["compiler_identity_matches_pinned"], "0.2.13 source drift against recorded hashes"

    # the removed symbol must still be gone, and the replacement must work
    try:
        importlib.import_module("swegemma.models.discovery")
        report["removed_symbol_present"] = True
    except ModuleNotFoundError:
        report["removed_symbol_present"] = False
    report["declared_model"] = declared_model(CAND)

    # 2. candidate validation and official compilation of exact V5
    import make_compare_notebook as M
    assert M.P.bundle(CAND)[1] == CAND_SHA, "candidate is not the exact V5 agent"
    report["candidate_sha256"] = CAND_SHA

    import official_check as O
    from google.adk.models.lite_llm import LiteLlm
    O.validate_directory(CAND, O.LIMITS)
    registry = O.ModelRegistry()
    registry.register(report["declared_model"],
                      LiteLlm(model="openai/" + report["declared_model"],
                              api_base="http://127.0.0.1:9/v1", api_key="EMPTY"))
    agent = O.compile_submission(submission_dir=CAND, tool_registry=O.TOOLS,
                                 model_registry=registry, limits=O.LIMITS,
                                 generation_constraints=O.GEN)
    report["compiled_agent"] = getattr(agent, "name", "?")
    report["compiled_sub_agents"] = [t.agent.name for t in agent.tools
                                     if getattr(t, "agent", None) is not None]

    # 3. effective budget mapping for V5's four values
    from swegemma.config import EvalConfig
    cfg = EvalConfig(tasks_path="/dev/null", snapshots_dir="/dev/null",
                     results_dir="/dev/null", submission_dir=str(CAND), models={}, **BUDGET)
    eff = {k: getattr(cfg.budget, k.replace("max_", "").replace("_minutes", "_minutes"), None)
           for k in BUDGET}
    report["budget_requested"] = BUDGET
    effective = {
        "time_minutes": cfg.budget.time_minutes,
        "turns": cfg.budget.turns,
        "tool_calls": cfg.budget.tool_calls,
        "command_timeout_seconds": cfg.harness.command_timeout_seconds,
    }
    report["effective_limits"] = effective
    # config.py maps timeout_seconds into harness.command_timeout_seconds (lines 181-183) and
    # tools/execution.py:32 consumes it. All four limits map; there is no mapping difference.
    assert effective["time_minutes"] == BUDGET["max_time_minutes"], effective
    assert effective["turns"] == BUDGET["max_turns"], effective
    assert effective["tool_calls"] == BUDGET["max_tool_calls"], effective
    assert effective["command_timeout_seconds"] == BUDGET["timeout_seconds"], effective
    report["all_four_limits_asserted"] = True

    # 4. all eight control arms through the real comparison code
    import compare_cells as C
    import ast
    tree = ast.parse(C.CONTROL_REVALIDATION)
    want = {"_nodes_from_junit", "compare_control_nodes", "_canon_path", "_canon_re",
            "canonicalize_nodes", "canonicalize_targets", "_workspace_root_from_evidence"}
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
    assign = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, "id", "") in ("WORKSPACE_TOKEN", "_EMPTY_DETAIL")
                      for t in n.targets)]
    import xml.etree.ElementTree as _ET_mod
    ns: dict = {"_ET": _ET_mod}
    exec(compile(ast.fix_missing_locations(ast.Module(body=assign + keep, type_ignores=[])),
                 "<fragment>", "exec"), ns)
    ev = M.EVID
    arms = []
    for task in ("rich_3278", "rich_3535", "rich_3675", "rich_3942"):
        for arm in ("baseline", "reference"):
            d = ev / task / arm
            xml = sorted(d.glob("*.xml"))
            saved = json.loads((d / "arm.json").read_text(encoding="utf-8"))
            nodes, dupes, err = ns["_nodes_from_junit"](
                xml[0].read_text(encoding="utf-8") if xml else "")
            arms.append({"task": task, "arm": arm, "parse_error": err,
                         "duplicates": dupes,
                         "nodes_match_saved": nodes == (saved.get("nodes") or {}),
                         "n_nodes": len(nodes or {}),
                         "skipped": sum(1 for v in (nodes or {}).values() if v == "skipped")})
    report["saved_evidence_consistency"] = arms
    report["saved_evidence_label"] = (
        "SAVED-EVIDENCE CONSISTENCY ONLY: parses the stored JUnit XML and compares it with the "
        "stored node maps. This is NOT a fresh control replay; no sandbox is created and no test "
        "is executed. Fresh replay is the separate CPU notebook.")
    assert len(arms) == 8, "expected eight arms"
    assert all(a["nodes_match_saved"] for a in arms), "saved evidence inconsistent"
    assert not any(a["parse_error"] for a in arms), "parse error in saved evidence"
    assert not any(a["duplicates"] for a in arms), "duplicate node identity in saved evidence"
    report["saved_evidence_ok"] = 8

    # negative test: one changed outcome must be detected, not tolerated
    import copy as _copy
    first = ev / "rich_3278" / "baseline"
    xml_text = sorted(first.glob("*.xml"))[0].read_text(encoding="utf-8")
    saved_nodes = json.loads((first / "arm.json").read_text(encoding="utf-8"))["nodes"]
    flipped = xml_text.replace("<testcase ", "<testcase ", 1)
    i = flipped.find("<testcase ")
    end = flipped.find("/>", i)
    flipped = flipped[:i] + flipped[i:end] + "><failure message=\"injected\"/></testcase>" + flipped[end + 2:]
    bad_nodes, _, bad_err = ns["_nodes_from_junit"](flipped)
    assert bad_err is None, bad_err
    assert bad_nodes != saved_nodes, "a changed outcome was NOT detected"
    report["negative_test_changed_outcome_detected"] = True

    # 4. declared_model edge cases, on throwaway directories
    import tempfile as _tf
    edge = {}
    with _tf.TemporaryDirectory() as td:
        base = Path(td)
        NL = chr(10)
        (base / "none").mkdir()
        (base / "none" / "a.yaml").write_text("name: x" + NL, encoding="utf-8")
        (base / "multi").mkdir()
        (base / "multi" / "a.yaml").write_text("model: m1" + NL, encoding="utf-8")
        (base / "multi" / "b.yaml").write_text("model: m2" + NL, encoding="utf-8")
        (base / "blank").mkdir()
        (base / "blank" / "a.yaml").write_text('model: "   "' + NL, encoding="utf-8")
        for case in ("none", "multi", "blank"):
            try:
                edge[case] = {"result": declared_model(base / case), "raised": False}
            except AssertionError as exc:
                edge[case] = {"raised": True, "message": str(exc)[:80]}
    report["declared_model_edge_cases"] = edge
    assert edge["none"]["raised"] and edge["multi"]["raised"], edge
    assert edge["blank"]["raised"], "a blank model string must not be accepted"
    report["declared_model_scope"] = (
        "Sufficient for THIS frozen candidate's YAML shape. Broader equivalence with the removed "
        "swegemma helper is NOT established: that helper's discovery rules over arbitrary "
        "submissions were not reproduced or tested.")

    # 5. swegemma identity alongside the compiler identity
    sg_pin = json.loads((ROOT / "experiments/v5_budget_v2/swegemma_0_2_11_hashes.json")
                        .read_text(encoding="utf-8"))
    sg_root = SWEGEMMA_SRC / "swegemma"
    sg_found = {q.relative_to(sg_root).as_posix(): hashlib.sha256(q.read_bytes()).hexdigest()
                for q in sorted(sg_root.rglob("*.py"))}
    report["swegemma_identity_matches_pinned"] = (sg_found == sg_pin["python_files"])
    report["swegemma_wheel_sha256"] = sg_pin["wheel_sha256"]
    assert report["swegemma_identity_matches_pinned"], "swegemma 0.2.11 source drift"
    report["private_grader_versions"] = "UNKNOWN; not observed by any check here"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("versions:", json.dumps(report["versions"]))
    print("compiler identity matches recorded 0.2.13 hashes:",
          report["compiler_identity_matches_pinned"])
    print("swegemma.models.discovery present:", report["removed_symbol_present"],
          "| declared model via replacement:", report["declared_model"])
    print("candidate:", report["candidate_sha256"][:16], "| compiled:", report["compiled_agent"],
          "| sub-agents:", report["compiled_sub_agents"])
    print("effective limits asserted:", report["effective_limits"])
    print("saved-evidence consistency (NOT fresh replay): %d of 8, no parse errors, no duplicates"
          % report["saved_evidence_ok"])
    print("negative test, changed outcome detected:",
          report["negative_test_changed_outcome_detected"])
    print("declared_model edge cases all raised:",
          all(v.get("raised") for v in report["declared_model_edge_cases"].values()))
    print("swegemma identity matches recorded 0.2.11 hashes:",
          report["swegemma_identity_matches_pinned"])
    print("private grader versions:", report["private_grader_versions"])
    print("wrote", OUT.relative_to(ROOT))
    print("CPU PREFLIGHT PASS. This does not verify GPU inference or agent behaviour.")


if __name__ == "__main__":
    main()
