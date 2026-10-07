"""Cell fragments that turn the pilot's four-run notebook into the eight-run comparison.

Each fragment here exists because a reviewer named a specific defect in the pilot's cells:

  * dispatch decisions read only the ESCAPED exception, but swegemma's Evaluator.run() returns
    normally in most failure modes and records the reason in TaskResult.error, so the common case
    was invisible (DISPATCH_HELPER, RUN_REPLACEMENTS);
  * every BadRequestError was classified as a candidate failure without examining its cause, so a
    broken model server would have been recorded as a candidate result (DISPATCH_HELPER);
  * leftover sandboxes were printed, never gated, and the glob counted every sandbox on the box
    rather than the ones this run created (RUN_REPLACEMENTS);
  * the report iterated RUNS, so an early stop silently produced fewer than eight rows
    (REPORT_REPLACEMENTS);
  * the four selected controls were taken on trust from a different environment
    (CONTROL_REVALIDATION).

Kept separate from make_compare_notebook.py so the substitutions stay readable and each one can
assert that its anchor still exists rather than silently not applying.
"""
from __future__ import annotations

# --------------------------------------------------------------------------------------------
# Outcome classification, inserted into the RUN cell before the dispatch loop.
# --------------------------------------------------------------------------------------------
DISPATCH_HELPER = '''
# --------------------------------------------------------------------------------------------
# Outcome classification.
#
# swegemma's Evaluator.run() RETURNS NORMALLY in most failure modes and records the reason in
# TaskResult.error (models/task.py:181), which is persisted to results_dir/task_results.jsonl.
# Reading only the escaped exception therefore misses the common case. Both are consumed below.
#
# Persisted error vocabulary, read from the installed harness source, not guessed:
#   'Agent exceeded session timeout (N min)'                     -> candidate (budget)
#   'Failed to apply agent patch: ...'                           -> candidate (its own patch)
#   'Failed to apply test_patch: ...'                            -> environment (answer key)
#   'Missing JUnit XML report (possible premature os._exit(0))'  -> grading not observed
#   'Pytest stdout summary indicates zero or no passing tests'   -> graded, zero passes (a RESULT)
#   'Sandbox execution error: ...'                               -> environment
#   'Evaluation error: ...' / 'Unexpected evaluation worker error: ...' -> wrapper, inspect cause
#
# The harness contains NO BadRequestError or context-window handling of its own (grep over the
# installed source finds none), so any such text comes from litellm or the model server. A 400 is a
# candidate failure only when its cause is the request the agent produced; a 400 from an unready or
# misconfigured server is an environment failure. An unexamined 400 is therefore NOT attributed to
# the candidate.
# --------------------------------------------------------------------------------------------
_CANDIDATE_MARKERS = (
    'contextwindowexceeded', 'context window', 'maximum context length',
    'reduce the length of the messages', 'too many tokens', 'prompt is too long',
    'exceeded session timeout', 'turns budget', 'tool call budget',
    'failed to apply agent patch',
)
# Specific, self-describing environment causes. NOT wrappers.
_ENVIRONMENT_MARKERS = (
    'failed to apply test_patch', 'connection refused', 'connection error',
    'apiconnectionerror', 'read timed out', 'service unavailable', 'internal server error',
    'bad gateway', 'out of memory', 'cuda error', 'no such file or directory',
)
# Generic wrappers: the harness puts the REAL cause inside these, so they are examined only after
# the specific markers above have had a chance to match the text they contain.
_WRAPPER_MARKERS = (
    'unexpected evaluation worker error', 'sandbox execution error', 'evaluation error',
)
_UNOBSERVED_MARKERS = ('missing junit xml report',)
# A graded run with zero passes is an OUTCOME, not a failure of the run.
_RESULT_MARKERS = ('indicates zero or no passing tests',)
# The agent loop ended with no patch submitted. Observed in compare kernel version 2 (candidate B on
# rich_3278): the model emitted `<|tool_call>...<tool_call|>` with mismatched delimiters, the server's
# tool parser did not recognise it as a tool call, the harness treated the text as a final answer,
# and swegemma persisted exactly this message. Nothing about the environment failed: four L4s were
# up, the sandbox was clean, both setup provenance probes passed, and the SAME server had just
# carried candidate A through 60 turns. This is the candidate's own tool use, so it is a candidate
# outcome and must not stop the other candidate's runs.
#
# Deliberately checked AFTER _ENVIRONMENT_MARKERS: when a real environment cause is named in the
# same string, that cause wins. A missing submission is what remains when nothing else is wrong.
_CANDIDATE_NO_SUBMISSION_MARKERS = ('completed execution without calling submit_patch',)

# Worst-first. A genuine environment failure must never be hidden behind a candidate error, and a
# candidate error must never be hidden behind a clean-looking second source.
_PRECEDENCE = ('environment', 'unobserved_grading', 'candidate', 'ok')


def _classify_one(text):
    """Classify ONE error string. Candidate causes are examined before generic wrappers."""
    low = text.lower()
    for m in _RESULT_MARKERS:
        if m in low:
            return 'ok', m
    for m in _UNOBSERVED_MARKERS:
        if m in low:
            return 'unobserved_grading', m
    # Before the wrappers: 'Unexpected evaluation worker error: ...ContextWindowExceededError...'
    # is a context-window failure reported through a wrapper, and belongs to the candidate.
    for m in _CANDIDATE_MARKERS:
        if m in low:
            return 'candidate', m
    for m in _ENVIRONMENT_MARKERS:
        if m in low:
            return 'environment', m
    # After the specific environment causes, before the generic wrappers: a run that simply never
    # submitted has an identified cause, and that cause is the candidate's.
    for m in _CANDIDATE_NO_SUBMISSION_MARKERS:
        if m in low:
            return 'candidate', 'agent ended without submitting a patch (no environment cause found)'
    if 'badrequesterror' in low or 'invalidrequesterror' in low:
        return 'environment', 'BadRequest/InvalidRequest with no identified cause (not charged to the candidate)'
    for m in _WRAPPER_MARKERS:
        if m in low:
            return 'environment', 'wrapper with no identified cause: ' + m
    return 'environment', 'unclassified error'


def classify_outcome(escaped_error, persisted_error):
    """Return (outcome, reason).

    outcome is one of: ok | candidate | environment | unobserved_grading.

    BOTH sources are classified before any decision is taken. An earlier implementation returned on
    the first source that matched, so an escaped candidate error silently discarded a persisted
    environment failure. Results are combined worst-first via _PRECEDENCE, and the reason names
    every source so a combined verdict can be audited.
    """
    per_source = []
    for label, text in (('escaped', escaped_error), ('persisted', persisted_error)):
        if text:
            cls, why = _classify_one(text)
            per_source.append((label, cls, why))
    if not per_source:
        return 'ok', ''
    for want in _PRECEDENCE:
        hits = [p for p in per_source if p[1] == want]
        if hits:
            label, cls, why = hits[0]
            others = '; '.join(f'{l}={c}' for l, c, _ in per_source if l != label)
            return cls, f'{label}: {why}' + (f' [also {others}]' if others else '')
    return 'ok', ''


def read_persisted_result(out_dir, tid):
    """(record_or_None, persisted_error, n_records) from the evaluator's own output file."""
    jf = Path(out_dir) / 'task_results.jsonl'
    if not jf.exists():
        return None, None, 0
    recs = [json.loads(l) for l in jf.read_text(encoding='utf-8').splitlines() if l.strip()]
    if not recs:
        return None, None, 0
    rec = recs[0]
    if rec.get('instance_id') not in (None, tid):
        return rec, f"result is for {rec.get('instance_id')}, expected {tid}", len(recs)
    return rec, rec.get('error'), len(recs)


'''


