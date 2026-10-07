"""Prepare the CPU-only environment probe. Reuses the comparison's own setup code verbatim.

Authorized scope: request the recorded Python 3.12 image digest, report the interpreter and wheel
tag compatibility, then run the EXISTING wheelhouse install and verify required imports plus the
compiler version and per-file hashes. No GPU, no model startup, no agent evaluation, no submission.

The install cell and the compiler-identity gate are lifted byte-for-byte out of the preserved
disabled comparison notebook, so no dependency is substituted, no required wheel is skipped and no
check is relaxed. Diagnostics are written before each risky step so they survive a failure.

    python scripts/prepare_env_probe.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "experiments/thinking_v2/thinking_v2_disabled.ipynb"
SRC_SHA = "93dc58362ac07d7cf9554f2c164b752cf52f9de89e003a78896f3407ebca8061"
OUT_DIR = ROOT / "experiments/env_probe_v1"
OUT_NB = OUT_DIR / "env_probe.ipynb"
IMAGE = ("gcr.io/kaggle-private-byod/python@sha256:"
         "37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461")

HEADER = f"""# CPU-only environment probe

Requests the exact image digest the 2026-10-03 verification run used:

    {IMAGE}

Reports the interpreter and wheel-tag compatibility, then runs the comparison's own wheelhouse
install and verifies required imports and the compiler version plus per-file hashes.

