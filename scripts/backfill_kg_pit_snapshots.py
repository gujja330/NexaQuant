"""Backfill KG PIT community snapshots from data/archive/*/knowledge_graph.json.

Sprint A · CANONICAL 3 companion · CEO 2026-09-03.

The archived knowledge_graph.json artifacts store aggregate graph stats
(n_nodes / n_edges / top_influencers / entity counts) but NOT per-node
community assignments. This backfill emits SCAFFOLDING snapshots that
capture what IS available and mark confidence=LOW on community IDs · so
downstream P3 code can be exercised end-to-end without fabricating
community memberships we don't actually have.

Emits:
  reports/research/kg_pit_snapshots/{market}/{asof}.json

Each snapshot marks:
  - communities: {ticker: "UNKNOWN"}   (structural presence only)
  - confidence: "LOW"
  - source: "archive_backfill_stub"

Going forward the daily KG runner should persist real per-node community
IDs · this backfill is a one-time historical scaffold.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _snapshot_dir(root: Path, market: str) -> Path:
    d = root / "reports" / "research" / "kg_pit_snapshots" / market
    d.mkdir(parents=True, exist_ok=True)
    return d


def _archive_files(root: Path):
    """Yield (yyyy-mm-dd, path) for every knowledge_graph.json in the archive."""
    base = root / "data" / "archive"
    if not base.exists(): return
    for year_dir in sorted(base.glob("*")):
        if not year_dir.is_dir(): continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir(): continue
            for day_dir in sorted(month_dir.glob("*")):
                if not day_dir.is_dir(): continue
                kg = day_dir / "bundle" / "knowledge_graph.json"
                if kg.exists():
                    date_str = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                    yield date_str, kg


def _emit_snapshot(root: Path, market: str, date_str: str, kg_data: dict) -> Path:
    tickers = []
    e = kg_data.get("entities_by_type", {}) if isinstance(kg_data, dict) else {}
    if isinstance(e, dict) and "Company" in e:
        cos = e["Company"]
        if isinstance(cos, list):
            tickers = [str(t).upper() for t in cos]
    elif isinstance(e, str):
        try:
            e = json.loads(e)
            cos = e.get("Company", [])
            tickers = [str(t).upper() for t in cos]
        except Exception:
            pass

    # Structural presence only · communities set to UNKNOWN sentinel · confidence LOW
    communities = {t: "UNKNOWN" for t in tickers}
    out = _snapshot_dir(root, market) / f"{date_str}.json"
    payload = {
        "asof": date_str, "market": market,
        "communities": communities,
        "n_nodes": kg_data.get("n_nodes", len(tickers)),
        "n_communities": 0,
        "confidence": "LOW",
        "source": "archive_backfill_stub",
        "note": (
            "Historical knowledge_graph.json artifacts stored aggregate "
            "graph stats but not per-node community IDs. This snapshot "
            "captures structural membership only · community_id set to "
            "UNKNOWN sentinel · downstream code degrades to gamma=0 for "
            "these dates until the daily KG runner is upgraded to persist "
            "per-node community assignments."
        ),
        "graph_stats": kg_data.get("graph_stats", {}),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), default="india",
                    help="Market to backfill · KG archives are India-primary")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india", "usa"] if args.market == "both" else [args.market]

    total = 0
    for market in markets:
        n = 0
        for date_str, kg_path in _archive_files(root):
            try:
                d = json.loads(kg_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            _emit_snapshot(root, market, date_str, d)
            n += 1
        print(f"[kg-pit-backfill] {market}: {n} snapshots written")
        total += n
    print(json.dumps({"total_snapshots": total, "markets": markets}, indent=2))


if __name__ == "__main__":
    main()
