"""Read-only verification of a downloaded artifact tree against a saved SHA-256 inventory.

Usage: python scripts/verify_artifact_manifest.py ARTIFACTS MANIFEST.json
The manifest must contain a 'files' object mapping relative POSIX paths to hashes.
No downloads, repairs, model execution or output files are performed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate manifest key: ' + key)
        result[key] = value
    return result


def verify(artifacts, manifest):
    root = Path(artifacts).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('artifact root must be a directory')
    record = json.loads(Path(manifest).read_text(encoding='utf-8'), object_pairs_hook=_unique_pairs)
    expected = record.get('files') if isinstance(record, dict) else None
    if not isinstance(expected, dict) or not expected:
        raise ValueError('manifest must contain a nonempty files object')
    # Validate the entire inventory before reading any listed artifact.
    for name, digest in expected.items():
        path = PurePosixPath(name)
        if (not name or '\\' in name or path.is_absolute() or PureWindowsPath(name).drive
                or '..' in path.parts or path.as_posix() != name
                or any(':' in part or part.endswith((' ', '.'))
                       or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',
                                       part, flags=re.IGNORECASE)
                       for part in path.parts)):
            raise ValueError('unsafe or noncanonical manifest path: ' + name)
        if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('invalid SHA-256 for: ' + name)
    actual = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlinks are not accepted in artifact evidence: ' + str(path))
        if path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError('artifact resolves outside its root: ' + str(path))
            actual[path.relative_to(root).as_posix()] = path
    missing, extra = sorted(expected.keys() - actual.keys()), sorted(actual.keys() - expected.keys())
    if missing or extra:
        raise ValueError(f'inventory mismatch: missing={missing}, extra={extra}')
    mismatches, total_bytes = [], 0
    for name, path in actual.items():
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
                total_bytes += len(chunk)
        if digest.hexdigest() != expected[name]:
            mismatches.append(name)
    if mismatches:
        raise ValueError('hash mismatch: ' + ', '.join(sorted(mismatches)))
    return {'verified': True, 'files': len(actual), 'bytes': total_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.artifacts, args.manifest)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'VERIFICATION FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
