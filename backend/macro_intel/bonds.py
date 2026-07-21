"""Bond intelligence — yields, curve, inversion."""
from __future__ import annotations

from backend.macro_intel.types import BondReading


BOND_LABELS = {
    "^TNX":  "10Y Treasury yield",
    "^TYX":  "30Y Treasury yield",
    "^FVX":  "5Y Treasury yield",
    "^IRX":  "13W T-Bill yield",
}
BOND_ONLY = set(BOND_LABELS.keys())


def _pct_to_bps(last, chg_pct):
    """A 1% move in a 4%-yield security is 4 bps (rough conversion)."""
    if last is None or chg_pct is None: return None
    return float(last * chg_pct)


def read_bonds(macro_summary: dict | None) -> list[BondReading]:
    out: list[BondReading] = []
    if not macro_summary: return out
    for row in macro_summary.get("per_symbol", []):
        sym = str(row.get("symbol") or "")
        if sym not in BOND_ONLY: continue
        last = row.get("last")
        if last is None: continue
        out.append(BondReading(
            symbol=sym, label=BOND_LABELS.get(sym, sym),
            yield_pct=float(last),
            chg_1d_bps=_pct_to_bps(last, row.get("chg_1d_pct")),
            chg_1w_bps=_pct_to_bps(last, row.get("chg_1w_pct")),
            chg_1m_bps=_pct_to_bps(last, row.get("chg_1m_pct")),
        ))
    return sorted(out, key=lambda r: r.symbol)


def compute_yield_curve(bonds: list[BondReading]) -> tuple[float | None, bool]:
    """Return (slope_bps_10y_minus_2y, inversion_flag). 2y proxied by IRX or FVX."""
    by_sym = {b.symbol: b for b in bonds}
    ten = by_sym.get("^TNX")
    # Prefer FVX (5Y) as the short leg if IRX (13W) unavailable
    short = by_sym.get("^FVX") or by_sym.get("^IRX")
    if ten is None or short is None:
        return None, False
    slope_bps = (ten.yield_pct - short.yield_pct) * 100    # yields in %, slope in bps
    return round(float(slope_bps), 2), bool(slope_bps < 0)
