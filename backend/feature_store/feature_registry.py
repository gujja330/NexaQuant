"""Feature Registry — every Feature Store column is declared HERE.

Rationale: engines downstream will assume specific column names + dtypes.
The registry is the contract. Adding a column bumps the schema fingerprint;
removing/renaming a column requires a migration entry in feature_versioning.

Categories map to the per-category computers under
`backend.feature_store.features.*`.
"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Feature:
    name:      str
    category:  FeatureCategory
    dtype:     str                # "float", "int", "str"
    producer:  str                # "backend.feature_store.features.technical", etc.
    unit:      str = ""           # "%", "USD", "days", "zscore"
    nullable:  bool = True        # some features are naturally missing (e.g. RSI for young tickers)
    description: str = ""


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
