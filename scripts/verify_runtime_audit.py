"""Recompute saved runtime audit evidence offline; never rewrite its files."""
import argparse
import json
from pathlib import Path
from inspect_eval_config import inspect_archive
from runtime_budget import budget

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {'v3': 'releases/v3_submission.zip', 'v4': 'releases/v4_thinking_on_submission.zip'}


def verify(audit, root=ROOT):
    audit = Path(audit)
    saved = json.loads((audit/'archive_config.json').read_text(encoding='utf-8'))
    actual = {name: inspect_archive(root/path) for name, path in PACKAGES.items()}
    if json.dumps(saved, sort_keys=True) != json.dumps(actual, sort_keys=True):
        raise ValueError('archive evidence differs from packaged bytes')
    scenarios = json.loads((audit/'scenarios.json').read_text(encoding='utf-8'))
    if scenarios.get('hypothetical_inputs_not_hidden_dataset_estimates') is not True:
        raise ValueError('hypothetical scenario declaration missing')
    rows = scenarios.get('scenarios')
    if not isinstance(rows, list) or not rows:
        raise ValueError('no scenarios to verify')
    for index, row in enumerate(rows):
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
