"""Graph utilities for constructing, serializing, and inspecting repository graphs locally."""

import json
import os
import threading
from typing import Any

import cachetools
import networkx as nx
import numpy as np

from swegemma.graph import embedding_utils

_LOCK = threading.Lock()
_GRAPH_CACHE: cachetools.LRUCache = cachetools.LRUCache(maxsize=100)


def clear_caches() -> None:
    """Clears the in-memory graph cache."""
    with _LOCK:
        _GRAPH_CACHE.clear()


def clear_cache_for_repo(repo_name: str | bytes) -> None:
    """Clears the in-memory graph cache for a specific repository."""
    repo_str = (
        repo_name.decode('utf-8', errors='replace')
        if isinstance(repo_name, bytes)
        else str(repo_name)
    )
    with _LOCK:
        keys_to_remove = [k for k in _GRAPH_CACHE if k[0] == repo_str]
        for k in keys_to_remove:
            del _GRAPH_CACHE[k]


class CustomMultiEdgeView(nx.classes.reportviews.OutMultiEdgeView):
    """Custom OutMultiEdgeView supporting 2-tuple (u, v) edge indexing."""

    def __getitem__(self, e: Any) -> Any:
        if isinstance(e, tuple) and len(e) == 2:
            u, v = e[0], e[1]
            return self._adjdict[u][v]
        return super().__getitem__(e)


class CustomMultiDiGraph(nx.MultiDiGraph):
    """Custom MultiDiGraph whose edges property returns CustomMultiEdgeView."""

    @property
    def edges(self):
        return CustomMultiEdgeView(self)


def _clean_for_json(obj: Any, include_embeddings: bool = False) -> Any:
    """Recursively cleans an object for JSON serialization, handling sets, bytes, and numpy types."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            k_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
            if k_str == 'embedding' and not include_embeddings:
                continue
            if k_str == 'embedding' and isinstance(v, np.ndarray):
                cleaned[k_str] = v.tolist()
            else:
                cleaned[k_str] = _clean_for_json(v, include_embeddings)
        return cleaned
    elif isinstance(obj, (set, frozenset)):
        return sorted(
            [_clean_for_json(item, include_embeddings) for item in obj],
            key=str,
        )
    elif isinstance(obj, (list, tuple)):
        return [_clean_for_json(item, include_embeddings) for item in obj]
    elif isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    else:
        return obj


def save_graph_to_json(
    graph: nx.DiGraph | nx.MultiDiGraph,
    output_dir: str = 'data/graphs',
    include_embeddings: bool = False,
) -> str:
    """Saves a networkx graph topology to a local JSON file using node_link_data.

    Args:
        graph: A networkx DiGraph or MultiDiGraph to serialize.
        output_dir: Base directory or target .json file path.
        include_embeddings: Whether to serialize node embedding arrays into JSON.

    Returns:
        The path of the written JSON file.
    """
    repo_name = getattr(graph, 'graph', {}).get('repo_name')
    if isinstance(repo_name, bytes):
        repo_name = repo_name.decode('utf-8', errors='replace')

    if output_dir.endswith('.json'):
        file_path = output_dir
    elif repo_name:
        file_path = embedding_utils.repo_to_file_path(
            output_dir, str(repo_name), '.json'
        )
    else:
        raise ValueError(
            "Graph missing required 'repo_name' in graph.graph for JSON output."
        )

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    raw_data = nx.node_link_data(graph, edges='edges')
    clean_data = _clean_for_json(raw_data, include_embeddings=include_embeddings)

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(clean_data, f, indent=2)

    return file_path


def load_graph_from_json(file_path: str) -> CustomMultiDiGraph:
    """Loads a CustomMultiDiGraph from a JSON file serialized via node_link_data."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'Graph JSON file not found at: {file_path}')

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    edge_key = 'edges' if 'edges' in data else ('links' if 'links' in data else 'edges')
    base_g = nx.node_link_graph(data, edges=edge_key)
    g = CustomMultiDiGraph(base_g)
    if hasattr(base_g, 'graph') and isinstance(base_g.graph, dict):
        g.graph.update(base_g.graph)

    for _n, attrs in g.nodes(data=True):
        if 'embedding' in attrs and attrs['embedding'] is not None:
            attrs['embedding'] = np.array(attrs['embedding'], dtype=np.float32)

    return g


