"""Shared snapshot metadata and EPS normalization for yfinance ingestion."""
from math import isfinite


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def eps_snapshot(info, observed_at):
    currency = info.get("financialCurrency")
    trailing = _number(info.get("trailingEps"))
    forward = _number(info.get("forwardEps"))
    return {
        "eps_trailing": trailing,
        "eps_forward": forward,
        "eps_currency": currency if isinstance(currency, str) and currency.strip() else None,
        "eps_share_basis": "PROVIDER_REPORTED_UNVERIFIED",
        "eps_source": "yfinance",
        "eps_observed_at_utc": observed_at,
        "eps_point_in_time": False,
        "eps_availability": (
            "AVAILABLE" if trailing is not None and forward is not None
            else "PARTIAL" if trailing is not None or forward is not None
            else "MISSING"
        ),
    }
