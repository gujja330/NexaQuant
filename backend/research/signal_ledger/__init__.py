"""AEGIS · Daily Signal Ledger

Substrate for R2 calibration, IC computation, Deflated Sharpe, and any
research that needs "who said what on which day, and how did the market
respond over 5/10/20/60 trading days."

Append-only parquet keyed by (market, runner, asof, ticker). Forward returns
are recomputed on every build as more market data lands.
"""
from backend.research.signal_ledger.build import (
    build_ledger, load_ledger, LEDGER_SCHEMA,
)

__all__ = ["build_ledger", "load_ledger", "LEDGER_SCHEMA"]
