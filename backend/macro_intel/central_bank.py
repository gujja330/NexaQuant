"""Central Bank rate cycle inference from yield movements.

Sprint 6.5 baseline: uses short-yield trend + curve movement to infer whether
the central bank is in a tightening / easing / neutral cycle. Deterministic —
no external central-bank speeches ingested (deferred).
"""
from __future__ import annotations

from backend.macro_intel.types import BondReading, CentralBankState


def infer_central_bank_state(market: str, bonds: list[BondReading],
                                curve_slope_bps: float | None,
                                inversion: bool) -> CentralBankState:
    """Infer rate cycle from short-yield 1m change."""
    by_sym = {b.symbol: b for b in bonds}
    short = by_sym.get("^IRX") or by_sym.get("^FVX")
    long  = by_sym.get("^TNX")

    if market == "usa":
        bank = "Fed"
    elif market == "india":
        bank = "RBI"
    else:
        bank = "Central Bank"

    if short is None:
        return CentralBankState(
            market=market, bank=bank, rate_cycle="unknown",
            short_yield_pct=None, long_yield_pct=(long.yield_pct if long else None),
            yield_curve_slope=curve_slope_bps, inversion=inversion,
            liquidity_score=0.0,
            notes=[f"{bank}: insufficient data (no short-yield reading)"],
        )

    # Rule: if short yields rising over the past month → tightening cycle
    chg_1m = short.chg_1m_bps
    rate_cycle = "neutral"
    liq_score = 0.0
    if chg_1m is not None:
        if chg_1m > 15:
            rate_cycle = "tightening"; liq_score = -0.7
        elif chg_1m < -15:
            rate_cycle = "easing"; liq_score = +0.7
        elif abs(chg_1m) < 5:
            rate_cycle = "neutral"; liq_score = 0.0

    notes = [f"{bank}: cycle={rate_cycle} · short_1m={chg_1m}bps"]
    if inversion:
        notes.append("Yield curve INVERTED — historical recession leading indicator")

    return CentralBankState(
        market=market, bank=bank, rate_cycle=rate_cycle,
        short_yield_pct=short.yield_pct,
        long_yield_pct=(long.yield_pct if long else None),
        yield_curve_slope=curve_slope_bps,
        inversion=inversion,
        liquidity_score=round(liq_score, 2),
        notes=notes,
    )
