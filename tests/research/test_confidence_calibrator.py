"""Unit tests for confidence_calibrator · V2 §P1 · Phase C."""
from __future__ import annotations
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.calibration.confidence_calibrator import (
    fit_platt, apply_platt, expected_calibration_error, brier_score, _sigmoid,
    build_calibration_dataset,
)


def test_sigmoid_bounds():
    assert 0.0 <= _sigmoid(0.0) <= 1.0
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(500) > 0.99
    assert _sigmoid(-500) < 0.01


def test_platt_identity_fit_on_perfect_signal():
    """Perfectly-separated scores · Platt should assign large positive A."""
    scores = [-2, -1, -0.5, 0.5, 1, 2] * 10
    outcomes = [0, 0, 0, 1, 1, 1] * 10
    a, b = fit_platt(scores, outcomes)
    assert a > 0, f"expected positive slope on positive-signal data, got A={a}"
    # Predictions should be monotonic
    preds = apply_platt(scores, a, b)
    assert preds[0] < preds[-1], "Platt output not monotonic with score"


def test_platt_insufficient_data_returns_identity():
    a, b = fit_platt([0.5, 0.6], [1, 0])
    assert a == 1.0 and b == 0.0


def test_ece_perfect_calibration_is_zero():
    """If predicted prob matches empirical frequency in every bin, ECE=0."""
    probs = [0.1] * 100 + [0.5] * 100 + [0.9] * 100
    # 10% of low-prob succeed, 50% of mid, 90% of high
    outcomes = ([1]*10 + [0]*90) + ([1]*50 + [0]*50) + ([1]*90 + [0]*10)
    ece = expected_calibration_error(probs, outcomes, n_bins=10)
    assert ece < 0.02, f"perfect calibration should have ECE~0, got {ece}"


def test_ece_uncalibrated_is_high():
    """Predictions=0.9 but only 10% actually win → ECE should be ~0.8."""
    probs = [0.9] * 100
    outcomes = [1]*10 + [0]*90
    ece = expected_calibration_error(probs, outcomes, n_bins=10)
    assert ece > 0.5, f"expected high ECE on badly-miscalibrated data, got {ece}"


def test_brier_bounds():
    b = brier_score([0.5, 0.5], [1, 0])
    assert 0.0 <= b <= 1.0
    # Perfect prediction
    assert brier_score([1.0, 0.0], [1, 0]) < 0.001
    # Worst prediction
    assert brier_score([0.0, 1.0], [1, 0]) > 0.99


def test_calibration_dataset_both_markets():
    """Dataset builder must return samples for both markets."""
    for m in ("india", "usa"):
        samples = build_calibration_dataset(Path(__file__).resolve().parents[2], m)
        # Should get non-trivial coverage on both
        assert len(samples) > 100, f"{m}: too few samples ({len(samples)})"
        with_outcome = [s for s in samples if s.win_flag is not None]
        assert len(with_outcome) > 50, f"{m}: too few with outcome"


def test_platt_improves_ece_on_synthetic_miscalibrated():
    """Synthetic 'overconfident' predictions · Platt refit should reduce ECE."""
    import random
    random.seed(42)
    # Ground-truth win probability ≈ 0.3 + 0.5*score (score in [0,1])
    scores = [random.random() for _ in range(500)]
    outcomes = [1 if random.random() < (0.3 + 0.5 * s) else 0 for s in scores]
    # Raw "confidence" = score (miscalibrated · overestimates for high scores)
    ece_raw = expected_calibration_error(scores, outcomes)
    a, b = fit_platt(scores, outcomes)
    calibrated = apply_platt(scores, a, b)
    ece_cal = expected_calibration_error(calibrated, outcomes)
    assert ece_cal < ece_raw, f"Platt should reduce ECE · raw={ece_raw:.3f} cal={ece_cal:.3f}"
