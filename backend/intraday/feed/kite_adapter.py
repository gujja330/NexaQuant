"""Zerodha Kite adapter · STUB for LIVE_60D + PRODUCTION phases.

Requires:
  · Zerodha trading account
  · Kite Connect API subscription (₹2000/mo)
  · KITE_API_KEY + KITE_ACCESS_TOKEN in .env.intraday

Enable steps (when credentials land):
  1. pip install kiteconnect
  2. Set env vars
  3. Replace `_kite_client()` stub below with real KiteConnect(...)
  4. Implement fetch_1m_live() to use kite.historical_data()
  5. Implement subscribe_ticks() for WebSocket streaming

Until credentials arrive, ALL calls return None · router falls back
to yfinance_adapter.
"""
from __future__ import annotations

import os
from pathlib import Path


AVAILABLE = False    # flip to True once credentials + kiteconnect installed


def _kite_client():
    """Return authenticated Kite client · or None if unavailable."""
    if not AVAILABLE:
        return None
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    if not (api_key and access_token):
        return None
    try:
        from kiteconnect import KiteConnect
        k = KiteConnect(api_key=api_key)
        k.set_access_token(access_token)
        return k
    except Exception:
        return None


def fetch_1m_live(ticker: str, from_ts, to_ts) -> "pd.DataFrame | None":
    """Placeholder · return None until Kite integration complete."""
    return None


def subscribe_ticks(tickers: list[str], on_tick):
    """Placeholder · WebSocket streaming not yet wired."""
    return None