# --------------------------------------------------------------------------------------------
# Sandbox cleanup helpers. Appended to the COMMON cell so BOTH the control re-validation (which
# runs before the model server starts) and the dispatch loop use the same implementation. They
# previously lived in the RUN cell, which executes after the controls, so the controls could not
# check their own teardown at all.
# --------------------------------------------------------------------------------------------
COMMON_CLEANUP_HELPERS = """

import time
from pathlib import Path

def sandbox_set():
    '''Sandbox directories currently on disk. Used to attribute cleanup to a specific run.'''
    return {str(p) for p in Path(SANDBOX_ROOT_STR).glob('swegemma_sandbox_*')}


def confirm_cleanup(before, grace_s=None):
    '''Sandboxes THIS run created that are still present after a bounded grace period.

    Only directories absent before the run are counted, so an unrelated leftover cannot mask or
    manufacture a failure. Nothing is ever deleted here: a leak is reported, not tidied away, and an
    unrelated sandbox is never touched. Returns (ok, owned_leftovers).
    '''
    grace_s = CLEANUP_GRACE_S if grace_s is None else grace_s
    deadline = time.time() + grace_s
    owned = sorted(sandbox_set() - before)
    while owned and time.time() < deadline:
        time.sleep(3)
        owned = sorted(sandbox_set() - before)
    return (not owned), owned
"""

