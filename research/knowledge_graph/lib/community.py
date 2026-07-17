"""DEV031 · community detection.

Deterministic Label Propagation on the undirected weighted graph.

Algorithm:
1. Each node starts in its own community (id = its own node id).
2. In each pass we visit nodes in a fixed sort order, and each node adopts
   the community label that appears most often (weighted by edge weight)
   among its neighbours. Ties are broken by lexicographic min of the
   candidate label — hence deterministic across runs.
3. Stop when no node changes label or after `max_iter` iterations.

Reference: Raghavan, Albert & Kumara (2007), "Near linear time algorithm to
detect community structures in large-scale networks."

Determinism note: standard Label Propagation is order-dependent; we sort
node visitation lexicographically and tie-break by min-label so identical
inputs always yield identical outputs — required by AEGIS governance."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from knowledge_graph.lib import algorithms


def label_propagation(adj: algorithms.AdjMap,
                        max_iter: int = 20,
                        subset_prefix: str | None = None) -> dict[str, str]:
    """Return {node_id: community_label} mapping."""
    if subset_prefix:
        nodes = sorted([k for k in adj.keys() if k.startswith(subset_prefix)])
    else:
        nodes = sorted(adj.keys())
    if not nodes:
        return {}

    labels = {n: n for n in nodes}  # everyone starts in its own community
    node_set = set(nodes)

    for _ in range(max_iter):
        changed = False
        for n in nodes:  # stable iteration order
            neighbors = [(nbr, w) for nbr, w in adj.get(n, []) if nbr in node_set]
            if not neighbors:
                continue
            votes: dict[str, float] = defaultdict(float)
            for nbr, w in neighbors:
                votes[labels[nbr]] += float(w or 0.0)
            if not votes:
                continue
            max_weight = max(votes.values())
            # Winners = all labels with the top vote weight. Break ties lex.
            winners = sorted([lb for lb, v in votes.items() if v == max_weight])
            new_label = winners[0]
            if labels[n] != new_label:
                labels[n] = new_label
                changed = True
        if not changed:
            break
    return labels


def group_by_community(labels: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for node, lb in labels.items():
        groups[lb].append(node)
    for k in groups:
        groups[k].sort()
    return dict(groups)


def detect_communities(adj: algorithms.AdjMap,
                          node_lookup: dict[str, Any],
                          subset_prefix: str | None = "Company:",
                          min_size: int = 2) -> list[dict]:
    """Return the sorted community list, largest first, with member metadata."""
    labels = label_propagation(adj, subset_prefix=subset_prefix)
    groups = group_by_community(labels)

    result = []
    for i, (comm_id, members) in enumerate(sorted(groups.items(),
                                                        key=lambda kv: -len(kv[1]))):
        if len(members) < min_size:
            continue
        # Enrich with lookup: dominant industry + sector inside the community
        industry_counts: dict[str, int] = defaultdict(int)
        sector_counts: dict[str, int] = defaultdict(int)
        for m in members:
            node = node_lookup.get(m)
            if node is None:
                continue
            ind = (node.attributes or {}).get("industry")
            sec = (node.attributes or {}).get("sector")
            if ind: industry_counts[ind] += 1
            if sec: sector_counts[sec] += 1
        dominant_industry = (max(industry_counts.items(), key=lambda kv: kv[1])[0]
                              if industry_counts else None)
        dominant_sector = (max(sector_counts.items(), key=lambda kv: kv[1])[0]
                              if sector_counts else None)

        # Human-readable community name
        name_base = dominant_industry or dominant_sector or f"Community-{i+1}"
        result.append({
            "id":                comm_id,
            "name":              f"{name_base} Cluster",
            "size":              len(members),
            "dominant_industry": dominant_industry,
            "dominant_sector":   dominant_sector,
            "members":           [m.split(":", 1)[1] for m in members],
            "industry_mix":      dict(sorted(industry_counts.items(),
                                                key=lambda kv: -kv[1])[:5]),
            "sector_mix":        dict(sorted(sector_counts.items(),
                                                key=lambda kv: -kv[1])[:5]),
        })
    return result


def modularity(adj: algorithms.AdjMap, labels: dict[str, str]) -> float:
    """Newman modularity Q for the given community assignment.

    Q = (1 / 2m) * sum_ij [ A_ij - (k_i * k_j) / (2m) ] * delta(c_i, c_j)
    Higher Q (up to ~0.7) = stronger community structure."""
    if not adj or not labels:
        return 0.0
    two_m = sum(w for k in adj for _, w in adj.get(k, []))
    if two_m == 0:
        return 0.0
    strengths = {k: sum(w for _, w in adj.get(k, [])) for k in adj}
    q = 0.0
    for i in adj:
        for j, w_ij in adj.get(i, []):
            if labels.get(i) == labels.get(j):
                expected = strengths[i] * strengths[j] / two_m
                q += (w_ij - expected)
    q /= two_m
    return round(q, 6)
