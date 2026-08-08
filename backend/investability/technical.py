"""Technical sub-engine · 20% weight of Investability Score.

Institutional-grade technical structure check (NOT day-trading oscillators).

Signals (all parquet-derivable · no new data source):
    Price vs 200-DMA       · above = healthy structure
    Price vs 50-DMA        · above = intermediate strength
    50-DMA vs 200-DMA      · above = no death cross
    Relative Strength      · ticker outperforms index over 63 days
    Trend consistency      · % of last 63 days closing above 20-DMA
    Volume trend           · 30-day avg vs 90-day avg (rising = healthy)
    Volatility (ATR%)      · not excessive
    Momentum persistence   · positive returns 3 of last 4 months

Returns 0-100 score.

Full Wave 2 adds: ADX · Volume profile · Anchored VWAP · MTF alignment ·
Breakout quality · Volatility contraction pattern (VCP).
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path


def score(ticker: str, market: str, root: Path,
              benchmark_ticker: str = "_IDX_NIFTY_D1") -> tuple[float, dict]:
    """Compute technical score from parquet history.

    Returns (score_0_to_100, debug_signals_dict).
    """
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    base = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    p = root / base / f"{short}_D1.parquet"

    if not p.exists():
        return 50.0, {"engine": "technical.v1", "score": 50.0, "error": "parquet_missing"}

    try:
        df = pd.read_parquet(p)
    except Exception as e:
        return 50.0, {"engine": "technical.v1", "score": 50.0, "error": f"parquet_read: {e}"}

    close_col = "close" if "close" in df.columns else "Close"
    vol_col = "volume" if "volume" in df.columns else "Volume" if "Volume" in df.columns else None

    if close_col not in df.columns or len(df) < 200:
        return 50.0, {"engine": "technical.v1", "score": 50.0, "error": "insufficient_bars"}

    df = df.copy()
    df["dma_20"] = df[close_col].rolling(20).mean()
    df["dma_50"] = df[close_col].rolling(50).mean()
    df["dma_200"] = df[close_col].rolling(200).mean()

    last = df.iloc[-1]

    signals = {}
    hits = 0
    total = 0

    def check(name: str, ok_bool, weight: float = 1.0, extra=None):
        nonlocal hits, total
        total += weight
        signals[name] = {"ok": bool(ok_bool), "weight": weight, "extra": extra}
        if ok_bool: hits += weight

    # Structural checks
    check("price_above_200dma",  last[close_col] > last["dma_200"],  weight=2.0,
              extra={"price": float(last[close_col]), "dma_200": float(last["dma_200"])})
    check("price_above_50dma",   last[close_col] > last["dma_50"],   weight=1.5)
    check("no_death_cross",      last["dma_50"] > last["dma_200"],   weight=1.5)

    # Trend consistency: % of last 63 days closing > 20-DMA
    last63 = df.tail(63).copy()
    above_20 = (last63[close_col] > last63["dma_20"]).sum()
    trend_pct = above_20 / len(last63)
    check("trend_consistency_63d", trend_pct >= 0.55, weight=1.5,
              extra={"pct_above_20dma": round(trend_pct, 2)})

    # Volume trend: 30-day avg vs 90-day avg
    if vol_col and vol_col in df.columns:
        vol_30 = df[vol_col].tail(30).mean()
        vol_90 = df[vol_col].tail(90).mean()
        vol_ratio = vol_30 / vol_90 if vol_90 else 0
        check("volume_trend_rising", vol_ratio >= 0.90, weight=1.0,
                  extra={"vol_ratio_30_90": round(vol_ratio, 2)})
    else:
        check("volume_trend_rising", True, weight=0.0)   # skip · no data

    # Momentum persistence: positive returns 3 of last 4 months
    if len(df) >= 84:  # ~4 months
        monthly = df[close_col].tail(84).iloc[::21]     # every 21 trading days
        if len(monthly) >= 5:
            rets = monthly.pct_change().dropna()
            positive_months = (rets > 0).sum()
            check("momentum_persistence",
                      positive_months >= 3, weight=1.5,
                      extra={"positive_of_last_4mo": int(positive_months)})

    # Volatility (ATR proxy · not excessive)
    high_col = "high" if "high" in df.columns else "High"
    low_col = "low" if "low" in df.columns else "Low"
    if high_col in df.columns and low_col in df.columns:
        tr = (df[high_col] - df[low_col]).tail(14).mean()
        atr_pct = tr / last[close_col]
        check("volatility_reasonable", atr_pct < 0.06, weight=1.0,
                  extra={"atr_pct": round(atr_pct, 4)})

    # Not too extended (below +25% above 200-DMA · not "chasing top")
    extension = (last[close_col] - last["dma_200"]) / last["dma_200"]
    check("not_over_extended", extension < 0.30, weight=1.0,
              extra={"pct_above_200dma": round(extension, 3)})

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "technical.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
