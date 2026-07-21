"""Sprint 4 regression — Risk Engine + AI Risk Analyst."""
from __future__ import annotations

import io
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.risk                 import (                                                # noqa: E402
    RiskEngine, kelly_fractional_size, confidence_tier_multiplier,
    apply_per_ticker_cap, apply_per_sector_cap,
    vol_adjusted_size, vix_regime_dampener,
    herfindahl_hirschman, top_k_concentration_pct,
    parametric_var_cvar,
)
from backend.risk.types           import RiskBudget, CapReason                              # noqa: E402
from backend.ai import risk_analyst                                                          # noqa: E402


def _budget(market="usa", shorts=True):
    return RiskBudget(
        market=market, max_kelly_fraction=0.30, per_ticker_cap=0.08,
        per_sector_cap=0.30, target_portfolio_vol=0.14,
        enable_shorts=shorts, default_stop_loss_pct=-0.10,
        confidence_tier_mult={"STRONG_BUY": 1.0, "BUY": 0.6, "HOLD": 0.0,
                                "SELL": -0.6, "STRONG_SELL": -1.0},
    )


# ── Sizing math ────────────────────────────────────────────────
def test_kelly_bounded_by_max_fraction():
    """Kelly output magnitude never exceeds max_kelly_fraction."""
    for edge in [-2.0, -0.5, 0.0, 0.5, 2.0]:
        for vol in [0.10, 0.30, 0.60]:
            k = kelly_fractional_size(edge, vol, max_kelly_fraction=0.25)
            assert abs(k) <= 0.25 + 1e-9, f"edge={edge} vol={vol} k={k}"
    print(f"  [OK] Kelly bounded by max_kelly_fraction across sweep")


def test_kelly_zero_when_vol_is_zero_or_missing():
    assert kelly_fractional_size(0.5, 0.0) == 0.0
    assert kelly_fractional_size(0.5, None) == 0.0
    print(f"  [OK] Kelly returns 0 on invalid vol")


def test_confidence_tier_signs():
    tm = {"STRONG_BUY": 1.0, "BUY": 0.6, "SELL": -0.6, "STRONG_SELL": -1.0, "HOLD": 0.0}
    assert confidence_tier_multiplier("STRONG_BUY", tm) > 0
    assert confidence_tier_multiplier("STRONG_SELL", tm) < 0
    assert confidence_tier_multiplier("HOLD", tm) == 0.0
    print(f"  [OK] confidence tier multipliers signed correctly")


# ── Exposure caps ──────────────────────────────────────────────
def test_per_ticker_cap_clips_both_sides():
    w, hit = apply_per_ticker_cap(0.15, per_ticker_cap=0.06)
    assert w == 0.06 and hit
    w, hit = apply_per_ticker_cap(-0.15, per_ticker_cap=0.06)
    assert w == -0.06 and hit
    w, hit = apply_per_ticker_cap(0.04, per_ticker_cap=0.06)
    assert w == 0.04 and not hit
    print(f"  [OK] per-ticker cap clips both sides + preserves under-cap")


def test_per_sector_cap_reduces_headroom():
    """After 22% Tech exposure, adding another 5% must be reduced to 3%."""
    current = {"Tech": 0.22}
    w, hit = apply_per_sector_cap(0.05, "Tech", current, per_sector_cap=0.25)
    assert hit and abs(w - 0.03) < 1e-9, f"expected 0.03 got {w}"
    print(f"  [OK] per-sector cap reduces available headroom")


def test_per_sector_cap_full_returns_zero():
    current = {"Tech": 0.25}
    w, hit = apply_per_sector_cap(0.05, "Tech", current, per_sector_cap=0.25)
    assert hit and w == 0.0
    print(f"  [OK] per-sector cap saturated → 0")


# ── Vol adjustment ─────────────────────────────────────────────
def test_vol_adjustment_scales_by_target_vs_ticker():
    s = vol_adjusted_size(0.10, ticker_vol_annualised=0.20, target_portfolio_vol=0.10)
    # scale = 0.10 / 0.20 = 0.5 → 0.10 × 0.5 = 0.05
    assert abs(s - 0.05) < 1e-9
    print(f"  [OK] vol-adjusted size scales inversely with ticker vol")


def test_vix_dampener_by_regime():
    assert vix_regime_dampener("bull", 15) == 1.00
    assert vix_regime_dampener("stress", 40) == 0.55
    # Elevated VIX in any regime dampens
    assert vix_regime_dampener("neutral", 30) == 0.80
    assert vix_regime_dampener("bear", 10) == 0.85
    print(f"  [OK] VIX dampener respects regime + level")


