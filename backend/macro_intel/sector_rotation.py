"""Sector rotation — daily flow scoring from ETF or sector composite returns."""
from __future__ import annotations

from datetime import date

from backend.macro_intel.types import SectorRotationReading


# USA sector ETF ticker → readable sector name
_USA_ETF_TO_SECTOR = {
    "XLK":  "Technology",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLE":  "Energy",
    "XLI":  "Industrials",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication Services",
}


def compute_sector_rotation(market: str, asof: date,
                              etf_flows_summary: dict | None = None,
                              sector_context: dict | None = None) -> SectorRotationReading:
    """Return a SectorRotationReading.

    Prefers ETF returns (USA) via Sprint 1B etf_flows_summary.json;
    India falls back to sector_context.json if present.
    """
    reading = SectorRotationReading(market=market, asof=asof)

    sector_returns: dict[str, float] = {}

    if market == "usa" and etf_flows_summary:
        for row in etf_flows_summary.get("per_etf", []):
            sym = str(row.get("ticker") or "")
            sec = _USA_ETF_TO_SECTOR.get(sym)
            if not sec: continue
            ret = row.get("return_pct")
            if ret is None: continue
            sector_returns[sec] = float(ret)
    elif market == "india" and sector_context:
        sectors = sector_context.get("sectors") or {}
        if isinstance(sectors, dict):
            for name, s in sectors.items():
                if not isinstance(s, dict): continue
                ret = s.get("return_pct") or s.get("mean_return_pct")
                if ret is None: continue
                sector_returns[str(name)] = float(ret)

    if not sector_returns:
        return reading

    ranked = sorted(sector_returns.items(), key=lambda kv: kv[1], reverse=True)
    reading.sector_returns = {k: round(v, 4) for k, v in ranked}
    reading.leaders  = [{"sector": s, "return_pct": v} for s, v in ranked[:3]]
    reading.laggards = [{"sector": s, "return_pct": v} for s, v in ranked[-3:][::-1]]

    # Rotation strength = std of returns / mean-abs (bounded)
    vals = list(sector_returns.values())
    if len(vals) >= 3:
        mean_abs = sum(abs(v) for v in vals) / len(vals)
        if mean_abs > 0:
            # Simple dispersion measure
            reading.rotation_strength = round(min(1.0, mean_abs / 10.0), 3)
    return reading
