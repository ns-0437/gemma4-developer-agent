"""Generated-cell tests for the CPU control replay's runtime identity gates.

Proves:
  1. matching compiler and swegemma identities reach the control stage;
  2. a changed swegemma module, and a wrong swegemma version, each refuse BEFORE any sandbox is
     created, with the observed identity and mismatch details persisted.

Offline. No model, server, evaluator dispatch or GPU.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ["NB_TARGET"] = "v5_control_replay"
import test_pilot_notebook as H  # noqa: E402

COMPILER = ROOT / "experiments/v5_budget_v2/compiler_0_2_13/src/adk_submission"
SWEGEMMA = ROOT / "experiments/v5_budget_v2/swegemma_0_2_11/src/swegemma"


def hook(fault=None):
    """Point both real gates at the extracted sources. The gates themselves are unchanged."""
    def edit(i, cell, ns):
        if "verify_runtime_compiler()" in cell:
            ns["COMPILER_FIXTURE"] = COMPILER
            ns["SWEGEMMA_FIXTURE"] = SWEGEMMA
            cell = cell.replace("verify_runtime_compiler()",
                                "verify_runtime_compiler(COMPILER_FIXTURE, '0.2.13')")
            version = "0.2.10" if fault == "swegemma_version" else "0.2.11"
            cell = cell.replace("verify_runtime_swegemma()",
                                f"verify_runtime_swegemma(SWEGEMMA_FIXTURE, {version!r})")
            if fault == "swegemma_module":
                cell = cell.replace(
                    "verify_runtime_swegemma(SWEGEMMA_FIXTURE",
                    "EXPECTED_SWEGEMMA_FILES['config.py'] = 'changed'\n"
                    "verify_runtime_swegemma(SWEGEMMA_FIXTURE", 1)
        return cell
    return edit


def run(tmp, fault=None):
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        ns = H.run_cells(Path(tmp), dispatch=False, server_healthy=True, hook=hook(fault))
    return ns


def main():
    print("1. matching identities reach the control stage")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "ok"
        ns = run(work, None)
        arms = ns["CONTROL_RECHECK"]
        counts = H.counts()
        assert len(arms) == 8, f"expected eight control arms, got {len(arms)}"
        assert counts["evaluations"] == 0 and counts["server_created"] == 0, counts
        rec = json.loads((work / "working" / "pilot" / "swegemma_identity.json")
                         .read_text(encoding="utf-8"))
        assert rec["matches"] and rec["version_ok"] and rec["hashes_ok"], rec
        assert rec["missing"] == [] and rec["extra"] == [] and rec["changed"] == []
        print(f"  PASS  control stage reached, 8 arms, swegemma {rec['version']} "
              f"{rec['n_modules']} modules, identity persisted")
        print("  PASS  no evaluation, no server, no evaluator dispatch")

    for fault, label in (("swegemma_module", "a changed swegemma module"),
                         ("swegemma_version", "a wrong swegemma version")):
        print(f"2. {label} refuses before sandbox creation")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / fault
            refused = None
            try:
                run(work, fault)
            except AssertionError as exc:
                refused = str(exc)
            assert refused, f"gate did NOT refuse for {label}"
            assert "Runtime swegemma drift" in refused, refused[:160]
            counts = H.counts()
            assert counts["server_created"] == 0 and counts["evaluations"] == 0, counts
            # the control cell must not have run at all, so no recheck file exists
            assert not (work / "working" / "pilot" / "control_recheck.json").exists(), \
                "controls ran despite a refused swegemma identity"
            rec = json.loads((work / "working" / "pilot" / "swegemma_identity.json")
                             .read_text(encoding="utf-8"))
            assert rec["matches"] is False, rec
            if fault == "swegemma_module":
                assert rec["changed"], "changed-module detail not persisted"
                assert rec["version_ok"] is True and rec["hashes_ok"] is False, rec
            else:
                assert rec["version_ok"] is False, rec
            print(f"  PASS  refused, 0 sandboxes, no control_recheck.json, details persisted "
                  f"(version_ok={rec['version_ok']} hashes_ok={rec['hashes_ok']} "
                  f"changed={rec['changed'][:2]})")

    print("\nPASS: both runtime identity gates are embedded in the notebook; matching identities "
          "reach the control stage and either kind of swegemma drift refuses before any sandbox "
          "is created, with evidence persisted.")


if __name__ == "__main__":
    main()
