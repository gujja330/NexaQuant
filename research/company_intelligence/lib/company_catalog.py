"""DEV020 company catalogue — reverse-derived from DEV019 industry catalog + AEGIS sector map.

Every AEGIS-universe ticker (data/raw/india/*.parquet) is mapped to at most one
industry (from DEV019's industry_catalog.INDUSTRIES) and inherits that industry's
parent sector.

Companies that appear in NO industry map are excluded from DEV020 v0.1 —
listed under `unmapped_tickers()` for v0.2 attention.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PARQ_DIR = _ROOT / "data" / "raw" / "india"

sys.path.insert(0, str(_ROOT / "research"))
from industry_intelligence.lib import industry_catalog                             # noqa: E402

# Also reuse the AEGIS sector map for sector-name fallback when industry has none
sys.path.insert(0, str(_ROOT))
try:
    from india.sectors import SECTORS as _AEGIS_SECTOR_MAP
except Exception:
    _AEGIS_SECTOR_MAP = {}


@dataclass
class CompanySpec:
    ticker: str
    industry_key: str
    industry_display: str
    parent_sector_key: str
    parent_sector_display: str
    aegis_sector_label: str | None                            # from india/sectors.py

    @property
    def parquet_path(self) -> Path:
        return _PARQ_DIR / f"{self.ticker}_D1.parquet"

    @property
    def available(self) -> bool:
        return self.parquet_path.exists()


def _build_universe() -> tuple[list[CompanySpec], list[str]]:
    """Build the company universe from industry_catalog. Every industry ticker
    becomes a CompanySpec — deduplicated to first-occurrence (industry ordering)."""
    seen: dict[str, CompanySpec] = {}
    for i in industry_catalog.INDUSTRIES:
        for t in i.tickers:
            if t in seen:
                continue                                        # first industry wins
            seen[t] = CompanySpec(
                ticker=t,
                industry_key=i.industry_key,
                industry_display=i.display_name,
                parent_sector_key=i.parent_sector_key,
                parent_sector_display=i.parent_sector_name,
                aegis_sector_label=_AEGIS_SECTOR_MAP.get(t),
            )
    companies = sorted(seen.values(), key=lambda x: x.ticker)

    # Companies present as parquets on disk but not in any industry mapping
    all_on_disk = {p.stem.replace("_D1", "") for p in _PARQ_DIR.glob("*_D1.parquet")}
    unmapped = sorted(all_on_disk - set(seen.keys()))
    return companies, unmapped


COMPANIES, UNMAPPED_TICKERS = _build_universe()


def summary() -> dict:
    available = [c for c in COMPANIES if c.available]
    return {
        "total_companies_mapped": len(COMPANIES),
        "with_parquet_on_disk": len(available),
        "unmapped_tickers_on_disk": len(UNMAPPED_TICKERS),
        "unmapped_sample": UNMAPPED_TICKERS[:10],
    }


def by_ticker(ticker: str) -> CompanySpec:
    for c in COMPANIES:
        if c.ticker == ticker:
            return c
    raise KeyError(f"unknown ticker: {ticker}")


def by_industry(industry_key: str) -> list[CompanySpec]:
    return [c for c in COMPANIES if c.industry_key == industry_key]


def by_sector(sector_key: str) -> list[CompanySpec]:
    return [c for c in COMPANIES if c.parent_sector_key == sector_key]