# --------------------------------------------------------------------------------------------
# RUN cell substitutions.
# --------------------------------------------------------------------------------------------
RUN_REPLACEMENTS = [
    # 1. record the sandboxes that existed before the run, so cleanup can be attributed
    (
        "            out.mkdir(parents=True, exist_ok=True)\n            PHASE.clear()",
        "            out.mkdir(parents=True, exist_ok=True)\n"
        "            sandboxes_before = sandbox_set()\n"
        "            PHASE.clear()",
    ),
    # 2. consume BOTH the escaped exception and the evaluator's own persisted result
    (
        """                # A candidate-only model error (context window, malformed request) is a RESULT.
                candidate_error = bool(err) and any(k in (err or '') for k in (
                    'ContextWindowExceededError', 'BadRequestError', 'InvalidRequestError'))
                environment_error = bool(err) and not candidate_error""",
        """                # Both sources: the escaped exception AND what the evaluator persisted. The
                # evaluator returns normally in most failure modes, so `err` alone is usually None.
                rec, persisted_err, n_recs = read_persisted_result(out, tid)
                outcome, outcome_reason = classify_outcome(err, persisted_err)
                grading_observed = bool(PHASE.get('grading_phase_s'))
                if outcome == 'ok' and n_recs == 0:
                    outcome, outcome_reason = 'environment', 'evaluator wrote no task result'
                elif n_recs > 1:
                    outcome, outcome_reason = 'environment', f'{n_recs} task results written, expected 1'
                elif outcome == 'ok' and not grading_observed:
                    # Grading that never started is NOT a provenance failure and NOT a candidate
                    # failure: it is an absence of observation, and is reported as one.
                    outcome, outcome_reason = 'unobserved_grading', 'grading phase never ran'
                candidate_error = outcome == 'candidate'
                environment_error = outcome == 'environment'
                unobserved_grading = outcome == 'unobserved_grading'
                cleanup_ok, owned_sandboxes = confirm_cleanup(sandboxes_before)""",
    ),
    # 3. carry the new fields into the run record
    (
        """                    candidate_error=candidate_error,
                    environment_error=environment_error,""",
        """                    candidate_error=candidate_error,
                    environment_error=environment_error,
                    unobserved_grading=unobserved_grading,
                    outcome=outcome, outcome_reason=outcome_reason,
                    grading_observed=grading_observed,
                    persisted_error=persisted_err,
                    n_persisted_results=n_recs,
                    cleanup_ok=cleanup_ok, owned_sandboxes=owned_sandboxes,""",
    ),
    # 4. gate on cleanup and report the outcome class, before any continue/stop decision
    (
        """            last = RUNS[-1]
            print('  phase status:', last['phase_status'])""",
        """            last = RUNS[-1]
            print('  phase status:', last['phase_status'])
            print('  outcome:', last['outcome'], '|', last['outcome_reason'] or 'clean')
            print('  grading observed:', last['grading_observed'],
                  '| results written:', last['n_persisted_results'])
            print('  cleanup of THIS run\\'s sandboxes:', last['cleanup_ok'],
                  '' if last['cleanup_ok'] else f"| still present: {last['owned_sandboxes']}")
            if not last['cleanup_ok']:
                # A leaked sandbox means the next run does not start from a known state.
                STOP_REASON = 'sandbox cleanup for this run could not be confirmed'
                print('Stopping further dispatch:', STOP_REASON)
                break
            if last['unobserved_grading']:
                STOP_REASON = 'grading was not observed; the result cannot be graded or attributed'
                print('Stopping further dispatch:', STOP_REASON)
                break""",
    ),
    # 5. record why we stopped, for the report's not_attempted rows
    (
        """            if last['provenance_failed'] or last['environment_error']:
                print('Stopping further dispatch: genuine environment/provenance failure.')
                break""",
        """            if last['provenance_failed'] or last['environment_error']:
                STOP_REASON = ('provenance failure' if last['provenance_failed']
                               else f"environment failure: {last['outcome_reason']}")
                print('Stopping further dispatch:', STOP_REASON)
                break""",
    ),
    (
        """                    print('Stopping further dispatch: candidate error and the model server is not healthy.')
                    break""",
        """                    STOP_REASON = 'candidate error and the model server is not healthy'
                    print('Stopping further dispatch:', STOP_REASON)
                    break""",
    ),
    (
        """                print('Insufficient session allowance for another run; preserving partial artifacts.')
                break""",
        """                STOP_REASON = 'insufficient session allowance for another run'
                print(STOP_REASON + '; preserving partial artifacts.')
                break""",
    ),
    # 6. declare STOP_REASON alongside RUNS
    (
        "RUNS = []\nprint('planned run order:', ORDER)",
        "RUNS = []\nSTOP_REASON = None\nprint('planned run order:', ORDER)\n"
        "print('backend for BOTH preconditions and evaluation: subprocess')",
    ),
]

# --------------------------------------------------------------------------------------------
# REPORT cell substitutions: one row per planned ORDER entry, always.
# --------------------------------------------------------------------------------------------
REPORT_REPLACEMENTS = [
    (
        '''rows = []
for r in (RUNS if "RUNS" in dir() else []):
    d = Path(r["dir"]); tid = r["task"]''',
        '''# Every planned run appears exactly once, executed or not. An early stop must not shrink the
# report: a missing row is indistinguishable from a run that was never planned.
ROW_KEYS = ["candidate", "task", "attempted", "stop_reason", "resolved", "attribution",
            "harness_error", "test_exit_code", "grading_ran", "grading_observed",
            "outcome", "outcome_reason", "cleanup_ok", "owned_sandboxes",
            "patch_bytes", "patch_touches_source", "patch_files", "wall_s",
            "agent_phase_s", "grading_phase_s", "both_setup_imports_verified", "phase_status",
            "failure_class", "agent_loop_s", "termination_error", "duration_seconds_harness",
            "tool_calls", "edit_calls", "shell_edit_hints", "repeated_identical_cmds",
            "tool_errors", "first_source_edit_attempt_step", "finish_reasons",
            "prompt_tokens", "completion_tokens",
            "successful_tool_calls", "rejected_tool_calls", "acknowledged_source_edit_calls",
            "tmp_scratch_writes", "repeated_identical_tool_calls", "unparsed_tool_call_texts",
            "tool_use_flags",
            "run_error"]

_runs = RUNS if "RUNS" in dir() else []
RUN_BY_KEY = {}
for _r in _runs:
    _k = (_r["task"], _r["candidate"])
    assert _k not in RUN_BY_KEY, f"duplicate run record for {_k}"
    RUN_BY_KEY[_k] = _r
PLANNED = list(ORDER) if "ORDER" in dir() else []
assert len(PLANNED) == len(set(PLANNED)), "ORDER contains duplicate (task, candidate) pairs"
_orphans = set(RUN_BY_KEY) - set(PLANNED)
assert not _orphans, f"run records outside the planned ORDER: {sorted(_orphans)}"
_stop = STOP_REASON if "STOP_REASON" in dir() else None

rows = []
for _tid, _cand in PLANNED:
    r = RUN_BY_KEY.get((_tid, _cand))
    if r is None:
        row = {k: UNAVAILABLE for k in ROW_KEYS}
        row.update({"candidate": _cand, "task": _tid, "attempted": False,
                    "attribution": "not_attempted",
                    "stop_reason": _stop or "not reached before the run loop ended",
                    "failure_class": "not_attempted", "outcome": "not_attempted",
                    "run_error": "", "harness_error": UNAVAILABLE})
        assert set(row) == set(ROW_KEYS), "not_attempted row shape drifted from ROW_KEYS"
        rows.append(row)
        continue
    d = Path(r["dir"]); tid = r["task"]''',
    ),
    (
        '''    rows.append({
        "candidate": r["candidate"], "task": tid,
        "resolved": rec.get("resolved", UNAVAILABLE),''',
        '''    row = {
        "candidate": r["candidate"], "task": tid,
        "attempted": True, "stop_reason": "",
        "grading_observed": r.get("grading_observed", UNAVAILABLE),
        "outcome": r.get("outcome", UNAVAILABLE),
        "outcome_reason": r.get("outcome_reason", ""),
        "cleanup_ok": r.get("cleanup_ok", UNAVAILABLE),
        "owned_sandboxes": ";".join(r.get("owned_sandboxes") or []) or "",
        "resolved": rec.get("resolved", UNAVAILABLE),''',
    ),
    (
        '''        "failure_class": ("environment" if r.get('environment_error') else
                          "provenance" if r.get('provenance_failed') else
                          "candidate" if r.get('candidate_error') else "none"),''',
        '''        "failure_class": ("provenance" if r.get('provenance_failed') else
                          "environment" if r.get('environment_error') else
                          "unobserved_grading" if r.get('unobserved_grading') else
                          "candidate" if r.get('candidate_error') else "none"),''',
    ),
    (
        '''        **ts, "run_error": (r.get("error") or "")[:120] or "",
    })''',
        '''        **ts, "run_error": (r.get("error") or "")[:120] or "",
    }
    missing, extra = set(ROW_KEYS) - set(row), set(row) - set(ROW_KEYS)
    assert not missing and not extra, f"row shape drift: missing={missing} extra={extra}"
    rows.append(row)''',
    ),
]

