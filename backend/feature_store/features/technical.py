"""Technical features from CanonicalBar rows.

Computes: returns, volatility, RSI, MACD, SMAs, ATR, ADX, 52W distances,
drawdown, volume ratios. All computations are as-of the last row per ticker
(walk-forward safe — adapter already cuts off future dates).

Wave Y · Constitution Article 30: all indicator primitives now import from
the canonical shared library at `backend.shared.indicators`. Local
reimplementations removed.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backend.canonical.schemas import CanonicalDataset
from backend.shared.indicators import (
    rsi as _rsi_shared,
    atr_pct as _atr_pct_shared,
    adx as _adx_shared,
    macd as _macd_shared,
    returns_pct as _returns_pct_shared,
    volatility_daily as _volatility_daily_shared,
    max_drawdown_pct as _max_drawdown_pct_shared,
)


# Thin adapters kept for backward-compat with any legacy callers of these
# module-level names. Delegate to shared. Do NOT reimplement here.
_returns_pct = _returns_pct_shared
_rsi         = _rsi_shared
_macd        = _macd_shared


# Wave Y · Constitution Article 30: ATR + ADX delegated to shared library.
# Local Wave 3 · C0 implementations removed. Contract preserved via thin adapters.
_atr = _atr_pct_shared
_adx = _adx_shared


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    bars = canon.get("bar")
    if not bars or not bars.rows:
        return out

    df = pd.DataFrame([{"symbol": b.symbol, "date": b.date,
                          "open":   float(b.open)   if b.open   is not None else float(b.close),
                          "high":   float(b.high)   if b.high   is not None else float(b.close),
                          "low":    float(b.low)    if b.low    is not None else float(b.close),
                          "close":  float(b.close),
                          "volume": b.volume}
                         for b in bars.rows])
    df["date"] = pd.to_datetime(df["date"])
    for sym, g in df.groupby("symbol", sort=True):
        if sym not in universe: continue
        g = g.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
        if len(g) < 30:   # need enough history for anything meaningful
            out[sym] = {}
            continue

        closes = g["close"].astype(float)
        vols   = g["volume"].astype(float)
        row: dict = {}

        row["close"]  = round(float(closes.iloc[-1]), 4)
        row["volume"] = float(vols.iloc[-1]) if len(vols) else None

        # Returns
        for w in (1, 5, 10, 20, 60):
            row[f"return_{w}d_pct"] = _returns_pct(closes, w)

        # Volatility (stdev of daily returns)
        for w in (20, 60):
            if len(closes) > w + 1:
                r = closes.pct_change().dropna().tail(w)
                row[f"volatility_{w}d"] = round(float(r.std()), 5) if len(r) else None
            else:
                row[f"volatility_{w}d"] = None

        # RSI
        row["rsi_14"] = _rsi(closes, 14)

        # SMAs
        for p in (20, 50, 200):
            if len(closes) >= p:
                sma = float(closes.tail(p).mean())
                row[f"sma_{p}"] = round(sma, 4)
                row[f"price_above_sma{p}"] = 1 if float(closes.iloc[-1]) > sma else 0
            else:
                row[f"sma_{p}"] = None
                row[f"price_above_sma{p}"] = None

        # ATR + ADX
        row["atr_14_pct"] = _atr(g, 14)
        row["adx_14"]     = _adx(g, 14)

        # MACD
        macd, sig, hist = _macd(closes)
        row["macd"] = macd
        row["macd_signal"] = sig
        row["macd_hist"] = hist

        # 52W window
        w52 = closes.tail(252)
        if len(w52) >= 60:
            hi = float(w52.max()); lo = float(w52.min()); last = float(closes.iloc[-1])
            if hi > 0:
                row["distance_from_52w_high_pct"] = round((last / hi - 1) * 100, 3)
            if lo > 0:
                row["distance_from_52w_low_pct"] = round((last / lo - 1) * 100, 3)
            if hi > lo:
                row["position_in_52w_range"] = round((last - lo) / (hi - lo), 4)

        # Max drawdown 60d
        if len(closes) >= 60:
            cs = closes.tail(60)
            running_max = cs.cummax()
            dd = (cs / running_max - 1) * 100
            row["max_drawdown_60d_pct"] = round(float(dd.min()), 3)

        # Volume ratio 5v20
        if len(vols) >= 20 and vols.tail(20).sum() > 0:
            r5 = float(vols.tail(5).mean())
            r20 = float(vols.tail(20).mean())
            if r20 > 0:
                row["volume_ratio_5v20"] = round(r5 / r20, 3)

        out[sym] = row
    return out