# ── Concentration ──────────────────────────────────────────────
def test_hhi_single_position_equals_1():
    assert abs(herfindahl_hirschman([0.5]) - 1.0) < 1e-9
    assert abs(herfindahl_hirschman([]) - 0.0) < 1e-9
    print(f"  [OK] HHI(single_position)=1.0, HHI(empty)=0.0")


def test_hhi_uniform_equals_1_over_n():
    hhi = herfindahl_hirschman([0.1] * 10)
    assert abs(hhi - 0.1) < 1e-9
    print(f"  [OK] HHI(uniform 10 positions)=0.1")


def test_top_k_concentration():
    weights = [0.20, 0.15, 0.10, 0.08, 0.05, 0.02, 0.01]
    total = sum(weights)
    top5 = top_k_concentration_pct(weights, 5)
    assert abs(top5 - (0.20 + 0.15 + 0.10 + 0.08 + 0.05) / total) < 1e-9
    print(f"  [OK] top-5 concentration matches expected ratio")


# ── VaR / CVaR ─────────────────────────────────────────────────
def test_var_cvar_zero_when_no_positions():
    var, cvar, vol = parametric_var_cvar([], [])
    assert var == 0.0 and cvar == 0.0 and vol == 0.0
    print(f"  [OK] VaR/CVaR = 0 on empty portfolio")


def test_var_cvar_positive_and_cvar_ge_var():
    var, cvar, vol = parametric_var_cvar([0.05, 0.03, 0.02], [0.30, 0.25, 0.40])
    assert var > 0 and cvar > 0 and vol > 0
    assert cvar >= var, f"CVaR ({cvar}) must be >= VaR ({var})"
    print(f"  [OK] CVaR ≥ VaR ≥ 0 on non-trivial portfolio (VaR={var:.4f} CVaR={cvar:.4f})")


# ── End-to-end engine ──────────────────────────────────────────
def _sample_recs():
    return [
        {"ticker": "T1", "action": "STRONG_BUY",
         "ensemble_score": 0.7, "regime_adjusted_confidence": 0.85,
         "disagreement_flag": False},
        {"ticker": "T2", "action": "BUY",
         "ensemble_score": 0.4, "regime_adjusted_confidence": 0.65,
         "disagreement_flag": False},
        {"ticker": "T3", "action": "HOLD",
         "ensemble_score": 0.0, "regime_adjusted_confidence": 0.5,
         "disagreement_flag": False},
        {"ticker": "T4", "action": "STRONG_SELL",
         "ensemble_score": -0.6, "regime_adjusted_confidence": 0.75,
         "disagreement_flag": False},
        {"ticker": "T5", "action": "BUY",
         "ensemble_score": 0.5, "regime_adjusted_confidence": 0.10,   # below gate
         "disagreement_flag": False},
    ]


def _sample_features():
    return pd.DataFrame([
        {"ticker": "T1", "market": "usa", "sector": "Tech",     "close": 100, "volatility_20d": 0.020},
        {"ticker": "T2", "market": "usa", "sector": "Tech",     "close": 80,  "volatility_20d": 0.018},
        {"ticker": "T3", "market": "usa", "sector": "Health",   "close": 60,  "volatility_20d": 0.015},
        {"ticker": "T4", "market": "usa", "sector": "Energy",   "close": 40,  "volatility_20d": 0.025},
        {"ticker": "T5", "market": "usa", "sector": "Finance",  "close": 90,  "volatility_20d": 0.020},
    ])


def test_engine_end_to_end():
    engine = RiskEngine(_ROOT, "usa", _budget(shorts=True), regime="neutral", vix_level=18)
    sized, report = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    # HOLD (T3) is skipped entirely; T5 is dropped by confidence gate
    tickers = {p.ticker for p in sized}
    assert "T3" not in tickers, "HOLD should be skipped"
    assert "T1" in tickers and "T2" in tickers
    # Confidence-gated position present but with 0 weight
    t5 = next((p for p in sized if p.ticker == "T5"), None)
    assert t5 is not None and t5.cap_reason == CapReason.CONFIDENCE_GATE
    assert t5.target_weight == 0.0
    # Active positions have non-zero weight
    active = [p for p in sized if abs(p.target_weight) > 1e-9]
    assert len(active) >= 2
    # Every position carries model_stamp fields
    for p in sized:
        assert hasattr(p, "model_stamp")
        assert hasattr(p, "schema_fingerprint")
        assert hasattr(p, "feature_set_version")
    # Report populated
    assert report.n_positions >= 2
    assert report.verdict in {"PASS", "WARNING", "FAIL"}
    print(f"  [OK] engine end-to-end · n_sized={len(sized)} active={len(active)} verdict={report.verdict}")


