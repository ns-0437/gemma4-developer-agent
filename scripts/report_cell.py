# Read the actual swegemma JSONL schema plus its separate patch and test artifacts.
import csv, json, re
from collections import Counter
from pathlib import Path

def read_candidate(results_root, name):
    out = results_root / name
    file = out / 'task_results.jsonl'
    rows = []
    if not file.exists():
        return rows
    seen = set()
    for line in file.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        tid = r['instance_id']
        if tid in seen:
            raise ValueError(f'Duplicate result for {name}/{tid}; do not silently combine reruns')
        seen.add(tid)
        safe = tid.replace('/', '__')
        patch_path = out / 'patches' / f'{safe}.patch'
        test_path = out / 'test_outputs' / f'{safe}.log'
        log_path = out / 'logs' / (tid.replace('/', '_') + '.log')
        patch = patch_path.read_text(encoding='utf-8') if patch_path.exists() else ''
        tests = test_path.read_text(encoding='utf-8') if test_path.exists() else ''
        log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
        error = r.get('error') or ''
        reported_size = r.get('agent_patch_size', 0)
        artifact_ok = len(patch) == reported_size
        exit_code = r.get('test_exit_code')
        grading_ran = exit_code is not None and exit_code >= 0 and bool(tests.strip())
        if not artifact_ok:
            cause = 'artifact_missing_or_mismatched'
        elif r.get('resolved'):
            cause = 'passed'
        elif 'Failed to apply' in error:
            cause = 'patch_apply_failed'
        elif 'timeout' in error.lower() or 'exceeded session' in error.lower():
            cause = 'budget_time'
        elif 'budget' in error.lower():
            cause = 'budget_exhausted'
        elif not grading_ran:
            cause = 'pipeline_error'
        elif not patch:
            cause = 'empty_patch'
        else:
            cause = 'tests_failed'
        rows.append(dict(candidate=name, task=tid, resolved=bool(r.get('resolved')),
            cause=cause, total_minutes=round(float(r.get('duration_seconds') or 0)/60, 3),
            tool_calls=r.get('tool_calls', 0), patch_bytes=len(patch.encode('utf-8')),
            artifact_ok=artifact_ok, test_exit=exit_code, grading_ran=grading_ran,
            trace_saved=(out/'traces'/f'trace_{safe}.json').exists(),
            log_saved=log_path.exists(),
            truncation_mentions=len(re.findall(r'reached the token limit', log)),
            tool_error_mentions=len(re.findall(r'"status":\s*"error"', log)), error=error))
    return rows

def paired_counts(rows, names):
    a, b = names
    by_name = {n: {r['task']: r['resolved'] for r in rows if r['candidate'] == n} for n in names}
    common = sorted(by_name[a].keys() & by_name[b].keys())
    counts = Counter((by_name[a][t], by_name[b][t]) for t in common)
    return dict(both=counts[True, True], neither=counts[False, False],
                only_a=counts[True, False], only_b=counts[False, True],
                missing_a=sorted(by_name[b].keys()-by_name[a].keys()),
                missing_b=sorted(by_name[a].keys()-by_name[b].keys()))

rows = [r for n in CANDIDATE_DIRS for r in read_candidate(RESULTS_ROOT, n)]
if rows:
    with (WORKING_DIR / 'eval_results.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
for name in CANDIDATE_DIRS:
    subset = [r for r in rows if r['candidate'] == name]
    expected = set(TASK_IDS)
    actual = {r['task'] for r in subset}
    print(name, 'solved', sum(r['resolved'] for r in subset), '/', len(subset),
          'missing', sorted(expected-actual), 'unexpected', sorted(actual-expected))
    print('failure categories:', dict(Counter(r['cause'] for r in subset)))
    for r in subset:
        print(json.dumps(r))
if len(CANDIDATE_DIRS) == 2:
    print('PAIRED (completed common tasks only):', paired_counts(rows, list(CANDIDATE_DIRS)))
print('total_minutes includes setup, agent execution AND grading; it is not an inference-time projection.')
print('Log mention counts are diagnostics, not authoritative event counts.')
print('Prompt checks do not establish filesystem isolation for the subprocess backend.')
if MODE == 'smoke':
    assert len(rows) == 1 and rows[0]['task'] == TASK_IDS[0], 'Expected exactly the smoke task result'
    r = rows[0]
    checks = dict(summary=(RESULTS_ROOT/r['candidate']/'summary.json').exists(),
        trace=r['trace_saved'], agent_log=r['log_saved'], tools=r['tool_calls'] > 0,
        patch_artifact_consistent=r['artifact_ok'], phase_2=r['grading_ran'])
    print('SMOKE STAGES:', checks, 'resolved=', r['resolved'], 'patch_bytes=', r['patch_bytes'])
    assert all(checks.values()), 'Pipeline stage failed; inspect saved results before a paired run'
    if r['patch_bytes'] == 0:
        print('EMPTY PATCH: pipeline reached grading, but nonempty patch extraction/apply remains unproven.')
