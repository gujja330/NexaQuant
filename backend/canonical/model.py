"""Canonical dataset model + per-market profile.

`MarketProfile` — currency, timezone, symbol format, benchmark index,
trading calendar hint per market.

`CanonicalDatasetSpec` — the shape every entry in datasets.yaml must
carry:
    name:              unique dataset key
    path:              relative to market data root
    producer:          script path OR external label
    freshness_sla_trading_days: max age in bdays
    optional:          skip gracefully if missing
    schema:            required_columns / required_keys
    completeness:      row/coverage/null-pct rules
    quality:           duplicate/outlier/negative rules
    consumers:         who reads this artifact
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketProfile:
    name:            str
    currency:        str
    currency_symbol: str
    timezone:        str
    benchmark:       str        # primary index symbol
    exchange_mix:    list[str]
    trading_calendar_hint: str  # e.g. "NSE", "NYSE"


INDIA_PROFILE = MarketProfile(
    name="india", currency="INR", currency_symbol="₹",
    timezone="Asia/Kolkata", benchmark="^NSEI",
    exchange_mix=["NSE", "BSE"], trading_calendar_hint="NSE",
)

USA_PROFILE = MarketProfile(
    name="usa", currency="USD", currency_symbol="$",
    timezone="America/New_York", benchmark="^GSPC",
    exchange_mix=["NYSE", "NASDAQ", "AMEX"], trading_calendar_hint="NYSE",
)


@dataclass
class CanonicalDatasetSpec:
    """Fields available on every dataset entry in datasets.yaml.

    Only `name`, `path`, `producer` are required. Everything else is
    optional and enables specific validators.
    """
    name:      str
    path:      str
    producer:  str
    kind:      str = "unknown"   # price / fundamentals / news / etc.
    optional:  bool = False
    freshness_sla_trading_days: int = 1
    schema:    dict = field(default_factory=dict)
    completeness: dict = field(default_factory=dict)
    quality:   dict = field(default_factory=dict)
    consumers: list[str] = field(default_factory=list)
    notes:     str = ""