def test_engine_deterministic():
    """Same inputs → identical output."""
    engine = RiskEngine(_ROOT, "usa", _budget(), regime="neutral", vix_level=18)
    s1, _ = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    s2, _ = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    w1 = [(p.ticker, p.target_weight) for p in s1]
    w2 = [(p.ticker, p.target_weight) for p in s2]
    assert w1 == w2, "engine not deterministic"
    print(f"  [OK] engine deterministic across identical calls")


def test_engine_accepts_cutoff():
    """Walk-forward safety: engine accepts historical cutoff."""
    engine = RiskEngine(_ROOT, "usa", _budget(), regime="bull", vix_level=15)
    past = date(2020, 1, 1)
    _, report = engine.run(_sample_recs(), _sample_features(), asof=past)
    assert report.asof == past
    print(f"  [OK] engine accepts historical cutoff (walk-forward ready)")


def test_shorts_disabled_when_flag_false():
    engine = RiskEngine(_ROOT, "india", _budget("india", shorts=False), regime="neutral")
    sized, _ = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    for p in sized:
        if p.action in ("SELL", "STRONG_SELL"):
            assert p.cap_reason == CapReason.SHORT_DISABLED
            assert p.target_weight == 0.0
    print(f"  [OK] SHORTs disabled → short positions have cap_reason=SHORT_DISABLED, weight=0")


def test_per_ticker_cap_enforced():
    """No sized position weight exceeds per_ticker_cap."""
    budget = _budget()
    engine = RiskEngine(_ROOT, "usa", budget, regime="bull", vix_level=12)
    sized, _ = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    for p in sized:
        assert abs(p.target_weight) <= budget.per_ticker_cap + 1e-9, \
            f"{p.ticker}: |weight|={abs(p.target_weight)} > cap={budget.per_ticker_cap}"
    print(f"  [OK] no sized position exceeds per_ticker_cap")


def test_per_sector_cap_enforced():
    """Total per-sector exposure never exceeds per_sector_cap."""
    budget = _budget()
    engine = RiskEngine(_ROOT, "usa", budget, regime="bull", vix_level=12)
    sized, report = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    for sec, expo in report.per_sector_exposure_pct.items():
        assert abs(expo) <= budget.per_sector_cap + 1e-9, \
            f"sector {sec} exposure {expo} > cap {budget.per_sector_cap}"
    print(f"  [OK] no sector exceeds per_sector_cap")


# ── AI Risk Analyst ────────────────────────────────────────────
def test_ai_risk_analyst_runs():
    engine = RiskEngine(_ROOT, "usa", _budget(), regime="neutral", vix_level=18)
    sized, report = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    out = risk_analyst.run(report, sized, "usa", date(2026, 7, 21))
    assert out.agent == "risk_analyst"
    assert out.headline and out.narrative
    assert len(out.findings) >= 2
    print(f"  [OK] AI Risk Analyst produced narrative: {out.headline[:80]}")


def test_ai_risk_analyst_never_promotes():
    engine = RiskEngine(_ROOT, "usa", _budget(), regime="neutral", vix_level=18)
    sized, report = engine.run(_sample_recs(), _sample_features(), asof=date(2026, 7, 21))
    out = risk_analyst.run(report, sized, "usa", date(2026, 7, 21))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Risk Analyst leaked: {leak}"
    print(f"  [OK] AI Risk Analyst obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_runner():
    r = subprocess.run(
        [sys.executable, "india/risk_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "sized_positions.json").read_text(encoding="utf-8"))
    assert d["market"] == "india"
    assert "positions" in d and "model_stamp" in d and "budget_snapshot" in d
    print(f"  [OK] india runner: n_positions={d['n_positions']}")


def test_usa_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/risk_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "sized_positions.json").read_text(encoding="utf-8"))
    assert d["market"] == "usa"
    assert d["currency"] == "USD"
    print(f"  [OK] usa runner: n_positions={d['n_positions']} currency={d['currency']}")


TESTS = [
    test_kelly_bounded_by_max_fraction, test_kelly_zero_when_vol_is_zero_or_missing,
    test_confidence_tier_signs,
    test_per_ticker_cap_clips_both_sides, test_per_sector_cap_reduces_headroom,
    test_per_sector_cap_full_returns_zero,
    test_vol_adjustment_scales_by_target_vs_ticker, test_vix_dampener_by_regime,
    test_hhi_single_position_equals_1, test_hhi_uniform_equals_1_over_n,
    test_top_k_concentration,
    test_var_cvar_zero_when_no_positions, test_var_cvar_positive_and_cvar_ge_var,
    test_engine_end_to_end, test_engine_deterministic, test_engine_accepts_cutoff,
    test_shorts_disabled_when_flag_false,
    test_per_ticker_cap_enforced, test_per_sector_cap_enforced,
    test_ai_risk_analyst_runs, test_ai_risk_analyst_never_promotes,
    test_india_runner, test_usa_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 4 · Risk Engine · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t(); n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}"); n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}"); n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
