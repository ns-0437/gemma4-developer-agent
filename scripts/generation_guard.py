"""Refuse to overwrite experiment artifacts once a launch has been recorded."""
from pathlib import Path


def require_unlaunched(record_dir):
    root = Path(record_dir)
    # Versioned receipts also protect a directory. Do not parse them: incomplete
    # or malformed launch evidence must never permit an overwrite.
    receipts = sorted(p for p in root.glob('LAUNCH_RECORD*.json')
                      if p.name == 'LAUNCH_RECORD.json' or p.name.startswith('LAUNCH_RECORD_'))
    if receipts:
        raise RuntimeError(f"Refusing to overwrite launched experiment: {receipts[0]}. "
                           "Use a fresh versioned output directory and preserve the receipt.")
