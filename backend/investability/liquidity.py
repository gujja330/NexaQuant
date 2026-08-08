"""Liquidity sub-engine · 5% weight of Investability Score.

Signals (all parquet-derivable):
    Average daily volume       · min threshold prevents illiquid picks
    Volume consistency         · std/mean · stability check
    Days-to-liquidate estimate · position size / avg_vol · < 5 days is good
    Trend (30-day vs 90-day)   · rising liquidity is bullish

Full Wave 2 adds: Delivery % (bhavcopy) · Impact cost · Spread ·
Turnover ratio (avg_vol / free_float_shares).
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path


def score(ticker: str, market: str, root: Path,
              position_target_shares: int = 10_000) -> tuple[float, dict]:
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    base = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    p = root / base / f"{short}_D1.parquet"

    if not p.exists():
        return 50.0, {"engine": "liquidity.v1", "score": 50.0, "error": "parquet_missing"}

    try:
        df = pd.read_parquet(p)
    except Exception:
        return 50.0, {"engine": "liquidity.v1", "score": 50.0, "error": "parquet_read"}

    vol_col = "volume" if "volume" in df.columns else "Volume" if "Volume" in df.columns else None
    if not vol_col or len(df) < 30:
        return 50.0, {"engine": "liquidity.v1", "score": 50.0, "error": "no_volume"}

    vol_30 = df[vol_col].tail(30).mean()
    vol_90 = df[vol_col].tail(min(90, len(df))).mean()
    vol_std_30 = df[vol_col].tail(30).std()
    vol_cv = vol_std_30 / vol_30 if vol_30 else 999

    signals = {}
    hits = 0
    total = 0

    def check(name, ok, weight=1.0, extra=None):
        nonlocal hits, total
        total += weight
        signals[name] = {"ok": bool(ok), "weight": weight, "extra": extra}
        if ok: hits += weight

    # Minimum liquidity thresholds (differs India vs USA)
    min_vol = 50_000 if market.lower() == "india" else 500_000
    check("avg_volume_sufficient", vol_30 >= min_vol, weight=2.0,
              extra={"avg_vol_30d": int(vol_30), "threshold": min_vol})

    # Consistency · CV < 1.5 = reasonably stable
    check("volume_consistent", vol_cv < 1.5, weight=1.0,
              extra={"coefficient_of_variation": round(vol_cv, 2)})

    # Days to liquidate target position
    days_to_liquidate = position_target_shares / vol_30 if vol_30 else 999
    check("liquidatable_in_5_days", days_to_liquidate < 5, weight=1.5,
              extra={"days_to_liquidate": round(days_to_liquidate, 2)})

    # Trend
    check("liquidity_trend_ok", vol_30 >= 0.85 * vol_90, weight=1.0,
              extra={"vol_30d": int(vol_30), "vol_90d": int(vol_90)})

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "liquidity.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
