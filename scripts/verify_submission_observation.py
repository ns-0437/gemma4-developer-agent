"""Cross-check a saved status observation against its original CSV, offline."""
import argparse
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from read_submission_snapshot import read_submission
from read_submission_details import read_details
from verify_final_validation_packet import strict_json


def verify(folder):
    folder = Path(folder)
    record = strict_json((folder / 'observation.json').read_text(encoding='utf-8'))
    if not isinstance(record, dict):
        raise ValueError('observation record must be an object')
    if not isinstance(record.get('checked_at_utc'), str):
        raise ValueError('observation timestamp must be a string')
    digest = record.get('stdout_sha256')
    if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise ValueError('observation digest must be a lowercase SHA-256')
    observed = record.get('observation')
    if not isinstance(observed, dict):
        raise ValueError('parsed observation must be an object')
    if type(observed.get('score_available')) is not bool or observed.get('live_status_checked') is not False:
        raise ValueError('observation flags must be booleans with no live-check claim')
    format_name = record.get('format', 'csv')
    if format_name not in ('csv', 'api_json'):
        raise ValueError('unsupported observation format')
    filename = 'submissions.json' if format_name == 'api_json' else 'submissions.csv'
    raw = (folder / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record['stdout_sha256']:
        raise ValueError('status CSV digest mismatch')
    time = datetime.fromisoformat(record['checked_at_utc'])
    if time.tzinfo is None or time.utcoffset().total_seconds() != 0:
        raise ValueError('observation timestamp must be UTC with an offset')
    observed = record['observation']
    parser = read_details if format_name == 'api_json' else read_submission
    parsed = parser(raw.decode('utf-8-sig'), observed['submission_ref'])
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
