"""Offline pre-flight check for a submission dir, mirroring HARNESS_README.md section 2-3, then zip it.

Usage: python scripts/validate_and_zip.py [submission_dir] [--out submission.zip] [--no-zip]
This is a local approximation of adk-submission's validator, not the real thing; the real
compile happens on Kaggle. It catches the mistakes that would waste a daily submission.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import yaml

MODEL = "gemma-4-31b-it-qat-w4a16-ct"
ROOT_NAMES = ["agent.yaml", "agent.yml", "root_agent.yaml", "root_agent.yml"]
ALLOWED_EXT = {".yaml", ".yml", ".md", ".txt", ".py", ".json", ".safetensors"}
MAX_TOTAL = 3 * 1024**3
HARNESS_TOOLS = {
    "run_command", "submit_patch", "get_status", "read_file", "edit_file", "write_file",
    "get_code_neighbors", "search_similar_code", "get_code_subgraph",
}
GEN_FIELDS = {
    "temperature", "top_p", "top_k", "max_output_tokens", "presence_penalty", "frequency_penalty",
    "stop_sequences", "response_mime_type", "seed", "thinking_config",
}
THINK_LEVELS = {"MINIMAL", "LOW", "MEDIUM", "HIGH", "NONE"}
AGENT_CLASSES = {"LlmAgent", "SequentialAgent", "ParallelAgent", "LoopAgent"}

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def make_loader(root: Path, base: Path, depth: int):
    class L(yaml.SafeLoader):
        pass

    def include(loader, node):
        rel = loader.construct_scalar(node)
        if rel.startswith("/") or "\0" in rel:
            err(f"!include absolute path or null byte: {rel!r}")
            return ""
        # The official sample uses ../prompts from sub_agents/, so '..' that stays inside root is OK
        # locally; the README says '..' components are blocked, so we warn and prefer root-relative
        # layouts that don't need it.
        if ".." in Path(rel).parts:
            print(f"note: '..' in !include {rel} (from {base.name}/) - README says blocked, but the 0.12 LB notebook uses it fine")
        target = (base / rel).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            err(f"!include escapes submission root: {rel} (from {base})")
            return ""
        if not target.exists():
            err(f"!include target missing: {rel} (from {base})")
            return ""
        if target.suffix in (".md", ".txt"):
            return target.read_text(encoding="utf-8")
        if target.suffix in (".yaml", ".yml"):
            if depth >= 10:
                err(f"!include depth > 10 at {rel}")
                return None
            return load_yaml(root, target, depth + 1)
        err(f"!include of unsupported type: {rel}")
        return ""

    L.add_constructor("!include", include)
    return L


def load_yaml(root: Path, path: Path, depth: int = 0):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=make_loader(root, path.parent, depth))


def check_gen(cfg, where: str) -> None:
    if cfg is None:
        return
    for k in cfg:
        if k not in GEN_FIELDS:
            err(f"{where}: generate_content_config field not allowed: {k}")
    mot = cfg.get("max_output_tokens")
    if mot is not None and not (1 <= mot <= 32768):
        err(f"{where}: max_output_tokens {mot} out of 1..32768")
    tc = cfg.get("thinking_config") or {}
    tb = tc.get("thinking_budget")
    if tb is not None and not (1 <= tb <= 32768):
        err(f"{where}: thinking_budget {tb} out of 1..32768")
    lvl = tc.get("thinking_level")
    if lvl is not None and str(lvl).upper() not in THINK_LEVELS:
        err(f"{where}: bad thinking_level {lvl}")


def walk_agent(root: Path, cfg: dict, cfg_dir: Path, where: str, models: set, depth: int = 0) -> None:
    if not isinstance(cfg, dict):
        err(f"{where}: agent config is not a mapping")
        return
    cls = cfg.get("agent_class", "LlmAgent")
    if cls not in AGENT_CLASSES:
        err(f"{where}: unsupported agent_class {cls}")
    if "name" not in cfg:
        err(f"{where}: missing name")
    if cls == "LlmAgent":
        m = cfg.get("model")
        if m is None:
            err(f"{where}: LlmAgent without model")
        else:
            models.add(str(m).split("/")[-1])
        ad = cfg.get("adapter")
        if ad:
            d = root / "adapters" / ad
            if not (d / "adapter_config.json").exists() or not (d / "adapter_model.safetensors").exists():
                err(f"{where}: adapter '{ad}' missing adapter_config.json or adapter_model.safetensors")
        for s in cfg.get("skills") or []:
            sd = (cfg_dir / s).resolve()
            if not (sd / "SKILL.md").exists():
                err(f"{where}: skill dir {s} has no SKILL.md")
        check_gen(cfg.get("generate_content_config"), where)
    for t in cfg.get("tools") or []:
        if isinstance(t, str):
            if t not in HARNESS_TOOLS:
                err(f"{where}: unknown tool '{t}' (skill tools are attached via skills:, not tools:)")
        elif isinstance(t, dict) and "agent_tool" in t:
            sub_path = (cfg_dir / t["agent_tool"]["config_path"]).resolve()
            walk_file(root, sub_path, models, depth + 1)
        elif isinstance(t, dict):
            walk_agent(root, t, cfg_dir, f"{where}/inline", models, depth + 1)
    for sa in cfg.get("sub_agents") or []:
        if isinstance(sa, dict) and "config_path" in sa:
            walk_file(root, (cfg_dir / sa["config_path"]).resolve(), models, depth + 1)
        else:
            walk_agent(root, sa, cfg_dir, f"{where}/sub", models, depth + 1)


def walk_file(root: Path, path: Path, models: set, depth: int = 0) -> None:
    if depth > 50:
        err("sub-agent depth > 50")
        return
    if root.resolve() not in path.parents:
        err(f"config_path escapes root: {path}")
        return
    if not path.exists():
        err(f"config_path missing: {path}")
        return
    cfg = load_yaml(root, path)
    walk_agent(root, cfg, path.parent, str(path.relative_to(root.resolve())), models, depth)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission_dir", nargs="?", default="submission")
    ap.add_argument("--out", default="submission.zip")
    ap.add_argument("--no-zip", action="store_true")
    a = ap.parse_args()
    root = Path(a.submission_dir)

    roots = [n for n in ROOT_NAMES if (root / n).exists()]
    if len(roots) != 1:
        err(f"need exactly one root config, found {roots}")
    total, files = 0, []
    for p in root.rglob("*"):
        if p.is_symlink():
            err(f"symlink not allowed: {p}")
        if p.is_file():
            files.append(p)
            total += p.stat().st_size
            if p.suffix not in ALLOWED_EXT:
                err(f"disallowed file extension: {p.relative_to(root)}")
    if total >= MAX_TOTAL:
        err(f"total size {total/1e9:.2f} GB >= 3 GiB")
    if len(files) > 10000:
        err("more than 10,000 files")
    for sk in (root / "skills").glob("*") if (root / "skills").exists() else []:
        md = sk / "SKILL.md"
        if not md.exists() or "name:" not in md.read_text(encoding="utf-8").split("---")[1]:
            err(f"skill {sk.name}: SKILL.md missing or no 'name:' frontmatter")

    models: set = set()
    if roots:
        walk_file(root, (root / roots[0]).resolve(), models)
    if len(models) > 1:
        err(f"more than one base model declared: {models}")
    if models and models != {MODEL}:
        err(f"model must be {MODEL}, got {models}")

    if errors:
        print("INVALID:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: {len(files)} files, {total/1e6:.2f} MB, model={models}")
    if not a.no_zip:
        # Deterministic bytes (fixed timestamp, sorted names) so the Kaggle notebook's zip hash must match.
        with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(files, key=lambda f: f.relative_to(root).as_posix()):
                info = zipfile.ZipInfo(p.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, p.read_bytes())
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
