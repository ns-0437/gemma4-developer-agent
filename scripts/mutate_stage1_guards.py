"""Mutation-check the Stage-1 reviewer and the Stage-1 notebook composition.

Tests passing is not coverage. Each mutation removes or weakens exactly one guard; the suite must go
red. A mutation that survives means the guard is unprotected, whatever the pass count says.

Run:  python scripts/mutate_stage1_guards.py
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REV = ROOT / 'scripts' / 'review_stage1.py'

Q = '"'


def m(label, old, new, suite='reviewer', path=None):
    return (label, path or REV, old, new, suite)


MUTATIONS = [
    # ---------------------------------------------------------------- gate lines
    m('source-patch requirement dropped from the gate',
      '"valid non-empty source patch": bool(perf.get("valid_source_patch")),', ''),
    m('grading requirement dropped from the gate',
      '"grading exercised": grading["observed"],', ''),
    m('verdict-exit requirement dropped from the gate',
      '"verdict exit code": grading["verdict_exit"],', ''),
    m('missing-submission check dropped',
      '"no missing submission": not rel.get("missing_submission"),', ''),
    m('patch-size tie dropped from the gate',
      '"patch tied to the recorded size": bool(perf.get("size_matches")),', ''),

    # ---------------------------------------------------------------- pin and isolation
    m('notebook hash pin no longer enforced', '    if got != want:', '    if False:'),
    m('report may be written inside the artifact tree',
      '    if out_dir == artifacts or artifacts in out_dir.parents:', '    if False:'),

    # ---------------------------------------------------------------- recovery attribution
    # Mutate the branch that actually routes the operation, not the early return in
    # classify_operation: that one is an equivalent mutant, since recovery() re-tests op["read_only"].
    m('read-only successes routed to the modifying candidates',
      '        if op["read_only"]:\n            out["read_only_after"].append(entry)\n'
      '        elif op["modifying"]:\n            out["candidates"].append(entry)',
      '        if op["modifying"] or op["read_only"]:\n            out["candidates"].append(entry)'),
    m('recovery accepts the SAME tool again',
      '        if rejected_at is None or not tool or tool == rejected_tool:',
      '        if rejected_at is None or not tool:'),
    m('a same-basename match is accepted as exact',
      '    exact = [c for c in rec_info["candidates"] if c.get("target") and c["target"] in src]',
      '    exact = [c for c in rec_info["candidates"] if c.get("target")\n'
      '             and PurePosixPath(c["target"]).name in {PurePosixPath(p).name for p in src}]'),
    m('a write_file acknowledgment restored as change evidence',
      '            info["ack_only"] = bool(reported and isinstance((parsed or {}).get("size"), int))\n'
      '            info["change_evidence"] = None',
      '            info["ack_only"] = bool(reported and isinstance((parsed or {}).get("size"), int))\n'
      '            info["change_evidence"] = "write_file reported the written path and size"'),
    m('operation-level change evidence no longer required',
      '    with_evidence = [c for c in exact if c.get("change_evidence")]',
      '    with_evidence = list(exact)'),
    m('a shell command is credited with an exact target and evidence',
      '        info["shell"] = cmd[:120]\n        return info',
      '        info["shell"] = cmd[:120]\n'
      '        info["target"] = norm(args.get("filepath", "") or "rich/ansi.py")\n'
      '        info["change_evidence"] = "shell ran"\n        return info'),

    # ---------------------------------------------------------------- patch validity
    m('absent patch size treated as a match',
      '    p["size_matches"] = bool(p["size_type_ok"] and size == len(patch))',
      '    p["size_matches"] = bool(size is None or (p["size_type_ok"] and size == len(patch)))'),
    m('non-int patch size accepted',
      '    p["size_type_ok"] = isinstance(size, int) and not isinstance(size, bool)',
      '    p["size_type_ok"] = size is not None'),
    m('a header alone counts as a patch',
      "            errors.append(" + Q + "no '@@' hunk header: a header alone is not a patch" + Q + ")",
      '            pass'),
    m('hunk counts no longer checked against the body',
      '            if (got_old, got_new) != (old_n, new_n):',
      '            if False:'),
    m('syntactic validity ignored when accepting a patch',
      '    p["valid_source_patch"] = bool(shape["non_empty"] and p["syntactically_valid"]\n'
      '                                   and p["size_matches"] and p["changes_source"])',
      '    p["valid_source_patch"] = bool(shape["non_empty"] and p["size_matches"]\n'
      '                                   and p["changes_source"])'),
    m('a REPORT-cell refusal no longer invalidates the instrument',
      '        inst["valid"] = False\n    inst["report_cell_error"] = report_cell_error',
      '    inst["report_cell_error"] = report_cell_error'),

    # ---------------------------------------------------------------- provenance and identity
    m('grading-phase provenance no longer required',
      '    v["checks"]["grading_provenance_observed"] = "grading" in ok_phases', ''),
    m('duplicate control arms no longer refused',
      '        out["errors"].append(f"duplicate control arms: {arms}")', '        pass'),
    m('off-plan runs no longer refused',
      '        out["errors"].append(f"run records outside the frozen plan: {off}")', '        pass'),
    m('manifest run order no longer pinned',
      '            out["errors"].append(f"manifest run_order {got} != frozen {FROZEN_ORDER}")',
      '            pass'),
]

SUITES = {
    'reviewer': [sys.executable, 'scripts/test_review_stage1.py'],
    'stage1': [sys.executable, 'scripts/test_stage1_notebook.py'],
}
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'NB_TARGET': 'stage1'}


def run(suite):
    r = subprocess.run(SUITES[suite], cwd=ROOT, capture_output=True, text=True, env=ENV)
    line = [l for l in r.stdout.splitlines() if 'passed,' in l]
    return r.returncode, (line[-1] if line else '(no summary)')


def main():
    for suite in sorted(SUITES):
        rc, line = run(suite)
        print(f'BASELINE {suite}: rc={rc} {line}')
        if rc != 0:
            raise SystemExit(f'baseline {suite} already failing')

    survivors = []
    for label, path, old, new, suite in MUTATIONS:
        src = io.open(path, encoding='utf-8').read()
        if src.count(old) != 1:
            print(f'SKIP      {label}: anchor not unique ({src.count(old)})')
            survivors.append(label + ' (anchor)')
            continue
        try:
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(old, new))
            rc, line = run(suite)
            verdict = 'CAUGHT' if rc != 0 else 'SURVIVED'
            if rc == 0:
                survivors.append(label)
            print(f'{verdict:9s} {label}  [{suite}] rc={rc} {line}')
        finally:
            io.open(path, 'w', encoding='utf-8', newline='').write(src)

    print()
    if survivors:
        print(f'NOT CAUGHT ({len(survivors)}):')
        for x in survivors:
            print('  -', x)
        return 1
    print(f'every one of {len(MUTATIONS)} mutations was caught')
    for suite in sorted(SUITES):
        rc, line = run(suite)
        print(f'restored {suite}: rc={rc} {line}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
