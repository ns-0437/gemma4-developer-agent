"""Fetch the official vLLM 0.19.1 sdist, verify it, and extract ONLY the parser files.

Deliberately avoids pip. `pip download --no-binary :all:` runs the project's own metadata preparation,
which for vLLM means executing setup.py and resolving a CUDA toolchain. The archive is fetched straight
from the release URL in PyPI's JSON metadata and its SHA-256 is checked against that metadata before
anything is opened.

Extraction is allow-listed by path prefix and every member is checked to resolve inside the
destination, so a crafted archive path cannot escape. Nothing is installed and nothing is executed
from the archive.

Run:
  python scripts/fetch_vllm_parser_source.py            # download, verify, extract, record
  python scripts/fetch_vllm_parser_source.py --list     # list matching members only, extract nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "reference" / "vllm_0.19.1_src"
SCRATCH = Path(os.environ.get("CLAUDE_SCRATCH", "")) if os.environ.get("CLAUDE_SCRATCH") else None
CACHE = (SCRATCH or Path(os.environ.get("TEMP", "/tmp"))) / "vllm-0.19.1.tar.gz"

METADATA_URL = "https://pypi.org/pypi/vllm/0.19.1/json"

# Only what the investigation needs. Everything else in a 30 MB archive stays unread.
# Paths confirmed by listing the archive first: in 0.19.1 the tool parsers live at
# vllm/tool_parsers/, not the vllm/entrypoints/openai/tool_parsers/ of older releases.
WANTED_PREFIXES = (
    "vllm/tool_parsers/",
    "vllm/entrypoints/openai/chat_completion/",
    "vllm/entrypoints/openai/cli_args.py",
    "vllm/entrypoints/chat_utils.py",
    "vllm/reasoning/gemma4",
    "vllm/reasoning/abs_reasoning_parsers.py",
    "vllm/reasoning/__init__.py",
    "vllm/version.py",
    "examples/tool_chat_template_gemma4.jinja",
    "tests/tool_parsers/test_gemma4_tool_parser.py",
    "tests/tool_parsers/common_tests.py",
    "tests/tool_parsers/conftest.py",
    "tests/reasoning/test_gemma4_reasoning_parser.py",
    "PKG-INFO",
)


def fetch_metadata() -> dict:
    with urllib.request.urlopen(METADATA_URL, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def sdist_record(meta: dict) -> dict:
    for u in meta["urls"]:
        if u["packagetype"] == "sdist":
            return u
    raise SystemExit("no sdist in the 0.19.1 metadata")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}\n         -> {dest}")
    with urllib.request.urlopen(url, timeout=600) as r, dest.open("wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            print(f"\r  {total/1e6:7.1f} MB", end="", flush=True)
    print()


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_members(tf: tarfile.TarFile, dest: Path):
    """Yield allow-listed regular-file members whose resolved path stays inside dest."""
    dest_res = dest.resolve()
    for m in tf.getmembers():
        # strip the single top-level "vllm-0.19.1/" component the sdist uses
        parts = m.name.split("/", 1)
        rel = parts[1] if len(parts) == 2 else parts[0]
        if not rel or not rel.startswith(WANTED_PREFIXES):
            continue
        if not m.isfile():
            print(f"  SKIP non-regular member: {m.name} (type {m.type!r})")
            continue
        if m.issym() or m.islnk():
            print(f"  SKIP link member: {m.name}")
            continue
        target = (dest_res / rel).resolve()
        if not str(target).startswith(str(dest_res) + os.sep):
            print(f"  REFUSED path escape: {m.name} -> {target}")
            continue
        yield m, rel, target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list matching members, extract nothing")
    args = ap.parse_args()

    meta = fetch_metadata()
    rec = sdist_record(meta)
    print(f"PyPI metadata : {METADATA_URL}")
    print(f"  version     : {meta['info']['version']}")
    print(f"  filename    : {rec['filename']}")
    print(f"  size        : {rec['size']} bytes")
    print(f"  sha256      : {rec['digests']['sha256']}")
    print(f"  uploaded    : {rec['upload_time_iso_8601']}")
    print(f"  url         : {rec['url']}")

    if not CACHE.exists() or CACHE.stat().st_size != rec["size"]:
        download(rec["url"], CACHE)
    else:
        print(f"using cached archive {CACHE}")

    got = sha256_of(CACHE)
    ok = got == rec["digests"]["sha256"]
    print(f"\nSHA-256 check : {'MATCH' if ok else 'MISMATCH'}")
    print(f"  expected    : {rec['digests']['sha256']}")
    print(f"  computed    : {got}")
    if not ok:
        print("Refusing to open an archive that does not match its published digest.")
        return 3

    with tarfile.open(CACHE, "r:gz") as tf:
        selected = list(safe_members(tf, DEST))
        print(f"\n{len(selected)} allow-listed members")
        for _m, rel, _t in selected:
            print("   ", rel)
        if args.list:
            return 0
        DEST.mkdir(parents=True, exist_ok=True)
        extracted = {}
        for m, rel, target in selected:
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            if src is None:
                print(f"  SKIP unreadable {rel}")
                continue
            data = src.read()
            target.write_bytes(data)
            extracted[rel] = {"bytes": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()}

    provenance = {
        "recorded": "2026-09-30",
        "metadata_url": METADATA_URL,
        "distribution": rec["filename"],
        "packagetype": rec["packagetype"],
        "release_url": rec["url"],
        "published_size": rec["size"],
        "published_sha256": rec["digests"]["sha256"],
        "computed_sha256": got,
        "digest_verified": ok,
        "upload_time": rec["upload_time_iso_8601"],
        "requires_python": meta["info"].get("requires_python"),
        "installed": False,
        "extraction": "allow-listed prefixes only; members checked to resolve inside the destination",
        "files": extracted,
        "caveat": (
            "This is the UPSTREAM PyPI release. The evaluation ran a wheel installed from the host's "
            "Kaggle dataset metric/gemma-4-developer-agent-wheelhouse with pip --no-deps "
            "--force-reinstall, and that wheel is not available here. Its distribution metadata "
            "reports 0.19.1, but byte equivalence with this upstream release is NOT established."
        ),
    }
    (DEST / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"\nextracted {len(extracted)} files to {DEST}")
    print(f"provenance written to {DEST / 'PROVENANCE.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
