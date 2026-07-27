"""Institutional Proof · Intelligence Enhancement tests (Article 101.2)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.quality.calibration import (  # noqa: E402
    fit_calibration_curve, apply_calibration_to_recs,
    SCHEMA_FINGERPRINT as CAL_FP, KELLY_CAP, _kelly_fraction, _wilson,
)
from backend.certification.learning_effectiveness import (  # noqa: E402
    compute_learning_effectiveness, SCHEMA_FINGERPRINT as LE_FP,
)
from backend.macro_intel.regime_strategy_router import (  # noqa: E402
    route_regime_to_strategies, REGIME_STRATEGY_WEIGHTS,
    SCHEMA_FINGERPRINT as RSR_FP,
)


# ── Calibration ──────────────────────────────────────────────
def test_wilson_ci_bounds():
    lo, hi = _wilson(50, 100)
    assert 0.0 <= lo <= hi <= 1.0


def test_kelly_bounded_and_nonneg():
    k = _kelly_fraction(0.6, 8.0, -6.0)
    assert 0.0 <= k <= KELLY_CAP


def test_kelly_none_on_invalid():
    assert _kelly_fraction(None, 8.0, -6.0) is None
    assert _kelly_fraction(0.5, -1.0, -1.0) is None


def test_calibration_curve_from_synthetic_data():
    import pandas as pd
    df = pd.DataFrame({
        "confidence": [0.1]*20 + [0.5]*20 + [0.9]*20,
        "return_pct": [-1.0]*15 + [2.0]*5 + [-1.0]*10 + [2.0]*10 + [-1.0]*4 + [3.0]*16,
    })
    curve = fit_calibration_curve(df)
    from dataclasses import asdict
    d = asdict(curve)
    assert d["n_total_trades"] == 60
    assert d["overall_win_rate"] == round(31/60, 4)
    # High-confidence bucket must have higher win rate than low
    high = next(b for b in d["buckets"] if b["label"] == "very_high(0.80-1.0)")
    low = next(b for b in d["buckets"] if b["label"] == "very_low(0-0.20)")
    assert high["win_rate"] > low["win_rate"]


def test_calibration_enrich_adds_fields():
    curve = {"buckets": [{"label": "high", "lo": 0.5, "hi": 1.0, "n": 100,
                            "win_rate": 0.62, "mean_return_pct": 2.5,
                            "kelly_fraction": 0.15, "suggested_allocation_pct": 0.15}]}
    recs = [{"ticker": "T", "confidence": 0.7}]
    enriched = apply_calibration_to_recs(recs, curve)
    assert enriched[0]["calibrated_kelly_fraction"] == 0.15
    assert enriched[0]["calibrated_win_probability"] == 0.62
    assert enriched[0]["calibration_bucket"] == "high"


def test_calibration_schema_fingerprint():
    from backend.recommendation.quality.calibration import CalibrationCurve
    c = CalibrationCurve()
    assert c.schema_fingerprint == CAL_FP


# ── Learning Effectiveness ──────────────────────────────────
def test_learning_effectiveness_computes_ic():
    import pandas as pd
    df = pd.DataFrame({
        "dim_momentum": [1.0, 2.0, 3.0, 4.0, 5.0]*10,
        "return_pct":   [1.0, 2.0, 3.0, 4.0, 5.0]*10,
        "sector":       ["A"]*25 + ["B"]*25,
        "n_bars_held":  [10]*50,
    })
    rep = compute_learning_effectiveness(df)
    # Perfect correlation
    assert rep.per_dimension_ic["dim_momentum"] > 0.99
    assert rep.n_trades == 50


def test_learning_effectiveness_recommends_sectors():
    import pandas as pd
    df = pd.DataFrame({
        "sector":     ["Boost"]*40 + ["Reduce"]*40 + ["Underweight"]*40,
        "return_pct": [1.0]*30 + [-1.0]*10 + [1.0]*20 + [-1.0]*20 + [1.0]*10 + [-1.0]*30,
        "dim_x":      [0.5]*120,
    })
    rep = compute_learning_effectiveness(df)
    assert rep.per_sector_recommendation.get("Boost") in ("BOOST", "HOLD")
    assert rep.per_sector_recommendation.get("Underweight") in ("REDUCE", "UNDERWEIGHT")


def test_learning_effectiveness_schema():
    import pandas as pd
    rep = compute_learning_effectiveness(pd.DataFrame({
        "return_pct": [1.0, -1.0, 1.0, -1.0], "dim_x": [1, 2, 3, 4],
    }))
    assert rep.schema_fingerprint == LE_FP


# ── Regime → Strategy Router ────────────────────────────────
def test_regime_router_all_regimes_present():
    for regime in ("risk_on", "neutral", "risk_off", "stress",
                    "recession_warning", "unknown"):
        assert regime in REGIME_STRATEGY_WEIGHTS


def test_regime_router_weights_sum_to_one():
    for regime, weights in REGIME_STRATEGY_WEIGHTS.items():
        s = sum(weights.values())
        assert abs(s - 1.0) < 0.05, f"regime {regime} weights sum {s} not ~1.0"


def test_regime_router_risk_on_favors_momentum_over_stress():
    r_on = route_regime_to_strategies("risk_on")
    r_st = route_regime_to_strategies("stress")
    assert r_on.active_strategy_weights["momentum"] > r_st.active_strategy_weights["momentum"]
    assert r_st.active_strategy_weights["quality"] > r_on.active_strategy_weights["quality"]


def test_regime_router_vol_overlay_boosts_quality():
    normal = route_regime_to_strategies("neutral", vol_regime="normal")
    panic  = route_regime_to_strategies("neutral", vol_regime="panic")
    assert panic.active_strategy_weights["quality"] > normal.active_strategy_weights["quality"]


def test_regime_router_produces_top4_and_reduced3():
    d = route_regime_to_strategies("neutral")
    assert len(d.top_active_strategies) == 4
    assert len(d.reduced_strategies) == 3


def test_regime_router_schema_fingerprint():
    d = route_regime_to_strategies("neutral")
    assert d.schema_fingerprint == RSR_FP


def test_regime_router_unknown_defaults_to_equal_weight_ish():
    d = route_regime_to_strategies("some_garbage_regime")
    # Falls through to "unknown" prior
    assert d.regime == "some_garbage_regime"
    total = sum(d.active_strategy_weights.values())
    assert 0.9 < total < 1.1
