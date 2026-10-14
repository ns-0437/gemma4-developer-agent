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
from read_submission_details import read_details
from verify_submission_observation import verify


def capture(folder, reference, *, runner=subprocess.run):
    folder = Path(folder)
    if folder.exists():
        raise ValueError('output directory already exists; preserve prior evidence')
    if type(reference) is not int or reference <= 0:
        raise ValueError('reference must be a positive integer')
    # CLI summary serializers omit errorDescription, even with --format json.
    fetch = ("import json; from kaggle.api.kaggle_api_extended import KaggleApi; "
             "api=KaggleApi(); api.authenticate(); "
             "rows=api.competition_submissions('gemma-4-developer-agent'); "
             "print(json.dumps([json.loads(s.to_json()) for s in rows]))")
    command = [sys.executable, '-X', 'utf8', '-c', fetch]
    response = runner(command, capture_output=True, timeout=90, check=True)
    raw = response.stdout
    parsed = read_details(raw.decode('utf-8-sig'), reference)
    record = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'command': command[1:], 'format': 'api_json', 'stdout_sha256': hashlib.sha256(raw).hexdigest(),
              'observation': parsed,
              'note': 'One read-only request; saved snapshot, not a live status guarantee.'}
    # A second process creating the directory during the request must also refuse.
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'submissions.json').write_bytes(raw)
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
