"""Inspect packaged evaluation-config evidence without extracting or executing it.

Reports presence and bytes only; does not parse YAML or infer runtime defaults.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


MAX_CONFIG_BYTES = 1024 * 1024

def inspect_archive(path):
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP members')
        configs = [n for n in names if n in ('eval_config.yaml', 'eval_config.yml')]
        if len(configs) > 1:
            raise ValueError('ambiguous root evaluation configs')
        nested = [n for n in names if n not in configs and n.rsplit('/',1)[-1] in ('eval_config.yaml','eval_config.yml')]
        content = None
        if configs:
            info = archive.getinfo(configs[0])
            if info.file_size > MAX_CONFIG_BYTES:
                raise ValueError('evaluation config exceeds 1 MiB inspection limit')
            with archive.open(info) as stream:
                content = stream.read(MAX_CONFIG_BYTES + 1)
            if len(content) > MAX_CONFIG_BYTES:
                raise ValueError('evaluation config exceeds 1 MiB inspection limit')
    return {'archive_sha256': hashlib.sha256(raw).hexdigest(),
            'root_eval_config_present': bool(configs), 'root_eval_config': configs[0] if configs else None,
            'config_sha256': hashlib.sha256(content).hexdigest() if content is not None else None,
            'config_text': content.decode('utf-8') if content is not None else None,
            'nested_config_paths': nested, 'effective_limits_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        result = inspect_archive(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'ARCHIVE INSPECTION FAILED: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__': main()
