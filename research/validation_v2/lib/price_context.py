"""Validation Engine v2.0 · per-ticker price context.

Extracts current market price + yesterday's close + 52-week high/low
from `data/raw/india/{ticker}_D1.parquet` for every ticker in the
current recommendation set.

Emits reports/price_context.json — the dashboard consumes this to
show CMP, day change, and 52W distance on every stock card."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = _ROOT / "data" / "raw" / "india"


def _load_prices(ticker: str) -> pd.DataFrame:
    p = RAW_DIR / f"{ticker}_D1.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
    date_col  = next((c for c in df.columns if c.lower() in ("date", "dt", "timestamp")),
                       df.index.name)
    if close_col is None:
        return pd.DataFrame()
    if date_col and date_col in df.columns:
        df = df.rename(columns={close_col: "close"})[["close"] + ([date_col] if date_col != "close" else [])]
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.set_index(date_col).sort_index()
    else:
        # Assume the index is already the date
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
        except Exception:
            pass
        df = df.rename(columns={close_col: "close"}).sort_index()
    return df[["close"]] if "close" in df.columns else pd.DataFrame()


def build_ticker_price_context(ticker: str) -> dict:
    df = _load_prices(ticker)
    if df.empty or len(df) < 2:
        return {"ticker": ticker, "available": False,
                "note": "no price series on disk"}
    closes = df["close"].dropna().astype(float)
    if len(closes) < 2:
        return {"ticker": ticker, "available": False, "note": "insufficient history"}

    cmp_val = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    day_change_pct = (cmp_val - prev) / prev if prev else 0.0

    # 52-week window (approx 252 trading days)
    tail = closes.tail(252)
    high_52w = float(tail.max())
    low_52w  = float(tail.min())
    dist_hi = (cmp_val - high_52w) / high_52w if high_52w > 0 else 0.0
    dist_lo = (cmp_val - low_52w) / low_52w if low_52w > 0 else 0.0

    latest_date = closes.index[-1]
    return {
        "ticker":                 ticker,
        "available":              True,
        "cmp":                    round(cmp_val, 2),
        "previous_close":         round(prev, 2),
        "day_change_pct":         round(day_change_pct, 5),
        "high_52w":               round(high_52w, 2),
        "low_52w":                round(low_52w, 2),
        "distance_from_52w_high": round(dist_hi, 5),
        "distance_from_52w_low":  round(dist_lo, 5),
        "latest_date":            str(latest_date.date()) if hasattr(latest_date, "date") else str(latest_date)[:10],
    }


def build_all() -> dict:
    """Build price context for every ticker present in recommendations.json
    (or every ticker with a parquet file if recommendations is missing)."""
    tickers: set[str] = set()

    recs_path = _ROOT / "reports" / "recommendations.json"
    if recs_path.exists():
        try:
            j = json.loads(recs_path.read_text(encoding="utf-8"))
            for r in (j.get("recommendations") or []):
                if r.get("ticker"):
                    tickers.add(str(r["ticker"]))
        except Exception:
            pass

    # Fallback: read the raw universe if no recs
    if not tickers and RAW_DIR.exists():
        for p in RAW_DIR.glob("*_D1.parquet"):
            tickers.add(p.stem.replace("_D1", ""))

    result: dict[str, dict] = {}
    for t in sorted(tickers):
        result[t] = build_ticker_price_context(t)

    n_avail = sum(1 for r in result.values() if r.get("available"))
    return {
        "n_tickers":      len(result),
        "n_available":    n_avail,
        "n_missing":      len(result) - n_avail,
        "tickers":        result,
    }
