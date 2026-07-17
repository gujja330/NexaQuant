"""DEV031 · Knowledge Graph CLI."""
from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from knowledge_graph.compute import engine                                              # noqa: E402
from knowledge_graph.publish import bundle as publish                                    # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def main() -> int:
    t0 = time.time()
    _banner("DEV031 - KNOWLEDGE GRAPH & RELATIONSHIP INTELLIGENCE")
    print(f"  time (IST): {_now_ist()}")

    _banner("STEP 1/2 - Build graph")
    result = engine.run(verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 - Publish 11 outputs (7 core + 4 DEV031-B)")
    published = publish.build_and_publish(result)
    for name in ["knowledge_graph.json", "entity_network.json", "relationship_matrix.json",
                   "company_network.json", "sector_network.json", "graph_statistics.json",
                   "knowledge_graph.parquet",
                   "recommendation_paths.json", "community_clusters.json",
                   "influence_propagation.json", "graph_timeline.json"]:
        print(f"  written: reports/{name}")

    stats = result["graph_stats"]
    _banner("GRAPH STATISTICS")
    print(f"  n_nodes:         {stats['n_nodes']}")
    print(f"  n_edges:         {stats['n_edges']}")
    print(f"  entity types:    {stats['n_entity_types']}")
    print(f"  relation types:  {stats['n_relation_types']}")
    print(f"  avg degree:      {stats['avg_degree']}")
    print()
    print("  entity counts:")
    for t, c in stats["entity_counts"].items():
        print(f"    {t:<24} {c}")
    print()
    print("  relation counts:")
    for r, c in stats["relation_counts"].items():
        print(f"    {r:<28} {c}")

    _banner("TOP 10 INFLUENCERS (PageRank-style)")
    for row in stats["top_influencers"][:10]:
        print(f"  {row['node']:<50} {row['score']:.6f}")

    _banner("COMMUNITY DETECTION")
    communities = result.get("communities", [])
    print(f"  discovered:   {len(communities)}")
    print(f"  modularity Q: {result.get('community_modularity')}")
    print()
    for c in communities[:6]:
        print(f"  {c['name']:<40} n={c['size']:<4} dom={c.get('dominant_industry')}")

    _banner("INFLUENCE PROPAGATION (sample sources)")
    for row in result.get("propagation", [])[:3]:
        print(f"  source: {row['source']}")
        for reach in row["top_reach_overall"][:5]:
            print(f"    -> {reach['node']:<45} score {reach['score']:.6f}")
        print()

    _banner("TIMELINE DIFF (vs prior run)")
    td = result.get("timeline_diff", {})
    if td.get("note"):
        print(f"  {td['note']}")
    else:
        print(f"  nodes delta: {td.get('n_nodes_delta')}   edges delta: {td.get('n_edges_delta')}")
        for et, delta in (td.get("entities_delta") or {}).items():
            print(f"    {et:<18} added {delta['n_added']:<3} removed {delta['n_removed']}")

    _banner("RECOMMENDATION EXPLANATIONS (top 3 samples)")
    for path in result.get("recommendation_paths", [])[:3]:
        if not path.get("found"):
            continue
        print(f"  {path['ticker']}")
        walk = " -> ".join(f"{n['entity_type']}:{n['label']}"
                              for n in path["primary_path"])
        print(f"    path:     {walk}")
        if path.get("champion"):
            print(f"    champion: {path['champion']['label']}")
        if path.get("outcome"):
            print(f"    outcome:  {path['outcome']['label']}  win_rate {path['outcome']['win_rate']}")

    _banner(f"DEV031 - DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
