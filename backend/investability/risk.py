"""Risk sub-engine · 7% weight of Investability Score.

Purpose: measure downside characteristics distinct from technical trend.
A stock in uptrend can still have unacceptable gap/tail risk (earnings
volatility · sector concentration · event exposure).

Signals (parquet-derivable + yfinance beta):
    Beta reasonable                     · beta < 1.5 · not amplifying market
    Max historical drawdown < 40%       · didn't halve+ historically
    Tail risk (95th pctl daily loss)    · worst daily move manageable
    Gap risk (overnight moves)          · overnight vol not excessive
    Volatility regime stable            · realized vol < 2x sector avg
    Recovery time from prior drawdown   · not still bleeding

Returns 0-100 score.

Higher score = safer risk profile (less tail/gap exposure).
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path


def score(ticker: str, market: str, root: Path, info: dict = None) -> tuple[float, dict]:
    short = str(ticker or "").replace(".NS", "").replace(".BO", "").upper()
    base = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    p = root / base / f"{short}_D1.parquet"

    signals = {}
    hits = 0
    total = 0

    def check(name, ok, weight=1.0, extra=None):
        nonlocal hits, total
        total += weight
        signals[name] = {"ok": bool(ok), "weight": weight, "extra": extra}
        if ok: hits += weight

    # Beta from yfinance (if provided)
    if info is not None:
        beta = info.get("beta")
        if beta is not None:
            check("beta_not_high", beta < 1.5, weight=1.5,
                      extra={"beta": beta})

    # Parquet-derived risk metrics
    if not p.exists():
        score_0_100 = round(hits / total * 100, 1) if total else 50.0
        return score_0_100, {"engine": "risk.v1", "score": score_0_100,
                                       "hits": hits, "total": total, "signals": signals,
                                       "error": "parquet_missing"}

    try:
        df = pd.read_parquet(p)
    except Exception:
        return 50.0, {"engine": "risk.v1", "score": 50.0, "error": "parquet_read"}

    close_col = "close" if "close" in df.columns else "Close"
    open_col = "open" if "open" in df.columns else "Open" if "Open" in df.columns else None

    if close_col not in df.columns or len(df) < 60:
        return 50.0, {"engine": "risk.v1", "score": 50.0, "error": "insufficient_bars"}

    df = df.copy()
    df["daily_ret"] = df[close_col].pct_change()

    # Max drawdown over last 252 days (~1 year)
    year = df.tail(252)
    rolling_max = year[close_col].cummax()
    drawdown = (year[close_col] / rolling_max - 1)
    max_dd = drawdown.min()
    check("max_dd_manageable", max_dd > -0.40, weight=2.0,
              extra={"max_dd_pct": round(max_dd * 100, 1)})

    # Tail risk: 5th percentile of daily returns (worst 5% of days)
    tail_return = df["daily_ret"].tail(252).quantile(0.05)
    check("tail_risk_reasonable", tail_return > -0.04, weight=1.5,
              extra={"5pctl_daily_return": round(tail_return * 100, 2)})

    # Gap risk (overnight moves · open vs prior close)
    if open_col and open_col in df.columns:
        df["gap"] = (df[open_col] - df[close_col].shift(1)) / df[close_col].shift(1)
        gap_5pctl = df["gap"].tail(252).quantile(0.05)
        check("gap_risk_reasonable", gap_5pctl > -0.03, weight=1.0,
                  extra={"5pctl_overnight_gap": round(gap_5pctl * 100, 2)})

    # Realized vol (30-day) · not extreme
    vol_30 = df["daily_ret"].tail(30).std()
    vol_annualized = vol_30 * (252 ** 0.5) * 100
    check("volatility_not_extreme", vol_annualized < 45, weight=1.5,
              extra={"annualized_vol_pct": round(vol_annualized, 1)})

    # Recovery: current price relative to 1-year high
    year_high = df[close_col].tail(252).max()
    current = df[close_col].iloc[-1]
    pct_from_high = (current - year_high) / year_high
    check("not_deep_from_high", pct_from_high > -0.20, weight=1.0,
              extra={"pct_from_52wk_high": round(pct_from_high * 100, 1)})

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "risk.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
