"""DEV031 · publish 7 outputs."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, tuple):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    return obj


def _nodes_export(nodes) -> list[dict]:
    return [_sanitize({"id": n.id, "entity_type": n.entity_type,
                          "label": n.label, "attributes": n.attributes})
             for n in nodes]


def _edges_export(edges) -> list[dict]:
    return [_sanitize({"src": e.src, "dst": e.dst, "relation": e.relation,
                          "weight": e.weight, "attributes": e.attributes})
             for e in edges]


def _adjacency_export(adj: dict) -> dict:
    return {k: [(nbr, round(float(w), 6)) for nbr, w in v] for k, v in adj.items()}


def build_and_publish(result: dict) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)

    nodes_json = _nodes_export(result["nodes"])
    edges_json = _edges_export(result["edges"])

    # ── knowledge_graph.json (headline) ───────────────────────────────
    with (REPORTS / "knowledge_graph.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "code_sha":        result["code_sha"],
            "dev_version":     result["dev_version"],
            "graph_stats":     result["graph_stats"],
            "n_nodes":         len(nodes_json),
            "n_edges":         len(edges_json),
            "governance":      "Advisory only; graph reflects validated AEGIS outputs only.",
        }), f, indent=2, default=str)

    # ── entity_network.json (all nodes + top influence scores) ─────────
    influence = result["influence"]
    with (REPORTS / "entity_network.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":  result["run_utc"],
            "nodes":    [{**n, "influence": round(influence.get(n["id"], 0.0), 6),
                            "degree_centrality": round(result["degree"].get(n["id"], 0.0), 6),
                            "strength":         round(result["strength"].get(n["id"], 0.0), 6)}
                          for n in nodes_json],
            "entity_types": sorted({n["entity_type"] for n in nodes_json}),
        }), f, indent=2, default=str)

    # ── relationship_matrix.json (edge list) ──────────────────────────
    with (REPORTS / "relationship_matrix.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "relation_types":  sorted({e["relation"] for e in edges_json}),
            "edges":           edges_json,
        }), f, indent=2, default=str)

    # ── company_network.json ─────────────────────────────────────────
    with (REPORTS / "company_network.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":     result["run_utc"],
            "adjacency":   _adjacency_export(result["company_subgraph"]),
            "n_companies": len(result["company_subgraph"]),
        }), f, indent=2, default=str)

    # ── sector_network.json ──────────────────────────────────────────
    with (REPORTS / "sector_network.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":    result["run_utc"],
            "adjacency":  _adjacency_export(result["sector_subgraph"]),
            "n_sectors":  len(result["sector_subgraph"]),
        }), f, indent=2, default=str)

    # ── graph_statistics.json ────────────────────────────────────────
    with (REPORTS / "graph_statistics.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       result["run_utc"],
            "graph_stats":   result["graph_stats"],
        }), f, indent=2, default=str)

    # ── knowledge_graph.parquet (edges as rows) ──────────────────────
    if edges_json:
        rows = []
        for e in edges_json:
            attrs_str = json.dumps(e.get("attributes") or {}, default=str)
            rows.append({
                "src":        e["src"],
                "dst":        e["dst"],
                "relation":   e["relation"],
                "weight":     float(e.get("weight") or 0.0),
                "attributes": attrs_str,
            })
        pd.DataFrame(rows).to_parquet(REPORTS / "knowledge_graph.parquet", index=False)

    # ── DEV031-B additions ─────────────────────────────────────────────

    # recommendation_paths.json
    if "recommendation_paths" in result:
        with (REPORTS / "recommendation_paths.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize({
                "run_utc":  result["run_utc"],
                "paths":    result["recommendation_paths"],
                "count":    len(result["recommendation_paths"]),
                "governance": "Advisory only; graph traversal explains existing recs. No inference.",
            }), f, indent=2, default=str)

    # community_clusters.json
    if "communities" in result:
        with (REPORTS / "community_clusters.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize({
                "run_utc":     result["run_utc"],
                "algorithm":   "deterministic label propagation",
                "modularity":  result.get("community_modularity"),
                "communities": result["communities"],
                "count":       len(result["communities"]),
            }), f, indent=2, default=str)

    # influence_propagation.json
    if "propagation" in result:
        with (REPORTS / "influence_propagation.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize({
                "run_utc":     result["run_utc"],
                "algorithm":   "personalized PageRank (damping=0.85, iterations=30)",
                "propagation": result["propagation"],
                "count":       len(result["propagation"]),
            }), f, indent=2, default=str)

    # graph_timeline.json
    if "timeline_diff" in result:
        with (REPORTS / "graph_timeline.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize({
                "run_utc":  result["run_utc"],
                "diff":     result["timeline_diff"],
            }), f, indent=2, default=str)

    # stress_scenarios.json (v1.6)
    if "stress_scenarios" in result:
        with (REPORTS / "stress_scenarios.json").open("w", encoding="utf-8") as f:
            json.dump(_sanitize({
                "run_utc":    result["run_utc"],
                "algorithm":  "personalized PageRank cascade + portfolio overlay",
                "scenarios":  result["stress_scenarios"],
                "count":      len(result["stress_scenarios"]),
                "governance": "Advisory. Simulated stress cascades. Not price forecasts.",
            }), f, indent=2, default=str)

    return {
        "n_nodes":         len(nodes_json),
        "n_edges":         len(edges_json),
        "n_communities":   len(result.get("communities", [])),
        "modularity":      result.get("community_modularity"),
        "n_explanations":  len(result.get("recommendation_paths", [])),
        "n_propagations":  len(result.get("propagation", [])),
        "top_influencer":  (result["graph_stats"]["top_influencers"][0]["node"]
                             if result["graph_stats"]["top_influencers"] else None),
    }
