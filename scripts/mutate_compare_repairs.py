"""Mutation-test the repairs: break the shipped logic, confirm a test FAILS, restore.

Tests passing is not evidence that a test covers the change. Each mutation below removes or
misplaces exactly one thing the repair added, and the run must go red.
"""
import io, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(r'C:\Documents2\KaggleMLChallenge\The Gemma 4')
CELLS = ROOT / 'scripts' / 'compare_cells.py'
GEN = ROOT / 'scripts' / 'make_pilot_notebook.py'
NB = ROOT / 'notebooks' / 'compare' / 'compare.ipynb'

MUTATIONS = [
    # (label, file, old, new, suite)
    ('classification tier removed entirely', CELLS,
     """    for m in _CANDIDATE_NO_SUBMISSION_MARKERS:
        if m in low:
            return 'candidate', 'agent ended without submitting a patch (no environment cause found)'
""", '', 'dispatch'),
    ('tier moved BEFORE the environment markers', CELLS,
     """    for m in _ENVIRONMENT_MARKERS:
        if m in low:
            return 'environment', m
    # After the specific environment causes, before the generic wrappers: a run that simply never
    # submitted has an identified cause, and that cause is the candidate's.
    for m in _CANDIDATE_NO_SUBMISSION_MARKERS:
        if m in low:
            return 'candidate', 'agent ended without submitting a patch (no environment cause found)'
""",
     """    for m in _CANDIDATE_NO_SUBMISSION_MARKERS:
        if m in low:
            return 'candidate', 'agent ended without submitting a patch (no environment cause found)'
    for m in _ENVIRONMENT_MARKERS:
        if m in low:
            return 'environment', m
""", 'dispatch'),
    ('no_submission attribution removed', GEN,
     """    if "completed execution without calling submit_patch" in err.lower():
        return "no_submission"
""", '', 'dispatch'),
    ('plain-error observations stop being counted', GEN,
     '''    is_error = ("error" in parsed or parsed.get("status") == "error"''',
     '''    is_error = (parsed.get("status") == "error"''', 'metrics'),
    ('scratch /tmp writes counted as source edits again', GEN,
     """        if not p.endswith(".py"):
            continue
        (scratch if _is_scratch_path(p) else src).append(p)""",
     """        if not p.endswith(".py"):
            continue
        src.append(p)""", 'metrics'),
    ('rejected calls credited as acknowledged source edits', GEN,
     """                    if status == "ok":
                        ack_edits += 1
            if fn == "run_command":""",
     """                    ack_edits += 1
            if fn == "run_command":""", 'metrics'),
]

SUITES = {
    'dispatch': [sys.executable, 'scripts/test_compare_dispatch.py'],
    'metrics': [sys.executable, 'scripts/test_trace_metrics.py'],
}


def regenerate():
    r = subprocess.run([sys.executable, 'scripts/make_compare_notebook.py'], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('regeneration failed:\n' + r.stdout + r.stderr)


def run(suite):
    env = dict(os.environ, NB_TARGET='compare', PYTHONIOENCODING='utf-8')
    r = subprocess.run(SUITES[suite], cwd=ROOT, capture_output=True, text=True, env=env)
    tail = [l for l in r.stdout.splitlines() if 'passed,' in l]
    return r.returncode, (tail[-1] if tail else r.stdout.strip().splitlines()[-1:] or '')


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    baseline = {}
    for suite in sorted({m[4] for m in MUTATIONS}):
        if only and suite != only:
            continue
        rc, line = run(suite)
        baseline[suite] = (rc, line)
        print(f'BASELINE {suite}: rc={rc} {line}')
        if rc != 0:
            raise SystemExit(f'baseline {suite} is already failing; fix that first')

    survivors = []
    for label, path, old, new, suite in MUTATIONS:
        if only and suite != only:
            continue
        src = io.open(path, encoding='utf-8').read()
        if src.count(old) != 1:
            print(f'SKIP  {label}: anchor not unique ({src.count(old)})')
            survivors.append(label + ' (anchor)')
            continue
        backup = src
        try:
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(old, new))
            regenerate()
            rc, line = run(suite)
            verdict = 'CAUGHT' if rc != 0 else 'SURVIVED'
            if rc == 0:
                survivors.append(label)
            print(f'{verdict:9s} {label}  [{suite}] rc={rc} {line}')
        finally:
            io.open(path, 'w', encoding='utf-8', newline='').write(backup)
            regenerate()

    print()
    if survivors:
        print('MUTATIONS NOT CAUGHT:', survivors)
        return 1
    print('every mutation was caught by a test')
    for suite, (rc, line) in baseline.items():
        rc2, line2 = run(suite)
        print(f'restored {suite}: rc={rc2} {line2}')
        assert (rc2, line2) == (rc, line), 'restore did not return to baseline'
    return 0


if __name__ == '__main__':
    sys.exit(main())
