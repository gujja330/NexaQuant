"""DEV031 · high-level query interface.

Every query returns explainable, evidence-based structured data — no LLM,
no summarisation beyond graph traversal + attribute lookup."""
from __future__ import annotations

from typing import Any

from knowledge_graph.lib import algorithms


def _split_id(node_id: str) -> tuple[str, str]:
    if ":" not in node_id:
        return ("", node_id)
    t, label = node_id.split(":", 1)
    return t, label


def related_companies(adj: algorithms.AdjMap, ticker: str,
                        node_lookup: dict[str, Any], top_k: int = 10) -> list[dict]:
    """Companies most strongly connected to `ticker` (competitors + industry peers)."""
    src = f"Company:{ticker}"
    if src not in adj:
        return []
    peers = [(n, w) for n, w in adj[src] if n.startswith("Company:")]
    peers.sort(key=lambda nw: -nw[1])
    out = []
    for pid, w in peers[:top_k]:
        _, label = _split_id(pid)
        node = node_lookup.get(pid)
        out.append({
            "ticker":       label,
            "strength":     round(w, 4),
            "industry":     (node.attributes.get("industry") if node else None),
            "score":        (node.attributes.get("score") if node else None),
            "recommendation": (node.attributes.get("recommendation") if node else None),
        })
    return out


def strongest_competitors(adj: algorithms.AdjMap, ticker: str,
                              node_lookup: dict[str, Any], top_k: int = 5) -> list[dict]:
    return related_companies(adj, ticker, node_lookup, top_k=top_k)


def portfolio_dependencies(adj: algorithms.AdjMap, portfolio_label: str,
                              node_lookup: dict[str, Any]) -> list[dict]:
    pid = f"Portfolio:{portfolio_label}"
    if pid not in adj:
        return []
    holdings = [(n, w) for n, w in adj[pid] if n.startswith("Company:")]
    holdings.sort(key=lambda nw: -nw[1])
    out = []
    for cid, w in holdings:
        _, label = _split_id(cid)
        node = node_lookup.get(cid)
        out.append({
            "ticker":   label,
            "weight":   round(w, 5),
            "sector":   (node.attributes.get("sector") if node else None),
            "industry": (node.attributes.get("industry") if node else None),
            "score":    (node.attributes.get("score") if node else None),
        })
    return out


def explain_recommendation_relationships(adj: algorithms.AdjMap, ticker: str,
                                              node_lookup: dict[str, Any]) -> dict:
    """Show all edges touching a company's Recommendation node(s)."""
    rec_ids = [k for k in adj.keys()
                 if k.startswith("Recommendation:") and k.split(":", 1)[1].startswith(f"{ticker}·")]
    if not rec_ids:
        return {"ticker": ticker, "recs": []}
    result = []
    for rid in rec_ids:
        _, label = _split_id(rid)
        signals = [{"signal": n.split(":", 1)[1], "weight": round(w, 4)}
                     for n, w in adj[rid] if n.startswith("Signal:")]
        outcomes = [{"outcome": n.split(":", 1)[1], "weight": round(w, 4)}
                       for n, w in adj[rid] if n.startswith("Signal:")
                       and n.split(":", 1)[1] in ("winner", "loser")]
        companies = [{"company": n.split(":", 1)[1], "weight": round(w, 4)}
                        for n, w in adj[rid] if n.startswith("Company:")]
        result.append({
            "recommendation":  label,
            "connected_signals": [s for s in signals if s["signal"] not in ("winner", "loser")],
            "outcomes":        outcomes,
            "companies":       companies,
        })
    return {"ticker": ticker, "recs": result}


def explain_sector_influence(adj: algorithms.AdjMap, node_lookup: dict[str, Any],
                                  top_k: int = 5) -> list[dict]:
    """Rank sectors by their outgoing influence (via companies + regime)."""
    sector_ids = [k for k in adj.keys() if k.startswith("Sector:")]
    weighted = []
    for sid in sector_ids:
        _, label = _split_id(sid)
        neighbours = adj[sid]
        strength = sum(w for _, w in neighbours)
        # companies below this sector (via industry)
        industries = [n for n, _ in neighbours if n.startswith("Industry:")]
        n_companies = 0
        for iid in industries:
            for nn, _ in adj.get(iid, []):
                if nn.startswith("Company:"):
                    n_companies += 1
        weighted.append({
            "sector":       label,
            "strength":     round(strength, 3),
            "n_industries": len(industries),
            "n_companies":  n_companies,
        })
    weighted.sort(key=lambda x: -x["strength"])
    return weighted[:top_k]


def signal_propagation(adj: algorithms.AdjMap, signal_label: str) -> dict:
    """From a Signal node, list which Recommendations (and thus Companies) it touches."""
    sid = f"Signal:{signal_label}"
    if sid not in adj:
        return {"signal": signal_label, "recs": [], "companies": []}
    recs = [(n, w) for n, w in adj[sid] if n.startswith("Recommendation:")]
    companies = set()
    for rid, _ in recs:
        _, label = _split_id(rid)
        # label is 'TICKER·REC_TYPE'
        if "·" in label:
            companies.add(label.split("·")[0])
    return {
        "signal":    signal_label,
        "n_recs":    len(recs),
        "n_companies": len(companies),
        "top_recs":  [{"rec": r.split(":", 1)[1], "weight": round(w, 4)} for r, w in recs[:10]],
        "companies": sorted(companies)[:20],
    }
