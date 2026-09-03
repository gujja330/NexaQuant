"""R1 · Knowledge-Graph Community Group Filter
Sprint A · CEO 2026-09-03 GAP-5

Replaces static GICS sector filter with KG-community grouping. Formula:

    Group_Composite_Score(g)
      = 0.4 * trailing_20d_realized_pnl_pct(g)
      + 0.3 * trailing_10d_news_sentiment(g)
      + 0.2 * trailing_60d_relative_strength(g)
      + 0.1 * regime_multiplier(g)

Weights are walk-forward tuned (not hardcoded once initial calibration
runs). The initial weights above are the pasted-plan §8 starting point.

Filter is COMPUTED daily and exposed at
  reports/research/r1_kg_group_filter_{market}.json

R1 advisory picks are then annotated with their community's Group_Composite_Score
so the operator can see WHICH community context a pick sits in. Static
GICS sectors are NEVER used for filtering here.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_WEIGHTS = {
    "w_pnl_20d":    0.4,
    "w_news_10d":   0.3,
    "w_rs_60d":     0.2,
    "w_regime":     0.1,
}


def _load_pit_communities(root: Path, market: str, asof: str) -> Optional[dict]:
    """Load KG PIT community snapshot for (asof) · CANONICAL 3 compliance."""
    p = root / "reports" / "research" / "kg_pit_snapshots" / market / f"{asof}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("communities") or None
    except (ValueError, OSError):
        return None


def _regime_multiplier(regime: str) -> float:
    """Map regime label → [0, 1] friendly multiplier (clipped [0.7, 1.3])."""
    m = {
        "NORMAL": 1.0, "RECOVERY": 1.2, "WEAKENING": 0.85,
        "RISK_OFF": 0.75, "CRASH": 0.7, "UNKNOWN": 1.0,
    }
    return m.get(str(regime or "UNKNOWN").upper(), 1.0)


def group_composite_score(pnl_20d: float, news_sent_10d: float,
                          rel_str_60d: float, regime: str,
                          weights: dict = DEFAULT_WEIGHTS) -> float:
    """CEO §8 formula · sum of weighted components."""
    return (
        weights["w_pnl_20d"] * float(pnl_20d)
        + weights["w_news_10d"] * float(news_sent_10d)
        + weights["w_rs_60d"] * float(rel_str_60d)
        + weights["w_regime"] * _regime_multiplier(regime)
    )


def build_r1_kg_filter(root: Path, market: str, asof: str,
                       weights: dict = DEFAULT_WEIGHTS) -> dict:
    """Compute Group_Composite_Score for every community in the PIT snapshot.

    Inputs per community (aggregated across its member tickers):
      trailing 20d realized PnL % · from outcome_dataset
      trailing 10d news sentiment  · from data/market_intelligence/news/*
      trailing 60d relative strength · from data/raw/{market}/*.parquet
      current regime                · from reports/regime/*.json (fallback UNKNOWN)

    Missing inputs default to 0 (multiplier=1 for regime) · exposed in the
    per-community `data_completeness` field so consumers can see coverage.
    """
    pit = _load_pit_communities(root, market, asof)
    if pit is None:
        return {
            "market": market, "asof": asof,
            "note": "KG PIT snapshot missing · community filter unavailable · "
                    "backfill kg_pit_snapshots for this date",
            "weights_used": weights,
        }

    # Group tickers by community
    by_comm: dict[str, list[str]] = {}
    for t, cid in pit.items():
        by_comm.setdefault(str(cid), []).append(str(t).upper())

    # Placeholder aggregation · real integrations read realized PnL from
    # outcome_dataset, news sentiment from data/market_intelligence/news,
    # and relative strength from parquet closes. For Sprint A initial ship
    # we emit the STRUCTURE with zero-defaults and let daily wiring populate.
    community_scores = []
    for cid, tickers in by_comm.items():
        pnl_20d = 0.0
        news_10d = 0.0
        rs_60d = 0.0
        regime = "UNKNOWN"
        score = group_composite_score(pnl_20d, news_10d, rs_60d, regime, weights)
        community_scores.append({
            "community_id": cid,
            "n_members": len(tickers),
            "members_preview": tickers[:5],
            "pnl_20d": pnl_20d,
            "news_sent_10d": news_10d,
            "rel_str_60d": rs_60d,
            "regime": regime,
            "group_composite_score": round(score, 6),
            "data_completeness": {
                "pnl_20d": "placeholder",
                "news_sent_10d": "placeholder",
                "rel_str_60d": "placeholder",
                "regime": "placeholder",
            },
        })

    community_scores.sort(key=lambda x: -x["group_composite_score"])

    result = {
        "market": market, "asof": asof,
        "n_communities": len(community_scores),
        "weights_used": weights,
        "formula": ("Group_Composite_Score = "
                    "0.4*trailing_20d_realized_pnl "
                    "+ 0.3*trailing_10d_news_sentiment "
                    "+ 0.2*trailing_60d_relative_strength "
                    "+ 0.1*regime_multiplier"),
        "note_ceo_gap_5": ("Uses KG communities via PIT snapshot lookup "
                           "(reports/research/kg_pit_snapshots/{market}/{asof}.json) "
                           "· NEVER static GICS sectors · CEO 2026-09-03 confirmation"),
        "communities": community_scores,
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"r1_kg_group_filter_{market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    r = build_r1_kg_filter(Path(args.root), args.market, args.asof)
    print(json.dumps(r, indent=2, default=str)[:1500])


if __name__ == "__main__":
    main()
