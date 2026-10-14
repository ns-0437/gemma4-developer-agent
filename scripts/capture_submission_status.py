"""Read Kaggle submission status once and preserve a new evidence directory.

No retries, polling, notebook pushes or competition submissions.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from read_submission_snapshot import read_submission
from verify_submission_observation import verify


def capture(folder, reference, *, runner=subprocess.run):
    folder = Path(folder)
    if folder.exists():
        raise ValueError('output directory already exists; preserve prior evidence')
    if type(reference) is not int or reference <= 0:
        raise ValueError('reference must be a positive integer')
    command = [sys.executable, '-m', 'kaggle', 'competitions', 'submissions',
               'gemma-4-developer-agent', '--csv']
    response = runner(command, capture_output=True, timeout=90, check=True)
    raw = response.stdout
    parsed = read_submission(raw.decode('utf-8-sig'), reference)
    record = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'command': command[1:], 'stdout_sha256': hashlib.sha256(raw).hexdigest(),
              'observation': parsed,
              'note': 'One read-only request; saved snapshot, not a live status guarantee.'}
    # A second process creating the directory during the request must also refuse.
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'submissions.csv').write_bytes(raw)
    (folder / 'observation.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return verify(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--reference', required=True, type=int)
    args = parser.parse_args()
    try:
        result = capture(args.folder, args.reference)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'STATUS CAPTURE FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
