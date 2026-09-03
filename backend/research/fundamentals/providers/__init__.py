"""Provider adapters for the Fundamentals Feature Store.

Each adapter translates a source (yfinance, nseindia, finviz, moneycontrol)
into the standardized input dict expected by layer1-5 derivations.

Rate-limited, cached, and free-data only per Wave 5 policy.
"""
from backend.research.fundamentals.providers.yfinance_adapter import (
    fetch_yfinance_inputs,
)

__all__ = ["fetch_yfinance_inputs"]
