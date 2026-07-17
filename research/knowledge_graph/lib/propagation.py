"""DEV031 · influence propagation.

Given a source node (e.g., `Signal:momentum`, `Sector:Financial Services`,
`MarketRegime:Risk-Off`), compute how influence propagates outward through
the graph using **personalized PageRank** — a decayed random walk starting
from the source.

The result is a score in [0, 1] for every node, representing how strongly
the source node reaches it. High scores = strongly propagated to.

Deterministic (fixed iteration count, no random seed)."""
from __future__ import annotations

from typing import Any

from knowledge_graph.lib import algorithms


def personalized_pagerank(adj: algorithms.AdjMap,
                              source: str,
                              damping: float = 0.85,
                              iterations: int = 30) -> dict[str, float]:
    """Personalized PageRank with restart to `source` node."""
    nodes = list(adj.keys())
    if source not in adj or not nodes:
        return {}
    n = len(nodes)
    score = {k: 0.0 for k in nodes}
    score[source] = 1.0

    for _ in range(iterations):
        new_score = {k: 0.0 for k in nodes}
        # Restart mass
        new_score[source] += (1.0 - damping)
        # Diffuse
        for u in nodes:
            if score[u] == 0.0:
                continue
            neighbors = adj.get(u, [])
            if not neighbors:
                new_score[source] += damping * score[u]  # dangling → source
                continue
            total_w = sum(w for _, w in neighbors) or 1.0
            for v, w in neighbors:
                new_score[v] += damping * score[u] * (w / total_w)
        # Normalize so it sums to 1
        s = sum(new_score.values()) or 1.0
        new_score = {k: v / s for k, v in new_score.items()}
        score = new_score
    return score


def top_reached(scores: dict[str, float],
                  source: str,
                  entity_type: str | None = None,
                  n: int = 10) -> list[tuple[str, float]]:
    filtered = [(k, v) for k, v in scores.items() if k != source]
    if entity_type:
        prefix = f"{entity_type}:"
        filtered = [(k, v) for k, v in filtered if k.startswith(prefix)]
    filtered.sort(key=lambda kv: -kv[1])
    return filtered[:n]


def propagation_report(adj: algorithms.AdjMap,
                          node_lookup: dict[str, Any],
                          sources: list[str] | None = None,
                          top_k: int = 10) -> list[dict]:
    """Generate a report showing propagation from a set of interesting sources.

    Default sources = current regime + top-influence signals + top-influence
    strategies + top-influence sectors."""
    if sources is None:
        sources = _default_sources(adj)

    report = []
    for src in sources:
        if src not in adj:
            continue
        scores = personalized_pagerank(adj, src)
        _, label = src.split(":", 1) if ":" in src else ("", src)
        row = {
            "source":            src,
            "source_label":      label,
            "top_reach_overall": [{"node": k, "score": round(v, 6)}
                                     for k, v in top_reached(scores, src, n=top_k)],
        }
        # Per-entity-type top reach
        for et in ["Company", "Industry", "Sector", "Portfolio", "Strategy"]:
            row[f"top_{et.lower()}"] = [
                {"node": k.split(":", 1)[1], "score": round(v, 6)}
                for k, v in top_reached(scores, src, entity_type=et, n=5)
            ]
        report.append(row)
    return report


def _default_sources(adj: algorithms.AdjMap) -> list[str]:
    sources = []
    # Current regime (best guess: whichever MarketRegime is connected to
    # sectors — that's the current one, per relationships.edges_sector_regime)
    regime_ids = [k for k in adj if k.startswith("MarketRegime:")]
    for rid in regime_ids:
        has_sectors = any(n.startswith("Sector:") for n, _ in adj.get(rid, []))
        if has_sectors:
            sources.append(rid)
            break
    # Champion strategy
    strategy_ids = sorted([k for k in adj if k.startswith("Strategy:")])
    if strategy_ids:
        sources.append(strategy_ids[0])
    # A representative signal
    signal_ids = sorted([k for k in adj if k.startswith("Signal:")])
    if signal_ids:
        sources.extend(signal_ids[:2])
    # A large sector (financials/health are common)
    sector_ids = [k for k in adj if k.startswith("Sector:")]
    # pick sectors with highest connected-industry count
    if sector_ids:
        sector_ids.sort(key=lambda k: -len([n for n, _ in adj.get(k, []) if n.startswith("Industry:")]))
        sources.append(sector_ids[0])
    return sources


def cascade_path(adj: algorithms.AdjMap,
                   source: str, target: str,
                   max_hops: int = 5) -> list[str]:
    """Human-readable cascade path source -> ... -> target, if reachable."""
    d, path = algorithms.shortest_path(adj, source, target)
    if not path:
        return []
    if len(path) > max_hops + 1:
        return path[:max_hops + 1]
    return path
