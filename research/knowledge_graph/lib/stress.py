"""DEV031 · v1.6 · stress propagation & scenario cascade.

Given a stress source (a MarketRegime shift, a Sector shock, a Signal
firing, a specific Company collapse), compute:

  1. Personalized PageRank cascade — how strongly the stress reaches
     every other node (uses existing lib/propagation.py).
  2. Portfolio exposure — how much of the current DEV022 portfolio
     sits in the cascade's high-reach zone.
  3. Sector contagion — which sectors are next-most-affected after
     the stress source's own sector.
  4. Position-level stress impact — top-K holdings ranked by reach
     from the stress source.

Scenarios are declarative: a name + a source-node id + a description.
No new data feeds; leverages the already-built graph."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from knowledge_graph.lib import algorithms, propagation


_ROOT = Path(__file__).resolve().parents[3]


def _load_portfolio_weights() -> dict[str, float]:
    """Load current balanced/hrp portfolio holdings as {ticker: weight}."""
    p = _ROOT / "reports" / "portfolio.json"
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    portfolios = j.get("portfolios", []) or []
    ref = None
    for pt in portfolios:
        if pt.get("portfolio_type") == "balanced" and pt.get("allocator") == "hrp":
            ref = pt; break
    if ref is None and portfolios:
        ref = portfolios[0]
    if ref is None:
        return {}
    positions = ref.get("positions", []) or []
    return {p["ticker"]: float(p.get("weight", 0.0)) for p in positions}


# ────────────────────────────────────────────────────────────────
# CANONICAL SCENARIOS
# ────────────────────────────────────────────────────────────────
def canonical_scenarios(adj: algorithms.AdjMap) -> list[dict]:
    """A small library of stress scenarios. Each names a source node
    that must exist in the graph — sources absent from the current
    graph are silently skipped."""
    scenarios = []

    # 1. Regime shift to Risk-Off
    src = "MarketRegime:Risk-Off"
    if src in adj:
        scenarios.append({"name": "regime_shift_risk_off",
                             "source": src,
                             "description": "Regime flips to Risk-Off; broad-market drawdown."})

    # 2. Signal:loser propagation — historically-loser recommendations amplify
    src = "Signal:loser"
    if src in adj:
        scenarios.append({"name": "loser_signal_amplification",
                             "source": src,
                             "description": "Loser signal amplifies across recommendations."})

    # 3. Sector shock — pick the largest sector by connectivity
    sector_ids = [k for k in adj if k.startswith("Sector:")]
    if sector_ids:
        # Sort by neighbour count (sector with most industries)
        sector_ids.sort(key=lambda k: -len([n for n, _ in adj.get(k, []) if n.startswith("Industry:")]))
        src = sector_ids[0]
        scenarios.append({"name": f"sector_shock_{src.split(':', 1)[1].lower().replace(' ', '_')}",
                             "source": src,
                             "description": f"Sector-specific shock on {src.split(':', 1)[1]}."})

    # 4. Company-specific collapse — pick the top-influence company
    company_ids = [k for k in adj if k.startswith("Company:")]
    if company_ids:
        # Rank by weighted degree
        deg = {k: sum(w for _, w in adj[k]) for k in company_ids}
        top_company = max(deg, key=deg.get) if deg else None
        if top_company:
            scenarios.append({"name": f"company_collapse_{top_company.split(':', 1)[1].lower()}",
                                 "source": top_company,
                                 "description": f"Idiosyncratic collapse of "
                                                 f"{top_company.split(':', 1)[1]}."})

    # 5. Champion Strategy failure
    strat_ids = [k for k in adj if k.startswith("Strategy:")]
    if strat_ids:
        src = sorted(strat_ids)[0]
        scenarios.append({"name": "champion_strategy_failure",
                             "source": src,
                             "description": f"Champion {src.split(':', 1)[1]} degrades sharply."})

    return scenarios


# ────────────────────────────────────────────────────────────────
# SIMULATION
# ────────────────────────────────────────────────────────────────
def simulate_stress(adj: algorithms.AdjMap,
                       node_lookup: dict,
                       scenario: dict,
                       portfolio_weights: dict[str, float] | None = None,
                       reach_percentile: float = 90.0) -> dict:
    """Simulate a stress cascade from `scenario['source']`.

    Returns:
      - top_reached nodes (by personalized PageRank score)
      - per_sector_reach
      - portfolio_exposure — sum of portfolio weights in the
        high-reach zone (nodes above `reach_percentile`)
      - impacted_positions — the actual holdings hit"""
    src = scenario["source"]
    if src not in adj:
        return {"scenario": scenario["name"], "error": "source not in graph"}

    scores = propagation.personalized_pagerank(adj, src)

    # Rank all nodes by reach
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])

    # High-reach threshold
    positive_scores = [s for _, s in ranked if s > 0]
    threshold = float(np.percentile(positive_scores, reach_percentile)) \
                    if positive_scores else 0.0

    # Company-level breakdown
    company_scores = [(n, s) for n, s in ranked if n.startswith("Company:")]
    company_scores.sort(key=lambda kv: -kv[1])

    # Sector aggregation
    sector_agg: dict[str, float] = {}
    for cid, s in company_scores:
        node = node_lookup.get(cid)
        if node is None:
            continue
        sec = (node.attributes or {}).get("sector") or "Unknown"
        sector_agg[sec] = sector_agg.get(sec, 0.0) + s
    sector_ranked = sorted(sector_agg.items(), key=lambda kv: -kv[1])

    # Portfolio exposure
    portfolio_weights = portfolio_weights or {}
    exposure = 0.0
    impacted_positions = []
    for ticker, weight in portfolio_weights.items():
        cid = f"Company:{ticker}"
        s = scores.get(cid, 0.0)
        if s > threshold:
            exposure += weight
            impacted_positions.append({
                "ticker":   ticker,
                "weight":   round(weight, 5),
                "reach":    round(s, 6),
                "in_stress_zone": True,
            })

    impacted_positions.sort(key=lambda x: -x["reach"])

    return {
        "scenario":               scenario["name"],
        "description":            scenario.get("description", ""),
        "source":                 src,
        "reach_threshold_pct":    reach_percentile,
        "reach_threshold":        round(threshold, 6),
        "top_reached_nodes":      [{"node": n, "score": round(s, 6)}
                                     for n, s in ranked[:20] if n != src],
        "top_reached_companies":  [{"node": n, "score": round(s, 6)}
                                     for n, s in company_scores[:15]],
        "sector_contagion":       [{"sector": s, "total_reach": round(v, 6)}
                                     for s, v in sector_ranked[:10]],
        "portfolio_exposure":     round(exposure, 4),
        "n_impacted_positions":   len(impacted_positions),
        "impacted_positions":     impacted_positions[:20],
    }


def run_all_scenarios(adj: algorithms.AdjMap,
                         node_lookup: dict,
                         portfolio_weights: dict[str, float] | None = None) -> list[dict]:
    """Run every canonical scenario and return the list of simulation
    reports."""
    weights = portfolio_weights if portfolio_weights is not None else _load_portfolio_weights()
    scenarios = canonical_scenarios(adj)
    return [simulate_stress(adj, node_lookup, sc, portfolio_weights=weights)
             for sc in scenarios]
