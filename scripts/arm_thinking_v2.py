"""Smallest explicit arming step for the authorized thinking_v2 four-run comparison.

The generator is preparation-only and refuses arming, so this performs exactly one
substitution, DISPATCH_CONFIRM False -> True, and then proves that nothing else moved:
every other cell source, the notebook metadata, the run order and both embedded candidate
payloads are compared structurally against the preserved disabled notebook.

Writes the armed notebook and prints its sha256. Pushes nothing.

    python scripts/arm_thinking_v2.py
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "notebooks/thinking_v2/thinking_v2.ipynb"
PRESERVED = ROOT / "experiments/thinking_v2/thinking_v2_disabled.ipynb"
DISABLED_SHA = "93dc58362ac07d7cf9554f2c164b752cf52f9de89e003a78896f3407ebca8061"
CANDIDATES = {
    "OFF": "640fadab5b5b638a7e8a31abb26fcecb6b2e139929d77cdb6691f2d832ca2ec1",
    "ON": "527acc5403d21a149ecea9d39d573d3d0f45dc65935d115952b772045339ea33",
}
OFF_LINE, ON_LINE = "DISPATCH_CONFIRM = False", "DISPATCH_CONFIRM = True"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def payload_hashes(src: str) -> set[str]:
    out = set()
    for blob in re.findall(r"['\"]([A-Za-z0-9+/=]{500,})['\"]", src):
        try:
            out.add(sha(base64.b64decode(blob)))
        except Exception:
            continue
    return out


def sources(nb: dict) -> list[str]:
    return ["".join(c["source"]) for c in nb["cells"]]


def main() -> None:
    global LIVE, PRESERVED
    if len(sys.argv) == 2:
        # Arm a finalized copy in its own directory; the preserved baseline stays beside it.
        LIVE = Path(sys.argv[1]).resolve()
        PRESERVED = LIVE.with_name(LIVE.stem + "_disabled" + LIVE.suffix)
    else:
        assert len(sys.argv) == 1, "pass at most one notebook path"

    # 1. Preserve the verified disabled notebook before touching anything.
    raw_disabled = LIVE.read_bytes()
    got = sha(raw_disabled)
    assert got == DISABLED_SHA, f"live notebook is not the verified disabled artifact: {got}"
    if PRESERVED.exists():
        assert sha(PRESERVED.read_bytes()) == DISABLED_SHA, "preserved copy differs; refusing"
    else:
        shutil.copy2(LIVE, PRESERVED)
    assert sha(PRESERVED.read_bytes()) == DISABLED_SHA

    # 2. Exactly one dispatch flag, currently disabled.
    assert raw_disabled.count(OFF_LINE.encode()) == 1, "expected exactly one disabled flag"
    assert ON_LINE.encode() not in raw_disabled, "an armed flag is already present"

    raw_armed = raw_disabled.replace(OFF_LINE.encode(), ON_LINE.encode(), 1)
    assert raw_armed.count(ON_LINE.encode()) == 1
    assert OFF_LINE.encode() not in raw_armed

    # 3. Prove the substitution is the only difference.
    nb_d, nb_a = json.loads(raw_disabled), json.loads(raw_armed)
    src_d, src_a = sources(nb_d), sources(nb_a)
    assert len(src_d) == len(src_a), "cell count changed"
    changed = [i for i, (a, b) in enumerate(zip(src_d, src_a)) if a != b]
    assert len(changed) == 1, f"expected one changed cell, got {changed}"
    idx = changed[0]
    assert src_d[idx].replace(OFF_LINE, ON_LINE, 1) == src_a[idx], "unexpected edit in that cell"

    skeleton_d, skeleton_a = copy.deepcopy(nb_d), copy.deepcopy(nb_a)
    for nb in (skeleton_d, skeleton_a):
        for c in nb["cells"]:
            c["source"] = []
    assert skeleton_d == skeleton_a, "notebook metadata or cell structure changed"

    assert payload_hashes(src_d[idx]) == payload_hashes(src_a[idx])
    all_d, all_a = payload_hashes("\n".join(src_d)), payload_hashes("\n".join(src_a))
    assert all_d == all_a == set(CANDIDATES.values()), "embedded candidate payloads changed"

    order_re = r"ORDER\s*=\s*\[[^\]]*\]"
    assert re.search(order_re, "\n".join(src_d)).group(0) == \
        re.search(order_re, "\n".join(src_a)).group(0), "run order changed"

    LIVE.write_bytes(raw_armed)
    armed = sha(raw_armed)
    print(f"preserved disabled : {PRESERVED.relative_to(ROOT)}  {DISABLED_SHA}")
    print(f"armed cell index   : {idx}")
    print(f"byte delta         : {len(raw_armed) - len(raw_disabled)} (False -> True)")
    print(f"embedded payloads  : unchanged, {len(all_a)} candidates")
    print(f"ARMED sha256       : {armed}")


if __name__ == "__main__":
    main()
