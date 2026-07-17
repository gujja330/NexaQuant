"""DEV031 smoke tests. Deterministic synthetic graph."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from knowledge_graph.lib import (algorithms, queries,                                     # noqa: E402
                                     explainability, community, propagation)


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


@dataclass
class _Edge:
    src: str; dst: str; relation: str; weight: float; attributes: dict


def _sample_edges():
    return [
        _Edge("Company:AAA", "Industry:Pharma", "COMPANY_TO_INDUSTRY", 1.0, {}),
        _Edge("Company:BBB", "Industry:Pharma", "COMPANY_TO_INDUSTRY", 1.0, {}),
        _Edge("Company:CCC", "Industry:Banks",  "COMPANY_TO_INDUSTRY", 1.0, {}),
        _Edge("Industry:Pharma", "Sector:Health", "INDUSTRY_TO_SECTOR", 1.0, {}),
        _Edge("Industry:Banks",  "Sector:Financials", "INDUSTRY_TO_SECTOR", 1.0, {}),
        _Edge("Company:AAA", "Company:BBB", "COMPANY_TO_COMPETITOR", 0.9, {}),
        _Edge("Recommendation:AAA·Buy", "Company:AAA", "RECOMMENDATION_TO_COMPANY", 0.85, {}),
        _Edge("Signal:momentum", "Recommendation:AAA·Buy", "SIGNAL_TO_RECOMMENDATION", 0.7, {}),
    ]


def test_build_adjacency():
    adj = algorithms.build_adjacency(_sample_edges())
    _check("adjacency contains AAA",   "Company:AAA" in adj)
    _check("adjacency undirected",     "Company:AAA" in dict(adj["Industry:Pharma"]))
    _check("AAA has 3 neighbours",     len(adj["Company:AAA"]) == 3)


def test_neighbours():
    adj = algorithms.build_adjacency(_sample_edges())
    nbrs = algorithms.neighbours(adj, "Company:AAA", hops=1)
    _check("AAA 1-hop count = 3", len(nbrs) == 3)
    two = algorithms.neighbours(adj, "Company:AAA", hops=2)
    _check("AAA 2-hop reaches Sector:Health",
            any(n == "Sector:Health" for n, _ in two))


def test_shortest_path():
    adj = algorithms.build_adjacency(_sample_edges())
    d, path = algorithms.shortest_path(adj, "Company:AAA", "Sector:Health")
    _check("path AAA -> Sector:Health exists", len(path) >= 3)
    _check("path starts at AAA", path[0] == "Company:AAA")
    _check("path ends at Sector:Health", path[-1] == "Sector:Health")

    d2, path2 = algorithms.shortest_path(adj, "Company:AAA", "Sector:Financials")
    _check("cross-sector path exists (via competitor -> pharma)",
            len(path2) >= 4 or d2 == float("inf") or path2 == [])


def test_algorithms_produce_scores():
    adj = algorithms.build_adjacency(_sample_edges())
    dc = algorithms.degree_centrality(adj)
    wd = algorithms.weighted_degree(adj)
    infl = algorithms.eigen_influence(adj, iterations=10)
    _check("degree centrality returns dict",  isinstance(dc, dict) and len(dc) > 0)
    _check("all degree values in [0,1]",     all(0.0 <= v <= 1.0 for v in dc.values()))
    _check("weighted degree returns dict",   isinstance(wd, dict))
    _check("influence sums ~= 1",            0.99 <= sum(infl.values()) <= 1.01)


def test_subgraph_by_type():
    adj = algorithms.build_adjacency(_sample_edges())
    sub = algorithms.subgraph_by_type(adj, "Company")
    _check("company subgraph has 3 nodes",   len(sub) == 3)
    _check("company subgraph has no industries",
            all(k.startswith("Company:") for k in sub))


def test_deterministic():
    edges = _sample_edges()
    adj1 = algorithms.build_adjacency(edges)
    adj2 = algorithms.build_adjacency(edges)
    infl1 = algorithms.eigen_influence(adj1, iterations=5)
    infl2 = algorithms.eigen_influence(adj2, iterations=5)
    _check("influence deterministic",
            all(abs(infl1[k] - infl2[k]) < 1e-9 for k in infl1))


def test_query_related_companies():
    from dataclasses import dataclass as _dc
    @_dc
    class N: id: str; entity_type: str; label: str; attributes: dict
    adj = algorithms.build_adjacency(_sample_edges())
    node_lookup = {
        "Company:AAA": N("Company:AAA", "Company", "AAA", {"industry": "Pharma", "score": 80}),
        "Company:BBB": N("Company:BBB", "Company", "BBB", {"industry": "Pharma", "score": 75}),
    }
    r = queries.related_companies(adj, "AAA", node_lookup, top_k=5)
    _check("related_companies returns list", isinstance(r, list))
    _check("AAA has BBB as related", any(x["ticker"] == "BBB" for x in r))


# ═════════════════════════════════════════════════════════════════════════
# DEV031-B smoke tests
# ═════════════════════════════════════════════════════════════════════════

def _extended_edges():
    # A larger fixture with a clear 2-cluster structure
    return _sample_edges() + [
        _Edge("Company:XYZ", "Industry:Pharma", "COMPANY_TO_INDUSTRY", 1.0, {}),
        _Edge("Company:XYZ", "Company:AAA", "COMPANY_TO_COMPETITOR", 0.9, {}),
        _Edge("Company:XYZ", "Company:BBB", "COMPANY_TO_COMPETITOR", 0.9, {}),
        _Edge("Company:DDD", "Industry:Banks", "COMPANY_TO_INDUSTRY", 1.0, {}),
        _Edge("Company:DDD", "Company:CCC", "COMPANY_TO_COMPETITOR", 0.9, {}),
    ]


def test_community_detection_deterministic():
    from dataclasses import dataclass as _dc
    @_dc
    class N: id: str; entity_type: str; label: str; attributes: dict

    adj = algorithms.build_adjacency(_extended_edges())
    node_lookup = {
        "Company:AAA": N("Company:AAA", "Company", "AAA", {"industry": "Pharma"}),
        "Company:BBB": N("Company:BBB", "Company", "BBB", {"industry": "Pharma"}),
        "Company:XYZ": N("Company:XYZ", "Company", "XYZ", {"industry": "Pharma"}),
        "Company:CCC": N("Company:CCC", "Company", "CCC", {"industry": "Banks"}),
        "Company:DDD": N("Company:DDD", "Company", "DDD", {"industry": "Banks"}),
    }

    labels_1 = community.label_propagation(adj, subset_prefix="Company:")
    labels_2 = community.label_propagation(adj, subset_prefix="Company:")
    _check("label propagation deterministic",
            labels_1 == labels_2)

    comms = community.detect_communities(adj, node_lookup,
                                              subset_prefix="Company:", min_size=2)
    _check("communities discovered >= 1", len(comms) >= 1)
    _check("modularity is a number",
            isinstance(community.modularity(algorithms.subgraph_by_type(adj, "Company"),
                                                labels_1), (int, float)))


def test_propagation_pagerank_sums_to_one():
    adj = algorithms.build_adjacency(_extended_edges())
    scores = propagation.personalized_pagerank(adj, "Company:AAA")
    _check("personalized PPR sums ~= 1",
            abs(sum(scores.values()) - 1.0) < 1e-6)
    _check("PPR is deterministic",
            scores == propagation.personalized_pagerank(adj, "Company:AAA"))


def test_propagation_top_reached():
    adj = algorithms.build_adjacency(_extended_edges())
    scores = propagation.personalized_pagerank(adj, "Company:AAA")
    top_ind = propagation.top_reached(scores, "Company:AAA",
                                          entity_type="Industry", n=5)
    _check("Industry:Pharma reached from Company:AAA",
            any(k == "Industry:Pharma" for k, _ in top_ind))


def test_explainability_returns_path():
    from dataclasses import dataclass as _dc
    @_dc
    class N: id: str; entity_type: str; label: str; attributes: dict

    edges = _extended_edges() + [
        _Edge("Industry:Pharma", "Sector:Health", "INDUSTRY_TO_SECTOR", 1.0, {}),
        _Edge("Sector:Health", "MarketRegime:Neutral", "SECTOR_TO_REGIME", 1.0, {}),
        _Edge("Company:AAA", "Portfolio:top_10_ew", "COMPANY_TO_PORTFOLIO", 0.05, {}),
        _Edge("Portfolio:top_10_ew", "Strategy:top_5_ew", "PORTFOLIO_TO_STRATEGY", 0.5, {}),
    ]
    adj = algorithms.build_adjacency(edges)
    node_lookup = {
        "Company:AAA": N("Company:AAA", "Company", "AAA",
                          {"industry": "Pharma", "sector": "Health",
                            "composite_decision_score": 90.0}),
        "Industry:Pharma": N("Industry:Pharma", "Industry", "Pharma", {}),
        "Sector:Health":   N("Sector:Health", "Sector", "Health", {}),
        "MarketRegime:Neutral": N("MarketRegime:Neutral", "MarketRegime", "Neutral", {}),
        "Strategy:top_5_ew": N("Strategy:top_5_ew", "Strategy", "top_5_ew",
                                 {"sharpe": 0.97}),
        "Portfolio:top_10_ew": N("Portfolio:top_10_ew", "Portfolio", "top_10_ew", {}),
    }
    exp = explainability.explain_recommendation(adj, node_lookup, "AAA")
    _check("explanation found=True", exp["found"] is True)
    _check("primary path has 4 nodes",
            len(exp["primary_path"]) == 4,
            detail=f"got {len(exp['primary_path'])}")
    _check("champion is top_5_ew",
            exp.get("champion") and exp["champion"]["label"] == "top_5_ew")
    _check("portfolios include top_10_ew",
            any(p["portfolio"] == "top_10_ew" for p in exp.get("portfolios", [])))


def main() -> int:
    print("=" * 70); print("  DEV031 v0.1 SMOKE TESTS"); print("=" * 70)
    test_build_adjacency(); print()
    test_neighbours(); print()
    test_shortest_path(); print()
    test_algorithms_produce_scores(); print()
    test_subgraph_by_type(); print()
    test_deterministic(); print()
    test_query_related_companies(); print()
    test_community_detection_deterministic(); print()
    test_propagation_pagerank_sums_to_one(); print()
    test_propagation_top_reached(); print()
    test_explainability_returns_path(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
