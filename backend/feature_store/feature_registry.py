"""Feature Registry — every Feature Store column is declared HERE.

Rationale: engines downstream will assume specific column names + dtypes.
The registry is the contract. Adding a column bumps the schema fingerprint;
removing/renaming a column requires a migration entry in feature_versioning.

Categories map to the per-category computers under
`backend.feature_store.features.*`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FeatureCategory(str, Enum):
    IDENTITY         = "identity"           # market, ticker, asof, sector
    TECHNICAL        = "technical"          # RSI, MACD, momentum, volatility
    FUNDAMENTAL      = "fundamental"        # ROE, D/E, PE, margins
    NEWS             = "news"               # sentiment, headline count
    EARNINGS         = "earnings"           # calendar, surprise
    MACRO            = "macro"              # rates, DXY, gold, oil, VIX (market-joined)
    SECTOR           = "sector"             # sector return, rank, leadership
    INSTITUTIONAL    = "institutional"      # 13F, insider, FII/DII
    CORPORATE_ACTION = "corporate_action"   # dividend, split
    MARKET_INTEL     = "market_intel"       # regime, composite health (joined)
    HISTORICAL       = "historical"         # winner genome, DNA (if available)


class FeatureStatus(str, Enum):
    """Feature lifecycle status (Sprint 2.6 governance).

    ACTIVE       — promoted, consumed by downstream engines
    EXPERIMENTAL — new candidate, present in snapshot but excluded from decisions
    DEPRECATED   — kept for historical replay but not used going forward
    """
    ACTIVE       = "active"
    EXPERIMENTAL = "experimental"
    DEPRECATED   = "deprecated"


class FeatureGranularity(str, Enum):
    """The unit a feature is actually OBSERVED at. CEO 2026-11-04.

    Without this, no quality check can tell a legitimately market-wide
    constant from a broken ticker-level fan-out — the two look identical
    to `nunique() == 1`. Measured on the 2026-11-03 snapshots, eight
    `mi_*` columns are constant and correct, while `sector` is constant
    at `'Unknown'` on all 516 USA rows and is a defect. Same shape,
    opposite verdicts.

    Declared from the PRODUCER'S SOURCE, never inferred from a name
    prefix: `fii_net_5d` reads as per-ticker and is one national
    aggregate broadcast to every row.
    """
    TICKER  = "ticker"    # independently observed per ticker
    SECTOR  = "sector"    # shared by every ticker in a sector
    MARKET  = "market"    # shared by every ticker in one market
    GLOBAL  = "global"    # shared across markets · one world observation
    UNKNOWN = "unknown"   # not yet classified · validation must not assume


#: Granularities at which one repeated value across all rows is correct.
SHARED_GRANULARITIES = (FeatureGranularity.SECTOR, FeatureGranularity.MARKET,
                        FeatureGranularity.GLOBAL)


@dataclass(frozen=True)
class Feature:
    """Feature governance record (Sprint 2.6).

    Every feature the platform uses is described here. Sprint 2.6's Governance
    Engine will WARN on features missing `business_rationale` or
    `economic_intuition` — those are the anti-overfitting anchors.
    """
    # ── Sprint 2.5 base ────────────────────────────────────────
    name:      str
    category:  FeatureCategory
    dtype:     str                # "float", "int", "str"
    producer:  str                # module path, e.g. "backend.feature_store.features.technical"
    unit:      str = ""           # "%", "USD", "days", "zscore"
    nullable:  bool = True        # some features are naturally missing (e.g. RSI for young tickers)
    description: str = ""

    # ── Sprint 2.6 governance ─────────────────────────────────
    version:            str  = "1.0.0"
    status:             FeatureStatus = FeatureStatus.ACTIVE
    owner:              str  = "aegis-core"
    # Governance dates default to empty (unknown) rather than a stale
    # hardcoded string — operator directive: never hardcode dates. Features
    # authored explicitly should pass created= at registration time.
    created:            str  = ""
    last_updated:       str  = ""
    confidence:         float = 1.0                 # governance confidence (0..1)
    formula:            str  = ""                   # human-readable formula / definition
    dependencies:       tuple = ()                  # upstream feature names this depends on
    business_rationale: str  = ""                   # WHY this predicts returns or risk
    economic_intuition: str  = ""                   # what market behavior it represents

    # ── Semantic quality declarations (CEO 2026-11-04) ────────
    # Granularity alone does not establish validity, so each feature
    # also declares where its value comes from, how old an observation
    # may be, and how much of the universe should carry it.
    granularity:        FeatureGranularity = FeatureGranularity.UNKNOWN
    provenance:         str  = ""          # the producing source, concretely
    freshness_days:     "int | None" = None   # max observation age · None = unspecified
    expected_coverage_pct: "float | None" = None   # of the market universe
    validity_note:      str  = ""          # domain / placeholder policy

    @property
    def constant_is_legitimate(self) -> bool:
        """Is one value repeated on every row correct for this feature?

        True only at a shared granularity. A TICKER feature that is
        constant carries zero cross-sectional information and cannot
        differentiate names in a ranking model, which is a defect even
        though every cell passes `notna()`.
        """
        return self.granularity in SHARED_GRANULARITIES


# ─── The registry (add features here, never elsewhere) ────────────
FEATURE_REGISTRY: list[Feature] = []


def register(f: Feature) -> Feature:
    """Register a feature. Duplicate names raise."""
    if any(existing.name == f.name for existing in FEATURE_REGISTRY):
        raise ValueError(f"duplicate feature: {f.name}")
    FEATURE_REGISTRY.append(f)
    return f


def list_features(category: FeatureCategory | None = None) -> list[Feature]:
    if category is None:
        return list(FEATURE_REGISTRY)
    return [f for f in FEATURE_REGISTRY if f.category == category]


def list_categories() -> list[FeatureCategory]:
    seen: list[FeatureCategory] = []
    for f in FEATURE_REGISTRY:
        if f.category not in seen:
            seen.append(f.category)
    return seen


def list_by_status(status: FeatureStatus) -> list[Feature]:
    return [f for f in FEATURE_REGISTRY if f.status == status]


def active_feature_names() -> list[str]:
    """The feature subset downstream engines are allowed to consume."""
    return [f.name for f in FEATURE_REGISTRY if f.status == FeatureStatus.ACTIVE]


# ─── Identity columns (always present) ────────────────────────────
_MOD_IDENTITY = "backend.feature_store"

register(Feature("market",   FeatureCategory.IDENTITY, "str", _MOD_IDENTITY, "", False, "india | usa"))
register(Feature("ticker",   FeatureCategory.IDENTITY, "str", _MOD_IDENTITY, "", False, "market-native symbol"))
register(Feature("asof",     FeatureCategory.IDENTITY, "str", _MOD_IDENTITY, "date", False, "ISO date of the feature snapshot"))
register(Feature("sector",   FeatureCategory.IDENTITY, "str", _MOD_IDENTITY, "", True,  "sector from universe metadata"))
register(Feature("currency", FeatureCategory.IDENTITY, "str", _MOD_IDENTITY, "", False, "INR | USD"))


# ─── Technical (from CanonicalBar) ────────────────────────────────
_MOD_TECH = "backend.feature_store.features.technical"

for f in [
    Feature("close",                        FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native", False, "last close"),
    Feature("volume",                       FeatureCategory.TECHNICAL, "float", _MOD_TECH, "shares"),
    Feature("return_1d_pct",                FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("return_5d_pct",                FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("return_10d_pct",               FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("return_20d_pct",               FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("return_60d_pct",               FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("volatility_20d",               FeatureCategory.TECHNICAL, "float", _MOD_TECH, "stdev daily return"),
    Feature("volatility_60d",               FeatureCategory.TECHNICAL, "float", _MOD_TECH, "stdev daily return"),
    Feature("rsi_14",                       FeatureCategory.TECHNICAL, "float", _MOD_TECH, "0..100"),
    Feature("sma_20",                       FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("sma_50",                       FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("sma_200",                      FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("price_above_sma20",            FeatureCategory.TECHNICAL, "int",   _MOD_TECH, "0/1"),
    Feature("price_above_sma50",            FeatureCategory.TECHNICAL, "int",   _MOD_TECH, "0/1"),
    Feature("price_above_sma200",           FeatureCategory.TECHNICAL, "int",   _MOD_TECH, "0/1"),
    Feature("atr_14_pct",                   FeatureCategory.TECHNICAL, "float", _MOD_TECH, "% of close"),
    Feature("adx_14",                       FeatureCategory.TECHNICAL, "float", _MOD_TECH, "0..100"),
    Feature("macd",                         FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("macd_signal",                  FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("macd_hist",                    FeatureCategory.TECHNICAL, "float", _MOD_TECH, "native"),
    Feature("distance_from_52w_high_pct",   FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("distance_from_52w_low_pct",    FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("position_in_52w_range",        FeatureCategory.TECHNICAL, "float", _MOD_TECH, "0..1"),
    Feature("max_drawdown_60d_pct",         FeatureCategory.TECHNICAL, "float", _MOD_TECH, "%"),
    Feature("volume_ratio_5v20",            FeatureCategory.TECHNICAL, "float", _MOD_TECH, "ratio"),
]:
    register(f)


# ─── Fundamental (from CanonicalFundamentals) ─────────────────────
_MOD_FUND = "backend.feature_store.features.fundamental"

for f in [
    Feature("fund_roe",                FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "decimal"),
    Feature("fund_debt_to_equity",     FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "ratio"),
    Feature("fund_profit_margin",      FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "decimal"),
    Feature("fund_earnings_growth",    FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "decimal"),
    Feature("fund_trailing_pe",        FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "ratio"),
    Feature("fund_price_to_book",      FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "ratio"),
    Feature("fund_quality_score",      FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "0..100 or zscore"),
    Feature("fund_market_cap_log",     FeatureCategory.FUNDAMENTAL, "float", _MOD_FUND, "log(cap)"),
]:
    register(f)


# ─── News (from CanonicalNews) ────────────────────────────────────
_MOD_NEWS = "backend.feature_store.features.news"

for f in [
    Feature("news_sentiment",          FeatureCategory.NEWS, "float", _MOD_NEWS, "[-1, +1]"),
    Feature("news_n_headlines",        FeatureCategory.NEWS, "int",   _MOD_NEWS, "count"),
    Feature("news_n_positive",         FeatureCategory.NEWS, "int",   _MOD_NEWS, "count"),
    Feature("news_n_negative",         FeatureCategory.NEWS, "int",   _MOD_NEWS, "count"),
    Feature("news_polarity_ratio",     FeatureCategory.NEWS, "float", _MOD_NEWS, "(pos-neg)/total"),
]:
    register(f)


# ─── Earnings (from CanonicalEarnings) ────────────────────────────
_MOD_EARN = "backend.feature_store.features.earnings"

for f in [
    Feature("earn_days_to_next",       FeatureCategory.EARNINGS, "int",   _MOD_EARN, "days · null if unknown"),
    Feature("earn_last_surprise_pct",  FeatureCategory.EARNINGS, "float", _MOD_EARN, "%"),
    Feature("earn_last_eps_reported",  FeatureCategory.EARNINGS, "float", _MOD_EARN, "native"),
    Feature("earn_last_eps_estimate",  FeatureCategory.EARNINGS, "float", _MOD_EARN, "native"),
]:
    register(f)


# ─── Macro (from CanonicalMacro; joined to every ticker as market-level) ─
_MOD_MACRO = "backend.feature_store.features.macro"

for f in [
    Feature("macro_10y",               FeatureCategory.MACRO, "float", _MOD_MACRO, "%"),
    Feature("macro_10y_chg_1m_pct",    FeatureCategory.MACRO, "float", _MOD_MACRO, "%"),
    Feature("macro_dxy",               FeatureCategory.MACRO, "float", _MOD_MACRO, "level"),
    Feature("macro_gold",              FeatureCategory.MACRO, "float", _MOD_MACRO, "USD"),
    Feature("macro_wti_oil",           FeatureCategory.MACRO, "float", _MOD_MACRO, "USD"),
    Feature("macro_vix",               FeatureCategory.MACRO, "float", _MOD_MACRO, "level"),
    Feature("macro_vix_chg_1m_pct",    FeatureCategory.MACRO, "float", _MOD_MACRO, "%"),
    Feature("macro_move",              FeatureCategory.MACRO, "float", _MOD_MACRO, "level"),
]:
    register(f)


# ─── Sector (from CanonicalFlowProxy + universe) ──────────────────
_MOD_SECTOR = "backend.feature_store.features.sector"

for f in [
    Feature("sector_return_1m_pct",    FeatureCategory.SECTOR, "float", _MOD_SECTOR, "%"),
    Feature("sector_rank",             FeatureCategory.SECTOR, "int",   _MOD_SECTOR, "1=leader"),
    Feature("sector_is_leader",        FeatureCategory.SECTOR, "int",   _MOD_SECTOR, "0/1 top-3"),
    Feature("sector_is_laggard",       FeatureCategory.SECTOR, "int",   _MOD_SECTOR, "0/1 bottom-3"),
]:
    register(f)


# ─── Institutional (from CanonicalFlow + CanonicalHolding) ────────
_MOD_INST = "backend.feature_store.features.institutional"

for f in [
    Feature("inst_pct_owned",          FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "% of shares out"),
    Feature("inst_top_holder_pct",     FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "%"),
    Feature("insider_net_90d",         FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "USD net"),
    Feature("insider_buy_90d",         FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "USD"),
    Feature("insider_sell_90d",        FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "USD"),
    Feature("fii_net_5d",              FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "INR Cr (India · market-level)"),
    Feature("dii_net_5d",              FeatureCategory.INSTITUTIONAL, "float", _MOD_INST, "INR Cr (India · market-level)"),
]:
    register(f)


# ─── Corporate actions (from CanonicalCorporateAction) ────────────
_MOD_CA = "backend.feature_store.features.corporate_actions"

for f in [
    Feature("ca_days_since_last_dividend", FeatureCategory.CORPORATE_ACTION, "int",   _MOD_CA, "days"),
    Feature("ca_last_dividend_amount",     FeatureCategory.CORPORATE_ACTION, "float", _MOD_CA, "native"),
    Feature("ca_days_since_last_split",    FeatureCategory.CORPORATE_ACTION, "int",   _MOD_CA, "days"),
    Feature("ca_last_split_ratio",         FeatureCategory.CORPORATE_ACTION, "float", _MOD_CA, "ratio"),
]:
    register(f)


# ─── Market Intelligence (joined) ─────────────────────────────────
_MOD_MI = "backend.feature_store.features.market_intel"

for f in [
    Feature("mi_regime",                    FeatureCategory.MARKET_INTEL, "str",   _MOD_MI, "bull/bear/neutral/stress"),
    Feature("mi_composite_score",           FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "0..100"),
    Feature("mi_breadth_above_20ma_pct",    FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "%"),
    Feature("mi_breadth_at_52w_high_pct",   FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "%"),
    Feature("mi_liquidity_5v20_pct",        FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "%"),
    Feature("mi_news_pulse",                FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "avg sentiment"),
    Feature("mi_benchmark_1m_pct",          FeatureCategory.MARKET_INTEL, "float", _MOD_MI, "%"),
]:
    register(f)


# ─── Historical learning (optional — from learning corpus / winner genome) ─
_MOD_HIST = "backend.feature_store.features.historical"

for f in [
    Feature("hist_ticker_win_rate",        FeatureCategory.HISTORICAL, "float", _MOD_HIST, "0..1 · null if no history"),
    Feature("hist_ticker_n_trades",        FeatureCategory.HISTORICAL, "int",   _MOD_HIST, "count · null if no history"),
    Feature("hist_ticker_avg_return_pct",  FeatureCategory.HISTORICAL, "float", _MOD_HIST, "% · null if no history"),
]:
    register(f)


# ─── Semantic declarations · all 81 features, one row each ────────
#
# CEO 2026-11-04. Each feature declares (granularity, provenance,
# freshness_days, expected_coverage_pct, validity_note). Classified from
# the producer's SOURCE, with the evidence in the comment above each
# block. Anything genuinely unresolved stays UNKNOWN so the validator
# refuses to assume rather than guessing from a name.
#
# `freshness_days` is calendar days of acceptable observation age.
# `expected_coverage_pct` is of the market universe, and is set below
# 100 where the SOURCE itself is known to be partial — so that a real
# shortfall is distinguishable from a source that never covered
# everything.

_G = FeatureGranularity

_DECLARATIONS: dict = {}


def _declare(names, granularity, provenance, freshness_days,
             expected_coverage_pct, validity_note=""):
    for n in names:
        _DECLARATIONS[n] = (granularity, provenance, freshness_days,
                            expected_coverage_pct, validity_note)


# IDENTITY · `ticker` and `sector` are per-name; the rest describe the
# whole snapshot. `sector` is declared TICKER even though USA currently
# fills it with 'Unknown' on all 516 rows — the declaration says what it
# SHOULD be, which is what makes that constancy a detectable defect
# rather than an accepted fact.
_declare(["ticker"], _G.TICKER, "universe membership", None, 100.0)
_declare(["sector"], _G.TICKER,
         "india.sectors.SECTORS · usa/reports/universe.json tickers[].sector",
         None, 100.0, "'Unknown' and '' are placeholders, not values")
_declare(["market", "currency"], _G.MARKET, "MarketProfile", None, 100.0)
_declare(["asof"], _G.MARKET, "snapshot build parameter", 0, 100.0)

# TECHNICAL · computed per symbol from CanonicalBar.
_declare(["close", "volume", "return_1d_pct", "return_5d_pct",
          "return_10d_pct", "return_20d_pct", "return_60d_pct",
          "volatility_20d", "volatility_60d", "rsi_14", "sma_20", "sma_50",
          "price_above_sma20", "price_above_sma50", "atr_14_pct", "adx_14",
          "macd", "macd_signal", "macd_hist", "distance_from_52w_high_pct",
          "distance_from_52w_low_pct", "position_in_52w_range",
          "max_drawdown_60d_pct", "volume_ratio_5v20"],
         _G.TICKER, "data/raw/<market>/<SYMBOL>_D1.parquet via adapt_prices",
         4, 95.0)
_declare(["sma_200", "price_above_sma200"], _G.TICKER,
         "data/raw/<market>/<SYMBOL>_D1.parquet via adapt_prices", 4, 95.0,
         "needs 200 bars at or before the asof · abstains below that")

# FUNDAMENTAL · per issuer, revised quarterly.
_declare(["fund_roe", "fund_debt_to_equity", "fund_profit_margin",
          "fund_earnings_growth", "fund_trailing_pe", "fund_price_to_book",
          "fund_quality_score", "fund_market_cap_log"],
         _G.TICKER,
         "data/raw/india/fundamentals.parquet · usa/reports/fundamentals.json",
         120, 75.0, "0.0 is a real value for some ratios and a missing "
                    "marker for others · never coerce null to 0")

# NEWS · headlines are matched per ticker, so these are TICKER even
# though news_n_headlines is currently constant in BOTH markets. That
# constancy is exactly the defect the declaration makes visible.
_declare(["news_sentiment", "news_n_headlines", "news_n_positive",
          "news_n_negative", "news_polarity_ratio"],
         _G.TICKER, "per-ticker news ingest", 3, 40.0,
         "absence of headlines is not sentiment 0 · it is no observation")

# EARNINGS · per issuer calendar.
_declare(["earn_days_to_next", "earn_last_surprise_pct",
          "earn_last_eps_reported", "earn_last_eps_estimate"],
         _G.TICKER, "per-ticker earnings calendar", 30, 30.0)

# MACRO · GLOBAL, not MARKET: the SAME dated files under
# data/raw/india/global/ serve both India and USA, and the instruments
# (DXY, gold, WTI, VIX, US 10Y) are world risk factors rather than one
# market's own. Domains and units live in macro_series.SERIES.
_declare(["macro_10y", "macro_10y_chg_1m_pct", "macro_dxy", "macro_gold",
          "macro_wti_oil", "macro_vix", "macro_vix_chg_1m_pct"],
         _G.GLOBAL, "data/raw/india/global/*.parquet via macro_series", 5,
         100.0, "domain-checked per macro_series.SERIES · UUP is not DXY")
_declare(["macro_move"], _G.GLOBAL,
         "reports/macro_summary.json ^MOVE · UNDATED snapshot", 5, 100.0,
         "no dated source exists · abstains for any historical asof")

# SECTOR · one observation per sector, shared by its members. Verified
# in features/sector.py: a sector→rank map is assigned through each
# ticker's own sector, so values repeat WITHIN a sector and differ
# BETWEEN sectors. Neither TICKER nor MARKET would describe that.
_declare(["sector_return_1m_pct", "sector_rank", "sector_is_leader",
          "sector_is_laggard"],
         _G.SECTOR,
         "reports/sector_context.json (India) · sector ETF flows (USA)",
         5, 100.0)

# INSTITUTIONAL · SPLIT granularity, which is why this block is not
# classified by prefix. inst_/insider_ are per-issuer filings.
# fii_net_5d and dii_net_5d are ONE national aggregate summed in
# features/institutional.py and then written to every ticker — MARKET,
# and India-only.
_declare(["inst_pct_owned", "inst_top_holder_pct", "insider_net_90d",
          "insider_buy_90d", "insider_sell_90d"],
         _G.TICKER, "per-issuer holdings / insider filings", 120, 50.0)
_declare(["fii_net_5d", "dii_net_5d"], _G.MARKET,
         "india/fii_dii.py national aggregate · broadcast to every row",
         5, 100.0, "India only · absent for USA by design, not by failure")

# CORPORATE ACTION · per issuer.
_declare(["ca_days_since_last_dividend", "ca_last_dividend_amount",
          "ca_days_since_last_split", "ca_last_split_ratio"],
         _G.TICKER, "corporate_actions.parquet", 30, 40.0)

# MARKET INTEL · the producer states it outright: "These are
# MARKET-LEVEL — same values broadcast to every ticker in the universe."
_declare(["mi_regime", "mi_composite_score", "mi_breadth_above_20ma_pct",
          "mi_breadth_at_52w_high_pct", "mi_liquidity_5v20_pct",
          "mi_news_pulse", "mi_benchmark_1m_pct"],
         _G.MARKET,
         "reports/market_intelligence.json · "
         "usa/reports/market_intelligence.json",
         2, 100.0)

# HISTORICAL · per-ticker realised outcomes from the learning corpus.
_declare(["hist_ticker_win_rate", "hist_ticker_n_trades",
          "hist_ticker_avg_return_pct"],
         _G.TICKER, "reports/learning.parquet · per-ticker closed trades",
         None, 20.0, "no history is null, never a win rate of 0")


def _apply_declarations() -> None:
    """Fold the declarations into the frozen registry entries."""
    import dataclasses
    for i, f in enumerate(FEATURE_REGISTRY):
        d = _DECLARATIONS.get(f.name)
        if d is None:
            continue
        g, prov, fresh, cov, note = d
        FEATURE_REGISTRY[i] = dataclasses.replace(
            f, granularity=g, provenance=prov, freshness_days=fresh,
            expected_coverage_pct=cov, validity_note=note)


_apply_declarations()


def granularity_of(name: str) -> FeatureGranularity:
    for f in FEATURE_REGISTRY:
        if f.name == name:
            return f.granularity
    return FeatureGranularity.UNKNOWN


def feature_by_name(name: str):
    for f in FEATURE_REGISTRY:
        if f.name == name:
            return f
    return None


def unclassified_features() -> list[str]:
    """Features still at UNKNOWN granularity · the validator's blind spots."""
    return [f.name for f in FEATURE_REGISTRY
            if f.granularity == FeatureGranularity.UNKNOWN]


def features_by_granularity() -> dict:
    out: dict = {}
    for f in FEATURE_REGISTRY:
        out.setdefault(f.granularity.value, []).append(f.name)
    return out