**No GPU, model startup, agent evaluation or submission.** A pass establishes environment
compatibility only: it says nothing about vLLM operation on GPU or about candidate performance.
The four-run comparison and the frozen candidates are untouched by this probe.
"""

CONFIG = f'''# ============================ CONFIG ============================
EXPECTED_IMAGE = "{IMAGE}"
EXPECTED_PYTHON = (3, 12)      # observed on the successful run; verified below, never assumed
from pathlib import Path
WORKING_DIR = Path("/kaggle/working")
RESULTS = WORKING_DIR / "pilot"; RESULTS.mkdir(parents=True, exist_ok=True)
print("probe: CPU only, no GPU or model startup")
'''

PREFLIGHT = '''# Step 2 and 3: interpreter, platform, supported tags, and compatibility of EVERY wheelhouse file.
# Written to disk BEFORE the install so it survives an install failure.
import json, platform, sys, sysconfig
from pathlib import Path

probe = {
    "sys_version": sys.version,
    "sys_version_info": list(sys.version_info[:3]),
    "sys_executable": sys.executable,
    "platform": platform.platform(),
    "machine": platform.machine(),
    "python_implementation": platform.python_implementation(),
    "sysconfig_platform": sysconfig.get_platform(),
    "expected_image": EXPECTED_IMAGE,
    "expected_python": list(EXPECTED_PYTHON),
}
print("python     :", probe["sys_version_info"], probe["sys_executable"])
print("platform   :", probe["platform"], "|", probe["sysconfig_platform"])
probe["image_python_as_expected"] = tuple(sys.version_info[:2]) == EXPECTED_PYTHON
print("python matches the recorded successful run:", probe["image_python_as_expected"])

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
supported = [str(t) for t in sys_tags()]
probe["supported_tag_count"] = len(supported)
probe["supported_tags_sample"] = supported[:25]
print("supported tags:", len(supported), "e.g.", supported[:5])

WH = Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse")
probe["wheelhouse_dir"] = str(WH)
probe["wheelhouse_present"] = WH.is_dir()
files = sorted(p.name for p in WH.iterdir() if p.is_file()) if WH.is_dir() else []
wheels = [f for f in files if f.endswith(".whl")]
probe["file_count"] = len(files)
probe["wheel_count"] = len(wheels)
probe["non_wheel_files"] = [f for f in files if not f.endswith(".whl")]

sup = set(supported)
compatible, incompatible = [], []
for n in wheels:
    try:
        _, _, _, tags = parse_wheel_filename(n)
    except Exception as exc:
        incompatible.append({"wheel": n, "reason": f"unparsable: {exc}", "wheel_tags": []})
        continue
    tl = sorted(str(t) for t in tags)
    if any(t in sup for t in tl):
        compatible.append({"wheel": n})
    else:
        incompatible.append({"wheel": n, "reason": "no tag matches this interpreter",
                             "wheel_tags": tl[:6]})
probe["compatible_count"] = len(compatible)
probe["incompatible"] = incompatible
probe["all_wheels_compatible"] = (len(wheels) > 0 and not incompatible)

print(f"wheels: {len(wheels)} total, {len(compatible)} compatible, {len(incompatible)} incompatible")
for w in incompatible:
    print("   INCOMPATIBLE:", w["wheel"], "|", w.get("reason"), "|", w.get("wheel_tags"))

(RESULTS / "env_probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
print("saved", RESULTS / "env_probe.json")
PROBE = probe
'''

GATE = '''# Step 4 gate: only attempt the install when every wheel is compatible. No wheel is ever skipped.
if not PROBE["wheelhouse_present"]:
    raise SystemExit("wheelhouse dataset not mounted; diagnostics saved")
if not PROBE["all_wheels_compatible"]:
    raise SystemExit(f"{len(PROBE['incompatible'])} incompatible wheel(s) for this interpreter; "
                     "diagnostics saved, install not attempted, nothing substituted or skipped")
print("all wheelhouse wheels are tag-compatible; running the existing install")
'''

VERIFY = '''# Step 4 continued: required imports and compiler identity. Reuses the comparison's own gate.
import importlib, importlib.metadata as md, json, traceback
report = {"versions": VERSIONS, "imports": {}, "compiler": None}
REQUIRED = ["swegemma", "adk_submission", "adk_eval_core", "google.adk", "vllm",
            "transformers", "litellm", "packaging"]
for mod in REQUIRED:
    try:
        importlib.import_module(mod)
        report["imports"][mod] = "ok"
    except Exception as exc:
        report["imports"][mod] = f"FAILED: {type(exc).__name__}: {exc}"
print(json.dumps(report["imports"], indent=2))
(RESULTS / "probe_imports.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

failed = {k: v for k, v in report["imports"].items() if v != "ok"}
if failed:
    raise SystemExit(f"required imports failed: {sorted(failed)}; diagnostics saved")

try:
    verify_runtime_compiler()
    report["compiler"] = "version and per-file hashes match 0.2.12"
    print("compiler identity: PASS (version 0.2.12 and per-file hashes)")
except AssertionError as exc:
    report["compiler"] = f"FAILED: {exc}"
    (RESULTS / "probe_imports.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise
(RESULTS / "probe_imports.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("PROBE PASS: environment compatibility only. GPU/vLLM operation and candidate performance "
      "are NOT established by this probe.")
'''


def main() -> None:
    assert len(sys.argv) == 1, "Preparation only"
    raw = SRC.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SRC_SHA, "source is not the preserved disabled notebook"
    nb = json.loads(raw)
    srcs = ["".join(c["source"]) for c in nb["cells"]]

    install = srcs[2]
    assert "installing" in install and "wheelhouse install failed" in install, "install cell moved"

    c7 = srcs[7]
    a = c7.index("EXPECTED_COMPILER_FILES")
    b = c7.index("verify_runtime_compiler()", c7.index("def verify_runtime_compiler"))
    compiler_block = c7[a:b]          # definition only; the probe calls it from VERIFY
    assert "def verify_runtime_compiler" in compiler_block
    assert "RESULTS" in compiler_block

    def code(text: str) -> dict:
        return {"cell_type": "code", "execution_count": None, "metadata": {},
                "outputs": [], "source": text.splitlines(keepends=True)}

    cells = [
        {"cell_type": "markdown", "metadata": {}, "source": HEADER.splitlines(keepends=True)},
        code(CONFIG),
        code(PREFLIGHT),
        code(GATE),
        code(install),                                     # verbatim from the comparison
        code("# Compiler-identity gate, lifted verbatim from the comparison notebook.\n"
             "import hashlib, json\nfrom pathlib import Path\n" + compiler_block),
        code(VERIFY),
    ]
    out = {k: v for k, v in nb.items() if k != "cells"}
    out["cells"] = cells

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    OUT_NB.write_text(text, encoding="utf-8")

    meta = json.loads((ROOT / "notebooks/thinking_v2/kernel-metadata.json").read_text())
    meta.update({"id": "navin03/gemma4-env-probe", "title": "gemma4-env-probe",
                 "code_file": OUT_NB.name, "docker_image": IMAGE,
                 "enable_gpu": False, "enable_tpu": False, "enable_internet": False})
    meta.pop("machine_shape", None)
    (OUT_DIR / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    sha = hashlib.sha256(OUT_NB.read_bytes()).hexdigest()
    assert "DISPATCH_CONFIRM" not in text, "probe must carry no dispatch flag"
    assert "evaluate" not in text.lower() or "agent evaluation" in text
    print(f"reused verbatim: install cell (cell 2), compiler gate ({len(compiler_block)} chars from cell 7)")
    print(f"prepared: {OUT_NB.relative_to(ROOT)}")
    print(f"cells: {len(cells)} | enable_gpu: False | sha256: {sha}")


if __name__ == "__main__":
    main()
