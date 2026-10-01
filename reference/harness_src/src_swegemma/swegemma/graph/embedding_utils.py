"""Embedding utilities for local node vector lookup and NPZ storage."""

from __future__ import annotations

import io
import logging
import os
import threading
import zipfile
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_DIM = 128

_LOCK = threading.Lock()
_REPO_CACHES: dict[str, dict[str, np.ndarray]] = {}


def repo_to_file_path(base_dir: str, repo_name: str | bytes, ext: str) -> str:
    """Converts a repository name (e.g. 'owner/repo') into a local filesystem path.

    Args:
        base_dir: Root directory path.
        repo_name: Repository name string or bytes.
        ext: Extension starting with dot (e.g. '.npz' or '.json').

    Returns:
        Absolute or relative filepath formatted for local filesystem.
    """
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )
    safe_name = repo_str.replace('/', '_')
    if not ext.startswith('.'):
        ext = '.' + ext
    return os.path.join(base_dir, safe_name + ext)


def is_local_path(path: str | None) -> bool:
    """Returns True if path targets local filesystem storage."""
    if not path:
        return True
    return (
        path.endswith('.json')
        or path.endswith('.npz')
        or 'data/graphs' in path
        or 'data/embeddings' in path
        or not path.startswith('gs://')
    )


def clear_caches(repo_name: str | bytes | None = None) -> None:
    """Clears the in-memory embedding cache for a specific repo or all repos."""
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else repo_name
    )
    with _LOCK:
        if repo_str is not None:
            for k in list(_REPO_CACHES.keys()):
                if k == repo_str or k.startswith(f'{repo_str}_'):
                    _REPO_CACHES.pop(k, None)
        else:
            _REPO_CACHES.clear()


def save_embeddings_to_npz(
    repo_name: str | bytes,
    node_embeddings: dict[str | bytes, Any],
    output_dir: str = 'data/embeddings',
) -> str:
    """Saves node embedding vectors to an NPZ archive file.

    Args:
        repo_name: Name of repository.
        node_embeddings: Dictionary mapping node names to vectors.
        output_dir: Directory where embeddings are saved.

    Returns:
        Full path to written .npz file.
    """
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )
    file_path = repo_to_file_path(output_dir, repo_str, '.npz')
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    clean_dict: dict[str, np.ndarray] = {}
    for k, v in node_embeddings.items():
        key_str = (
            k.decode('utf-8', errors='replace') if isinstance(k, bytes) else str(k)
        )
        clean_dict[key_str] = np.asarray(v, dtype=np.float32)

    with zipfile.ZipFile(file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for k, arr in clean_dict.items():
            buf = io.BytesIO()
            np.save(buf, arr, allow_pickle=False)
            zf.writestr(f'{k}.npy', buf.getvalue())

    clear_caches(repo_str)
    return file_path


def load_embeddings_from_npz(file_path: str) -> dict[str, np.ndarray]:
    """Loads node embeddings from a compressed NumPy (.npz) file.

    Args:
        file_path: Path to .npz file.

    Returns:
        Dictionary mapping node names to float32 numpy arrays.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'Embedding file not found at: {file_path}')

    result: dict[str, np.ndarray] = {}
    with np.load(file_path, allow_pickle=False) as data:
        for k in data.files:
            result[str(k)] = data[k].astype(np.float32)
    return result


def embed(
    node_content: str | bytes | None,
    repo_name: str | bytes | None,
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> np.ndarray | None:
    """Returns numerical embedding vector for a given node/content string from local .npz storage.

    Args:
        node_content: Function/class node name or snippet content.
        repo_name: Target repository name.
        embeddings_dir: Base directory containing local .npz archives.
        base_commit: Optional base commit hash for snapshot-specific embedding lookup.

    Returns:
        Numpy array of float32, or None if not found.
    """
    if not node_content or not repo_name:
        return None

    node_str = (
        node_content.decode('utf-8', errors='replace')
        if isinstance(node_content, bytes)
        else str(node_content)
    )
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )

    cache_key = f"{repo_str}_{base_commit}" if base_commit else repo_str

    with _LOCK:
        if cache_key not in _REPO_CACHES:
            if embeddings_dir.endswith('.npz'):
                file_path = embeddings_dir
            else:
                repo_short = repo_str.split('/')[-1]
                repo_slug = repo_str.replace('/', '_')
                candidates = []
                if base_commit:
                    candidates.extend([
                        os.path.join(embeddings_dir, f"{repo_short}_{base_commit}.npz"),
                        os.path.join(embeddings_dir, f"{repo_slug}_{base_commit}.npz"),
                    ])
                candidates.extend([
                    repo_to_file_path(embeddings_dir, repo_str, '.npz'),
                    os.path.join(embeddings_dir, f"{repo_slug}.npz"),
                    os.path.join(embeddings_dir, f"{repo_short}.npz"),
                    os.path.join(embeddings_dir, f"{repo_str}.npz"),
                ])
                file_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

            cache: dict[str, np.ndarray] = {}
            if os.path.exists(file_path):
                try:
                    cache = load_embeddings_from_npz(file_path)
                except Exception as e:
                    logger.warning(
                        'Failed to load embeddings from %s: %s', file_path, e
                    )
            _REPO_CACHES[cache_key] = cache

        repo_cache = _REPO_CACHES[cache_key]
        if node_str in repo_cache:
            return repo_cache[node_str]

        # Key lookup with repo suffix fallback
        if repo_str and not node_str.startswith(f'{repo_str};'):
            alt_key = f'{repo_str};{node_str}'
            if alt_key in repo_cache:
                return repo_cache[alt_key]

        # Suffix matching fallback (e.g. FastAPI -> fastapi.applications.FastAPI)
        for k in repo_cache:
            if k == node_str or k.endswith(f'.{node_str}') or k.endswith(f';{node_str}'):
                return repo_cache[k]

        return None
