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

    _banner("STEP 2/2 - Publish 7 outputs")
    published = publish.build_and_publish(result)
    for name in ["knowledge_graph.json", "entity_network.json", "relationship_matrix.json",
                   "company_network.json", "sector_network.json", "graph_statistics.json",
                   "knowledge_graph.parquet"]:
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

    _banner(f"DEV031 - DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
