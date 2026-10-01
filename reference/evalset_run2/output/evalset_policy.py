"""Pure sampling / validity / allocation policy for the evaluation-set screen.

This module is the SINGLE source of truth: `make_evalset_notebook.py` embeds this file verbatim into
the generated notebook, and `test_evalset_policy.py` imports it directly. No logic is duplicated.

Fixes for defects found in the first draft:
  * screening order interleaves strata round-robin instead of sorting by repository then truncating,
    which silently dropped every `psf/requests` candidate from the first 40;
  * quotas are enforced per repository, and screening does not stop merely because 24 tasks are valid;
  * validity now requires reference exit 0, baseline exit 1, no errored nodes in either arm, and
    explicit patch return codes, not just a non-empty fail->pass set;
  * dev/held-out capacities are filled exactly, and previously studied tasks are barred from held-out.
"""
from __future__ import annotations

import hashlib
from collections import Counter, OrderedDict

# Tasks whose controls, patches or traces we have already inspected. They may be used for iteration
# (development) but must never land in the held-out set.
PREVIOUSLY_STUDIED = {
    "requests_7309", "requests_6589", "rich_3471", "rich_2725", "rich_3105", "rich_3676", "rich_3934",
    "fastapi_11194", "fastapi_14246", "fastapi_14361", "fastapi_14482", "fastapi_14794",
    "fastapi_15588", "httpx_3672",
}


def order_key(instance_id: str) -> str:
    """Deterministic, reproducible, independent of difficulty/recency/outcome."""
    return hashlib.sha256(instance_id.encode()).hexdigest()


def size_band(n_changed_lines: int) -> str:
    return "small" if n_changed_lines < 20 else ("medium" if n_changed_lines < 60 else "large")


def repo_quota(repo_counts: dict, total: int, floor: int = 2) -> dict:
    """Proportional quota per repository with a floor, summing exactly to `total`."""
    repos = {r: c for r, c in repo_counts.items() if c > 0}
    if not repos:
        return {}
    grand = sum(repos.values())
    q = {r: max(min(floor, repos[r]), round(total * repos[r] / grand)) for r in repos}
    # trim from the repo that is most over its proportional share
    while sum(q.values()) > total:
        r = max(q, key=lambda r: (q[r] - total * repos[r] / grand, q[r]))
        if q[r] <= 1:
            q.pop(r)
            continue
        q[r] -= 1
    while sum(q.values()) < total:
        r = max(q, key=lambda r: (repos[r] - q[r], repos[r]))
        if q[r] >= repos[r]:
            others = [x for x in q if q[x] < repos[x]]
            if not others:
                break
            r = max(others, key=lambda x: repos[x] - q[x])
        q[r] += 1
    return q


def screening_order(inventory: list, quota: dict, cap: int) -> list:
    """Round-robin interleave across (repo, size) strata so no repository can be truncated away.

    `inventory` rows need: id, repo, size. Returns rows in the order they should be screened.
    """
    queues = OrderedDict()
    for repo in sorted(quota, key=lambda r: (-quota[r], r)):
        rows = [r for r in inventory if r["repo"] == repo]
        bands = Counter(r["size"] for r in rows)
        for band in sorted(bands):
            pool = sorted([r for r in rows if r["size"] == band], key=lambda r: order_key(r["id"]))
            if pool:
                queues[(repo, band)] = pool
    out, guard = [], 0
    while queues and len(out) < cap and guard < cap * 20:
        guard += 1
        for key in list(queues):
            if len(out) >= cap:
                break
            # take from the repo furthest from its quota first by iterating repos in quota order
            pool = queues[key]
            out.append(pool.pop(0))
            if not pool:
                queues.pop(key)
    return out[:cap]


