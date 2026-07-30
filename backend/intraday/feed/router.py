"""Feed router · picks the best available data source for a ticker.

Priority order:
  1. Kite (India) / Polygon (USA) live · when credentials + AVAILABLE flag on
  2. yfinance cached · works today
  3. yfinance live fetch · works today

Never fails hard · returns None if no source works.
"""
from __future__ import annotations

from pathlib import Path

from . import angel_adapter, kite_adapter, polygon_adapter, yfinance_adapter


def get_intraday_bars(root: Path, ticker: str, market: str,
                          interval: str = "5m",
                          session_date: str | None = None) -> "pd.DataFrame | None":
    """Return intraday bars via best available adapter.

    Priority per market:
      India: Angel SmartAPI (real broker feed · uses .env.angel) → yfinance fallback
      USA:   Polygon (when wired) → yfinance fallback
    """
    # India · Angel SmartAPI primary
    if market == "india":
        df = angel_adapter.fetch_bars(root, ticker, market, interval)
        if df is not None and len(df) > 0:
            if session_date:
                import pandas as pd
                df.index = pd.to_datetime(df.index)
                target = pd.to_datetime(session_date).date()
                return df[df.index.date == target]
            return df
    # USA · Polygon (stub for now)
    if market == "usa" and polygon_adapter.AVAILABLE:
        pass    # placeholder

    # Fallback: yfinance (always available)
    if session_date:
        return yfinance_adapter.bars_for_session(root, ticker, market,
                                                       session_date, interval)
    df = yfinance_adapter.load_cached_bars(root, ticker, market, interval)
    if df is None or df.empty:
        df = yfinance_adapter.fetch_bars(root, ticker, market, interval)
    return df


def fetch_5min_bars(root: Path, ticker: str, market: str) -> "pd.DataFrame | None":
    return get_intraday_bars(root, ticker, market, interval="5m")


def fetch_1min_bars(root: Path, ticker: str, market: str) -> "pd.DataFrame | None":
    return get_intraday_bars(root, ticker, market, interval="1m")