# --------------------------------------------------------------------------------------------
# Control re-validation, appended to the PRECOND cell. CPU only, before any model dispatch.
# --------------------------------------------------------------------------------------------
CONTROL_REVALIDATION = '''
# ---------------------------------------------------------------------------------------------
# Re-validate the four selected controls UNDER THIS NOTEBOOK'S SETUP.
#
# The saved controls came from the CPU screening kernel. Their environment_versions and
# setup_commands were recorded, but this session's versions are only observable here, at run time,
# so equivalence cannot be asserted in advance. Rather than assume it, the controls are re-run with
# the same patched setup path used above, and compared against what was recorded. This is CPU work
# and happens before the model server starts.
#
# The exact pytest command recorded by the screen is re-issued, so a difference in outcome cannot be
# blamed on a different invocation.
# ---------------------------------------------------------------------------------------------
import xml.etree.ElementTree as _ET

def _nodes_from_junit(xml_text):
    """Return (nodes, duplicates, parse_error).

    nodes is None when the report is missing, unparseable or contains no testcase elements. That
    stays distinct from an empty dict for the rest of the pipeline: an earlier version collapsed
    both to {} via `nodes or {}`, which let a missing report satisfy a reference arm whose expected
    failure set is empty. Duplicate node identities are reported rather than silently overwritten.
    """
    if not (xml_text or '').strip():
        return None, [], 'empty report'
    try:
        root = _ET.fromstring(xml_text)
    except Exception as exc:
        return None, [], f'unparseable report: {type(exc).__name__}: {exc}'
    out, dupes = {}, []
    seen_any = False
    for tc in root.iter('testcase'):
        seen_any = True
        # Full classname, matching the screening side (make_evalset_notebook.py) exactly.
        # Collapsing to the last dotted component silently aliased `tests.test_vibe` to
        # `test_vibe`, so fastapi/requests evidence never matched; rich classnames carry no
        # dot, which is why development tasks hid the defect.
        cls = (tc.get('classname') or '').strip()
        name = tc.get('name') or ''
        key = (cls + '::' + name).strip(':') if cls else name
        outcome = 'passed'
        if tc.find('failure') is not None:
            outcome = 'failed'
        elif tc.find('error') is not None:
            outcome = 'errored'
        elif tc.find('skipped') is not None:
            outcome = 'skipped'
        if key in out:
            dupes.append(key)
        out[key] = outcome
    if not seen_any:
        return None, [], 'report contains no testcase elements'
    return out, sorted(set(dupes)), None



WORKSPACE_TOKEN = "<WS>"

# Same shape compare_control_nodes returns, so a refusal reports like any other failure.
_EMPTY_DETAIL = {"missing": [], "extra": [], "changed": [], "skipped": [],
                 "targets_wrong": [], "n_observed": 0, "n_expected": 0}


def _workspace_root_from_evidence(*candidates):
    """Derive the arm's workspace root from RECORDED evidence, or refuse.

    Each candidate is a recorded absolute path that is known to live inside the arm's workspace
    (an import probe path, a recorded workspace path). The root is the prefix ending at the
    "/workspace" component. Nothing is guessed, and nothing is chosen because it makes the
    comparison pass: if the candidates disagree, the root is AMBIGUOUS and the caller must fail.
    """
    roots = set()
    for value in candidates:
        if not isinstance(value, str) or not value:
            continue
        marker = "/workspace"
        i = value.find(marker + "/")
        if i < 0:
            i = len(value) - len(marker) if value.endswith(marker) else -1
        if i < 0:
            continue
        roots.add(value[: i + len(marker)])
    if len(roots) > 1:
        return None, "ambiguous workspace root in recorded evidence: " + repr(sorted(roots))
    if not roots:
        return None, "no workspace root could be derived from recorded evidence"
    return roots.pop(), None


def _canon_path(value, root):
    """Substitute `root` only at a real path boundary.

    The replacement fires when the match is followed by `/` or by any character that cannot
    continue a path component. That keeps sibling directories such as `<root>_backup` intact, and
    leaves classnames, test names and non-path parameters untouched because they do not contain
    the recorded absolute root. Used for BOTH node identities and target identities.
    """
    if not root or not isinstance(value, str):
        return value
    return _re_canon.sub(WORKSPACE_TOKEN, value) if (_re_canon := _canon_re(root)) else value


def _canon_re(root):
    import re as _re
    return _re.compile(_re.escape(root) + r"(?![A-Za-z0-9_.\-])")


def canonicalize_nodes(nodes, root):
    """Canonicalize node identities and reject EVERY many-to-one mapping.

    Returns (canonical_nodes, mapping, collisions). A collision is any canonical identity reached
    from more than one distinct original identity, whatever the insertion order and whatever the
    outcomes. That includes an identity that already contains the literal token colliding with a
    substituted path. Collisions must fail: collapsing two identities would hide a real difference.
    """
    if nodes is None:
        return None, {}, []
    mapping = {key: _canon_path(key, root) for key in nodes}
    sources = {}
    for key, new in mapping.items():
        sources.setdefault(new, []).append(key)
    collisions = sorted(new for new, keys in sources.items() if len(set(keys)) > 1)
    out = {}
    for key, new in mapping.items():
        out[new] = nodes[key]
    return out, mapping, collisions


def canonicalize_targets(targets, root):
    return [_canon_path(t, root) for t in (targets or [])]


def compare_control_nodes(observed, expected, targets, arm):
    """Full node/outcome comparison for a reproducibility control.

    Returns (ok, detail). `observed` may be None, which is always a failure. Every expected node
    must be present with the same outcome; every saved target node must fail in the baseline arm and
    pass in the reference arm. Comparing failure sets alone never proved the reference arm actually
    ran, let alone passed, the tests the baseline failed.
    """
    detail = {'missing': [], 'extra': [], 'changed': [], 'skipped': [],
              'targets_wrong': [], 'n_observed': 0, 'n_expected': len(expected)}
    if observed is None:
        detail['reason'] = 'no usable JUnit report'
        return False, detail
    if not observed:
        detail['reason'] = 'no nodes collected'
        return False, detail
    detail['n_observed'] = len(observed)
    detail['missing'] = sorted(set(expected) - set(observed))
    detail['extra'] = sorted(set(observed) - set(expected))
    detail['changed'] = sorted(f'{n}: expected {expected[n]}, observed {observed[n]}'
                               for n in set(expected) & set(observed)
                               if expected[n] != observed[n])
    detail['skipped'] = sorted(n for n, o in observed.items() if o == 'skipped')
    want_target = 'failed' if arm == 'baseline' else 'passed'
    detail['targets_wrong'] = sorted(
        f'{n}: expected {want_target}, observed {observed.get(n, "ABSENT")}'
        for n in targets if observed.get(n) != want_target)
    ok = not (detail['missing'] or detail['extra'] or detail['changed'] or detail['targets_wrong'])
    if ok:
        detail['reason'] = ''
    else:
        detail['reason'] = 'node map does not match the saved control'
    return ok, detail


async def _revalidate_control(task, arm):
    """Run one control arm in a fresh sandbox under this notebook's setup. arm: baseline|reference."""
    global ACTIVE_RUN, ACTIVE_PHASE
    ACTIVE_RUN = {"task": task.instance_id, "candidate": None, "package": pkg_of(task)}
    ACTIVE_PHASE = "control_" + arm
    mgr = SubprocessManager(timeout_seconds=900)
    # Snapshot BEFORE this arm creates anything, so only its own sandboxes are attributable to it.
    sandboxes_before = sandbox_set()
    sid = await sandbox_start(mgr)
    rec = {"task": task.instance_id, "arm": arm}
    try:
        cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / "snapshots",
                         results_dir=RESULTS / "control", submission_dir=WORKING_DIR,
                         models=ModelRegistry(), sandbox="subprocess", timeout_seconds=900,
                         display_mode="quiet")
        await asyncio.to_thread(setup_container_wheels, mgr, sid, cfg)
        await asyncio.to_thread(extract_snapshot, mgr, sid, snapshot_for(task))
        await asyncio.to_thread(setup_git_exclude, mgr, sid)
        await asyncio.to_thread(_cs.install_editable_package, mgr, sid)
        await asyncio.to_thread(install_test_dependencies, mgr, sid, task.repo, config=cfg)
        await asyncio.to_thread(setup_workspace_test_config, mgr, sid, repo=task.repo)
        await asyncio.to_thread(setup_baseline_commit, mgr, sid, "baseline")

        # PATCH APPLICATION.
        #
        # Comparison version 1 aborted here: all eight test-patch and all four reference-patch
        # applications returned 128. Measured with real git: 128 means the patch file was MISSING
        # or EMPTY ("can't open patch" / "No valid patches in input"); a patch that merely fails to
        # apply returns 1. The old helper wrote the patch with a shell `python3 -c` one-liner and
        # never checked that command's exit code, so a failed write was invisible and every pytest
        # run then passed against an unpatched checkout.
        #
        # This now does exactly what the screening run did for 38 tasks without a single failure:
        # write to a HOST file, copy it in with mgr.copy_to, and apply with the harness's own
        # multi-strategy apply_patch_in_container. Creation is verified before application, and the
        # command output is preserved either way.
        async def _put(text, name):
            with _tempfile.NamedTemporaryFile("w", suffix="_" + name, delete=False,
                                              encoding="utf-8") as f:
                f.write(text if text.endswith("\\n") else text + "\\n")
                host = Path(f.name)
            try:
                await asyncio.to_thread(mgr.copy_to, sid, host, "/tmp/")
                return "/tmp/" + host.name, len(text.encode("utf-8")), \\
                    _hashlib.sha256(text.encode("utf-8")).hexdigest()
            finally:
                os.unlink(host)

        async def _apply(diff, label):
            """Return (rc, evidence). rc None means no patch was requested for this arm."""
            ev = {"label": label, "requested": bool((diff or "").strip())}
            if not ev["requested"]:
                ev["note"] = "no patch requested for this arm (not a successful application)"
                return None, ev
            path, size, sha = await _put(diff, label + ".patch")
            ev.update({"sandbox_path": path, "bytes": size, "sha256": sha})
            # Verify creation BEFORE attempting application, so a missing or empty file is named
            # as such instead of surfacing later as an opaque git exit 128.
            probe = await sandbox_exec(mgr, sid, "wc -c < " + path + " || echo MISSING")
            ev["created_bytes"] = (probe.stdout or "").strip()
            ev["create_probe_rc"] = probe.exit_code
            if probe.exit_code != 0 or not (ev["created_bytes"] or "").strip().isdigit() \\
                    or int(ev["created_bytes"]) == 0:
                ev["error"] = "patch file was not created, or is empty; not attempting application"
                return 128, ev
            code, out, err = await asyncio.to_thread(apply_patch_in_container, mgr, sid, path)
            ev.update({"apply_rc": code, "stdout": (out or "")[-1500:], "stderr": (err or "")[-1500:]})
            return code, ev

        # Mirror the screening run: restore any test path before re-applying the verification patch.
        for _tf in _re_mod.findall(r"^\\+\\+\\+ b/(\\S+)", getattr(task, "test_patch", "") or "", _re_mod.M):
            await sandbox_exec(mgr, sid, "cd /workspace && git checkout HEAD -- " + _tf)
            await sandbox_exec(mgr, sid, "cd /workspace && git clean -f -- " + _tf)

        rec["test_patch_rc"], rec["test_patch_evidence"] = await _apply(
            getattr(task, "test_patch", ""), "testpatch")
        if arm == "reference":
            rec["patch_rc"], rec["patch_evidence"] = await _apply(getattr(task, "patch", ""), "gold")
        else:
            # NOT 0. The baseline arm applies no source patch; reporting 0 made "nothing was done"
            # indistinguishable from "applied successfully", which is how version 1 read as clean.
            rec["patch_rc"], rec["patch_evidence"] = None, {
                "label": "gold", "requested": False,
                "note": "baseline arm applies no source patch by design"}

        cmd = CONTROL_PYTEST_CMD[task.instance_id]
        xml = "/tmp/ctl_" + arm + ".xml"
        r = await sandbox_exec(mgr, sid, "cd /workspace && " + cmd + " -q --junit-xml=" + xml)
        rec["pytest_exit"] = r.exit_code
        rec["pytest_cmd"] = cmd
        rec["pytest_stdout"] = (r.stdout or "")[-8000:]
        rec["pytest_stderr"] = (getattr(r, "stderr", "") or "")[-4000:]
        rx = await sandbox_exec(mgr, sid, "cat " + xml)
        # The raw report is preserved verbatim. It is never synthesised: if cat failed, that is
        # recorded as a missing report, not replaced with an empty document.
        rec["junit_xml"] = (rx.stdout or "") if rx.exit_code == 0 else None
        rec["junit_read_rc"] = rx.exit_code
        nodes, dupes, parse_error = _nodes_from_junit(rec["junit_xml"] or "")
        rec["nodes"] = nodes
        rec["duplicate_nodes"] = dupes
        rec["junit_parse_error"] = parse_error if rx.exit_code == 0 else "JUnit report not readable"
        # Record THIS arm's real workspace path as provenance, so the identity mapping below is
        # derived from recorded evidence rather than from a path pattern assumed by convention.
        wsp = await sandbox_exec(
            mgr, sid, "cd /workspace && python3 -c \\"import os;print(os.path.realpath('.'))\\"")
        rec["workspace_real"] = (wsp.stdout or "").strip() or None
        rec["workspace_probe_rc"] = wsp.exit_code
        rv = await sandbox_exec(mgr, sid,
            "python3 -c \\"import importlib.metadata as m;"
            "print({p: m.version(p) for p in ['swegemma','adk-submission','adk-eval-core','google-adk']})\\"")
        rec["environment_versions"] = (rv.stdout or "").strip()
    except BaseException as exc:
        rec["exception"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = _tbmod.format_exc()
        rec.setdefault("nodes", None)
    finally:
        try:
            await sandbox_stop(mgr, sid)
        except BaseException as stop_exc:
            rec["teardown_error"] = f"{type(stop_exc).__name__}: {stop_exc}"
            rec["teardown_traceback"] = _tbmod.format_exc()
        # Teardown that RETURNS is not proof of teardown. Verify the arm's own sandboxes are gone,
        # with the same bounded grace the dispatch loop uses. Nothing is deleted here, and a
        # sandbox that existed before this arm is never attributed to it.
        rec["cleanup_ok"], rec["owned_sandboxes"] = confirm_cleanup(sandboxes_before)
        ACTIVE_RUN = None
    return rec


CONTROL_DIR = RESULTS / "control_evidence"
CONTROL_DIR.mkdir(parents=True, exist_ok=True)
CONTROL_RECHECK = []


def _persist_arm(record):
    """Write one arm's evidence the moment it exists, so a later failure cannot erase it."""
    stem = f"{record['task']}__{record['arm']}"
    raw = record.pop("junit_xml", None)
    if raw is not None:
        (CONTROL_DIR / (stem + ".junit.xml")).write_text(raw, encoding="utf-8")
    else:
        (CONTROL_DIR / (stem + ".NO_JUNIT.txt")).write_text(
            "no readable JUnit report; nothing was synthesised\\n"
            + str(record.get("junit_parse_error") or ""), encoding="utf-8")
    (CONTROL_DIR / (stem + ".json")).write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8")


CONTROL_STOP_REASON = None
for _t in SELECTED:
    if CONTROL_STOP_REASON:
        break
    saved = CONTROL_EVIDENCE[_t.instance_id]
    targets = CONTROL_TARGET_NODES[_t.instance_id]
    for _arm, _phase in (("baseline", "negative"), ("reference", "positive")):
        try:
            got = run_sync(lambda _t=_t, _a=_arm: _revalidate_control(_t, _a))
        except BaseException as _exc:
            got = {"task": _t.instance_id, "arm": _arm, "nodes": None,
                   "exception": f"{type(_exc).__name__}: {_exc}",
                   "traceback": _tbmod.format_exc(),
                   "cleanup_ok": False,
                   "owned_sandboxes": ["unknown: the arm did not reach its cleanup check"]}
        want = saved[_phase]
        expected = dict(want.get("nodes") or {})

        # ---- sandbox-root canonicalization -------------------------------------------------
        # requests_7427's suite parametrises a test with the ABSOLUTE workspace path, so its node
        # ID necessarily differs between the screening run and any later run. Both roots are
        # derived from recorded evidence: the saved arm's own recorded import/workspace paths, and
        # this arm's recorded workspace probe. An ambiguous root, an underivable root, or a
        # collision after substitution all FAIL; nothing is chosen to make the comparison pass.
        _saved_root, _saved_err = _workspace_root_from_evidence(
            want.get("workspace_real"), want.get("grading_import"), want.get("agent_import"))
        # The probe's stdout is only evidence if the probe SUCCEEDED. A nonzero exit with
        # plausible-looking output must not be trusted.
        if got.get("workspace_probe_rc") not in (0, None):
            _obs_root, _obs_err = None, (
                "workspace probe exited %r; its output is not usable as evidence"
                % (got.get("workspace_probe_rc"),))
        elif got.get("workspace_probe_rc") is None and got.get("workspace_real"):
            _obs_root, _obs_err = None, "workspace probe exit code was not recorded"
        else:
            _obs_root, _obs_err = _workspace_root_from_evidence(got.get("workspace_real"))
        _canon = {"saved_root": _saved_root, "saved_root_error": _saved_err,
                  "observed_root": _obs_root, "observed_root_error": _obs_err,
                  "token": WORKSPACE_TOKEN, "applied": False}

        _needs = any(isinstance(k, str) and "/workspace" in k
                     for k in list(expected) + list(got.get("nodes") or {})) \
            or any("/workspace" in t for t in targets)
        if _needs:
            if _saved_err or _obs_err:
                _canon["refused"] = _saved_err or _obs_err
                ok_nodes, detail = False, dict(
                    _EMPTY_DETAIL, canonicalization_refused=_canon["refused"],
                    n_observed=len(got.get("nodes") or {}), n_expected=len(expected))
            else:
                _exp_c, _exp_map, _exp_coll = canonicalize_nodes(expected, _saved_root)
                _obs_c, _obs_map, _obs_coll = canonicalize_nodes(got.get("nodes"), _obs_root)
                _tgt_c = canonicalize_targets(targets, _saved_root)
                _canon.update({"applied": True,
                               "expected_mapping": _exp_map, "observed_mapping": _obs_map,
                               "targets_canonical": _tgt_c,
                               "expected_collisions": _exp_coll,
                               "observed_collisions": _obs_coll})
                if _exp_coll or _obs_coll:
                    ok_nodes, detail = False, dict(
                        _EMPTY_DETAIL,
                        canonicalization_collision={"expected": _exp_coll,
                                                    "observed": _obs_coll},
                        n_observed=len(_obs_c or {}), n_expected=len(_exp_c))
                else:
                    ok_nodes, detail = compare_control_nodes(_obs_c, _exp_c, _tgt_c, _arm)
        else:
            ok_nodes, detail = compare_control_nodes(got.get("nodes"), expected, targets, _arm)
        got["canonicalization"] = _canon
        # ------------------------------------------------------------------------------------
        # A sandbox this arm leaked would be snapshotted as "pre-existing" by the dispatch loop's
        # own cleanup check, so it would never be caught there. It has to be caught here.
        agree = (ok_nodes
                 and not got.get("exception")
                 and not got.get("teardown_error")
                 and got.get("cleanup_ok") is True
                 and not got.get("duplicate_nodes")
                 and got.get("pytest_exit") == want.get("pytest_exit")
                 # baseline applies no source patch, so None is correct there and 0 would
                 # be a false success; reference MUST have applied its patch.
                 and got.get("patch_rc") == (None if _arm == "baseline" else 0)
                 and got.get("test_patch_rc") == 0
                 and not [n for n, o in (got.get("nodes") or {}).items() if o == "errored"])
        got["agrees_with_saved"] = bool(agree)
        got["saved_exit"] = want.get("pytest_exit")
        got["node_comparison"] = detail
        got["n_targets"] = len(targets)
        CONTROL_RECHECK.append(got)
        _persist_arm(dict(got))          # immediately, before the next arm runs
        print(f"  {_t.instance_id:14s} {_arm:9s} exit={got.get('pytest_exit')} "
              f"(saved {want.get('pytest_exit')}) nodes={detail['n_observed']}/{detail['n_expected']} "
              f"targets={len(targets)} agrees={agree}")
        for _k in ("missing", "extra", "changed", "skipped", "targets_wrong"):
            if detail.get(_k):
                print(f"                 {_k}: {detail[_k][:4]}"
                      + (" ..." if len(detail[_k]) > 4 else ""))
        if got.get("duplicate_nodes"):
            print(f"                 DUPLICATE node identities: {got['duplicate_nodes'][:4]}")
        if got.get("junit_parse_error"):
            print(f"                 junit: {got['junit_parse_error']}")
        if got.get("exception"):
            print(f"                 EXCEPTION: {got['exception'][:150]}")
        if got.get("teardown_error"):
            print(f"                 TEARDOWN ERROR: {got['teardown_error'][:150]}")
        if not got.get("cleanup_ok"):
            print(f"                 SANDBOX NOT CLEANED UP: {got.get('owned_sandboxes')}")
        # Evidence for this arm is already on disk (_persist_arm above). Stop before any further
        # arm runs, so a leaked sandbox cannot be inherited as "pre-existing" by the next one.
        if got.get("teardown_error") or not got.get("cleanup_ok"):
            CONTROL_STOP_REASON = (
                f"{_t.instance_id}/{_arm}: control sandbox cleanup could not be confirmed"
                + (f" ({got['teardown_error']})" if got.get("teardown_error") else ""))
            print("Stopping control re-validation:", CONTROL_STOP_REASON)
            break

(RESULTS / "control_recheck.json").write_text(
    json.dumps(CONTROL_RECHECK, indent=2, default=str), encoding="utf-8")
assert not CONTROL_STOP_REASON, (
    "control sandbox cleanup failed: " + str(CONTROL_STOP_REASON) +
    "; evidence is preserved in control_evidence/, and the model is NOT started")
_expected_arms = 2 * len(SELECTED)
assert len(CONTROL_RECHECK) == _expected_arms, (
    f"only {len(CONTROL_RECHECK)} of {_expected_arms} control arms ran; do not start the model")
_bad = [f"{c['task']}/{c['arm']}" for c in CONTROL_RECHECK if not c["agrees_with_saved"]]
assert not _bad, ("controls do not reproduce under this notebook's setup: " + str(_bad) +
                  "; do not start the model")
print("ALL FOUR CONTROLS REPRODUCE UNDER THIS SETUP (both arms, full node map, targets verified)")
'''

