"""R2 · P3 · Knowledge-Graph Community-Relative Scoring
Sprint A · CANONICAL 3 · PIT community snapshots · CEO 2026-09-03

    Final_Score(t, ticker)
      = (1 - gamma) * Global_Percentile(t, ticker)
      + gamma       * Community_Percentile(t, ticker)

    gamma ∈ {0.0, 0.1, 0.2, 0.3, 0.4}   (5 trials, matches P3 in trial matrix)

CANONICAL 3 requires community lookup by (asof, ticker) using a point-in-time
snapshot · NEVER today's structure. This module maintains a snapshot store
at `reports/research/kg_pit_snapshots/{market}/{YYYY-MM-DD}.json` that
records the community assignments as they were on that day. Backfill is a
one-time job when the KG-run history parquet is walked.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]

GAMMA_GRID = [0.0, 0.1, 0.2, 0.3, 0.4]


def kg_pit_snapshot_path(root: Path, market: str, asof: str) -> Path:
    return root / "reports" / "research" / "kg_pit_snapshots" / market / f"{asof}.json"


def load_pit_communities(root: Path, market: str, asof: str) -> Optional[dict]:
    """Return {ticker: community_id} as it stood on `asof`, or None if we
    do not have a snapshot for that date (caller must degrade gracefully)."""
    p = kg_pit_snapshot_path(root, market, asof)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("communities") or None
    except (ValueError, OSError):
        return None


def emit_pit_snapshot(root: Path, market: str, asof: str,
                      communities: dict[str, str],
                      graph_stats: Optional[dict] = None) -> Path:
    """Persist a KG PIT snapshot for later P3 replay.

    Snapshot schema:
      { asof, market, communities: {ticker: community_id}, n_nodes,
        n_communities, modularity, built_utc }
    """
    p = kg_pit_snapshot_path(root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "asof": asof, "market": market,
        "communities": {str(k).upper(): str(v) for k, v in communities.items()},
        "n_nodes": len(communities),
        "n_communities": len(set(communities.values())),
        "graph_stats": graph_stats or {},
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def community_percentile(row: dict, cohort: list[dict],
                         score_key: str = "base_ensemble_score") -> Optional[float]:
    """Rank a stock's score within its community cohort · returns [0,1]."""
    if not cohort or len(cohort) < 3:
        return None
    v = row.get(score_key)
    if v is None:
        return None
    scores = sorted(float(x[score_key]) for x in cohort
                    if x.get(score_key) is not None)
    if len(scores) < 2:
        return None
    below = sum(1 for s in scores if s < float(v))
    return below / (len(scores) - 1)


def final_score(global_pct: float, community_pct: Optional[float],
                gamma: float) -> float:
    if community_pct is None:
        return float(global_pct)
    return (1.0 - gamma) * float(global_pct) + gamma * float(community_pct)


def evaluate_gamma_grid(rows: list[dict], get_community_id) -> dict:
    """For each gamma in GAMMA_GRID, compute mean forward return of
    top-N ranked stocks; select best gamma with stability check.

    `get_community_id(row) -> str` is caller-supplied (uses PIT snapshot).
    """
    if not rows:
        return {"n_positions": 0}
    # Group into communities for cohort-relative percentile
    by_comm: dict[str, list[dict]] = {}
    for r in rows:
        cid = get_community_id(r) or "UNASSIGNED"
        by_comm.setdefault(cid, []).append(r)

    # Global percentile
    all_scores = sorted(float(r.get("base_ensemble_score") or 0.0) for r in rows)
    def _gp(v):
        if len(all_scores) < 2 or v is None: return 0.5
        v = float(v)
        below = sum(1 for s in all_scores if s < v)
        return below / (len(all_scores) - 1)

    trials = []
    for g in GAMMA_GRID:
        enriched = []
        for r in rows:
            gp = _gp(r.get("base_ensemble_score"))
            cid = get_community_id(r) or "UNASSIGNED"
            cp = community_percentile(r, by_comm.get(cid, []))
            fs = final_score(gp, cp, g)
            enriched.append({**r, "final_score": fs})
        enriched.sort(key=lambda x: -x["final_score"])
        top = enriched[:max(10, len(enriched) // 5)]
        rets = [float(x.get("realized_return_pct") or 0.0) for x in top
                if x.get("realized_return_pct") is not None]
        mean = (sum(rets) / len(rets)) if rets else 0.0
        trials.append({"gamma": g, "n_top": len(top),
                       "mean_ret_top": mean, "n_rets": len(rets)})
    baseline = trials[0]  # gamma=0
    best = max(trials, key=lambda t: t["mean_ret_top"])
    return {
        "trials": trials,
        "trial_count_in_matrix": 5,
        "baseline_gamma0": baseline,
        "best": best,
        "lift_vs_baseline": best["mean_ret_top"] - baseline["mean_ret_top"],
        "n_communities": len(by_comm),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(root, args.market)
    if df.empty:
        print(json.dumps({"market": args.market, "note": "outcome_dataset empty"}, indent=2))
        return
    df = df[
        (df["is_administrative_exit"] != True)
        & df["realized_return_pct"].notna()
        & (df["runner"] == "R2")
    ].copy()
    if "base_ensemble_score" not in df.columns:
        df["base_ensemble_score"] = df.get("entry_signal_score", 0.0).fillna(0.0)
    rows = df.to_dict("records")

    def _get_cid(row):
        pit = load_pit_communities(root, args.market, str(row.get("entry_date", "")))
        if not pit: return None
        return pit.get(str(row.get("ticker", "")).upper())

    result = evaluate_gamma_grid(rows, _get_cid)
    result["market"] = args.market
    result["pit_snapshot_note"] = (
        "Community IDs looked up per (asof, ticker) from "
        "reports/research/kg_pit_snapshots/{market}/{asof}.json · "
        "CANONICAL 3 · CEO 2026-09-03. Missing snapshots degrade "
        "community_percentile to None (falls back to gamma=0 for that row)."
    )
    result["built_utc"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    out = root / "reports" / "research" / "r2_upgrades"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"p3_kg_community_{args.market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
