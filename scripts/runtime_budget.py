"""Scenario arithmetic only: not a measured runtime or grader guarantee."""
import math


def finite(name, value, *, positive=False):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + ' must be finite numeric input')
    if value < 0 or (positive and value == 0):
        raise ValueError(name + ' is outside the allowed range')


def budget(task_count, per_task_minutes, *, setup_seconds=0, startup_minutes=0,
           total_minutes=720, reserve_minutes=0):
    if type(task_count) is not int or task_count <= 0:
        raise ValueError('task_count must be a positive integer')
    for name, value in locals().copy().items():
        if name != 'task_count': finite(name, value, positive=name == 'total_minutes')
    try:
        overhead = startup_minutes + task_count * setup_seconds / 60 + reserve_minutes
        required = overhead + task_count * per_task_minutes
        remaining = total_minutes - required
        affordable = max(0, (total_minutes - overhead) / task_count)
        if not all(math.isfinite(v) for v in (overhead, required, remaining, affordable)):
            raise ValueError("scenario arithmetic exceeds finite numeric range")
    except OverflowError as exc:
        raise ValueError("scenario arithmetic exceeds finite numeric range") from exc
    return {'task_count': task_count, 'scenario_minutes': required,
            'remaining_minutes': remaining, 'fits_scenario': remaining >= 0,
            'affordable_task_minutes': affordable,
            'overhead_exceeds_budget': overhead > total_minutes,
            'measured_runtime': False, 'runtime_guarantee': False}


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=int, required=True)
    parser.add_argument('--per-task-minutes', type=float, required=True)
    parser.add_argument('--setup-seconds', type=float, default=0)
    parser.add_argument('--startup-minutes', type=float, default=0)
    parser.add_argument('--total-minutes', type=float, required=True)
    parser.add_argument('--reserve-minutes', type=float, default=0)
    args = parser.parse_args()
    try:
        result = budget(args.tasks, args.per_task_minutes, setup_seconds=args.setup_seconds,
                        startup_minutes=args.startup_minutes, total_minutes=args.total_minutes,
                        reserve_minutes=args.reserve_minutes)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['fits_scenario'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
