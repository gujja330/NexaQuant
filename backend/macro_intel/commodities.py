"""Commodity readers — extract from Sprint 1B macro ingestion."""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.macro_intel.types import CommodityReading


COMMODITY_LABELS = {
    "CL=F":  "WTI Crude",
    "BZ=F":  "Brent Crude",
    "GC=F":  "Gold",
    "SI=F":  "Silver",
    "HG=F":  "Copper",
    "NG=F":  "Natural Gas",
    "^TNX":  "10Y Treasury yield",     # not commodity but often lives here
}
COMMODITY_ONLY = {"CL=F", "BZ=F", "GC=F", "SI=F", "HG=F", "NG=F"}


def _trend(chg_1w_pct: float | None) -> str:
    if chg_1w_pct is None: return "unknown"
    if chg_1w_pct > 2:  return "bull"
    if chg_1w_pct < -2: return "bear"
    return "sideways"


def read_commodities(macro_summary: dict | None) -> list[CommodityReading]:
    """Read commodity block from a macro_summary.json (Sprint 1B output).

    macro_summary shape: {per_symbol: [{symbol, label, last, chg_1d_pct, chg_1w_pct, chg_1m_pct}, ...]}
    """
    out: list[CommodityReading] = []
    if not macro_summary:
        return out
    per = macro_summary.get("per_symbol", [])
    for row in per:
        sym = str(row.get("symbol") or "")
        if sym not in COMMODITY_ONLY: continue
        last = row.get("last")
        if last is None: continue
        chg_1w = row.get("chg_1w_pct")
        out.append(CommodityReading(
            symbol=sym,
            label=COMMODITY_LABELS.get(sym, sym),
            last=float(last),
            chg_1d_pct=row.get("chg_1d_pct"),
            chg_1w_pct=chg_1w,
            chg_1m_pct=row.get("chg_1m_pct"),
            trend=_trend(chg_1w),
        ))
    return sorted(out, key=lambda c: c.symbol)
