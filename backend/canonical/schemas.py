"""Canonical row schemas — one shape per data kind, shared across markets.

Every ingested dataset (India + USA) can be adapted into one of these row
types via `backend/canonical/adapters.py`. Downstream engines (Market
Intelligence, Investment Intelligence, Fusion, etc.) consume ONLY canonical
rows — they never touch raw parquets — so a change to the India yfinance
schema or the USA yfinance schema has no reach beyond the adapter layer.

**Determinism contract:** every canonical row carries the source market
identifier + the source asof date. Walk-forward replay must be able to
reproduce these rows from the raw data as it existed on any historical
freeze date.

**Currency contract:** every monetary field is EITHER in the market's
native currency (INR for India, USD for USA) OR in a canonical numeraire
(USD) if explicitly labelled. Never mix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# ── Price / Bar ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalBar:
    market:     str        # "india" | "usa"
    symbol:     str        # market-native ticker (RELIANCE, AAPL)
    date:       date
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    currency:   str        # "INR" | "USD"


# ── Fundamentals snapshot ───────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalFundamentals:
    market:            str
    symbol:            str
    asof:              date
    roe:               float | None            # return on equity, decimal (0.22 = 22%)
    debt_to_equity:    float | None
    profit_margin:     float | None
    earnings_growth:   float | None
    trailing_pe:       float | None
    price_to_book:     float | None
    quality_score:     float | None            # engine's composite (0..100 or z-score)
    market_cap:        float | None            # in market currency
    currency:          str
    source:            str                     # producer path or vendor tag


# ── News sentiment ──────────────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalNews:
    market:      str
    symbol:      str
    asof:        date
    sentiment:   float                         # bounded [-1, +1]
    n_headlines: int
    n_positive:  int
    n_negative:  int
    source:      str                           # "google_news_rss" | "finbert" | ...


# ── Institutional flows (FII/DII for India, insider Form 4 for USA) ──
@dataclass(frozen=True)
class CanonicalFlow:
    market:       str
    asof:         date
    kind:         str        # "foreign_institutional" | "domestic_institutional" | "insider_buy" | "insider_sell"
    scope:        str        # "market" (India FII/DII) | "ticker" (USA insider)
    symbol:       str | None
    value_native: float      # in market currency
    currency:     str
    source:       str


# ── Corporate actions (dividends + splits) ──────────────────────────
@dataclass(frozen=True)
class CanonicalCorporateAction:
    market:       str
    symbol:       str
    action_date:  date
    dividend:     float                        # in market currency; 0 if not a dividend
    split_ratio:  float                        # ratio; 0 if not a split
    currency:     str
    source:       str


# ── Earnings calendar entry ─────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalEarnings:
    market:              str
    symbol:              str
    asof:                date
    next_earnings_date:  date | None
    last_report_date:    date | None
    last_reported_eps:   float | None
    last_eps_estimate:   float | None
    last_surprise_pct:   float | None
    source:              str


# ── Macro indicator (rates, dollar, commodities, vol) ───────────────
@dataclass(frozen=True)
class CanonicalMacro:
    market:      str                # market this macro is scoped to ("global" is also fine)
    symbol:      str                # ^TNX, UUP, GC=F, ^VIX, etc.
    label:       str                # "10Y Treasury yield"
    asof:        date
    close:       float
    chg_1d_pct:  float | None
    chg_1w_pct:  float | None
    chg_1m_pct:  float | None
    source:      str


# ── Flow proxy (ETF dollar volume for USA, sector composites for India) ─
@dataclass(frozen=True)
class CanonicalFlowProxy:
    market:                 str
    symbol:                 str            # ETF ticker OR sector composite name
    label:                  str            # "Financials", "S&P 500", etc.
    asof:                   date
    period_days:            int
    return_pct:             float
    avg_dollar_volume:      float | None   # in market currency
    currency:               str
    source:                 str


# ── Institutional holdings (SEC 13F top-holders view for USA) ────────
@dataclass(frozen=True)
class CanonicalHolding:
    market:          str
    symbol:          str
    holder:          str
    shares:          float | None
    pct_out:         float | None
    value_native:    float | None
    date_reported:   date | None
    currency:        str
    source:          str


# ── Envelope: what an adapter yields ────────────────────────────────
@dataclass
class CanonicalDataset:
    """A named collection of canonical rows produced by an adapter.

    Downstream engines match on `kind` (bar/fundamentals/news/…) rather
    than on individual dataclass types, so future kinds can be added
    without breaking consumers.
    """
    kind:      str                  # matches one of the CanonicalXxx classes above
    market:    str                  # "india" | "usa"
    asof:      date                 # canonical asof date for the whole batch
    n_rows:    int
    rows:      list = field(default_factory=list)
    source:    str = ""
    notes:     str = ""


# For convenience — string identifiers used throughout the layer.
KINDS = (
    "bar", "fundamentals", "news", "flow", "corporate_action",
    "earnings", "macro", "flow_proxy", "holding",
)
