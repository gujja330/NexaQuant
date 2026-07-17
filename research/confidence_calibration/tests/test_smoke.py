"""DEV029 smoke tests. Deterministic synthetic data; no network."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np

from confidence_calibration.lib import methods, metrics                              # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _make_overconfident_data(n=500, seed=42):
    """Predicted 0.9 but only wins 0.5 — extreme overconfidence.
    Truth: p_true = 0.5.  Predicted: p_pred = 0.9.  All outcomes ~ Bernoulli(0.5)."""
    rng = np.random.default_rng(seed)
    conf = rng.uniform(0.75, 0.95, n)
    outcomes = rng.binomial(1, 0.5, n)
    return conf, outcomes


def _make_wellcalibrated_data(n=500, seed=42):
    """Perfect calibration: predicted p exactly matches outcome probability."""
    rng = np.random.default_rng(seed)
    conf = rng.uniform(0.1, 0.9, n)
    outcomes = rng.binomial(1, conf, n)
    return conf, outcomes


def test_methods_registry():
    _check("5 methods registered", len(methods.METHODS) == 5)
    for name in ["platt_scaling", "isotonic_regression", "histogram_binning",
                  "beta_calibration", "temperature_scaling"]:
        _check(f"{name} in registry", name in methods.METHODS)


def test_platt():
    conf, y = _make_overconfident_data()
    cal = methods.platt_scaling(conf, y)
    _check("Platt returns Calibrator with .predict", callable(cal.predict))
    predicted = cal.predict(conf)
    _check("Platt output in [0, 1]", (predicted >= 0).all() and (predicted <= 1).all())
    _check("Platt improves Brier vs raw",
            metrics.brier_score(predicted, y) < metrics.brier_score(conf, y))


def test_isotonic():
    conf, y = _make_overconfident_data()
    cal = methods.isotonic_regression(conf, y)
    predicted = cal.predict(conf)
    _check("Isotonic output in [0, 1]", (predicted >= 0).all() and (predicted <= 1).all())
    _check("Isotonic improves Brier",
            metrics.brier_score(predicted, y) <= metrics.brier_score(conf, y))


def test_histogram():
    conf, y = _make_overconfident_data()
    cal = methods.histogram_binning(conf, y, n_bins=8)
    predicted = cal.predict(conf)
    _check("Histogram output in [0, 1]", (predicted >= 0).all() and (predicted <= 1).all())
    _check("Histogram binning improves Brier",
            metrics.brier_score(predicted, y) < metrics.brier_score(conf, y))


def test_beta():
    conf, y = _make_overconfident_data()
    cal = methods.beta_calibration(conf, y)
    predicted = cal.predict(conf)
    _check("Beta output in [0, 1]", (predicted >= 0).all() and (predicted <= 1).all())
    _check("Beta improves Brier",
            metrics.brier_score(predicted, y) < metrics.brier_score(conf, y))


def test_temperature():
    conf, y = _make_overconfident_data()
    cal = methods.temperature_scaling(conf, y)
    predicted = cal.predict(conf)
    _check("Temperature output in [0, 1]", (predicted >= 0).all() and (predicted <= 1).all())
    _check("Temperature learned T > 0", cal.params["T"] > 0)


def test_metrics_brier():
    y = np.array([1, 0, 1, 1, 0])
    p_perfect = y.astype(float)
    p_worst = 1 - y.astype(float)
    _check("Brier = 0 for perfect predictions",
            metrics.brier_score(p_perfect, y) < 1e-9)
    _check("Brier = 1 for worst predictions",
            abs(metrics.brier_score(p_worst, y) - 1.0) < 1e-9)


def test_metrics_ece():
    y = np.array([1] * 100 + [0] * 100)
    # Perfectly calibrated 0.5 predictions
    p_perfect = np.full(200, 0.5)
    ece = metrics.expected_calibration_error(p_perfect, y)
    _check("ECE ~= 0 for perfectly-calibrated 0.5 predictions",
            ece < 0.01, detail=f"got {ece}")


def test_metrics_bias():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.9, 0.9, 0.9, 0.9])
    _check("bias = predicted - actual",
            abs(metrics.confidence_bias(p, y) - 0.4) < 1e-6)


def test_reliability_curve():
    conf, y = _make_overconfident_data()
    curve = metrics.reliability_curve(conf, y, n_bins=5)
    _check("reliability curve has 5 bins", len(curve) == 5)
    total_n = sum(r["n"] for r in curve)
    _check("bin ns sum to total", total_n == len(conf))


def test_calibration_end_to_end():
    """On overconfident data, best method should reduce ECE by >50%."""
    conf, y = _make_overconfident_data(1000)
    raw_ece = metrics.expected_calibration_error(conf, y)

    best_ece = 1.0
    best_name = None
    for name, fn in methods.METHODS.items():
        cal = fn(conf, y)
        pred = cal.predict(conf)
        ece = metrics.expected_calibration_error(pred, y)
        if ece < best_ece:
            best_ece = ece
            best_name = name

    _check("best calibration reduces ECE by >50%",
            best_ece < 0.5 * raw_ece,
            detail=f"raw={raw_ece:.4f} -> {best_name} {best_ece:.4f}")


def test_wellcalibrated_stays_wellcalibrated():
    """Well-calibrated data should not be broken by calibration."""
    conf, y = _make_wellcalibrated_data(1000)
    raw_ece = metrics.expected_calibration_error(conf, y)

    # Isotonic should preserve well-calibrated data (within noise)
    cal = methods.isotonic_regression(conf, y)
    predicted = cal.predict(conf)
    cal_ece = metrics.expected_calibration_error(predicted, y)

    _check("well-calibrated data stays well-calibrated (ECE change < 0.05)",
            abs(cal_ece - raw_ece) < 0.05,
            detail=f"raw={raw_ece:.4f} calibrated={cal_ece:.4f}")


def test_determinism():
    conf, y = _make_overconfident_data(500, seed=123)
    cal1 = methods.platt_scaling(conf, y)
    cal2 = methods.platt_scaling(conf, y)
    p1 = cal1.predict(conf)
    p2 = cal2.predict(conf)
    _check("Platt is deterministic",
            np.allclose(p1, p2), detail="same inputs must give same output")


def main() -> int:
    print("=" * 70)
    print("  DEV029 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_methods_registry(); print()
    test_platt(); print()
    test_isotonic(); print()
    test_histogram(); print()
    test_beta(); print()
    test_temperature(); print()
    test_metrics_brier(); print()
    test_metrics_ece(); print()
    test_metrics_bias(); print()
    test_reliability_curve(); print()
    test_calibration_end_to_end(); print()
    test_wellcalibrated_stays_wellcalibrated(); print()
    test_determinism(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