def resolve_node_name(
    target_str: str | bytes,
    graph: nx.DiGraph | nx.MultiDiGraph,
) -> str | None:
    """Resolves a short or partially-qualified symbol name to a concrete node identifier in the graph.

    Matching precedence:
    1. Exact match (e.g. 'fastapi.applications.FastAPI')
    2. Suffix match on delimiter boundary (e.g. '.FastAPI' or ';FastAPI')
    3. Case-insensitive exact / boundary match
    4. Substring containment match
    """
    if not graph:
        return None

    query = (
        target_str.decode('utf-8', errors='replace')
        if isinstance(target_str, bytes)
        else str(target_str)
    )

    if query in graph:
        return query

    # 1. Exact suffix matching on delimiter boundary (. or ;)
    candidates = [
        n
        for n in graph.nodes()
        if str(n).endswith(f'.{query}') or str(n).endswith(f';{query}')
    ]
    if candidates:
        # Prefer shortest hierarchical depth (e.g. class before method) and shortest name
        return min(candidates, key=lambda x: (len(str(x).split('.')), len(str(x))))

    # 2. Case-insensitive exact or boundary match
    lower_query = query.lower()
    ci_candidates = [
        n
        for n in graph.nodes()
        if str(n).lower() == lower_query
        or str(n).lower().endswith(f'.{lower_query}')
        or str(n).lower().endswith(f';{lower_query}')
    ]
    if ci_candidates:
        return min(ci_candidates, key=lambda x: (len(str(x).split('.')), len(str(x))))

    # 3. Substring containment match
    sub_candidates = [
        n
        for n in graph.nodes()
        if query in str(n) or lower_query in str(n).lower()
    ]
    if sub_candidates:
        return min(sub_candidates, key=lambda x: (len(str(x).split('.')), len(str(x))))

    return None


