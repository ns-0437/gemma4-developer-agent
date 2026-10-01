"""Tests for the evaluation-set sampling / validity / allocation policy.

Each test pins a defect found in the first draft, so a regression is caught rather than re-derived.
Run: python scripts/test_evalset_policy.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalset_policy as P  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


def real_inventory():
    """Use the real public task set when it is available locally; otherwise a faithful stand-in."""
    import re
    p = Path(__file__).resolve().parent.parent / "reference" / "tasks.jsonl"
    if not p.exists():
        return None
    inv = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        n = sum(1 for l in (t["patch"] or "").splitlines()
                if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
        inv.append({"id": t["instance_id"], "repo": t["repo"], "size": P.size_band(n)})
    return inv


def test_requests_included():
    print("\n[E1] every repository survives the screening cap (the first-40 defect)")
    inv = real_inventory()
    if inv is None:
        check("real task inventory available", False, "reference/tasks.jsonl missing")
        return
    counts = Counter(r["repo"] for r in inv)
    quota = P.repo_quota(counts, 24)
    order = P.screening_order(inv, quota, cap=40)
    dist = Counter(r["repo"] for r in order)
    print("    quota:", dict(quota))
    print("    first-40 distribution:", dict(dist))
    check("psf/requests appears in the first 40", dist.get("psf/requests", 0) > 0, str(dict(dist)))
    check("psf/requests reaches at least its quota", dist.get("psf/requests", 0) >= quota.get("psf/requests", 0))
    check("every quota'd repo appears", all(dist.get(r, 0) > 0 for r in quota), str(dict(dist)))
    check("cap respected", len(order) == 40, str(len(order)))
    check("order is deterministic", [r["id"] for r in P.screening_order(inv, quota, 40)] ==
          [r["id"] for r in order])


def test_quota_sums():
    print("\n[E2] quotas sum exactly and honour the floor")
    q = P.repo_quota({"a": 67, "b": 48, "c": 13, "d": 1}, 24)
    check("sums to target", sum(q.values()) == 24, str(q))
    check("small repo keeps a slot", q.get("c", 0) >= 2, str(q))
    check("single-task repo not over-allocated", q.get("d", 0) <= 1, str(q))
    q2 = P.repo_quota({"only": 5}, 24)
    check("single repo cannot exceed its pool", q2["only"] <= 24, str(q2))


def _arm(exit_code, nodes, **kw):
    d = {"pytest_exit": exit_code, "nodes": nodes, "import_in_checkout": True,
         "patch_rc": 0, "test_patch_rc": 0, "collection_error": False}
    d.update(kw)
    return d


def test_exit_codes_enforced():
    print("\n[E3] pytest exit codes are enforced, not merely recorded")
    base = _arm(1, {"t::a": "failed", "t::b": "passed"})
    ref = _arm(0, {"t::a": "passed", "t::b": "passed"})
    ok, reasons, target = P.classify(base, ref)
    check("clean pair is valid", ok, str(reasons))
    check("target node found", target == ["t::a"], str(target))

    ok2, r2, _ = P.classify(base, _arm(1, {"t::a": "passed", "t::b": "failed"}))
    check("nonzero reference exit rejected", not ok2 and any("reference" in x for x in r2), str(r2))

    ok3, r3, _ = P.classify(_arm(0, {"t::a": "passed"}), ref)
    check("baseline exit 0 rejected", not ok3 and any("baseline" in x and "exit" in x for x in r3), str(r3))

    ok4, r4, _ = P.classify(_arm(2, {"t::a": "failed"}), ref)
    check("interrupted baseline rejected", not ok4 and any("interrupt" in x for x in r4), str(r4))


def test_baseline_fixture_errors_rejected():
    print("\n[E4] a baseline mixing assertion failures with fixture errors is rejected")
    base = _arm(1, {"t::a": "failed", "t::b": "errored"})
    ref = _arm(0, {"t::a": "passed", "t::b": "passed"})
    ok, reasons, target = P.classify(base, ref)
    check("rejected despite a valid fail->pass node", not ok, str(reasons))
    check("reason names the JUnit errors", any("JUnit errors" in x for x in reasons), str(reasons))


def test_missing_patch_rc_rejected():
    print("\n[E5] missing or nonzero patch return codes are rejected")
    ref = _arm(0, {"t::a": "passed"})
    ok, r, _ = P.classify(_arm(1, {"t::a": "failed"}, patch_rc=None), ref)
    check("missing baseline patch rc rejected", not ok and any("missing patch" in x for x in r), str(r))
    ok2, r2, _ = P.classify(_arm(1, {"t::a": "failed"}), _arm(0, {"t::a": "passed"}, test_patch_rc=1))
    check("nonzero verification patch rc rejected", not ok2, str(r2))


def test_many_target_nodes_preserved():
    print("\n[E6] more than 12 target nodes are preserved, not truncated")
    n = 37
    base = _arm(1, {f"t::n{i}": "failed" for i in range(n)})
    ref = _arm(0, {f"t::n{i}": "passed" for i in range(n)})
    ok, reasons, target = P.classify(base, ref)
    check("valid", ok, str(reasons))
    check(f"all {n} target nodes returned", len(target) == n, str(len(target)))


def test_allocation_fills_both():
    print("\n[E7] both capacities fill, strata respected, studied tasks barred from held-out")
    rows = []
    for repo in ("fastapi/fastapi", "Textualize/rich", "psf/requests"):
        for i in range(8):
            rows.append({"id": f"{repo.split('/')[-1]}_{i}", "repo": repo,
                         "size": ["small", "medium", "large"][i % 3]})
    studied = {"fastapi_0", "rich_0", "requests_0"}
    dev, hold, short = P.allocate(rows, 12, 12, studied=studied)
    check("dev filled exactly", len(dev) == 12, str(len(dev)))
    check("held-out filled exactly", len(hold) == 12, str(len(hold)))
    check("no overlap", not (set(dev) & set(hold)))
    check("no studied task in held-out", not (set(hold) & studied), str(set(hold) & studied))
    check("studied tasks still usable for dev", bool(set(dev) & studied), str(dev))
    check("no shortfall reported", short["dev_short"] == 0 and short["holdout_short"] == 0, str(short))
    check("held-out spans repositories", len({h.split("_")[0] for h in hold}) >= 2, str(hold))


def test_allocation_uneven_strata():
    print("\n[E8] uneven strata: shortfall is reported, usable tasks are not discarded")
    rows = [{"id": f"rich_{i}", "repo": "Textualize/rich", "size": "small"} for i in range(5)]
    dev, hold, short = P.allocate(rows, 12, 12, studied=set())
    check("all five allocated", len(dev) + len(hold) == 5, f"dev={dev} hold={hold}")
    check("shortfall reported honestly", short["dev_short"] + short["holdout_short"] == 19, str(short))
    check("nothing left unused", short["unused_valid"] == 0, str(short))

    rows2 = [{"id": f"x_{i}", "repo": "r", "size": "small"} for i in range(4)]
    dev2, hold2, s2 = P.allocate(rows2, 2, 2, studied={"x_0", "x_1", "x_2"})
    check("only one held-out eligible task used", len(hold2) == 1, str(hold2))
    check("studied tasks fall through to dev", len(dev2) == 2, str(dev2))



def test_run2_degenerate_split_regression():
    print("\n[E9] run 2 regression: a pool smaller than both capacities is SHARED, not hogged")
    # Run 2 produced 20 valid tasks (rich 13, fastapi 5, requests 2); the repo quota capped rich at 9,
    # leaving a pool of 16 for capacities dev=12 / holdout=12. The old allocate() filled held-out to
    # 12 and handed development the 4 leftovers -- all from one repository. That split was unusable.
    rows, bands = [], ["small", "medium", "large"]
    for repo, n in (("Textualize/rich", 13), ("fastapi/fastapi", 5), ("psf/requests", 2)):
        for i in range(n):
            rows.append({"id": f"{repo.split('/')[-1]}_{i}", "repo": repo, "size": bands[i % 3]})
    quota = {"Textualize/rich": 9, "fastapi/fastapi": 5, "psf/requests": 2}
    dev, hold, short = P.allocate(rows, 12, 12, studied=set(), quota=quota)
    print("    pool_after_quota:", short["pool_after_quota"],
          " dev:", len(dev), " holdout:", len(hold))
    print("    dev_per_repo:", short["dev_per_repo"])
    print("    holdout_per_repo:", short["holdout_per_repo"])
    check("quota still caps the pool at 16", short["pool_after_quota"] == 16, str(short))
    check("whole pool is allocated", len(dev) + len(hold) == 16, f"dev={len(dev)} hold={len(hold)}")
    check("development is NOT starved (>=6, was 4)", len(dev) >= 6, str(len(dev)))
    check("shortfall is shared, not dumped on one set",
          abs(len(dev) - len(hold)) <= 1, f"dev={len(dev)} hold={len(hold)}")
    check("development spans more than one repository",
          len(short["dev_per_repo"]) >= 2, str(short["dev_per_repo"]))
    check("held-out spans more than one repository",
          len(short["holdout_per_repo"]) >= 2, str(short["holdout_per_repo"]))
    check("no overlap", not (set(dev) & set(hold)))
    check("quota respected", short["quota_respected"], str(short["selected_per_repo"]))
    check("nothing usable discarded", short["unused_valid"] == 0, str(short))


def test_holdout_spill_to_dev():
    print("\n[E10] held-out slots that cannot be filled spill to development, not to waste")
    rows = [{"id": f"r_{i}", "repo": "Textualize/rich", "size": "small"} for i in range(10)]
    studied = {f"r_{i}" for i in range(8)}          # only r_8, r_9 may be held out
    dev, hold, short = P.allocate(rows, 6, 6, studied=studied)
    check("held-out limited by eligibility", len(hold) == 2, str(hold))
    check("development absorbs the spill up to its capacity", len(dev) == 6, str(len(dev)))
    check("no studied task in held-out", not (set(hold) & studied), str(hold))
    check("targets reported for audit",
          short["target_dev"] + short["target_holdout"] == 10, str(short))


def main() -> int:
    for fn in (test_requests_included, test_quota_sums, test_exit_codes_enforced,
               test_baseline_fixture_errors_rejected, test_missing_patch_rc_rejected,
               test_many_target_nodes_preserved, test_allocation_fills_both,
               test_allocation_uneven_strata, test_run2_degenerate_split_regression,
               test_holdout_spill_to_dev):
        fn()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
