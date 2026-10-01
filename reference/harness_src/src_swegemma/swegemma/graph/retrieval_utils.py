"""Retrieval utilities for vector similarity search over local code graphs."""

import threading
from typing import Any

import numpy as np

from swegemma.graph import embedding_utils, graph_utils

_LOCK = threading.Lock()
_SIMILARITY_CACHE: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
_PRECOMPUTED_GRAPHS: dict[str, dict[str, list[dict[str, Any]]]] = {}
_PRECOMPUTED_TEXTS: dict[str, dict[str, str]] = {}


def clear_caches(repo_name: str | bytes | None = None) -> None:
    """Clears similarity and precomputed retrieval caches.

    Args:
        repo_name: If provided, clears caches for that repository only.
    """
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else repo_name
    )
    with _LOCK:
        if repo_str:
            for k in list(_PRECOMPUTED_GRAPHS.keys()):
                if k == repo_str or k.startswith(f'{repo_str}_'):
                    _PRECOMPUTED_GRAPHS.pop(k, None)
            for k in list(_PRECOMPUTED_TEXTS.keys()):
                if k == repo_str or k.startswith(f'{repo_str}_'):
                    _PRECOMPUTED_TEXTS.pop(k, None)
            keys_to_del = [
                k
                for k in _SIMILARITY_CACHE
                if len(k) > 1
                and (k[1] == repo_str or str(k[1]).startswith(f'{repo_str}_'))
            ]
            for k in keys_to_del:
                del _SIMILARITY_CACHE[k]
        else:
            _SIMILARITY_CACHE.clear()
            _PRECOMPUTED_GRAPHS.clear()
            _PRECOMPUTED_TEXTS.clear()

    if repo_str:
        graph_utils.clear_cache_for_repo(repo_str)
        embedding_utils.clear_caches(repo_str)
    else:
        graph_utils.clear_caches()
        embedding_utils.clear_caches()


def _extract_nodes_and_embeddings(
    graph: Any,
    repo_name: str | bytes,
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> tuple[list[str], list[str], np.ndarray]:
    """Extracts node names, code texts, and single-precision embedding matrix from graph."""
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )
    node_names = []
    node_texts = []
    raw_embeddings = []

    if hasattr(graph, 'nodes'):
        items = graph.nodes(data=True)
    elif isinstance(graph, dict):
        items = graph.items()
    else:
        raise ValueError(f'Unsupported graph type: {type(graph)}')

    detected_dim: int | None = None
    for n, raw_attrs in items:
        attrs = raw_attrs if isinstance(raw_attrs, dict) else {}

        name_str = (
            n.decode('utf-8', errors='replace')
            if isinstance(n, bytes)
            else str(n)
        )
        node_names.append(name_str)

        text_val = attrs.get('text', '')
        if not text_val and 'code' in attrs:
            text_val = attrs.get('code', '')
        if text_val is None:
            text_val = ''
        text_str = (
            text_val.decode('utf-8', errors='replace')
            if isinstance(text_val, bytes)
            else str(text_val)
        )
        node_texts.append(text_str)

        emb = attrs.get('embedding')
        if emb is None or not isinstance(emb, np.ndarray) or len(emb) == 0:
            emb = embedding_utils.embed(
                name_str,
                repo_str,
                embeddings_dir=embeddings_dir,
                base_commit=base_commit,
            )

        if emb is not None:
            emb_arr = np.asarray(emb, dtype=np.float32).flatten()
            if emb_arr.size > 0 and detected_dim is None:
                detected_dim = emb_arr.shape[0]
            raw_embeddings.append(emb_arr)
        else:
            raw_embeddings.append(None)

    target_dim = detected_dim or embedding_utils.DEFAULT_EMBEDDING_DIM
    embeddings: list[np.ndarray] = []
    for emb_item in raw_embeddings:
        if emb_item is None or emb_item.size == 0:
            embeddings.append(np.zeros((target_dim,), dtype=np.float32))
        elif emb_item.shape[0] != target_dim:
            adjusted = np.zeros((target_dim,), dtype=np.float32)
            dim = min(emb_item.shape[0], target_dim)
            adjusted[:dim] = emb_item[:dim]
            embeddings.append(adjusted)
        else:
            embeddings.append(emb_item)

    if not embeddings:
        emb_matrix = np.empty((0, target_dim), dtype=np.float32)
    else:
        emb_matrix = np.vstack(embeddings)

    return node_names, node_texts, emb_matrix


