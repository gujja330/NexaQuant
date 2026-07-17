"""DEV031 · graph algorithms.

Pure functions operating on an undirected weighted graph represented as an
adjacency map: `Dict[node_id, List[Tuple[neighbor_id, weight]]]`.

No external graph library dependency — deterministic, easy to audit."""
from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Iterable


AdjMap = dict[str, list[tuple[str, float]]]


def build_adjacency(edges: Iterable) -> AdjMap:
    """`edges` = iterable of Edge dataclasses. Undirected representation."""
    adj: AdjMap = defaultdict(list)
    for e in edges:
        adj[e.src].append((e.dst, float(e.weight or 0.0)))
        adj[e.dst].append((e.src, float(e.weight or 0.0)))
    # de-duplicate edges (multi-graph collapse to max-weight edge)
    for k in list(adj.keys()):
        best: dict[str, float] = {}
        for (nbr, w) in adj[k]:
            if nbr not in best or w > best[nbr]:
                best[nbr] = w
        adj[k] = [(n, w) for n, w in best.items()]
    return dict(adj)


def neighbours(adj: AdjMap, node_id: str, hops: int = 1) -> list[tuple[str, float]]:
    """BFS neighbours up to `hops`. Weight = shortest-path total edge weight sum."""
    if node_id not in adj or hops <= 0:
        return []
    if hops == 1:
        return sorted(adj[node_id], key=lambda nw: -nw[1])
    visited = {node_id: 0.0}
    q: deque = deque([(node_id, 0)])
    while q:
        cur, depth = q.popleft()
        if depth >= hops:
            continue
        for nbr, w in adj.get(cur, []):
            new_dist = visited[cur] + w
            if nbr not in visited or new_dist > visited[nbr]:
                visited[nbr] = new_dist
                q.append((nbr, depth + 1))
    result = [(k, v) for k, v in visited.items() if k != node_id]
    return sorted(result, key=lambda nw: -nw[1])


def shortest_path(adj: AdjMap, src: str, dst: str) -> tuple[float, list[str]]:
    """Dijkstra using INVERSE weight (higher-weight edges = closer nodes).
    Returns (total_distance, path). Empty path if unreachable."""
    if src not in adj or dst not in adj:
        return (float("inf"), [])
    if src == dst:
        return (0.0, [src])
    dist = {src: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v, w in adj.get(u, []):
            step = 1.0 / max(w, 1e-6)  # invert: higher weight = shorter distance
            nd = d + step
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if dst not in dist:
        return (float("inf"), [])
    # reconstruct path
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return (dist[dst], list(reversed(path)))


def degree_centrality(adj: AdjMap) -> dict[str, float]:
    """Fraction of the graph each node is connected to (n_neighbours / (N-1))."""
    n = len(adj)
    if n <= 1:
        return {k: 0.0 for k in adj}
    return {k: len(v) / (n - 1) for k, v in adj.items()}


def weighted_degree(adj: AdjMap) -> dict[str, float]:
    """Sum of edge weights per node (a.k.a. strength)."""
    return {k: sum(w for _, w in v) for k, v in adj.items()}


def eigen_influence(adj: AdjMap, iterations: int = 20, damping: float = 0.85) -> dict[str, float]:
    """Simplified PageRank as an influence proxy (deterministic, no external lib)."""
    nodes = list(adj.keys())
    n = len(nodes)
    if n == 0:
        return {}
    score = {k: 1.0 / n for k in nodes}
    for _ in range(iterations):
        new_score = {k: (1.0 - damping) / n for k in nodes}
        for u in nodes:
            neighbors = adj.get(u, [])
            if not neighbors:
                continue
            total_w = sum(w for _, w in neighbors) or 1.0
            for v, w in neighbors:
                new_score[v] += damping * score[u] * (w / total_w)
        # normalise so scores sum to 1
        s = sum(new_score.values()) or 1.0
        new_score = {k: v / s for k, v in new_score.items()}
        # convergence check (optional): could stop early on delta
        score = new_score
    return score


def closeness_centrality(adj: AdjMap, sample_size: int | None = None) -> dict[str, float]:
    """Simplified closeness = 1 / avg_shortest_path_from_this_node.

    For a large graph, we sample up to `sample_size` nodes to keep this O(sample_size * N)."""
    nodes = list(adj.keys())
    if not nodes:
        return {}
    targets = nodes if sample_size is None else nodes[:max(1, sample_size)]
    result = {}
    for src in nodes:
        # BFS unweighted-hop distances
        dist = {src: 0}
        q: deque = deque([src])
        while q:
            u = q.popleft()
            for v, _ in adj.get(u, []):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        # Only include reachable targets
        reachable = [dist[t] for t in targets if t in dist and t != src]
        if reachable:
            result[src] = round(1.0 / (sum(reachable) / len(reachable)), 6)
        else:
            result[src] = 0.0
    return result


def top_by(scores: dict[str, float], n: int = 10) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda kv: -kv[1])[:n]


def subgraph_by_type(adj: AdjMap, entity_type: str) -> AdjMap:
    """Return the subgraph containing only nodes whose id starts with `entity_type:`."""
    prefix = f"{entity_type}:"
    kept = {k for k in adj.keys() if k.startswith(prefix)}
    return {
        k: [(nbr, w) for nbr, w in adj[k] if nbr in kept]
        for k in kept
    }
