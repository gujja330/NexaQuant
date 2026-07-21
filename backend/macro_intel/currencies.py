"""Currency readers from macro_summary + optional overrides."""
from __future__ import annotations

from backend.macro_intel.types import CurrencyReading


CURRENCY_LABELS = {
    "UUP":     "USD Index (UUP proxy)",
    "USDINR":  "USD/INR",
    "EURUSD":  "EUR/USD",
    "USDJPY":  "USD/JPY",
    "GBPUSD":  "GBP/USD",
    "EURINR":  "EUR/INR",
    "JPYINR":  "JPY/INR",
}
CURRENCY_ONLY = set(CURRENCY_LABELS.keys())


def _trend(chg_1w_pct):
    if chg_1w_pct is None: return "unknown"
    if chg_1w_pct > 1.0:  return "strengthening"
    if chg_1w_pct < -1.0: return "weakening"
    return "range"


def read_currencies(macro_summary: dict | None) -> list[CurrencyReading]:
    out: list[CurrencyReading] = []
    if not macro_summary: return out
    for row in macro_summary.get("per_symbol", []):
        sym = str(row.get("symbol") or "")
        if sym not in CURRENCY_ONLY: continue
        last = row.get("last")
        if last is None: continue
        chg_1w = row.get("chg_1w_pct")
        out.append(CurrencyReading(
            symbol=sym, label=CURRENCY_LABELS.get(sym, sym),
            last=float(last),
            chg_1d_pct=row.get("chg_1d_pct"),
            chg_1w_pct=chg_1w,
            chg_1m_pct=row.get("chg_1m_pct"),
            trend=_trend(chg_1w),
        ))
    return sorted(out, key=lambda r: r.symbol)