def classify(baseline: dict, reference: dict) -> tuple:
    """Return (valid: bool, reasons: list[str], target_nodes: list[str]).

    Requires BOTH arms to be internally sound, not merely a non-empty fail->pass set.
    A JUnit <failure> alone does not establish the cause, so failure detail is preserved by the
    caller for human inspection; this function only enforces the mechanical preconditions.
    """
    reasons = []
    bn, rn = baseline.get("nodes"), reference.get("nodes")

    for arm, d in (("baseline", baseline), ("reference", reference)):
        if d.get("exception"):
            reasons.append(f"{arm}: sandbox exception: {str(d['exception'])[:80]}")
        if not d.get("import_in_checkout"):
            reasons.append(f"{arm}: grading import not from checkout")
        if d.get("patch_rc") is None:
            reasons.append(f"{arm}: missing patch return code")
        elif d["patch_rc"] != 0:
            reasons.append(f"{arm}: patch did not apply (rc={d['patch_rc']})")
        if d.get("test_patch_rc") is None:
            reasons.append(f"{arm}: missing verification patch return code")
        elif d["test_patch_rc"] != 0:
            reasons.append(f"{arm}: verification patch did not apply (rc={d['test_patch_rc']})")
        if d.get("collection_error"):
            reasons.append(f"{arm}: collection error")
        if d.get("pytest_exit") in (2, 3, 4):
            reasons.append(f"{arm}: pytest interrupted/internal error (exit={d['pytest_exit']})")

    if bn is None:
        reasons.append("baseline: no JUnit report (tests never ran)")
    elif not bn:
        reasons.append("baseline: empty collection")
    if rn is None:
        reasons.append("reference: no JUnit report (tests never ran)")
    elif not rn:
        reasons.append("reference: empty collection")

    if bn and any(o == "errored" for o in bn.values()):
        reasons.append("baseline: JUnit errors present")
    if rn and any(o == "errored" for o in rn.values()):
        reasons.append("reference: JUnit errors present")
    if rn and any(o == "failed" for o in rn.values()):
        reasons.append("reference: failing nodes present")

    if reference.get("pytest_exit") != 0:
        reasons.append(f"reference: pytest exit {reference.get('pytest_exit')} (must be 0)")
    if baseline.get("pytest_exit") != 1:
        reasons.append(f"baseline: pytest exit {baseline.get('pytest_exit')} (must be 1 = assertion failures)")

    target = sorted([n for n, o in (bn or {}).items()
                     if o == "failed" and (rn or {}).get(n) == "passed"])
    if not target:
        only_skipped = [n for n, o in (bn or {}).items() if o == "skipped"]
        reasons.append("no node fails at baseline and passes with reference"
                       + (" (candidate target nodes only skipped)" if only_skipped else ""))
    return (not reasons), reasons, target


def allocate(valid_rows: list, dev_capacity: int, holdout_capacity: int,
             studied: set = PREVIOUSLY_STUDIED, quota: dict | None = None) -> tuple:
    """Fill both capacities exactly where the pool allows, respecting strata where feasible.

    Held-out is filled FIRST and only from tasks never previously studied; development then takes the
    remainder. Filling held-out first prevents the earlier bug where every stratum started with dev
    and held-out slots were left empty while usable tasks were discarded.

    `quota` maps repository -> maximum tasks that repository may contribute to the FINAL selection
    (dev + held-out combined). Without it, one repository with many valid tasks could dominate the
    selection even though the screening order was balanced.
    """
    rows = sorted(valid_rows, key=lambda r: (r["repo"], r["size"], order_key(r["id"])))
    if quota:
        capped, used = [], Counter()
        for r in rows:
            lim = quota.get(r["repo"])
            if lim is None or used[r["repo"]] < lim:
                capped.append(r); used[r["repo"]] += 1
        rows = capped
    strata = OrderedDict()
    for r in rows:
        strata.setdefault((r["repo"], r["size"]), []).append(r)

    holdout, dev = [], []
    # pass 1: round-robin across strata, held-out eligible only
    while len(holdout) < holdout_capacity:
        took = False
        for key in list(strata):
            if len(holdout) >= holdout_capacity:
                break
            pool = strata[key]
            pick = next((r for r in pool if r["id"] not in studied and r not in holdout), None)
            if pick is not None:
                holdout.append(pick); pool.remove(pick); took = True
        if not took:
            break
    # pass 2: everything left goes to development, round-robin for balance
    remaining = [r for pool in strata.values() for r in pool]
    rem = OrderedDict()
    for r in remaining:
        rem.setdefault((r["repo"], r["size"]), []).append(r)
    while len(dev) < dev_capacity:
        took = False
        for key in list(rem):
            if len(dev) >= dev_capacity:
                break
            if rem[key]:
                dev.append(rem[key].pop(0)); took = True
        if not took:
            break
    sel = Counter(r["repo"] for r in dev + holdout)
    return ([r["id"] for r in dev], [r["id"] for r in holdout],
            {"dev_short": max(0, dev_capacity - len(dev)),
             "holdout_short": max(0, holdout_capacity - len(holdout)),
             "unused_valid": max(0, len(rows) - len(dev) - len(holdout)),
             "selected_per_repo": dict(sel),
             "quota_respected": (not quota) or all(sel[r] <= quota[r] for r in sel)})
