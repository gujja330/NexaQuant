"""Risk & Capital Engine v2.0 smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np

from risk_capital_v2.lib import sizing, risk_budget                                     # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def test_sizing_basic():
    d = sizing.size_position(
        ticker="AAA", calibrated_confidence=0.75, regime="Neutral",
        annualised_vol=0.30, sector_share_so_far=0.0,
    )
    _check("target in [floor, ceiling]",
            sizing.FLOOR_WEIGHT <= d.target_weight <= sizing.CEILING_WEIGHT)
    _check("factors has 4 entries", len(d.factors) == 4)
    _check("counterfactuals include at_4pct and at_12pct",
            {"at_4pct", "at_12pct"}.issubset(d.counterfactuals.keys()))
    _check("verdict is one of {PASS, WARNING, BLOCK}",
            d.verdict in ("PASS", "WARNING", "BLOCK"))


def test_sizing_deterministic():
    d1 = sizing.size_position("AAA", 0.75, "Neutral", 0.30, 0.0)
    d2 = sizing.size_position("AAA", 0.75, "Neutral", 0.30, 0.0)
    _check("same inputs -> same target_weight",
            d1.target_weight == d2.target_weight)


def test_sizing_regime_dampens_risk_off():
    d_on  = sizing.size_position("AAA", 0.80, "Risk-On", 0.30, 0.0)
    d_off = sizing.size_position("AAA", 0.80, "Risk-Off", 0.30, 0.0)
    _check("Risk-Off produces smaller size than Risk-On",
            d_off.target_weight < d_on.target_weight,
            detail=f"on={d_on.target_weight} off={d_off.target_weight}")


def test_sizing_volatility_dampens_high_vol():
    d_low  = sizing.size_position("AAA", 0.80, "Neutral", 0.20, 0.0)
    d_high = sizing.size_position("AAA", 0.80, "Neutral", 0.60, 0.0)
    _check("high vol produces smaller size",
            d_high.target_weight < d_low.target_weight,
            detail=f"low={d_low.target_weight} high={d_high.target_weight}")


def test_sector_cap_blocks_further_concentration():
    d = sizing.size_position("AAA", 0.80, "Neutral", 0.30, sector_share_so_far=0.30)
    _check("BLOCK when sector at cap",
            d.verdict == "BLOCK",
            detail=d.verdict)
    _check("target is floor when sector blocked",
            d.target_weight == sizing.FLOOR_WEIGHT)


def test_risk_empty_portfolio():
    r = risk_budget.compute_risk(weights={}, ann_vol_by_ticker={})
    _check("empty portfolio returns 0 vol", r.portfolio_vol_annual == 0.0)


def test_risk_computes():
    weights = {"AAA": 0.05, "BBB": 0.05, "CCC": 0.05}
    ann_vol = {"AAA": 0.30, "BBB": 0.30, "CCC": 0.30}
    r = risk_budget.compute_risk(weights=weights, ann_vol_by_ticker=ann_vol,
                                     sector_by_ticker={"AAA": "Pharma", "BBB": "Pharma",
                                                        "CCC": "Banks"})
    _check("portfolio vol positive", r.portfolio_vol_annual > 0)
    _check("per_position rows exist", len(r.per_position) == 3)
    _check("per_sector rows exist", len(r.per_sector) == 2)
    _check("VaR 95 > 0", r.var_95 > 0)


def test_risk_budget_alerts_on_concentrated_portfolio():
    weights = {f"T{i}": 0.15 for i in range(10)}  # heavily overweight
    ann_vol = {f"T{i}": 0.50 for i in range(10)}
    r = risk_budget.compute_risk(weights=weights, ann_vol_by_ticker=ann_vol)
    _check("concentrated + high-vol -> alerts",
            len(r.alerts) > 0,
            detail=f"got {len(r.alerts)} alerts")


def main() -> int:
    print("=" * 72); print("  RISK & CAPITAL ENGINE v2.0 · SMOKE TESTS"); print("=" * 72)
    test_sizing_basic(); print()
    test_sizing_deterministic(); print()
    test_sizing_regime_dampens_risk_off(); print()
    test_sizing_volatility_dampens_high_vol(); print()
    test_sector_cap_blocks_further_concentration(); print()
    test_risk_empty_portfolio(); print()
    test_risk_computes(); print()
    test_risk_budget_alerts_on_concentrated_portfolio(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
