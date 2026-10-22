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
            compiler_version = '0.2.12' if fault == 'compiler_version' else '0.2.13'
            cell = cell.replace("verify_runtime_compiler()",
                                f"verify_runtime_compiler(COMPILER_FIXTURE, {compiler_version!r})")
            if fault == 'compiler_module':
                cell = cell.replace('verify_runtime_compiler(COMPILER_FIXTURE',
                                    "EXPECTED_COMPILER_FILES['compiler.py'] = 'changed'\n"
                                    'verify_runtime_compiler(COMPILER_FIXTURE', 1)
            version = "0.2.10" if fault == "swegemma_version" else "0.2.11"
            cell = cell.replace("verify_runtime_swegemma()",
                                f"verify_runtime_swegemma(SWEGEMMA_FIXTURE, {version!r})")
            if fault == "swegemma_module":
                cell = cell.replace(
                    "verify_runtime_swegemma(SWEGEMMA_FIXTURE",
                    "EXPECTED_SWEGEMMA_FILES['config.py'] = 'changed'\n"
                    "verify_runtime_swegemma(SWEGEMMA_FIXTURE", 1)
            if fault in ('swegemma_missing', 'swegemma_extra'):
                mutation = ("EXPECTED_SWEGEMMA_FILES['missing.py'] = 'absent'" if fault == 'swegemma_missing'
                            else "EXPECTED_SWEGEMMA_FILES.pop('config.py')")
                cell = cell.replace('verify_runtime_swegemma(SWEGEMMA_FIXTURE',
                                    mutation + "\nverify_runtime_swegemma(SWEGEMMA_FIXTURE", 1)
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
        assert all(arm['agrees_with_saved'] is True for arm in arms), 'an arm was rejected'
        assert all(arm['cleanup_ok'] is True for arm in arms), 'cleanup not confirmed' 
        assert counts["evaluations"] == 0 and counts["server_created"] == 0, counts
        rec = json.loads((work / "working" / "pilot" / "swegemma_identity.json")
                         .read_text(encoding="utf-8"))
        assert rec["matches"] and rec["version_ok"] and rec["hashes_ok"], rec
        assert rec["missing"] == [] and rec["extra"] == [] and rec["changed"] == []
        print(f"  PASS  control stage reached, 8 arms, swegemma {rec['version']} "
              f"{rec['n_modules']} modules, identity persisted")
        print("  PASS  no evaluation, no server, no evaluator dispatch")

    for fault in ('swegemma_module', 'swegemma_version', 'swegemma_missing',
                  'swegemma_extra', 'compiler_version', 'compiler_module'):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / fault
            compiler = fault.startswith('compiler_')
            expected = 'Runtime compiler drift' if compiler else 'Runtime swegemma drift'
            try:
                run(work, fault)
            except AssertionError as exc:
                assert expected in str(exc), str(exc)
            else:
                raise AssertionError('gate did not refuse: ' + fault)
            counts = H.counts()
            assert counts['server_created'] == 0 and counts['evaluations'] == 0, counts
            pilot = work / 'working' / 'pilot'
            assert not (pilot / 'control_recheck.json').exists(), 'controls ran after refusal'
            identity = 'compiler_identity.json' if compiler else 'swegemma_identity.json'
            rec = json.loads((pilot / identity).read_text(encoding='utf-8'))
            assert rec['matches'] is False
            if compiler:
                assert not (pilot / 'swegemma_identity.json').exists(), 'later gate ran after refusal'
                if fault == 'compiler_version': assert rec['version'] == '0.2.12'
                else: assert rec['version'] == '0.2.13'
            else:
                expected_field = {'swegemma_module':'changed','swegemma_missing':'missing',
                                  'swegemma_extra':'extra'}.get(fault)
                if expected_field:
                    assert rec['version_ok'] is True and rec['hashes_ok'] is False, rec
                    assert rec[expected_field], rec
                    for field in {'missing','extra','changed'} - {expected_field}:
                        assert rec[field] == [], rec
                else:
                    assert rec['version_ok'] is False and rec['hashes_ok'] is True, rec
            print('  PASS:', fault, 'refused before controls; identity evidence persisted')

    print("\nPASS: both runtime identity gates are embedded in the notebook; matching identities "
          "reach the control stage and either kind of swegemma drift refuses before any sandbox "
          "is created, with evidence persisted.")


if __name__ == "__main__":
    main()
