"""India FII/DII net-flow + Options PCR adapter · Layer 4 shim.

Data status: **REQUIRES_LIVE_SOURCE**. Adapter returns clearly-marked
NOT_AVAILABLE payloads until an NSE FII/DII scraper + NSE Options OI
scraper are wired.

Interface preserved so downstream code can call `fetch_fii_dii_series_20d`
and `fetch_options_pcr` without change · the real ingest replaces the
stub returning `None`.
"""
from __future__ import annotations

from typing import Optional


REQUIRES_LIVE_SOURCE_MARKER = "REQUIRES_LIVE_SOURCE:india_flow_adapter"


def fetch_fii_dii_series_20d(ticker: str, asof: str) -> Optional[list[float]]:
    """Placeholder · returns None until NSE FII/DII CSV feed is wired.

    Once wired: fetch nsearchives.nseindia.com/content/fo/fii_stats_YYYYMMDD.csv
    for the last 20 trading days at/before `asof` and return the
    'FII+DII net' column as list[float] (₹ crores).
    """
    return None


def fetch_options_pcr(ticker: str, asof: str) -> Optional[float]:
    """Placeholder · returns None until nseindia option-chain scraper is wired.

    Once wired: pull put_oi / call_oi for the nearest monthly expiry at `asof`
    and return the ratio.
    """
    return None


def adapter_status() -> dict:
    return {
        "provider": "india_flow_adapter",
        "signals": ["fii_dii_net_flow_z", "options_pcr"],
        "status": REQUIRES_LIVE_SOURCE_MARKER,
        "wiring_notes": {
            "fii_dii": "NSE FII/DII CSV · nsearchives.nseindia.com/content/fo/fii_stats_YYYYMMDD.csv · daily",
            "options_pcr": "NSE option-chain JSON · nseindia.com/api/option-chain-indices?symbol=NIFTY · rate-limited",
        },
    }
