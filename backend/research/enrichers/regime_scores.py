"""B4 · Sector regime score + Market regime score enricher · Sprint A · Batch B
CEO 2026-09-03 · unblocks P2 (α · sector_regime_score + β · market_regime_score).

Populates:
  sector_regime_score  · sector-relative 20d strength · z-scored across sectors
  market_regime_score  · market-wide 20d strength · z-scored across window
  regime_score_source  · provenance tag

Both are PIT · computed from parquet closes at or before entry_date.

## sector_regime_score

For each (asof, sector):
  sector_20d_ret = mean over sector tickers of 20d close-to-close return
  z-score across all sectors on same asof
  clamped to [-3, 3]

## market_regime_score

For each asof:
  market_20d_ret = universe-mean 20d return
  z-score across trailing 90d values of market_20d_ret

## No fabrication

Any row where entry_date has < 20 bars available → score = None + source="insufficient_history".
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _z(v: float, series: list[float]) -> float | None:
    if not series or len(series) < 3: return None
    mu = sum(series) / len(series)
    var = sum((x - mu)**2 for x in series) / max(1, len(series) - 1)
    sd = math.sqrt(var)
    if sd <= 0: return 0.0
    z = (v - mu) / sd
    return max(-3.0, min(3.0, z))


def _ticker_20d_ret(root: Path, market: str, ticker: str, entry_date: str) -> float | None:
    from backend.research._paths import price_parquet_path
    import pandas as pd
    p = price_parquet_path(root, market, ticker)
    if not p or not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        asof_dt = pd.to_datetime(entry_date).normalize()
        window = df[df.index <= asof_dt].tail(21)
        if len(window) < 21: return None
        closes = window["close"].to_numpy()
        if closes[0] <= 0: return None
        return (closes[-1] / closes[0]) - 1.0
    except Exception:
        return None


def enrich_regime_scores(root: Path, market: str) -> dict:
    """In-place merge sector_regime_score + market_regime_score onto Outcome Dataset."""
    import pandas as pd
    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return {"market": market, "status": "OUTCOME_DATASET_MISSING"}
    df = pd.read_parquet(od_path)
    if df.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}

    for c in ("sector_regime_score", "market_regime_score",
              "regime_score_source"):
        if c not in df.columns:
            df[c] = None

    # Group rows by entry_date so we can compute per-day cross-sectional stats
    from collections import defaultdict
    rows_by_date: dict[str, list[int]] = defaultdict(list)
    for i in df.index:
        ed = str(df.at[i, "entry_date"]) if pd.notna(df.at[i, "entry_date"]) else ""
        if ed: rows_by_date[ed].append(i)

    ticker_ret_cache: dict[tuple, float | None] = {}
    def _get_ret(t, d):
        key = (t, d)
        if key not in ticker_ret_cache:
            ticker_ret_cache[key] = _ticker_20d_ret(root, market, t, d)
        return ticker_ret_cache[key]

    n_scored_sector = 0
    n_scored_market = 0
    per_date_market_ret: dict[str, float | None] = {}
    per_date_sector_zscores: dict[str, dict[str, float]] = {}

    # First pass · compute sector-by-day z-scores
    for date_str, idxs in rows_by_date.items():
        # Group by sector · aggregate mean 20d return per sector · then z-score
        sector_returns: dict[str, list[float]] = defaultdict(list)
        for i in idxs:
            t = str(df.at[i, "ticker"])
            sec = str(df.at[i, "sector"] or "UNKNOWN")
            r = _get_ret(t, date_str)
            if r is not None:
                sector_returns[sec].append(r)
        # sector mean
        sector_means = {s: sum(v)/len(v) for s, v in sector_returns.items() if v}
        # z across sectors
        all_means_list = list(sector_means.values())
        per_sec_z: dict[str, float] = {}
        for s, mean_r in sector_means.items():
            z = _z(mean_r, all_means_list)
            if z is not None: per_sec_z[s] = z
        per_date_sector_zscores[date_str] = per_sec_z
        # market 20d ret = mean of ALL ticker returns
        all_rets = [r for r_list in sector_returns.values() for r in r_list]
        if all_rets:
            per_date_market_ret[date_str] = sum(all_rets) / len(all_rets)
        else:
            per_date_market_ret[date_str] = None

    # Second pass · market_regime_score = z of today's market ret across trailing 90d
    sorted_dates = sorted(per_date_market_ret.keys())
    per_date_market_z: dict[str, float | None] = {}
    for i, d in enumerate(sorted_dates):
        v = per_date_market_ret[d]
        if v is None:
            per_date_market_z[d] = None; continue
        # trailing 90 calendar days (approx)
        window_vals = []
        for j in range(max(0, i - 90), i + 1):
            wv = per_date_market_ret[sorted_dates[j]]
            if wv is not None: window_vals.append(wv)
        per_date_market_z[d] = _z(v, window_vals) if len(window_vals) >= 5 else None

    # Third pass · write into df
    for i in df.index:
        ed = str(df.at[i, "entry_date"]) if pd.notna(df.at[i, "entry_date"]) else ""
        if not ed:
            df.at[i, "regime_score_source"] = "missing_entry_date"
            continue
        sec = str(df.at[i, "sector"] or "UNKNOWN")
        sec_z = per_date_sector_zscores.get(ed, {}).get(sec)
        mkt_z = per_date_market_z.get(ed)
        if sec_z is not None:
            df.at[i, "sector_regime_score"] = round(float(sec_z), 4)
            n_scored_sector += 1
        else:
            df.at[i, "sector_regime_score"] = None
        if mkt_z is not None:
            df.at[i, "market_regime_score"] = round(float(mkt_z), 4)
            n_scored_market += 1
        else:
            df.at[i, "market_regime_score"] = None
        src = []
        if sec_z is not None: src.append("sector_z_cross_section")
        if mkt_z is not None: src.append("market_z_trailing_90d")
        df.at[i, "regime_score_source"] = "+".join(src) if src else "insufficient_history"

    df.to_parquet(od_path, index=False)

    summary = {
        "market": market, "status": "ENRICHED",
        "n_rows": int(len(df)),
        "n_scored_sector": n_scored_sector,
        "n_scored_market": n_scored_market,
        "n_unique_dates": len(rows_by_date),
        "methodology": {
            "sector_regime_score": ("20d close-to-close mean return per sector on asof, "
                                     "z-scored across sectors on same asof, clamped [-3,3]"),
            "market_regime_score": ("universe-mean 20d return on asof, z-scored across "
                                     "trailing 90 calendar days of the same measure, clamped [-3,3]"),
            "pit_rule": "For entry_date D, only use bars with index <= D",
        },
        "no_fabrication_note": "Any row with < 20 bars → score = None with insufficient_history",
        "enriched_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research" / "enrichers"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"regime_scores_{market}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), default="both")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = enrich_regime_scores(root, m)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
