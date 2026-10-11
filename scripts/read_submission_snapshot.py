"""Read one Kaggle submission from a saved CSV response; never contacts Kaggle."""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path


def read_submission(text, reference):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not {'ref', 'status', 'publicScore'} <= set(fields):
        raise ValueError('missing or duplicate submission CSV columns')
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('malformed submission CSV row')
    matches = [r for r in rows if r['ref'].strip() == str(reference)]
    if len(matches) != 1:
        raise ValueError('expected exactly one matching submission reference')
    row = matches[0]
    status = row['status'].strip().removeprefix('SubmissionStatus.').upper()
    score = row['publicScore'].strip()
    if score:
        try:
            number = Decimal(score)
        except InvalidOperation as exc:
            raise ValueError('invalid public score') from exc
        if not number.is_finite():
            raise ValueError('nonfinite public score')
    return {'submission_ref': int(reference), 'status': status,
            'public_score': score or None,
            'score_available': bool(score), 'live_status_checked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path)
    parser.add_argument('--reference', type=int, required=True)
    args = parser.parse_args()
    try:
        result = read_submission(args.csv_file.read_text(encoding='utf-8'), args.reference)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'SUBMISSION SNAPSHOT INVALID: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
