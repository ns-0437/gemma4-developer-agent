"""Refuse to overwrite experiment artifacts once a launch has been recorded."""
from pathlib import Path


def require_unlaunched(record_dir):
    record = Path(record_dir) / "LAUNCH_RECORD.json"
    # Existence is enough: a malformed receipt must not permit overwriting evidence.
    if record.exists():
        raise RuntimeError(f"Refusing to overwrite launched experiment: {record}. "
                           "Use a fresh versioned output directory and preserve the receipt.")
