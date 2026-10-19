"""Recompute saved runtime audit evidence offline; never rewrite its files."""
import argparse
import json
from pathlib import Path
from inspect_eval_config import inspect_archive
from runtime_budget import budget

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {'v3': 'releases/v3_submission.zip', 'v4': 'releases/v4_thinking_on_submission.zip'}


def load_evidence(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f'non-finite JSON constant: {value}')

    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def verify(audit, root=ROOT):
    audit = Path(audit)
    saved = load_evidence(audit/'archive_config.json')
    actual = {name: inspect_archive(root/path) for name, path in PACKAGES.items()}
    if json.dumps(saved, sort_keys=True) != json.dumps(actual, sort_keys=True):
        raise ValueError('archive evidence differs from packaged bytes')
    scenarios = load_evidence(audit/'scenarios.json')
    if not isinstance(scenarios, dict):
        raise ValueError('scenario document must be an object')
    if scenarios.get('hypothetical_inputs_not_hidden_dataset_estimates') is not True:
        raise ValueError('hypothetical scenario declaration missing')
    rows = scenarios.get('scenarios')
    if not isinstance(rows, list) or not rows:
        raise ValueError('no scenarios to verify')
    keys = {'task_count', 'per_task_minutes', 'setup_seconds', 'startup_minutes', 'total_minutes', 'reserve_minutes'}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {'inputs', 'result'}:
            raise ValueError('scenario must contain exactly inputs and result')
        if not isinstance(row['inputs'], dict) or set(row['inputs']) != keys:
            raise ValueError('all six budget inputs must be explicit')
        if not isinstance(row['result'], dict):
            raise ValueError('scenario result must be an object')
        actual = budget(**row['inputs'])
        if json.dumps(row['result'], sort_keys=True) != json.dumps(actual, sort_keys=True):
            raise ValueError(f'scenario {index} result differs from recomputed arithmetic')
    return {'verified': True, 'archives': len(PACKAGES), 'scenarios': len(rows), 'live_status_checked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.audit), sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'RUNTIME AUDIT FAILED: {exc}\n')


if __name__ == '__main__':
    main()
