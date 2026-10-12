"""Cross-check a saved status observation against its original CSV, offline."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from read_submission_snapshot import read_submission
from verify_final_validation_packet import strict_json


def verify(folder):
    folder = Path(folder)
    record = strict_json((folder / 'observation.json').read_text(encoding='utf-8'))
    raw = (folder / 'submissions.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest() != record['stdout_sha256']:
        raise ValueError('status CSV digest mismatch')
    time = datetime.fromisoformat(record['checked_at_utc'])
    if time.tzinfo is None or time.utcoffset().total_seconds() != 0:
        raise ValueError('observation timestamp must be UTC with an offset')
    observed = record['observation']
    parsed = read_submission(raw.decode('utf-8-sig'), observed['submission_ref'])
    if parsed != observed:
        raise ValueError('observation differs from preserved CSV')
    return {'verified': True, 'checked_at_utc': record['checked_at_utc'],
            'observation': parsed, 'live_status_checked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.folder)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'OBSERVATION VERIFICATION FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
