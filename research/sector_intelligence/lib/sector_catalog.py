"""DEV018 sector catalogue.

NSE sector indices via yfinance. Each entry has a primary ticker plus optional
fallback tickers (yfinance's NSE-index symbols are unstable across versions).

The `constituents` list is derived from india/sectors.py — the tenant-generic
sector map used across the AEGIS repo.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Import the existing sector map — tenant-generic, per ARCH001A Article VII clause 7.6
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
try:
    from india.sectors import SECTORS as _AEGIS_SECTOR_MAP
except Exception:
    _AEGIS_SECTOR_MAP = {}


@dataclass
class SectorSpec:
    sector_key: str                              # ARCH017A canonical: sector.<name>
    display_name: str
    yfinance_tickers: list[str]                  # try in order; first non-empty wins
    unit: str = "index_pts"
    source_id: str = "yfinance.v0"
    tier: int = 2
    frequency: str = "daily"
    # AEGIS internal sector label the ticker→sector map uses (from india/sectors.py)
    aegis_sector_labels: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def constituents(self) -> list[str]:
        """AEGIS-universe tickers mapped to any of this sector's aegis labels."""
        out = []
        for tk, sec in _AEGIS_SECTOR_MAP.items():
            if sec in self.aegis_sector_labels:
                out.append(tk)
        return out


# ── NSE Sector Indices (yfinance-fetchable) ──────────────────────────────────
# Some ^CNX* tickers can be flaky; fallback names are included.
SECTORS: list[SectorSpec] = [
    SectorSpec(
        "sector.india.banking",       "Banking",
        yfinance_tickers=["^NSEBANK", "NIFTY_BANK.NS"],
        aegis_sector_labels=["Financials"],
        description="Nifty Bank index"),
    SectorSpec(
        "sector.india.it",            "IT",
        yfinance_tickers=["^CNXIT", "NIFTY_IT.NS"],
        aegis_sector_labels=["IT"],
        description="Nifty IT index"),
    SectorSpec(
        "sector.india.auto",          "Auto",
        yfinance_tickers=["^CNXAUTO", "NIFTY_AUTO.NS"],
        aegis_sector_labels=["Auto"],
        description="Nifty Auto index"),
    SectorSpec(
        "sector.india.pharma",        "Pharma",
        yfinance_tickers=["^CNXPHARMA", "NIFTY_PHARMA.NS"],
        aegis_sector_labels=["Pharma"],
        description="Nifty Pharma index"),
    SectorSpec(
        "sector.india.fmcg",          "FMCG",
        yfinance_tickers=["^CNXFMCG", "NIFTY_FMCG.NS"],
        aegis_sector_labels=["FMCG"],
        description="Nifty FMCG index"),
    SectorSpec(
        "sector.india.metal",         "Metal",
        yfinance_tickers=["^CNXMETAL", "NIFTY_METAL.NS"],
        aegis_sector_labels=["Metal"],
        description="Nifty Metal index"),
    SectorSpec(
        "sector.india.energy",        "Energy",
        yfinance_tickers=["^CNXENERGY", "NIFTY_ENERGY.NS"],
        aegis_sector_labels=["Energy"],
        description="Nifty Energy index (Oil & Gas + Power)"),
    SectorSpec(
        "sector.india.psu_bank",      "PSU Bank",
        yfinance_tickers=["^CNXPSUBANK", "NIFTY_PSU_BANK.NS"],
        aegis_sector_labels=["Financials"],       # subset — PSU banks live under Financials
        description="Nifty PSU Bank index"),
    SectorSpec(
        "sector.india.realty",        "Realty",
        yfinance_tickers=["^CNXREALTY", "NIFTY_REALTY.NS"],
        aegis_sector_labels=["Realty"],
        description="Nifty Realty index"),
    SectorSpec(
        "sector.india.infra",         "Infrastructure",
        yfinance_tickers=["^CNXINFRA", "NIFTY_INFRA.NS"],
        aegis_sector_labels=["Infra"],
        description="Nifty Infrastructure index"),
    SectorSpec(
        "sector.india.media",         "Media",
        yfinance_tickers=["^CNXMEDIA", "NIFTY_MEDIA.NS"],
        aegis_sector_labels=["Media"],
        description="Nifty Media index"),
    SectorSpec(
        "sector.india.financial_svc", "Financial Services",
        yfinance_tickers=["^CNXFIN", "NIFTY_FIN_SERVICE.NS"],
        aegis_sector_labels=["Financials"],
        description="Nifty Financial Services (broader than Bank Nifty)"),
    SectorSpec(
        "sector.india.consumption",   "Consumption",
        yfinance_tickers=["^CNXCONSUM", "NIFTY_CONSUMPTION.NS"],
        aegis_sector_labels=["Consumer", "FMCG"],
        description="Nifty Consumption index"),
    SectorSpec(
        "sector.india.healthcare",    "Healthcare",
        yfinance_tickers=["NIFTY_HEALTHCARE.NS", "^CNXHEALTHCARE"],
        aegis_sector_labels=["Healthcare", "Pharma"],
        description="Nifty Healthcare Index (broader than Pharma)"),
]


# ── Nifty benchmark for RS calculations ──────────────────────────────────────
# Already fetched by DEV017 as equity_index.india.nifty50.close; we reference by key.
NIFTY_50_KEY = "equity_index.india.nifty50.close"
NIFTY_500_KEY = "equity_index.india.nifty500.close"                  # not in DEV017 v0.1 catalog


def by_sector_key(sector_key: str) -> SectorSpec:
    for s in SECTORS:
        if s.sector_key == sector_key:
            return s
    raise KeyError(f"unknown sector_key: {sector_key}")


def summary() -> dict:
    return {
        "total_sectors": len(SECTORS),
        "sectors": [s.display_name for s in SECTORS],
        "constituent_universe_size": len(_AEGIS_SECTOR_MAP),
        "sector_map_source": "india/sectors.py (tenant-generic)",
    }
