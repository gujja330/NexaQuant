"""B5 · KG per-node community persistence hook · Sprint A · Batch B
CEO 2026-09-03 · forward-looking · never rewrites historical UNKNOWN.

Provides a helper that the daily KG runner should call to persist per-node
community IDs into a PIT snapshot. Historical archives that lack per-node
membership stay as UNKNOWN sentinel (see backfill_kg_pit_snapshots.py) ·
this hook only produces new snapshots from today forward.

Usage in the daily KG runner:

    from backend.research.enrichers.kg_persistence_hook import persist_pit_snapshot

    # After the KG runner has computed communities:
    communities = {ticker: community_id, ...}   # str : str
    persist_pit_snapshot(root, market, asof, communities,
                        graph_stats=..., algorithm="louvain",
                        modularity_q=0.86)

Snapshots land at:
    reports/research/kg_pit_snapshots/{market}/{asof}.json

with confidence="HIGH" (real per-node membership) vs. the backfill
scaffolds which are confidence="LOW".
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def persist_pit_snapshot(root: Path, market: str, asof: str,
                          communities: dict[str, str],
                          graph_stats: dict | None = None,
                          algorithm: str | None = None,
                          modularity_q: float | None = None) -> Path:
    """Write reports/research/kg_pit_snapshots/{market}/{asof}.json with real
    per-node community IDs. Idempotent · overwrites existing snapshot at
    same (market, asof).
    """
    out = root / "reports" / "research" / "kg_pit_snapshots" / market / f"{asof}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    clean: dict[str, str] = {}
    unknown_count = 0
    for k, v in (communities or {}).items():
        key = str(k).upper()
        val = str(v) if v is not None and str(v).strip() else "UNKNOWN"
        if val == "UNKNOWN": unknown_count += 1
        clean[key] = val
    payload = {
        "asof": asof, "market": market,
        "communities": clean,
        "n_nodes": len(clean),
        "n_communities": len(set(clean.values()) - {"UNKNOWN"}),
        "n_unknown": unknown_count,
        "confidence": "HIGH" if unknown_count == 0 else "MIXED",
        "source": "daily_kg_runner:live",
        "algorithm": algorithm or "unspecified",
        "modularity_q": modularity_q,
        "graph_stats": graph_stats or {},
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def is_snapshot_high_confidence(root: Path, market: str, asof: str) -> bool:
    """Loader helper · returns True if snapshot exists AND confidence==HIGH."""
    p = root / "reports" / "research" / "kg_pit_snapshots" / market / f"{asof}.json"
    if not p.exists(): return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("confidence") == "HIGH"
    except Exception:
        return False
