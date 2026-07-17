"""ARCH017 §3 variable catalogue — DEV017 v0.1 subset.

Only variables that can be reliably fetched via yfinance (free, no auth) are
included in v0.1. Macro variables (CPI, PMI, NFP), central-bank statements,
and India-specific flow data are deferred to v0.2 with a documented follow-up.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VariableSpec:
    variable_key: str
    yfinance_ticker: str
    unit: str
    source_id: str = "yfinance.v0"
    tier: int = 2
    frequency: str = "daily"
    description: str = ""


# ── Global equity indices (ARCH017 §3.1) ─────────────────────────────────────
EQUITY_INDICES: list[VariableSpec] = [
    VariableSpec("equity_index.us.spx.close",           "^GSPC",  "index_pts", description="S&P 500 close"),
    VariableSpec("equity_index.us.ndx.close",           "^NDX",   "index_pts", description="Nasdaq 100 close"),
    VariableSpec("equity_index.us.djia.close",          "^DJI",   "index_pts", description="Dow Jones Industrial close"),
    VariableSpec("equity_index.jp.n225.close",          "^N225",  "index_pts", description="Nikkei 225 close"),
    VariableSpec("equity_index.hk.hsi.close",           "^HSI",   "index_pts", description="Hang Seng close"),
    VariableSpec("equity_index.uk.ftse.close",          "^FTSE",  "index_pts", description="FTSE 100 close"),
    VariableSpec("equity_index.de.dax.close",           "^GDAXI", "index_pts", description="DAX close"),
    VariableSpec("equity_index.india.nifty50.close",    "^NSEI",  "index_pts", description="Nifty 50 close"),
    VariableSpec("equity_index.india.nifty_bank.close", "^NSEBANK","index_pts", description="Bank Nifty close"),
]

# ── Volatility indices (ARCH017 §3.2) ────────────────────────────────────────
VOLATILITY: list[VariableSpec] = [
    VariableSpec("volatility.us.vix.close",           "^VIX",       "index_pts", description="CBOE VIX"),
    VariableSpec("volatility.india.india_vix.close",  "^INDIAVIX",  "index_pts", description="India VIX"),
]

# ── Currencies (ARCH017 §3.3) ────────────────────────────────────────────────
CURRENCIES: list[VariableSpec] = [
    VariableSpec("fx.dxy.close",     "DX-Y.NYB",  "index_pts",   description="US Dollar Index (DXY)"),
    VariableSpec("fx.usd_inr.close", "INR=X",     "USD_per_INR", description="USD/INR spot"),
    VariableSpec("fx.eur_usd.close", "EURUSD=X",  "USD_per_EUR", description="EUR/USD"),
    VariableSpec("fx.usd_jpy.close", "JPY=X",     "JPY_per_USD", description="USD/JPY"),
]

# ── Commodities (ARCH017 §3.4) ───────────────────────────────────────────────
COMMODITIES: list[VariableSpec] = [
    VariableSpec("commodity.brent.close",        "BZ=F",  "USD_per_bbl",   description="Brent crude"),
    VariableSpec("commodity.wti.close",          "CL=F",  "USD_per_bbl",   description="WTI crude"),
    VariableSpec("commodity.gold.close",         "GC=F",  "USD_per_oz",    description="Gold futures"),
    VariableSpec("commodity.silver.close",       "SI=F",  "USD_per_oz",    description="Silver futures"),
    VariableSpec("commodity.copper.close",       "HG=F",  "USD_per_lb",    description="Copper futures"),
]

# ── Rates (ARCH017 §3.5) ─────────────────────────────────────────────────────
RATES: list[VariableSpec] = [
    VariableSpec("rates.us.10y.yield", "^TNX",  "%",  description="US 10Y treasury yield"),
    VariableSpec("rates.us.2y.yield",  "^IRX",  "%",  description="US 3-month T-bill (proxy for short end)"),  # 2Y ^UST2Y not available; using ^IRX
    VariableSpec("rates.us.30y.yield", "^TYX",  "%",  description="US 30Y treasury yield"),
]


ALL_VARIABLES: list[VariableSpec] = (
    EQUITY_INDICES + VOLATILITY + CURRENCIES + COMMODITIES + RATES
)


def by_key(variable_key: str) -> VariableSpec:
    for v in ALL_VARIABLES:
        if v.variable_key == variable_key:
            return v
    raise KeyError(f"unknown variable_key: {variable_key}")


def summary() -> dict:
    return {
        "total_variables": len(ALL_VARIABLES),
        "by_category": {
            "equity_indices":  len(EQUITY_INDICES),
            "volatility":      len(VOLATILITY),
            "currencies":      len(CURRENCIES),
            "commodities":     len(COMMODITIES),
            "rates":           len(RATES),
        },
        "deferred_to_v02": [
            "macro (CPI, PMI, NFP, GDP)",
            "central_bank (FOMC dots, RBI MPC)",
            "flow (FII/DII cash + F&O)",
            "breadth (NSE adv/dec, 52w highs/lows)",
            "liquidity (US credit spreads, overnight repo)",
        ],
    }
