"""DEV031 · recommendation explainability.

For a given ticker, produce a full evidence path through the graph that
explains WHY a recommendation exists. The path traverses the canonical
relationship chain:

    Recommendation -> Company -> Industry -> Sector -> MarketRegime
    Company -> Portfolio -> Strategy (champion)
    Signal -> Recommendation
    Recommendation -> Outcome (via DEV025 winner/loser)

Every explanation is a deterministic walk over the existing adjacency map.
No inference, no LLM — just graph traversal + attribute lookup."""
from __future__ import annotations

from typing import Any

from knowledge_graph.lib import algorithms


def _split_id(node_id: str) -> tuple[str, str]:
    if ":" not in node_id:
        return ("", node_id)
    t, label = node_id.split(":", 1)
    return t, label


def _first_neighbor_of_type(adj: algorithms.AdjMap, src: str, entity_type: str) -> tuple[str | None, float]:
    if src not in adj:
        return (None, 0.0)
    prefix = f"{entity_type}:"
    matches = [(n, w) for n, w in adj[src] if n.startswith(prefix)]
    if not matches:
        return (None, 0.0)
    matches.sort(key=lambda nw: -nw[1])
    return matches[0]


def _node_summary(node_lookup: dict[str, Any], node_id: str) -> dict:
    n = node_lookup.get(node_id)
    if n is None:
        _, label = _split_id(node_id)
        return {"id": node_id, "label": label, "attributes": {}}
    return {"id":         n.id,
             "entity_type": n.entity_type,
             "label":       n.label,
             "attributes":  {k: v for k, v in (n.attributes or {}).items()
                              if not isinstance(v, (list, dict))}}


def explain_recommendation(adj: algorithms.AdjMap,
                              node_lookup: dict[str, Any],
                              ticker: str) -> dict:
    """Trace WHY a company got its current recommendation."""
    company_id = f"Company:{ticker}"
    if company_id not in adj:
        return {"ticker": ticker, "found": False,
                 "reason": "no Company node — company not in current AEGIS universe"}

    # Find all Recommendation nodes touching this company
    rec_ids = [n for n, _ in adj[company_id] if n.startswith("Recommendation:")]

    # Traverse to industry, sector, current regime
    industry_id, ind_w = _first_neighbor_of_type(adj, company_id, "Industry")
    sector_id = None
    sec_w = 0.0
    if industry_id is not None:
        sector_id, sec_w = _first_neighbor_of_type(adj, industry_id, "Sector")

    regime_id = None
    reg_w = 0.0
    if sector_id is not None:
        regime_id, reg_w = _first_neighbor_of_type(adj, sector_id, "MarketRegime")

    # Portfolios that hold this company
    portfolio_matches = [(n, w) for n, w in adj[company_id] if n.startswith("Portfolio:")]
    portfolio_matches.sort(key=lambda nw: -nw[1])
    portfolios = portfolio_matches[:5]

    # Champion strategy (the strategy each portfolio links to; take mode)
    strategies: dict[str, float] = {}
    for pid, _ in portfolio_matches:
        for n, w in adj.get(pid, []):
            if n.startswith("Strategy:"):
                strategies[n] = strategies.get(n, 0.0) + w
    champion_id = None
    if strategies:
        champion_id = max(strategies.items(), key=lambda kv: kv[1])[0]

    # Signals that touch this company's recommendations
    signals: list[tuple[str, float]] = []
    for rid in rec_ids:
        for n, w in adj.get(rid, []):
            if n.startswith("Signal:") and n not in (
                "Signal:winner", "Signal:loser"):
                signals.append((n, w))
    signals.sort(key=lambda nw: -nw[1])

    # Outcome (winner vs loser) rate
    outcome = None
    for rid in rec_ids:
        for n, w in adj.get(rid, []):
            if n in ("Signal:winner", "Signal:loser"):
                outcome = {"label": n.split(":", 1)[1], "win_rate": round(w, 4)}
                break
        if outcome:
            break

    # Assemble the primary decision path (nodes in traversal order)
    path_ids = [company_id]
    if industry_id: path_ids.append(industry_id)
    if sector_id:   path_ids.append(sector_id)
    if regime_id:   path_ids.append(regime_id)

    return {
        "ticker":       ticker,
        "found":        True,
        "recommendations": [_node_summary(node_lookup, rid) for rid in rec_ids],
        "primary_path": [_node_summary(node_lookup, nid) for nid in path_ids],
        "portfolios":   [{"portfolio": p.split(":", 1)[1], "weight": round(w, 5)}
                            for p, w in portfolios],
        "champion":     (_node_summary(node_lookup, champion_id) if champion_id else None),
        "signals":      [{"signal": s.split(":", 1)[1], "strength": round(w, 4)}
                            for s, w in signals[:10]],
        "outcome":      outcome,
    }


def explain_top_recommendations(adj: algorithms.AdjMap,
                                    node_lookup: dict[str, Any],
                                    top_k: int = 20) -> list[dict]:
    """Explain every top-K rec by composite decision score."""
    ranked = [
        (n.attributes.get("composite_decision_score") or 0, n.label)
        for n in node_lookup.values()
        if n.entity_type == "Company" and n.attributes.get("composite_decision_score") is not None
    ]
    ranked.sort(key=lambda ts: -ts[0])
    return [explain_recommendation(adj, node_lookup, ticker) for _, ticker in ranked[:top_k]]
