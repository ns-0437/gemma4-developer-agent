"""Generate notebooks/submit/ (a Kaggle notebook that writes /kaggle/working/submission.zip) from submission/.

Submissions to this competition are made from a notebook's output, so the notebook just embeds every
file of submission/ and zips them. Text files only; LoRA adapters must come from an attached Kaggle
dataset instead (see ADAPTER_DATASET below) because they are too big to inline.

Usage:
  python scripts/make_submit_notebook.py --version v1 --note "coder+analyzer, default budgets"
  kaggle kernels push -p notebooks/submit
  (wait for the run to finish, then submit its output with `kaggle competitions submit`)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import zipfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "submission"
OUT = ROOT / "notebooks" / "submit"
KERNEL_ID = "navin03/gemma4-swe-agent-submit"
TEXT_EXT = {".yaml", ".yml", ".md", ".txt", ".py", ".json"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--source", default=str(SUB), help="dir to package (e.g. releases/v2); default submission/")
    a = ap.parse_args()

    files = {}
    src = Path(a.source).resolve()
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in TEXT_EXT:
            raise SystemExit(f"non-text file {p}; ship adapters via an attached dataset instead")
        files[p.relative_to(src).as_posix()] = p.read_bytes()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    code = f'''# Generated frozen archive: preserves exact bytes across Python/zlib platforms.
import base64, hashlib, io, zipfile
from pathlib import Path
payload = base64.b64decode({base64.b64encode(payload).decode("ascii")!r}, validate=True)
assert hashlib.sha256(payload).hexdigest() == {digest!r}
with zipfile.ZipFile(io.BytesIO(payload)) as z:
    assert "agent.yaml" in z.namelist()
    assert z.testzip() is None
out = Path("/kaggle/working/submission.zip")
out.write_bytes(payload)
print("sha256", hashlib.sha256(out.read_bytes()).hexdigest())
'''
    nb = {
        "cells": [
            {"cell_type": "markdown", "metadata": {},
             "source": [f"# Gemma 4 SWE agent — submission {a.version}\n\n{a.note}\n"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
             "source": code.splitlines(keepends=True)},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 4,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "submit.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    meta = {
        "id": KERNEL_ID,
        "title": "gemma4-swe-agent-submit",
        "code_file": "submit.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": False,
        "dataset_sources": [],
        "competition_sources": ["gemma-4-developer-agent"],
        "kernel_sources": [],
        "model_sources": [],
    }
    (OUT / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {OUT} with {len(files)} files: {', '.join(files)}")


if __name__ == "__main__":
    main()