def get_graph(
    repo_name: str | bytes,
    graph_dir: str = 'data/graphs',
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> CustomMultiDiGraph:
    """Loads and returns a CustomMultiDiGraph for the given repository name from local files.

    Args:
        repo_name: Name of repository (string or bytes).
        graph_dir: Local directory containing JSON topology files or explicit JSON path.
        embeddings_dir: Local directory containing NPZ embedding archives.
        base_commit: Optional base commit hash for snapshot-specific graph lookup.

    Returns:
        CustomMultiDiGraph populated with nodes, edges, and embeddings.
    """
    if isinstance(repo_name, bytes):
        repo_name = repo_name.decode('utf-8', errors='replace')

    cache_key = (repo_name, base_commit, graph_dir, embeddings_dir)
    with _LOCK:
        if cache_key in _GRAPH_CACHE:
            return _GRAPH_CACHE[cache_key]

    if graph_dir.endswith('.json'):
        local_path = graph_dir
    else:
        repo_str = str(repo_name)
        repo_short = repo_str.rsplit('/', maxsplit=1)[-1]
        repo_slug = repo_str.replace('/', '_')
        candidates = []
        if base_commit:
            candidates.extend([
                os.path.join(graph_dir, f"{repo_short}_{base_commit}.json"),
                os.path.join(graph_dir, f"{repo_slug}_{base_commit}.json"),
            ])
        candidates.extend([
            embedding_utils.repo_to_file_path(graph_dir, repo_name, '.json'),
            os.path.join(graph_dir, f"{repo_slug}.json"),
            os.path.join(graph_dir, f"{repo_short}.json"),
            os.path.join(graph_dir, f"{repo_str}.json"),
        ])
        local_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

    if not os.path.exists(local_path):
        raise KeyError(f'Repository {repo_name} topology not found at: {local_path}')

    g = load_graph_from_json(local_path)
    g.graph['repo_name'] = repo_name

    # Hydrate missing node attributes and embeddings
    for n, attrs in g.nodes(data=True):
        if 'name' not in attrs:
            attrs['name'] = str(n)
        if 'text' not in attrs:
            attrs['text'] = ''
        if 'embedding' not in attrs or attrs['embedding'] is None:
            emb = embedding_utils.embed(
                attrs['name'],
                repo_name,
                embeddings_dir=embeddings_dir,
                base_commit=base_commit,
            )
            if emb is not None:
                attrs['embedding'] = emb

    with _LOCK:
        _GRAPH_CACHE[cache_key] = g

    return g


def get_neighbor(
    node: str | bytes | list[str | bytes],
    graph: nx.DiGraph | nx.MultiDiGraph | None = None,
    repo_name: str | bytes | None = None,
    max_neighbors: int = 50,
    *,
    edge_type: str | None = None,
    direction: str = 'both',
    graph_dir: str = 'data/graphs',
    embeddings_dir: str = 'data/embeddings',
    base_commit: str | None = None,
) -> list[str] | dict[str, list[str]]:
    """Returns neighboring node names for one or more target nodes in a repository graph.

    Args:
        node: Target node name string or bytes, or list of node names.
        graph: Optional NetworkX graph object. Loaded via repo_name if omitted.
        repo_name: Repository name (required if graph is omitted).
        max_neighbors: Maximum neighbor results per node.
        edge_type: Optional filter by edge 'type' or 'relation' attribute.
        direction: Direction of edges to traverse ('both', 'out', or 'in').
        graph_dir: Directory containing graph topologies.
        embeddings_dir: Directory containing vector embeddings.
        base_commit: Optional base commit hash for snapshot-specific graph lookup.

    Returns:
        List of neighbor node names, or dictionary mapping target node to neighbor list.
    """
    if repo_name is not None and isinstance(repo_name, bytes):
        repo_name = repo_name.decode('utf-8', errors='replace')

    if graph is None:
        if not repo_name:
            raise ValueError('Either graph or repo_name must be provided.')
        graph = get_graph(
            repo_name,
            graph_dir=graph_dir,
            embeddings_dir=embeddings_dir,
            base_commit=base_commit,
        )

    single_input = isinstance(node, (str, bytes))
    node_list = [node] if single_input else list(node)

    results = {}
    for target in node_list:
        target_str = (
            target.decode('utf-8', errors='replace')
            if isinstance(target, bytes)
            else str(target)
        )
        resolved = resolve_node_name(target_str, graph)
        if not resolved:
            results[target] = []
            continue

        neighbors: set[str] = set()

        # Outgoing edges
        if direction in ('both', 'out'):
            for _, neighbor, data in graph.out_edges(resolved, data=True):
                if (
                    edge_type is None
                    or data.get('type') == edge_type
                    or data.get('relation') == edge_type
                ):
                    neighbors.add(str(neighbor))

        # Incoming edges
        if direction in ('both', 'in'):
            for neighbor, _, data in graph.in_edges(resolved, data=True):
                if (
                    edge_type is None
                    or data.get('type') == edge_type
                    or data.get('relation') == edge_type
                ):
                    neighbors.add(str(neighbor))

        results[target] = sorted(neighbors)[:max_neighbors]

    return results[node] if single_input else results


def get_induced_subgraph(
    graph: nx.DiGraph | nx.MultiDiGraph,
    subset_nodes: list[str | bytes] | None = None,
) -> nx.DiGraph | nx.MultiDiGraph:
    """Returns induced subgraph for specified subset of nodes."""
    if not subset_nodes:
        raise ValueError('subset_nodes cannot be empty.')
    valid_nodes = set()
    graph_nodes = set(graph.nodes())

    for target in subset_nodes:
        target_str = (
            target.decode('utf-8', errors='replace')
            if isinstance(target, bytes)
            else str(target)
        )
        resolved = resolve_node_name(target_str, graph)
        if resolved and resolved in graph_nodes:
            valid_nodes.add(resolved)

    subgraph = graph.subgraph(valid_nodes).copy()
    if hasattr(graph, 'graph') and isinstance(graph.graph, dict):
        subgraph.graph.update(graph.graph)

    return subgraph
