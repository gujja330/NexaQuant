"""DEV023 smoke tests. Fast; no network."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from recommendations.lib import decisions, entry_exit                                # noqa: E402


PASS = 0
FAIL = 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _base_input(**overrides) -> decisions.DecisionInput:
    """Baseline DecisionInput with sensible defaults; override as needed."""
    d = dict(
        ticker="T", company_score=70.0, classification="Bullish", confidence=0.7,
        industry_score=60.0, sector_score=55.0, global_posture="Neutral",
        in_target_portfolios=["top_20_ew"], currently_held=False,
        latest_close=100.0,
    )
    d.update(overrides)
    return decisions.DecisionInput(**d)


def test_strong_buy():
    inp = _base_input(company_score=80, classification="Strong-Bullish", confidence=0.8)
    d = decisions.decide(inp)
    _check("Strong-Buy triggers on high score", d.recommendation == decisions.RecType.STRONG_BUY)
    _check("Strong-Buy action is NEW_POSITION", d.action == decisions.ActionType.NEW_POSITION)


def test_buy():
    inp = _base_input(company_score=65, classification="Bullish", confidence=0.65,
                        in_target_portfolios=[])
    d = decisions.decide(inp)
    _check("Buy triggers on bullish", d.recommendation == decisions.RecType.BUY)


def test_watchlist():
    inp = _base_input(company_score=57, classification="Neutral", confidence=0.6,
                        in_target_portfolios=[])
    d = decisions.decide(inp)
    _check("Watchlist for 55-60 range", d.recommendation == decisions.RecType.WATCHLIST,
            detail=f"got {d.recommendation}")


def test_avoid_low_score():
    inp = _base_input(company_score=25, classification="Bearish", confidence=0.8,
                        in_target_portfolios=[])
    d = decisions.decide(inp)
    _check("Avoid on Bearish", d.recommendation == decisions.RecType.AVOID)


def test_hold():
    inp = _base_input(company_score=55, classification="Neutral", currently_held=True,
                        in_target_portfolios=[])
    d = decisions.decide(inp)
    _check("Hold for existing neutral position", d.recommendation == decisions.RecType.HOLD)


def test_sell_bearish():
    inp = _base_input(company_score=25, classification="Bearish", currently_held=True)
    d = decisions.decide(inp)
    _check("Sell bearish existing position", d.recommendation == decisions.RecType.SELL)


def test_reduce_weakening():
    inp = _base_input(company_score=42, classification="Weak", currently_held=True)
    d = decisions.decide(inp)
    _check("Reduce weakening existing", d.recommendation == decisions.RecType.REDUCE)


def test_accumulate():
    inp = _base_input(company_score=75, classification="Strong-Bullish",
                        currently_held=True, in_target_portfolios=["top_20_ew"],
                        confidence=0.8)
    d = decisions.decide(inp)
    _check("Accumulate strong-bullish held position",
            d.recommendation == decisions.RecType.ACCUMULATE)


def test_stop_loss():
    inp = _base_input(currently_held=True, unrealised_pnl_pct=-10.0)
    d = decisions.decide(inp)
    _check("Sell when unrealised loss > 8%", d.recommendation == decisions.RecType.SELL)


def test_composite_decision_score():
    inp = _base_input(company_score=80, industry_score=70, sector_score=65,
                        global_posture="Risk-On")
    cds = decisions.composite_decision_score(inp)
    _check("CDS in [0, 100]", 0 <= cds <= 100)
    _check("CDS reflects high inputs", cds > 60, detail=f"got {cds:.1f}")


def test_conviction_direction():
    inp = _base_input(company_score=85, classification="Strong-Bullish", confidence=0.9)
    d = decisions.decide(inp)
    _check("high-conviction Strong-Buy",
            d.conviction_pct > 60, detail=f"got {d.conviction_pct}")


def test_entry_exit_levels():
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    rng = np.random.default_rng(seed=42)
    prices = 100 * (1 + pd.Series(rng.normal(0.0006, 0.015, 252), index=idx)).cumprod()
    levels = entry_exit.compute(prices, "Strong-Buy")
    _check("entry_exit computes", levels is not None)
    if levels:
        _check("ideal_entry_low < high", levels.ideal_entry_low < levels.ideal_entry_high)
        _check("target_2 > target_1", levels.target_2 > levels.target_1)
        _check("stop_loss below latest",
                levels.stop_loss < levels.latest_close)
        _check("stop_loss_pct is negative", levels.stop_loss_pct < 0)
        _check("expected_hold <= max_hold",
                levels.expected_holding_days <= levels.maximum_holding_days)
        _check("vol > 0", levels.annualised_vol_pct > 0)


def test_entry_exit_insufficient_data():
    idx = pd.date_range("2024-01-01", periods=20, freq="B")
    prices = pd.Series(range(100, 120), index=idx, dtype=float)
    levels = entry_exit.compute(prices, "Buy")
    _check("entry_exit returns None on short history", levels is None)


def test_reasons_populated():
    inp = _base_input(company_score=82, classification="Strong-Bullish",
                        confidence=0.85, industry_score=70, sector_score=68)
    d = decisions.decide(inp)
    _check("reasons_for is non-empty", len(d.reasons_for) > 0)
    _check("no false positives in against",
            not any("bearish" in r for r in d.reasons_against))


def test_determinism():
    """Same input produces same output."""
    inp1 = _base_input(company_score=72, classification="Bullish", confidence=0.75)
    inp2 = _base_input(company_score=72, classification="Bullish", confidence=0.75)
    d1 = decisions.decide(inp1)
    d2 = decisions.decide(inp2)
    _check("deterministic recommendation",
            d1.recommendation == d2.recommendation)
    _check("deterministic composite_decision_score",
            abs(d1.composite_decision_score - d2.composite_decision_score) < 1e-9)
    _check("deterministic conviction",
            abs(d1.conviction_pct - d2.conviction_pct) < 1e-9)


def main() -> int:
    print("=" * 70)
    print("  DEV023 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_strong_buy(); print()
    test_buy(); print()
    test_watchlist(); print()
    test_avoid_low_score(); print()
    test_hold(); print()
    test_sell_bearish(); print()
    test_reduce_weakening(); print()
    test_accumulate(); print()
    test_stop_loss(); print()
    test_composite_decision_score(); print()
    test_conviction_direction(); print()
    test_entry_exit_levels(); print()
    test_entry_exit_insufficient_data(); print()
    test_reasons_populated(); print()
    test_determinism(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
