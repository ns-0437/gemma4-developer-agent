"""Interpret full Kaggle API records; COMPLETE alone is not scoring success."""
from decimal import Decimal, InvalidOperation
from verify_final_validation_packet import strict_json


def read_details(text, reference):
    if type(reference) is not int or reference <= 0:
        raise ValueError('reference must be a positive integer')
    rows = strict_json(text)
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError('expected a submission record list')
    matches = [r for r in rows if type(r.get('ref')) is int and r['ref'] == reference]
    if len(matches) != 1:
        raise ValueError('expected exactly one matching submission')
    row = matches[0]
    error_observed = 'errorDescription' in row
    status = row.get('status')
    error = row.get('errorDescription')
    if not isinstance(status, str) or not status.strip() or (error is not None and not isinstance(error, str)):
        raise ValueError('invalid status or error description')
    status = status.strip().removeprefix('SubmissionStatus.').upper()
    if not status:
        raise ValueError('empty normalized status')
    score = row.get('publicScore')
    if score not in (None, ''):
        if isinstance(score, bool): raise ValueError('invalid score')
        try:
            if not Decimal(str(score)).is_finite(): raise ValueError('nonfinite score')
        except InvalidOperation as exc:
            raise ValueError('invalid score') from exc
        score = str(score)
    else:
        score = None
    outcome = ('error' if error or status in {'ERROR', 'FAILED', 'CANCELLED', 'CANCELED'}
               else 'scored' if status == 'COMPLETE' and score is not None
               else 'complete_without_score' if status == 'COMPLETE'
               else 'pending_or_running' if status in {'PENDING', 'RUNNING', 'QUEUED'}
               else 'unknown_status')
    result = {'submission_ref': reference, 'status': status, 'public_score': score,
            'score_available': score is not None, 'error_description': error or None,
            'outcome': outcome, 'live_status_checked': False}
    if not error_observed:
        # A full API serializer may omit this field. Preserve the score as observed,
        # but never turn an unavailable error detail into an explicit no-error claim.
        result['error_description_observed'] = False
        if outcome == 'scored': result['outcome'] = 'score_observed_error_unknown'
        elif outcome == 'complete_without_score': result['outcome'] = 'complete_without_score_error_unknown'
    return result
