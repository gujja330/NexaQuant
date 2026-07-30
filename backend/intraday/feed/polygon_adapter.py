"""Polygon.io adapter · STUB for USA LIVE_60D + PRODUCTION phases.

Requires:
  · Polygon.io Starter subscription ($29/mo)
  · POLYGON_API_KEY in .env.intraday

Enable steps:
  1. pip install polygon-api-client
  2. Set POLYGON_API_KEY
  3. Replace `_polygon_client()` stub with real RESTClient(...)
  4. Implement fetch_1m_live() via /v2/aggs/ticker/{ticker}/range/1/minute/...
  5. Implement subscribe_ticks() for WebSocket streaming

Until then, all calls return None · router falls back to yfinance_adapter.
"""
from __future__ import annotations

import os


AVAILABLE = False    # flip to True once credentials + polygon-api-client installed


def _polygon_client():
    if not AVAILABLE:
        return None
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        return None
    try:
        from polygon import RESTClient
        return RESTClient(key)
    except Exception:
        return None


def fetch_1m_live(ticker: str, from_ts, to_ts) -> "pd.DataFrame | None":
    return None


def subscribe_ticks(tickers: list[str], on_tick):
    return None
