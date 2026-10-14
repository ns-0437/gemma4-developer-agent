"""Run the repository's offline validation suite; stop at the first failure.

Each check runs in a separate Python process so fixture monkeypatches cannot
leak into another check. No Kaggle or model commands are invoked.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CHECKS = (
    ('scripts/test_run_offline_checks.py',),
    ('scripts/test_read_submission_snapshot.py',),
    ('scripts/test_verify_submission_observation.py',),
    ('scripts/test_capture_submission_status.py',),
    ('scripts/test_read_submission_details.py',),
    ('scripts/verify_submission_observation.py', 'reference/submission_v4_error_2026-10-14'),
    ('scripts/verify_submission_observation.py', 'reference/submission_v4_status_2026-10-14'),
    ('scripts/verify_submission_observation.py', 'reference/submission_v4_status_2026-10-12'),
    ('scripts/read_submission_snapshot.py', 'reference/submission_v4_status_2026-10-12/submissions.csv',
     '--reference', '57064155'),
    ('scripts/test_verify_v4_submission.py',),
    ('scripts/verify_v4_submission.py',),
    ('scripts/verify_artifact_manifest.py', 'reference/submission_v4_2026-10-11',
     'reference/submission_v4_review/raw_sha256.json'),
    ('scripts/test_verify_final_validation_packet.py',),
    ('scripts/verify_final_validation_packet.py',),
    ('scripts/test_control_canonicalization.py',),
    ('scripts/test_final_validation_v2_notebook.py',),
    ('scripts/test_verify_artifact_manifest.py',),
    ('scripts/verify_artifact_manifest.py', 'reference/control_replay_run_2026-10-07',
     'reference/control_replay_review/raw_sha256.json'),
)


def run_checks(checks=CHECKS, *, root=ROOT, runner=subprocess.run):
    if not checks:
        print('CHECK FAILED: no offline checks configured', file=sys.stderr)
        return 1
    for index, args in enumerate(checks, 1):
        print(f'[{index}/{len(checks)}] {args[0]}', flush=True)
        try:
            result = runner([sys.executable, '-X', 'utf8', '-B', *args], cwd=root,
                            timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f'CHECK FAILED: {args[0]}: {exc}', file=sys.stderr)
            return 1
        if result.returncode:
            print(f'CHECK FAILED: {args[0]} (exit {result.returncode})', file=sys.stderr)
            return 1
    print(f'PASS: all {len(checks)} offline checks completed', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(run_checks())
