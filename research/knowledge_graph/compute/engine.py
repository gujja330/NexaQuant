"""DEV031 · orchestration.

Builds the full graph, computes statistics + top nodes by influence, produces
subgraphs (company / sector / industry) for the publish layer."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from knowledge_graph.lib import entities, relationships, algorithms                    # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def run(verbose: bool = True) -> dict:
    if verbose:
        print("  step 1/4 · extract entities from DEV017-DEV030 outputs")

    nodes = entities.extract_all()
    if not nodes:
        return {"error": "no entities found — run DEV017-DEV030 first"}

    node_lookup = {n.id: n for n in nodes}

    if verbose:
        print(f"    extracted {len(nodes)} entities")
        by_type = {}
        for n in nodes:
            by_type[n.entity_type] = by_type.get(n.entity_type, 0) + 1
        for t, c in sorted(by_type.items(), key=lambda kv: -kv[1]):
            print(f"      {t:<20} {c}")

    if verbose:
        print("  step 2/4 · materialise relationships")
    edges = relationships.build_all_edges()

    if verbose:
        by_rel = {}
        for e in edges:
            by_rel[e.relation] = by_rel.get(e.relation, 0) + 1
        print(f"    {len(edges)} edges across {len(by_rel)} relation types")
        for r, c in sorted(by_rel.items(), key=lambda kv: -kv[1]):
            print(f"      {r:<28} {c}")

    if verbose:
        print("  step 3/4 · build adjacency + compute algorithms")
    adj = algorithms.build_adjacency(edges)
    n_nodes = len(adj)
    n_edges = sum(len(v) for v in adj.values()) // 2  # undirected

    degrees = algorithms.degree_centrality(adj)
    strengths = algorithms.weighted_degree(adj)
    influence = algorithms.eigen_influence(adj, iterations=25)

    top_influencers = algorithms.top_by(influence, n=25)
    top_by_degree = algorithms.top_by(degrees, n=25)
    top_by_strength = algorithms.top_by(strengths, n=25)

    if verbose:
        print(f"    top influencer: {top_influencers[0][0] if top_influencers else 'none'}")

    if verbose:
        print("  step 4/4 · extract subgraphs")
    company_subgraph = algorithms.subgraph_by_type(adj, "Company")
    sector_subgraph = algorithms.subgraph_by_type(adj, "Sector")
    industry_subgraph = algorithms.subgraph_by_type(adj, "Industry")

    graph_stats = {
        "n_nodes":     n_nodes,
        "n_edges":     n_edges,
        "n_entity_types": len({n.entity_type for n in nodes}),
        "n_relation_types": len({e.relation for e in edges}),
        "avg_degree":  round(2 * n_edges / max(n_nodes, 1), 3),
        "top_influencers":  [{"node": nid, "score": round(s, 6)} for nid, s in top_influencers],
        "top_by_degree":    [{"node": nid, "score": round(s, 6)} for nid, s in top_by_degree],
        "top_by_strength":  [{"node": nid, "score": round(s, 6)} for nid, s in top_by_strength],
        "entity_counts":    {t: sum(1 for n in nodes if n.entity_type == t) for t in
                              sorted({n.entity_type for n in nodes})},
        "relation_counts":  {r: sum(1 for e in edges if e.relation == r) for r in
                              sorted({e.relation for e in edges})},
    }

    return {
        "run_utc":            datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":           _git_sha(),
        "dev_version":        "DEV031 v0.1",
        "nodes":              nodes,
        "edges":              edges,
        "adjacency":          adj,
        "node_lookup":        node_lookup,
        "influence":          influence,
        "degree":             degrees,
        "strength":           strengths,
        "company_subgraph":   company_subgraph,
        "sector_subgraph":    sector_subgraph,
        "industry_subgraph":  industry_subgraph,
        "graph_stats":        graph_stats,
    }
