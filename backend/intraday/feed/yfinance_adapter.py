"""yfinance adapter · works today · no external credentials needed.

Limits (yfinance free tier):
  · 1-min bars: last ~8 days
  · 5-min bars: last ~60 days
  · 1-hour bars: last ~730 days
  · daily: full history

Adequate for HISTORICAL_BACKTEST + PAPER_PORTFOLIO evaluation phases.
Real production (LIVE_60D → PRODUCTION) needs Kite (India) + Polygon (USA)
per §3 of the architecture doc · those adapters are stubbed in
kite_adapter.py + polygon_adapter.py.
"""
from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path


_INTERVAL_LIMITS = {
    "1m":  7,      # yfinance allows max 7d of 1m bars per request
    "5m":  59,
    "15m": 59,
    "30m": 59,
    "1h":  720,
}

_YF_SLEEP = 0.25    # be polite


def _yf_symbol(bare: str, market: str) -> str:
    if market == "india" and "." not in bare:
        return f"{bare}.NS"
    return bare


def _cache_dir(root: Path, market: str, interval: str) -> Path:
    subdir = "usa_intraday" if market == "usa" else "india_intraday"
    d = root / "data" / "raw" / subdir / interval
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_bars(root: Path, ticker: str, market: str,
                  interval: str = "5m",
                  lookback_days: int | None = None) -> "pd.DataFrame | None":
    """Fetch intraday bars. Returns pandas DataFrame or None on failure.

    Cached under data/raw/{us_intraday|india_intraday}/{interval}/{TICKER}.parquet.
    Merges into existing cache · deduplicated by index.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return None

    if lookback_days is None:
        lookback_days = _INTERVAL_LIMITS.get(interval, 5)
    lookback_days = min(lookback_days, _INTERVAL_LIMITS.get(interval, 5))

    symbol = _yf_symbol(ticker, market)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    try:
        df = yf.download(symbol, start=start, end=end, interval=interval,
                            progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            return None
        # Normalize columns · handle MultiIndex from single-ticker download
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        # Merge with existing cache
        cp = _cache_dir(root, market, interval) / f"{ticker}.parquet"
        if cp.exists():
            try:
                prev = pd.read_parquet(cp)
                combined = pd.concat([prev, df]).sort_index()
                combined = combined[~combined.index.duplicated(keep="last")]
                df = combined
            except Exception:
                pass
        df.to_parquet(cp)
        _time.sleep(_YF_SLEEP)
        return df
    except Exception:
        return None


def load_cached_bars(root: Path, ticker: str, market: str,
                       interval: str = "5m") -> "pd.DataFrame | None":
    try:
        import pandas as pd
    except ImportError:
        return None
    cp = _cache_dir(root, market, interval) / f"{ticker}.parquet"
    if not cp.exists():
        return None
    try:
        return pd.read_parquet(cp)
    except Exception:
        return None


def bars_for_session(root: Path, ticker: str, market: str,
                        session_date: str, interval: str = "5m") -> "pd.DataFrame | None":
    """Load bars for one specific session date · from cache if present,
    else fetch. Returns just that session's bars."""
    try:
        import pandas as pd
    except ImportError:
        return None
    df = load_cached_bars(root, ticker, market, interval)
    if df is None or df.empty:
        df = fetch_bars(root, ticker, market, interval, lookback_days=7)
    if df is None or df.empty:
        return None
    try:
        df.index = pd.to_datetime(df.index)
        target = pd.to_datetime(session_date).date()
        return df[df.index.date == target]
    except Exception:
        return None
