"""Angel One (Angel Broking) SmartAPI adapter · India PRIMARY intraday feed.

Credentials come from .env.angel:
  ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET

Provides:
  · Historical candle data (1min · 5min · 15min · 30min · 1hour · 1day)
  · Live streaming (WebSocket · optional · future integration)

Zero cost beyond an Angel One trading account. Higher-quality intraday
data than yfinance for NSE (real broker feed vs delayed Yahoo).

Enable steps (when credentials are populated · one-off):
  1. pip install smartapi-python pyotp
  2. Verify .env.angel has all four vars
  3. AVAILABLE will auto-flip to True on first successful login
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# Detected at import time · flips True after first successful auth
AVAILABLE = False
_CACHED_CLIENT = None
_INSTRUMENT_TOKENS: dict[str, str] = {}


def _load_env(root: Path) -> None:
    """Load .env.angel into os.environ if not already set."""
    p = root / ".env.angel"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get_client(root: Path):
    """Return authenticated SmartConnect client · or None."""
    global _CACHED_CLIENT, AVAILABLE
    if _CACHED_CLIENT is not None:
        return _CACHED_CLIENT
    _load_env(root)
    api_key = os.environ.get("ANGEL_API_KEY")
    client_code = os.environ.get("ANGEL_CLIENT_CODE")
    pin = os.environ.get("ANGEL_PIN")
    totp_secret = os.environ.get("ANGEL_TOTP_SECRET")
    if not all([api_key, client_code, pin, totp_secret]):
        return None
    try:
        from SmartApi import SmartConnect
        import pyotp
    except ImportError:
        return None
    try:
        totp = pyotp.TOTP(totp_secret).now()
        client = SmartConnect(api_key=api_key)
        data = client.generateSession(client_code, pin, totp)
        if not data or not data.get("status"):
            return None
        _CACHED_CLIENT = client
        AVAILABLE = True
        return client
    except Exception:
        return None


def _resolve_instrument_token(root: Path, ticker: str) -> Optional[str]:
    """Look up NSE instrument_token for a bare ticker (e.g. 'RELIANCE').
    Cached in-memory. Uses Angel's instrument-master download."""
    global _INSTRUMENT_TOKENS
    bare = ticker.split(".", 1)[0].strip().upper()
    if bare in _INSTRUMENT_TOKENS:
        return _INSTRUMENT_TOKENS[bare]
    # Try local cache first
    cache = root / "data" / "raw" / "angel_instruments.json"
    if cache.exists():
        try:
            import json
            data = json.loads(cache.read_text(encoding="utf-8"))
            _INSTRUMENT_TOKENS = {k.upper(): str(v) for k, v in (data or {}).items()}
            return _INSTRUMENT_TOKENS.get(bare)
        except Exception:
            pass
    # Fetch instrument master on-demand
    try:
        import urllib.request, json
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPI_StockList.json"
        with urllib.request.urlopen(url, timeout=30) as r:
            arr = json.loads(r.read().decode("utf-8"))
        mapping = {}
        for row in arr:
            if row.get("exch_seg") == "NSE" and row.get("symbol", "").endswith("-EQ"):
                sym = row["symbol"][:-3].upper()
                mapping[sym] = str(row.get("token"))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        _INSTRUMENT_TOKENS = mapping
        return mapping.get(bare)
    except Exception:
        return None


def _angel_interval(interval: str) -> str:
    return {
        "1m":  "ONE_MINUTE",
        "5m":  "FIVE_MINUTE",
        "15m": "FIFTEEN_MINUTE",
        "30m": "THIRTY_MINUTE",
        "1h":  "ONE_HOUR",
        "1d":  "ONE_DAY",
    }.get(interval, "FIVE_MINUTE")


def fetch_bars(root: Path, ticker: str, market: str,
                  interval: str = "5m",
                  lookback_days: int = 30) -> "pd.DataFrame | None":
    """Fetch intraday bars via Angel SmartAPI. Returns pandas DataFrame or None."""
    if market != "india":
        return None
    try:
        import pandas as pd
    except ImportError:
        return None
    client = _get_client(root)
    if client is None:
        return None
    token = _resolve_instrument_token(root, ticker)
    if not token:
        return None
    to_dt = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    from_dt = to_dt - timedelta(days=lookback_days)
    params = {
        "exchange":    "NSE",
        "symboltoken": token,
        "interval":    _angel_interval(interval),
        "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        resp = client.getCandleData(params)
        if not resp or not resp.get("status"):
            return None
        rows = resp.get("data") or []
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        # Cache
        cp = root / "data" / "raw" / "india_intraday" / interval / f"{ticker.split('.')[0]}.parquet"
        cp.parent.mkdir(parents=True, exist_ok=True)
        if cp.exists():
            try:
                prev = pd.read_parquet(cp)
                combined = pd.concat([prev, df]).sort_index()
                df = combined[~combined.index.duplicated(keep="last")]
            except Exception:
                pass
        df.to_parquet(cp)
        return df
    except Exception:
        return None
