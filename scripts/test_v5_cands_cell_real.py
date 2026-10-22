"""REAL-PACKAGE execution of the generated candidate-validation cell. No simulation.

Executes the generated cell with explicit identity-gate paths and versions against the real
adk-submission 0.2.13 and swegemma 0.2.11 sources. swegemma.models.discovery is deliberately
NOT stubbed and its removed helper is NOT injected, so an obsolete import is a hard failure here.

This is distinct from scripts/test_v5_control_replay_notebook.py, which exercises the gates with
simulated harness dependencies. Automatic runtime package/version discovery is not tested here.

    python scripts/test_v5_cands_cell_real.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks/v5_control_replay/v5_control_replay.ipynb"
COMPILER_SRC = ROOT / "experiments/v5_budget_v2/compiler_0_2_13/src"
SWEGEMMA_SRC = ROOT / "experiments/v5_budget_v2/swegemma_0_2_11/src"
EVALCORE_SRC = ROOT / "reference/harness_src/src_adk_eval_core"
CAND = ROOT / "experiments/v5_budget_v1/candidate_V5"
CAND_SHA = "527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33"


def cands_cell() -> str:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"]]
    hits = [s for s in cells if "declared_model(d)" in s]
    assert len(hits) == 1, f"expected one candidate-validation cell, found {len(hits)}"
    return hits[0]


def run_cell(cell: str, results: Path) -> dict:
    """Execute the complete cell with real packages. Only the host-specific bits are bound."""
    # Extracted sources must PRECEDE site-packages, which still holds older versions.
    wanted = [str(COMPILER_SRC), str(SWEGEMMA_SRC), str(EVALCORE_SRC),
              str(ROOT / ".venv/Lib/site-packages")]
    for q in reversed(wanted):
        while q in sys.path:
            sys.path.remove(q)
        sys.path.insert(0, q)
    import adk_submission
    assert Path(adk_submission.__file__).resolve().is_relative_to(COMPILER_SRC.resolve())
    import swegemma
    assert Path(swegemma.__file__).resolve().is_relative_to(SWEGEMMA_SRC.resolve())
    # the removed module must genuinely be absent; nothing is stubbed
    try:
        __import__("swegemma.models.discovery")
        raise AssertionError("swegemma.models.discovery is importable; the test is not honest")
    except ModuleNotFoundError:
        pass

    work = results.parent
    ns: dict = {"RESULTS": results, "Path": Path, "WORKING_DIR": work,
                "DATA_DIR": work / "input",
                "CAND_DIRS": {"V5": CAND},
                "BUNDLES": {"V5": {"sha256": CAND_SHA}},
                "COMPILER_FIXTURE": COMPILER_SRC / "adk_submission",
                "SWEGEMMA_FIXTURE": SWEGEMMA_SRC / "swegemma"}
    # Bind the two gates to the extracted sources; the gate bodies are untouched.
    cell = cell.replace("verify_runtime_compiler()",
                        "verify_runtime_compiler(COMPILER_FIXTURE, '0.2.13')")
    cell = cell.replace("verify_runtime_swegemma()",
                        "verify_runtime_swegemma(SWEGEMMA_FIXTURE, '0.2.11')")
    # The cell unpacks embedded zips; point it at the already-unpacked candidate instead.
    exec(compile(cell, "<generated cands cell>", "exec"), ns)
    return ns


def main() -> None:
    cell = cands_cell()
    assert "validate_single_declared_model" not in cell, "obsolete symbol still in generated cell"
    print("1. complete generated cell, real packages, nothing stubbed")
    with tempfile.TemporaryDirectory() as tmp:
        res = Path(tmp) / "pilot"
        res.mkdir()
        ns = run_cell(cell, res)
        comp = json.loads((res / "compiler_identity.json").read_text(encoding="utf-8"))
        sg = json.loads((res / "swegemma_identity.json").read_text(encoding="utf-8"))
        assert comp["matches"] and comp["version"] == "0.2.13", comp
        assert sg["matches"] and sg["version"] == "0.2.11", sg
        assert ns["declared_model"](CAND) == "gemma-4-31b-it-qat-w4a16-ct"
        print(f"  PASS  cell executed; compiler {comp['version']} ok, swegemma {sg['version']} ok "
              f"({sg['n_modules']} modules), declared model resolved")

    print("2. regression: restoring the obsolete import must fail this test")
    broken = cell.replace("import base64, hashlib, io, shutil, zipfile",
                          "import base64, hashlib, io, shutil, zipfile\n"
                          "from swegemma.models.discovery import validate_single_declared_model", 1)
    assert "validate_single_declared_model" in broken, "regression fixture did not inject"
    with tempfile.TemporaryDirectory() as tmp:
        res = Path(tmp) / "pilot"
        res.mkdir()
        try:
            run_cell(broken, res)
        except ModuleNotFoundError as exc:
            assert "swegemma.models.discovery" in str(exc), exc
            print(f"  PASS  obsolete import reintroduced -> {type(exc).__name__}: {exc}")
        else:
            raise AssertionError("the obsolete import did NOT fail; the fixture still masks it")

    print("\nPASS: the generated cell runs against real swegemma 0.2.11 and adk-submission 0.2.13, "
          "and reintroducing the removed import fails this test.")


if __name__ == "__main__":
    main()
