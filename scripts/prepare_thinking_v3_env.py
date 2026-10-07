"""Prepare the environment repair for the thinking comparison. Disabled; never pushes or arms.

Takes the preserved disabled thinking_v2 notebook as input, leaves it untouched, and writes a
separate preparation directory containing:

  * the same notebook with one inserted preflight cell before the wheelhouse install,
  * a kernel-metadata.json pinning docker_image to the digest of the image the 2026-10-03
    verification run actually used,
  * ENV_EVIDENCE.json recording both observed image digests.

The preflight records sys.version, sys.executable, platform and per-wheel tag compatibility and
prints it. It deliberately does NOT abort, skip wheels or relax any later check: the existing
install gate and the compiler/candidate gates are left exactly as they are.

    python scripts/prepare_thinking_v3_env.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "experiments/thinking_v2/thinking_v2_disabled.ipynb"
SRC_SHA = "93dc58362ac07d7cf9554f2c164b752cf52f9de89e003a78896f3407ebca8061"
OUT_DIR = ROOT / "experiments/thinking_v3_env"
OUT_NB = OUT_DIR / "thinking_v3_env_disabled.ipynb"

# Observed, from read-only `kaggle kernels pull -m` on each kernel.
IMAGE_OK = ("gcr.io/kaggle-private-byod/python@sha256:"
            "37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461")
IMAGE_BAD = ("gcr.io/kaggle-private-byod/python@sha256:"
             "2757e0c7d1e0a9cb43da657b97e223c321a98f5014bdf64f44f2f6b083ad2b2f")

PREFLIGHT = '''# Setup preflight. Records the interpreter and per-wheel tag compatibility BEFORE installing.
# It only reports: it does not abort, skip wheels, or relax any later gate.
import json, platform, sys, sysconfig
from pathlib import Path

PREFLIGHT = {
    "sys_version": sys.version,
    "sys_version_info": list(sys.version_info[:3]),
    "sys_executable": sys.executable,
    "platform": platform.platform(),
    "machine": platform.machine(),
    "python_implementation": platform.python_implementation(),
    "sysconfig_platform": sysconfig.get_platform(),
    "expected_image_digest": EXPECTED_IMAGE_DIGEST,
}
print("preflight interpreter:", PREFLIGHT["sys_version_info"], PREFLIGHT["sys_executable"])
print("preflight platform   :", PREFLIGHT["platform"], "|", PREFLIGHT["sysconfig_platform"])

_WH = Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse")
_names = sorted(w.name for w in _WH.glob("*.whl")) if _WH.is_dir() else []
PREFLIGHT["wheelhouse_present"] = _WH.is_dir()
PREFLIGHT["wheel_count"] = len(_names)

try:
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    _supported = {str(t) for t in sys_tags()}
    _incompatible = []
    for _n in _names:
        try:
            _, _, _, _tags = parse_wheel_filename(_n)
        except Exception as _exc:
            _incompatible.append({"wheel": _n, "reason": f"unparsable: {_exc}"})
            continue
        if not any(str(_t) in _supported for _t in _tags):
            _incompatible.append({"wheel": _n, "reason": "no tag matches this interpreter",
                                  "wheel_tags": sorted(str(_t) for _t in _tags)[:6]})
    PREFLIGHT["tag_check"] = "ran"
    PREFLIGHT["incompatible_wheels"] = _incompatible
except Exception as _exc:
    PREFLIGHT["tag_check"] = f"unavailable: {_exc}"
    PREFLIGHT["incompatible_wheels"] = None

if PREFLIGHT.get("incompatible_wheels"):
    print(f"preflight WARNING: {len(PREFLIGHT['incompatible_wheels'])} wheel(s) have no tag "
          f"matching this interpreter; the install gate below still decides:")
    for _w in PREFLIGHT["incompatible_wheels"]:
        print("   ", _w["wheel"], "|", _w["reason"])
elif PREFLIGHT["incompatible_wheels"] == []:
    print(f"preflight: all {PREFLIGHT['wheel_count']} wheels have a tag matching this interpreter")

if PREFLIGHT["sys_version_info"][:2] != EXPECTED_PYTHON:
    print(f"preflight WARNING: interpreter {PREFLIGHT['sys_version_info'][:2]} != expected "
          f"{EXPECTED_PYTHON}; the pinned image may not have been honoured")

Path("/kaggle/working").mkdir(parents=True, exist_ok=True)
Path("/kaggle/working/preflight.json").write_text(json.dumps(PREFLIGHT, indent=2), encoding="utf-8")
print("preflight written to /kaggle/working/preflight.json")
'''

HEADER = f'''# Environment repair for the thinking comparison. DISABLED preparation; nothing is armed.
# The 2026-10-03 verification run ran on image digest
#   {IMAGE_OK.split("sha256:")[1]}
# and installed all wheels. The 2026-10-06 thinking_v2 run ran on
#   {IMAGE_BAD.split("sha256:")[1]}
# under Python 3.13, where a cp312-only wheel could not install and no evaluation was attempted.
# kernel-metadata.json in this directory pins docker_image to the first digest. Availability of
# that digest cannot be confirmed by any read-only call and is the remaining blocker.
EXPECTED_IMAGE_DIGEST = "{IMAGE_OK}"
EXPECTED_PYTHON = [3, 12]   # observed on the successful run; the preflight verifies, never assumes
'''


def main() -> None:
    assert len(sys.argv) == 1, "Preparation only; arming requires a reviewed launch step"
    raw = SRC.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    assert got == SRC_SHA, f"source is not the preserved disabled notebook: {got}"

    nb = json.loads(raw)
    sources = ["".join(c["source"]) for c in nb["cells"]]
    install = [i for i, s in enumerate(sources) if "installing" in s and "wheels" in s]
    assert len(install) == 1, f"expected one wheelhouse install cell, found {install}"
    at = install[0]

    assert raw.count(b"DISPATCH_CONFIRM = False") == 1
    assert b"DISPATCH_CONFIRM = True" not in raw

    def cell(text: str) -> dict:
        return {"cell_type": "code", "execution_count": None, "metadata": {},
                "outputs": [], "source": text.splitlines(keepends=True)}

    nb["cells"] = nb["cells"][:at] + [cell(HEADER + "\n" + PREFLIGHT)] + nb["cells"][at:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = json.dumps(nb, indent=1, ensure_ascii=False) + "\n"
    OUT_NB.write_text(out, encoding="utf-8")
    nb_sha = hashlib.sha256(OUT_NB.read_bytes()).hexdigest()

    # Every original cell must survive byte-identically; only one cell is added.
    check = json.loads(OUT_NB.read_text(encoding="utf-8"))
    new_sources = ["".join(c["source"]) for c in check["cells"]]
    assert len(new_sources) == len(sources) + 1
    assert new_sources[:at] == sources[:at]
    assert new_sources[at + 1:] == sources[at:]
    assert out.count("DISPATCH_CONFIRM = False") == 1
    assert "DISPATCH_CONFIRM = True" not in out

    meta = json.loads((ROOT / "notebooks/thinking_v2/kernel-metadata.json").read_text())
    meta["id"] = "navin03/gemma4-swe-agent-thinking-v3-env"
    meta["title"] = "gemma4-swe-agent-thinking-v3-env"
    meta["code_file"] = OUT_NB.name
    meta["docker_image"] = IMAGE_OK
    (OUT_DIR / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    (OUT_DIR / "ENV_EVIDENCE.json").write_text(json.dumps({
        "source": "read-only `kaggle kernels pull -m` on each kernel",
        "verification_2026_10_03": {"kernel": "navin03/gemma4-swe-agent-verification",
                                    "docker_image": IMAGE_OK,
                                    "observed_interpreter": "python3.12 (from log dist-packages paths)",
                                    "wheel_install": "succeeded"},
        "thinking_v2_2026_10_06": {"kernel": "navin03/gemma4-swe-agent-thinking-v2",
                                   "docker_image": IMAGE_BAD,
                                   "observed_interpreter": "python3.13 (from log dist-packages paths)",
                                   "wheel_install": "failed: apache_tvm_ffi cp312 wheel unsupported"},
        "digests_differ": True,
        "docker_image_pinning_type": "absent from both kernels' metadata",
        "cli_mechanism": "kernel-metadata.json 'docker_image' is forwarded on push by the installed "
                         "Kaggle CLI; 'docker_image_pinning_type' accepts only 'original'/'latest' "
                         "and is a separate, coarser mechanism",
        "unverifiable": "whether the pinned digest is still pullable; no read-only call establishes it",
        "prepared_notebook_sha256": nb_sha,
        "dispatch": False,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"preflight inserted at cell index {at}; all original cells preserved")
    print(f"prepared (disabled): {OUT_NB.relative_to(ROOT)}")
    print(f"sha256: {nb_sha}")


if __name__ == "__main__":
    main()