# --------------------------------------------------------------------------------------------
# Closing note: the pilot's wording described two tasks and must not be reused verbatim here.
# --------------------------------------------------------------------------------------------
CLOSING_REPLACEMENT = (
    '    print("A two-task pilot establishes that the experiment executes. It does NOT establish which")'
    + chr(10) +
    '    print("candidate is better. agent_phase_s covers container-A setup plus the agent loop;")',

    '    print("Four tasks from ONE repository (Textualize/rich) are a narrow diagnostic, not a general")'
    + chr(10) +
    '    print("ranking: any result here generalises to rich at best, and cannot say which candidate is")'
    + chr(10) +
    '    print("better overall. Both preconditions and evaluation run on the SUBPROCESS backend, which is")'
    + chr(10) +
    '    print("not a filesystem isolation boundary. agent_phase_s covers container-A setup plus the agent loop;")',
)


# --------------------------------------------------------------------------------------------
# The precondition probe had the same unguarded teardown the control arms had: sandbox_stop was
# called bare in a finally block, so a teardown failure escaped as a raw exception and a silently
# leaked sandbox was never noticed. A leak here is just as damaging, because the dispatch loop
# would later snapshot it as 'pre-existing' and never attribute it to anyone.
# --------------------------------------------------------------------------------------------
PRECOND_REPLACEMENTS = [
    ('    mgr = SubprocessManager(timeout_seconds=600)\n    sid = await sandbox_start(mgr)',
     '    mgr = SubprocessManager(timeout_seconds=600)\n    sandboxes_before = sandbox_set()\n    sid = await sandbox_start(mgr)'),
    ('    finally:\n        await sandbox_stop(mgr, sid)\n        ACTIVE_RUN = None\n    return out',
     '    finally:\n        try:\n            await sandbox_stop(mgr, sid)\n        except BaseException as stop_exc:\n            out["teardown_error"] = f"{type(stop_exc).__name__}: {stop_exc}"\n        # Teardown returning is not proof of teardown.\n        out["cleanup_ok"], out["owned_sandboxes"] = confirm_cleanup(sandboxes_before)\n        ACTIVE_RUN = None\n    return out'),
    ('    ok = under(_pc.get("agent_file", ""), _pc.get("ws", "")) and \\\n         under(_pc.get("grading_file", ""), _pc.get("ws", ""))',
     '    ok = (under(_pc.get("agent_file", ""), _pc.get("ws", ""))\n          and under(_pc.get("grading_file", ""), _pc.get("ws", ""))\n          and not _pc.get("teardown_error")\n          and _pc.get("cleanup_ok") is True)\n    if _pc.get("teardown_error"):\n        print("    TEARDOWN ERROR: " + str(_pc.get("teardown_error"))[:150])\n    if not _pc.get("cleanup_ok"):\n        print("    SANDBOX NOT CLEANED UP: " + str(_pc.get("owned_sandboxes")))'),
]
