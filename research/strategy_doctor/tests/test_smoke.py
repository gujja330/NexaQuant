"""DEV027 smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from strategy_doctor.lib import diagnostics                                          # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _trade(**kw):
    default = {
        "ticker": "T", "sector": "IT", "industry": "IT Services",
        "score_at_entry": 70, "confidence": 0.8,
        "return_pct": -5, "mfe_pct": 2, "mae_pct": -8, "is_winner": False,
        "entry_date": "2024-01-31",
    }
    default.update(kw)
    return default


def test_wrong_company():
    t = _trade(score_at_entry=75, confidence=0.55, return_pct=-6)
    d = diagnostics.wrong_company(t)
    _check("wrong_company fires on score>=70 + conf<0.6 + loss", d.fires)
    t2 = _trade(return_pct=5)                                # winner
    _check("wrong_company doesn't fire on winner",
            not diagnostics.wrong_company(t2).fires)


def test_wrong_sector():
    t = _trade(return_pct=-5, sector="Banking")
    sector_ctx = {"sectors": [{"display_name": "Banking", "status": "computed", "score": 40}]}
    d = diagnostics.wrong_sector(t, sector_ctx)
    _check("wrong_sector fires when parent weak", d.fires)


def test_wrong_regime():
    t = _trade(return_pct=-5)
    global_ctx = {"classifications": {"global_posture": {"label": "Risk-Off"}}}
    d = diagnostics.wrong_regime(t, global_ctx)
    _check("wrong_regime fires on Risk-Off + loss", d.fires)


def test_late_entry():
    t = _trade(return_pct=-4, mfe_pct=6)
    d = diagnostics.late_entry(t)
    _check("late_entry fires when MFE >5 but final loss", d.fires)


def test_early_exit():
    t = _trade(return_pct=3, mfe_pct=10, is_winner=True)
    d = diagnostics.early_exit(t)
    _check("early_exit fires when MFE >> final", d.fires)


def test_weak_conviction():
    t = _trade(confidence=0.55, return_pct=-3)
    _check("weak_conviction fires", diagnostics.weak_conviction(t).fires)


def test_overconfidence():
    t = _trade(confidence=0.90, return_pct=-8)
    d = diagnostics.overconfidence(t)
    _check("overconfidence fires on high-conf + loss", d.fires)
    _check("severity is HIGH", d.severity == "HIGH")


def test_underconfidence():
    t = _trade(confidence=0.55, return_pct=10, is_winner=True)
    _check("underconfidence fires on low-conf + big gain",
            diagnostics.underconfidence(t).fires)


def test_high_correlation():
    losers = [_trade(sector="IT", return_pct=-5) for _ in range(4)]
    d = diagnostics.high_correlation(losers[0], losers)
    _check("high_correlation fires on same-sector losing cohort", d.fires)


def test_excess_concentration():
    trades = [_trade(sector="IT") for _ in range(7)] + [_trade(sector="Auto") for _ in range(3)]
    d = diagnostics.excess_concentration(trades[0], trades)
    _check("excess_concentration fires when >30% in one sector", d.fires)


def test_macro_shock():
    losers = [_trade(return_pct=-3) for _ in range(8)]
    winner = _trade(return_pct=+3, is_winner=True)
    trades = losers + [winner, winner]
    d = diagnostics.macro_shock(losers[0], trades)
    _check("macro_shock fires when >60% cohort losing", d.fires)


def test_volatility_risk():
    t = _trade(mfe_pct=15, mae_pct=-15)
    _check("volatility_risk fires on wild swings",
            diagnostics.volatility_risk(t).fires)


def test_liquidity_shock():
    t = _trade(mae_pct=-20, return_pct=-10)
    _check("liquidity_shock fires on extreme MAE",
            diagnostics.liquidity_shock(t).fires)


def test_poor_diversification():
    trades = [_trade(sector="IT") for _ in range(6)] + [_trade(sector="Auto") for _ in range(5)]
    d = diagnostics.poor_diversification(trades)
    _check("poor_diversification fires with <=3 sectors", d.fires)


def test_stop_loss_ineffective():
    t = _trade(mae_pct=-7, return_pct=5, is_winner=True)
    _check("stop_loss_ineffective fires when dipped then recovered",
            diagnostics.stop_loss_ineffective(t).fires)


def test_diagnostics_registry():
    _check("ALL_DIAGNOSTICS has 15 categories",
            len(diagnostics.ALL_DIAGNOSTICS) == 15)


def main() -> int:
    print("=" * 70)
    print("  DEV027 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_wrong_company(); print()
    test_wrong_sector(); print()
    test_wrong_regime(); print()
    test_late_entry(); print()
    test_early_exit(); print()
    test_weak_conviction(); print()
    test_overconfidence(); print()
    test_underconfidence(); print()
    test_high_correlation(); print()
    test_excess_concentration(); print()
    test_macro_shock(); print()
    test_volatility_risk(); print()
    test_liquidity_shock(); print()
    test_poor_diversification(); print()
    test_stop_loss_ineffective(); print()
    test_diagnostics_registry(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
