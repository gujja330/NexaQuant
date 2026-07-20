"""Technical features from CanonicalBar rows.

Computes: returns, volatility, RSI, MACD, SMAs, ATR, ADX, 52W distances,
drawdown, volume ratios. All computations are as-of the last row per ticker
(walk-forward safe — adapter already cuts off future dates).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backend.canonical.schemas import CanonicalDataset


def _returns_pct(series: pd.Series, window: int) -> float | None:
    if len(series) <= window: return None
    a = float(series.iloc[-window - 1])
    b = float(series.iloc[-1])
    if a <= 0: return None
    return round((b / a - 1.0) * 100, 4)


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) <= period: return None
    d = closes.diff().dropna()
    up = d.clip(lower=0).rolling(period).mean()
    dn = (-d.clip(upper=0)).rolling(period).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return round(float(v), 3) if pd.notna(v) else None


def _macd(closes: pd.Series) -> tuple[float | None, float | None, float | None]:
    if len(closes) < 35: return None, None, None
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return round(float(macd.iloc[-1]), 4), round(float(signal.iloc[-1]), 4), round(float(hist.iloc[-1]), 4)


def _atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """ATR as % of close."""
    if len(df) <= period + 1: return None
    high = df["close"] * 1.005      # canonical bars carry close only in feature context;
    low  = df["close"] * 0.995      # rough proxy — refined in future using true HLC
    # If actual high/low columns are present, prefer them
    if "high" in df.columns and "low" in df.columns:
        high = df["high"]; low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([high - low,
                       (high - prev_close).abs(),
                       (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    close = df["close"].iloc[-1]
    if pd.isna(atr) or close <= 0: return None
    return round(float(atr / close * 100), 4)


def _adx(df: pd.DataFrame, period: int = 14) -> float | None:
    """Simplified ADX from close-only bars."""
    if len(df) <= period * 2: return None
    close = df["close"]
    delta = close.diff().dropna()
    up = delta.clip(lower=0).abs().rolling(period).mean()
    down = delta.clip(upper=0).abs().rolling(period).mean()
    dx = (up - down).abs() / (up + down).replace(0, np.nan) * 100
    adx = dx.rolling(period).mean().iloc[-1]
    return round(float(adx), 3) if pd.notna(adx) else None


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    bars = canon.get("bar")
    if not bars or not bars.rows:
        return out

    df = pd.DataFrame([{"symbol": b.symbol, "date": b.date, "close": b.close,
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
