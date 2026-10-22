"""Verify pinned dependency source trees without importing third-party code."""
import argparse
import hashlib
import json
from email.parser import Parser
from pathlib import Path
from verify_final_validation_packet import strict_json

ROOT = Path(__file__).resolve().parent.parent
PINS = {'adk_submission': ('compiler_0_2_13', '0.2.13', '3412c47c6c927deba4275926da83a3a4b2c0bc29df4a6f26efe7e8e23ef00db7'), 'swegemma': ('swegemma_0_2_11', '0.2.11', 'f39106035131d6479c287cf9e47352a0ca4c0a762cd22184576298e432f24483')}


def verify_sources(package, metadata, manifest):
    package = Path(package)
    expected = manifest['python_files']
    found = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in package.rglob('*.py')}
    version = Parser().parsestr(Path(metadata).read_text(encoding='utf-8'))['Version']
    result = {'version': version, 'version_ok': version == manifest['version'],
              'missing': sorted(set(expected) - set(found)),
              'extra': sorted(set(found) - set(expected)),
              'changed': sorted(k for k in set(expected) & set(found) if expected[k] != found[k])}
    result['matches'] = result['version_ok'] and not any(result[k] for k in ('missing','extra','changed'))
    return result


def verify(root=ROOT):
    base = Path(root) / 'experiments/v5_budget_v2'
    results = {}
    for name, (stem, version, digest) in PINS.items():
        raw = (base / (stem + '_hashes.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('dependency manifest drift: ' + name)
        manifest = strict_json(raw)
        if manifest['version'] != version:
            raise ValueError('dependency manifest version: ' + name)
        source = base / stem / 'src'
        metadata = source / (name + '-' + version + '.dist-info') / 'METADATA'
        result = verify_sources(source / name, metadata, manifest)
        results[name] = result
        if not result['matches']:
            raise ValueError('dependency source drift: ' + name + ': ' + json.dumps(result))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root), indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, 'CHECK FAILED: ' + str(exc) + '\n')
