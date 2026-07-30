"""Evidence Cycle 1 tests · Calibration + Alpha Validation + YoY + Rolling IC.

Locks the invariants that these measurement engines rely on. Uses tiny
synthetic frames · not the real learning.parquet · so tests stay fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.analytics.evidence.calibration import (  # noqa: E402
    compute_calibration, _wilson_ci,
)
from backend.analytics.evidence.alpha_validation import (  # noqa: E402
    compute_alpha_validation,
)
from backend.analytics.evidence.yoy_improvement import compute_yoy_report  # noqa: E402
from backend.analytics.evidence.model_attribution_longitudinal import (  # noqa: E402
    compute_rolling_ic,
)


# ── Calibration ─────────────────────────────────────────────
def test_calibration_well_calibrated_dataset_verdicts_correctly():
    # Perfectly calibrated data · higher confidence → higher observed win rate
    rng = np.random.default_rng(42)
    rows = []
    for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
        for _ in range(100):
            rows.append({"confidence": conf,
                          "is_winner": bool(rng.uniform() < conf)})
    df = pd.DataFrame(rows)
    rep = compute_calibration(df)
    assert rep.verdict == "well_calibrated", (
        f"expected well_calibrated · got {rep.verdict} · slope={rep.calibration_slope}"
    )
    assert 0.85 <= rep.calibration_slope <= 1.15


def test_calibration_flat_confidence_detected():
    # Confidence has no relation to outcome (all conf = 0.8 but wins 50%)
    df = pd.DataFrame({
        "confidence": [0.8] * 200,
        "is_winner": [True] * 100 + [False] * 100,
    })
    rep = compute_calibration(df)
    # Only one bucket · slope undefined · verdict falls through to "insufficient_buckets"
    # OR "over_confident" if slope computable. Either way, NOT "well_calibrated".
    assert rep.verdict != "well_calibrated"


def test_calibration_over_confidence_detected():
    # 100% confidence but only 50% win rate · classic over-confidence
    rng = np.random.default_rng(7)
    rows = []
    for conf in [0.7, 0.8, 0.9]:
        for _ in range(200):
            rows.append({"confidence": conf, "is_winner": bool(rng.uniform() < 0.5)})
    df = pd.DataFrame(rows)
    rep = compute_calibration(df)
    assert rep.verdict in ("over_confident", "poorly_calibrated_flat", "approximately_calibrated"), (
        f"got unexpected verdict {rep.verdict}"
    )
    # Overall observed should be significantly below expected
    assert rep.overall_observed_win_rate < rep.overall_expected_win_rate - 0.10


def test_calibration_wilson_ci_bounds():
    lo, hi = _wilson_ci(50, 100)
    assert 0 <= lo < 0.5 < hi <= 1.0
    # Edge cases
    assert _wilson_ci(0, 0) == (0.0, 0.0)
    assert abs(_wilson_ci(100, 100)[1] - 1.0) < 1e-6


def test_calibration_insufficient_data():
    rep = compute_calibration(pd.DataFrame())
    assert rep.verdict == "insufficient_data"
    assert rep.n_trades == 0


def test_calibration_real_learning_parquet_gives_verdict():
    """Sanity: the real 1060-trade corpus produces SOME verdict · not crash."""
    lp = _ROOT / "reports" / "learning.parquet"
    if not lp.exists():
        return
    df = pd.read_parquet(lp)
    rep = compute_calibration(df)
    assert rep.n_trades == 1060
    assert rep.verdict != "insufficient_data"


# ── Alpha Validation ────────────────────────────────────────
def test_alpha_validation_perfect_predictor():
    # score EQUALS the return · perfect correlation
    rng = np.random.default_rng(11)
    scores = rng.normal(50, 20, 200)
    df = pd.DataFrame({
        "score_at_entry": scores,
        "return_pct": (scores - 50) * 0.5,   # linear function of score
        "exit_date": ["2024-01-01"] * 200,
    })
    rep = compute_alpha_validation(df)
    assert rep.pearson_r > 0.9
    assert rep.verdict == "strong_predictive_relationship"


def test_alpha_validation_no_predictor_detected():
    rng = np.random.default_rng(13)
    df = pd.DataFrame({
        "score_at_entry": rng.uniform(0, 100, 200),
        "return_pct":     rng.normal(0, 5, 200),   # noise
    })
    rep = compute_alpha_validation(df)
    assert abs(rep.pearson_r) < 0.2
    assert rep.verdict in ("no_predictive_relationship", "weak_predictive_relationship")


def test_alpha_validation_bucket_distribution_computed():
    rng = np.random.default_rng(17)
    df = pd.DataFrame({
        "score_at_entry": rng.uniform(0, 100, 500),
        "return_pct":     rng.normal(2, 8, 500),
    })
    rep = compute_alpha_validation(df)
    assert len(rep.buckets) > 0
    for b in rep.buckets:
        assert b["p10_return_pct"] <= b["median_return_pct"] <= b["p90_return_pct"]


def test_alpha_validation_sample_too_small():
    df = pd.DataFrame({
        "score_at_entry": [50, 60],
        "return_pct":     [1, 2],
    })
    rep = compute_alpha_validation(df)
    assert rep.verdict == "sample_too_small"


# ── YoY ────────────────────────────────────────────────────
def test_yoy_improving_detected():
    rows = []
    # 2022: low performance
    for i in range(50):
        rows.append({"exit_date": "2022-06-01", "is_winner": i < 25,
                       "return_pct": 0.5, "hit_5pct_target": False,
                       "hit_5pct_stop": True, "n_bars_held": 20})
    # 2024: high performance
    for i in range(50):
        rows.append({"exit_date": "2024-06-01", "is_winner": i < 40,
                       "return_pct": 5.0, "hit_5pct_target": True,
                       "hit_5pct_stop": False, "n_bars_held": 20})
    df = pd.DataFrame(rows)
    rep = compute_yoy_report(df)
    assert rep.win_rate_trend == "improving"
    assert rep.median_return_trend == "improving"
    assert rep.verdict == "learning_engine_effective"


def test_yoy_declining_detected():
    rows = []
    for i in range(50):
        rows.append({"exit_date": "2022-06-01", "is_winner": i < 40,
                       "return_pct": 5.0, "hit_5pct_target": True,
                       "hit_5pct_stop": False, "n_bars_held": 20})
    for i in range(50):
        rows.append({"exit_date": "2024-06-01", "is_winner": i < 20,
                       "return_pct": -1.0, "hit_5pct_target": False,
                       "hit_5pct_stop": True, "n_bars_held": 20})
    df = pd.DataFrame(rows)
    rep = compute_yoy_report(df)
    assert rep.win_rate_trend == "declining"
    assert rep.verdict == "learning_engine_regressing"


def test_yoy_ignores_years_below_threshold():
    rows = [{"exit_date": f"{y}-06-01", "is_winner": True,
              "return_pct": 5.0, "hit_5pct_target": True,
              "hit_5pct_stop": False, "n_bars_held": 20}
             for y in (2020, 2021, 2022, 2023, 2024) for _ in range(5)]
    df = pd.DataFrame(rows)
    rep = compute_yoy_report(df)
    assert rep.per_year == []   # each year has only 5 rows < 10-row threshold


# ── Rolling IC ─────────────────────────────────────────────
def test_rolling_ic_strong_dim_detected():
    rng = np.random.default_rng(23)
    rows = []
    for yr in (2022, 2023, 2024):
        for _ in range(50):
            d = rng.normal(0, 1)
            r = d * 2 + rng.normal(0, 0.5)   # dim strongly predicts return
            rows.append({"exit_date": f"{yr}-06-01",
                          "dim_strong": d, "return_pct": r})
    df = pd.DataFrame(rows)
    rep = compute_rolling_ic(df)
    strong = next((d for d in rep.per_dim_summary if d["dim"] == "dim_strong"), None)
    assert strong is not None
    assert strong["verdict"] in ("strong_and_consistent", "modest_and_consistent")
    assert strong["avg_ic"] > 0.5


def test_rolling_ic_quiet_dim_detected():
    rng = np.random.default_rng(29)
    rows = []
    for yr in (2022, 2023, 2024):
        for _ in range(100):
            rows.append({"exit_date": f"{yr}-06-01",
                          "dim_quiet": rng.normal(0, 1),
                          "return_pct": rng.normal(0, 5)})
    df = pd.DataFrame(rows)
    rep = compute_rolling_ic(df)
    quiet = next((d for d in rep.per_dim_summary if d["dim"] == "dim_quiet"), None)
    assert quiet is not None
    # Random signal → avg IC near zero
    assert abs(quiet["avg_ic"]) < 0.15


def test_rolling_ic_no_dim_columns():
    df = pd.DataFrame({"exit_date": ["2024-01-01"] * 20,
                          "return_pct": [1.0] * 20})
    rep = compute_rolling_ic(df)
    assert rep.verdict == "no_dim_columns"