def precompute_top_k_similar_nodes(
    repo_name: str | bytes,
    k: int = 10,
    chunk_size: int = 512,
    graph_dir: str = 'data/graphs',
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Pre-computes and caches top-K similar nodes for each node in a repository graph.

    Uses chunked cosine matrix multiplication and partition to prevent high memory usage.

    Args:
        repo_name: Name of target repository graph (string or bytes).
        k: Number of nearest neighbors per node.
        chunk_size: Number of query nodes processed per matrix multiplication block.
        graph_dir: Directory containing graph topology files.
        embeddings_dir: Directory containing vector archives.
        base_commit: Optional base commit hash for snapshot-specific precomputation.

    Returns:
        Mapping from node name to sorted top-K similar node dicts.
    """
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )
    g = graph_utils.get_graph(
        repo_str,
        graph_dir=graph_dir,
        embeddings_dir=embeddings_dir,
        base_commit=base_commit,
    )
    names, texts, emb_matrix = _extract_nodes_and_embeddings(
        g,
        repo_str,
        embeddings_dir=embeddings_dir,
        base_commit=base_commit,
    )

    n_nodes = len(names)
    if n_nodes == 0 or emb_matrix.shape[0] == 0:
        return {}

    # Normalize vectors for cosine similarity computation
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    norm_matrix = (emb_matrix / norms).astype(np.float32)

    results: dict[str, list[dict[str, Any]]] = {}
    text_dict = dict(zip(names, texts, strict=False))

    top_needed = min(k + 1, n_nodes)

    for start_idx in range(0, n_nodes, chunk_size):
        end_idx = min(start_idx + chunk_size, n_nodes)
        chunk_norm = norm_matrix[start_idx:end_idx]
        chunk_sims = np.dot(chunk_norm, norm_matrix.T)

        for i, idx in enumerate(range(start_idx, end_idx)):
            name = names[idx]
            sims = chunk_sims[i]

            if n_nodes <= top_needed:
                part_idx = np.argsort(sims)[::-1]
            else:
                part_idx = np.argpartition(sims, -top_needed)[-top_needed:]
                part_idx = part_idx[np.argsort(sims[part_idx])[::-1]]

            neighbors = []
            for n_idx in part_idx:
                other_name = names[n_idx]
                if other_name == name:
                    continue
                neighbors.append(
                    {
                        'node_name': other_name,
                        'code': texts[n_idx],
                        'similarity': float(sims[n_idx]),
                        'embedding': emb_matrix[n_idx],
                    }
                )
                if len(neighbors) == k:
                    break

            results[name] = neighbors

    precomp_key = f'{repo_str}_{base_commit}' if base_commit else repo_str
    with _LOCK:
        _PRECOMPUTED_GRAPHS[precomp_key] = results
        _PRECOMPUTED_TEXTS[precomp_key] = text_dict

    return results


def get_similar_nodes(
    node: Any,
    repo_name: str | bytes | None = None,
    k: int = 10,
    *,
    use_memoization: bool = True,
    graph: Any | None = None,
    graph_dir: str = 'data/graphs',
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieves top-K similar code nodes in the repository based on graph embeddings.

    Args:
        node: Target node identifier (str, bytes, dict, or object).
        repo_name: Target repository name (required if omitted from node).
        k: Number of nearest neighbors to retrieve.
        use_memoization: Whether to cache results in-memory.
        graph: Optional graph object to scope retrieval.
        graph_dir: Directory containing graph topologies.
        embeddings_dir: Directory containing NPZ vector archives.
        base_commit: Optional base commit hash for snapshot-specific lookup.

    Returns:
        List of dictionaries with keys: 'node_name', 'code', 'similarity', 'embedding'.
    """
    node_name = None
    target_repo = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else repo_name
    )
    query_emb = None

    if isinstance(node, (str, bytes)):
        node_str = (
            node.decode('utf-8', errors='replace')
            if isinstance(node, bytes)
            else str(node)
        )
        if ';' in node_str and not target_repo:
            target_repo, node_name = node_str.split(';', 1)
        else:
            node_name = node_str
    elif isinstance(node, dict):
        node_name = node.get('node_name') or node.get('name')
        if isinstance(node_name, bytes):
            node_name = node_name.decode('utf-8', errors='replace')
        repo_val = node.get('repo_name')
        if repo_val is not None:
            target_repo = (
                repo_val.decode('utf-8', errors='replace')
                if isinstance(repo_val, bytes)
                else str(repo_val)
            )
        query_emb = node.get('embedding')
    elif hasattr(node, 'node_name'):
        node_name = node.node_name
        if isinstance(node_name, bytes):
            node_name = node_name.decode('utf-8', errors='replace')
        repo_val = getattr(node, 'repo_name', None)
        if repo_val is not None:
            target_repo = (
                repo_val.decode('utf-8', errors='replace')
                if isinstance(repo_val, bytes)
                else str(repo_val)
            )

    if not target_repo:
        raise ValueError('repo_name must be specified either in node or args.')

    cache_key = (node_name, target_repo, k, base_commit)
    if use_memoization:
        with _LOCK:
            if cache_key in _SIMILARITY_CACHE:
                return _SIMILARITY_CACHE[cache_key]

    precomp_key = f'{target_repo}_{base_commit}' if base_commit else target_repo
    # Pre-computation lookup under lock (only when k does not exceed precomputed top-k length)
    if use_memoization and not graph and node_name is not None:
        with _LOCK:
            repo_precomp = _PRECOMPUTED_GRAPHS.get(precomp_key)
            if repo_precomp is not None and node_name in repo_precomp:
                cached_list = repo_precomp[node_name]
                if k <= len(cached_list):
                    res = cached_list[:k]
                    _SIMILARITY_CACHE[cache_key] = res
                    return res

    # Build target graph context
    if graph is None:
        graph = graph_utils.get_graph(
            target_repo,
            graph_dir=graph_dir,
            embeddings_dir=embeddings_dir,
            base_commit=base_commit,
        )

    if node_name and graph is not None:
        resolver = getattr(
            graph_utils,
            'resolve_node_name',
            getattr(graph_utils, '_resolve_node_name', None),
        )
        resolved_node = resolver(node_name, graph) if callable(resolver) else None
        if isinstance(resolved_node, str) and resolved_node:
            node_name = resolved_node
            if use_memoization:
                with _LOCK:
                    repo_precomp = _PRECOMPUTED_GRAPHS.get(precomp_key)
                    if repo_precomp is not None and node_name in repo_precomp:
                        cached_list = repo_precomp[node_name]
                        if k <= len(cached_list):
                            res = cached_list[:k]
                            _SIMILARITY_CACHE[cache_key] = res
                            return res

    names, texts, emb_matrix = _extract_nodes_and_embeddings(
        graph,
        target_repo,
        embeddings_dir=embeddings_dir,
        base_commit=base_commit,
    )

    if len(names) == 0:
        return []

    if query_emb is None and node_name:
        query_emb = embedding_utils.embed(
            node_name,
            target_repo,
            embeddings_dir=embeddings_dir,
            base_commit=base_commit,
        )

    if query_emb is None:
        return []

    query_emb = np.asarray(query_emb, dtype=np.float32).flatten()
    if emb_matrix.shape[1] > 0 and query_emb.shape[0] != emb_matrix.shape[1]:
        adjusted = np.zeros((emb_matrix.shape[1],), dtype=np.float32)
        dim = min(query_emb.shape[0], emb_matrix.shape[1])
        adjusted[:dim] = query_emb[:dim]
        query_emb = adjusted

    q_norm = np.linalg.norm(query_emb)
    if q_norm == 0:
        q_norm = 1e-10

    matrix_norms = np.linalg.norm(emb_matrix, axis=1)
    matrix_norms[matrix_norms == 0] = 1e-10

    dots = np.dot(emb_matrix, query_emb)
    sims = dots / (matrix_norms * q_norm)

    sorted_indices = np.argsort(sims)[::-1]

    results = []
    for idx in sorted_indices:
        cand_name = names[idx]
        if cand_name == node_name:
            continue
        results.append(
            {
                'node_name': cand_name,
                'code': texts[idx],
                'similarity': float(sims[idx]),
                'embedding': emb_matrix[idx],
            }
        )
        if len(results) == k:
            break

    if use_memoization:
        with _LOCK:
            _SIMILARITY_CACHE[cache_key] = results

    return results
