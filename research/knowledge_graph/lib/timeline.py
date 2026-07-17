"""DEV031 · graph timeline & versioning.

Every DEV031 run appends a compressed snapshot of the graph to a persistent
parquet under `data/market_intelligence/derived/`. The diff-vs-prior report
answers: what changed since the last run?

Design choices:
- Snapshot stores counts + top-influencers only (not the full edge list —
  that would explode the parquet). The full graph remains reproducible from
  the DEV017-DEV030 outputs as they existed at each run's `code_sha`.
- Diffs are node-level (added/removed) plus rank-drift of top influencers.
- All state is append-only; snapshots are never overwritten."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS = _ROOT / "data" / "market_intelligence" / "derived" / "graph_snapshots.parquet"


def _serialize(obj):
    if isinstance(obj, (list, dict)):
        return json.dumps(obj, default=str)
    return obj


def snapshot_current(result: dict) -> dict:
    """Compressed row-shaped snapshot of the current run's graph."""
    stats = result["graph_stats"]
    nodes = result["nodes"]
    entity_ids_by_type = {}
    for n in nodes:
        entity_ids_by_type.setdefault(n.entity_type, []).append(n.label)
    for k in entity_ids_by_type:
        entity_ids_by_type[k].sort()

    return {
        "run_utc":            result["run_utc"],
        "code_sha":           result["code_sha"],
        "n_nodes":            stats["n_nodes"],
        "n_edges":            stats["n_edges"],
        "avg_degree":         stats["avg_degree"],
        "entity_counts":      _serialize(stats["entity_counts"]),
        "relation_counts":    _serialize(stats["relation_counts"]),
        "top_influencers":    _serialize([r["node"] for r in stats["top_influencers"][:20]]),
        "entities_by_type":   _serialize(entity_ids_by_type),
    }


def append_snapshot(row: dict) -> None:
    SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame([row])
    if SNAPSHOTS.exists():
        try:
            old = pd.read_parquet(SNAPSHOTS)
            combined = pd.concat([old, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df
    combined.to_parquet(SNAPSHOTS, index=False)


def diff_vs_prior(current_row: dict) -> dict:
    """Compare the just-appended snapshot vs the previous one."""
    if not SNAPSHOTS.exists():
        return {"note": "no history yet — this is the first snapshot", "changes": {}}
    try:
        hist = pd.read_parquet(SNAPSHOTS)
    except Exception:
        return {"note": "history parquet unreadable", "changes": {}}
    if len(hist) < 2:
        return {"note": "only one snapshot on file (the current) — no diff available",
                 "changes": {}}

    prior = hist.sort_values("run_utc").iloc[-2]  # second-to-last is prior
    curr = current_row

    def _load(obj):
        if isinstance(obj, str):
            try:
                return json.loads(obj)
            except Exception:
                return {}
        return obj or {}

    prior_by_type = _load(prior.get("entities_by_type"))
    curr_by_type = _load(curr.get("entities_by_type"))

    changes_by_type = {}
    for et in sorted(set(prior_by_type.keys()) | set(curr_by_type.keys())):
        prior_set = set(prior_by_type.get(et, []))
        curr_set = set(curr_by_type.get(et, []))
        added = sorted(curr_set - prior_set)
        removed = sorted(prior_set - curr_set)
        if added or removed:
            changes_by_type[et] = {
                "added":   added[:20],
                "removed": removed[:20],
                "n_added":   len(added),
                "n_removed": len(removed),
            }

    prior_infl = _load(prior.get("top_influencers"))
    curr_infl = _load(curr.get("top_influencers"))
    prior_rank = {n: i + 1 for i, n in enumerate(prior_infl)}
    curr_rank  = {n: i + 1 for i, n in enumerate(curr_infl)}
    rank_changes = []
    for n in curr_infl[:20]:
        pr = prior_rank.get(n)
        cr = curr_rank.get(n)
        if pr is None:
            rank_changes.append({"node": n, "prior_rank": None, "current_rank": cr,
                                   "delta": None, "note": "new to top-20"})
        elif pr != cr:
            rank_changes.append({"node": n, "prior_rank": pr, "current_rank": cr,
                                   "delta": pr - cr})

    dropped_out = [n for n in prior_infl[:20] if n not in curr_infl[:20]]

    return {
        "prior_run_utc":     str(prior.get("run_utc")),
        "current_run_utc":   str(curr.get("run_utc")),
        "n_nodes_delta":     int(curr["n_nodes"] - int(prior.get("n_nodes", 0))),
        "n_edges_delta":     int(curr["n_edges"] - int(prior.get("n_edges", 0))),
        "avg_degree_delta":  round(float(curr["avg_degree"]) - float(prior.get("avg_degree", 0.0)), 4),
        "entities_delta":    changes_by_type,
        "influencer_rank_changes": rank_changes,
        "dropped_from_top20": dropped_out,
    }


def load_history() -> pd.DataFrame:
    if not SNAPSHOTS.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(SNAPSHOTS)
    except Exception:
        return pd.DataFrame()
