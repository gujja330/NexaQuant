"""DEV025 smoke tests. Fast; synthetic data; no network."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from adaptive_learning.lib import calibration, patterns                             # noqa: E402
from adaptive_learning.compute import suggestions                                     # noqa: E402


PASS, FAIL = 0, 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _synth_trades(n=200, seed=42):
    rng = np.random.default_rng(seed)
    scores = rng.uniform(40, 90, n)
    confs = np.clip(scores / 100 + rng.normal(0, 0.05, n), 0.5, 1.0)
    returns = rng.normal(scores.mean() / 20 - 3, 5, n)  # higher-score-adjacent
    return pd.DataFrame({
        "entry_date":     ["2024-01-31"] * n,
        "exit_date":      ["2024-02-29"] * n,
        "ticker":         [f"T{i}" for i in range(n)],
        "sector":         rng.choice(["Pharma", "IT", "Banking", "Auto"], n),
        "industry":       rng.choice(["Pharma_LC", "IT_Services", "Private_Banks"], n),
        "score_at_entry": scores,
        "confidence":     confs,
        "entry_px":       [100.0] * n,
        "exit_px":        [100.0 + r for r in returns],
        "return_pct":     returns,
        "mfe_pct":        returns + np.abs(rng.normal(2, 2, n)),
        "mae_pct":        returns - np.abs(rng.normal(2, 2, n)),
        "hit_5pct_target": returns > 0,     # rough
        "hit_10pct_target": returns > 5,
        "hit_5pct_stop":   returns < -5,
        "hit_10pct_stop":  returns < -10,
        "is_winner":      returns > 0,
        "n_bars_held":    [21] * n,
        "dim_momentum":   rng.uniform(20, 90, n),
        "dim_trend":      rng.uniform(20, 90, n),
        "dim_rs_nifty":   rng.uniform(20, 90, n),
        "dim_volatility": rng.uniform(20, 90, n),
        "dim_drawdown":   rng.uniform(20, 90, n),
        "dim_position_52w": rng.uniform(20, 90, n),
    })


def test_calibration_curve():
    trades = _synth_trades(300)
    curve = calibration.calibration_curve(trades, n_bins=8)
    _check("calibration_curve has rows", not curve.empty)
    _check("bin midpoints ordered",
            list(curve["bin_midpoint"]) == sorted(curve["bin_midpoint"]))
    _check("n_trades sums to trade count",
            curve["n_trades"].sum() == len(trades))


def test_brier_score():
    trades = _synth_trades(200)
    b = calibration.brier_score(trades)
    _check("brier finite", np.isfinite(b))
    _check("brier in [0, 1]", 0 <= b <= 1, detail=f"{b:.4f}")


def test_ece():
    trades = _synth_trades(300)
    curve = calibration.calibration_curve(trades, n_bins=10)
    ece = calibration.expected_calibration_error(curve)
    _check("ECE finite", np.isfinite(ece))
    _check("ECE non-negative", ece >= 0)


def test_score_bucket_accuracy():
    trades = _synth_trades(400)
    buckets = patterns.score_bucket_accuracy(trades)
    _check("score_buckets produce rows", not buckets.empty)
    _check("win_rate in [0, 100]",
            all(0 <= x <= 100 for x in buckets["win_rate_pct"]))


def test_sector_performance():
    trades = _synth_trades(400)
    perf = patterns.per_sector_performance(trades, min_n=20)
    _check("sector_performance produces rows", not perf.empty)


def test_dimension_correlations():
    trades = _synth_trades(400)
    dc = patterns.dimension_correlations(trades)
    _check("dimension_correlations non-empty", not dc.empty)
    _check("spearman in [-1, 1]",
            all(-1 <= x <= 1 for x in dc["spearman_correlation"]))


def test_stop_loss_stats():
    trades = _synth_trades(400)
    stats = patterns.stop_loss_effectiveness(trades)
    _check("stop_loss_stats has n_trades", "n_trades" in stats)
    _check("stop_loss_stats has hit_5pct_stop_rate",
            "hit_5pct_stop_rate" in stats)


def test_target_stats():
    trades = _synth_trades(400)
    stats = patterns.target_effectiveness(trades)
    _check("target_stats has hit_5pct_target_rate",
            "hit_5pct_target_rate" in stats)


def test_suggestions_generation():
    trades = _synth_trades(400)
    curve = calibration.calibration_curve(trades)
    sector_calib = calibration.per_sector_calibration(trades)
    result = {
        "aggregate": {
            "n_trades": len(trades),
            "brier_score": calibration.brier_score(trades),
            "expected_calibration_err": calibration.expected_calibration_error(curve),
        },
        "trades":                trades,
        "score_buckets":         patterns.score_bucket_accuracy(trades),
        "sector_performance":    patterns.per_sector_performance(trades),
        "industry_performance":  patterns.per_industry_performance(trades),
        "dimension_correlations": patterns.dimension_correlations(trades),
        "stop_loss_stats":       patterns.stop_loss_effectiveness(trades),
        "target_stats":          patterns.target_effectiveness(trades),
        "calibration_curve":     curve,
        "sector_calibration":    sector_calib,
    }
    sugg = suggestions.generate(result)
    _check("suggestions is a list", isinstance(sugg, list))
    _check("suggestions non-empty on synthetic data", len(sugg) > 0)
    for s in sugg:
        _check(f"suggestion {s['id']} has all fields",
                all(k in s for k in ["id", "category", "severity", "action",
                                        "evidence", "target_module"]))


def test_no_auto_learning():
    """Suggestions must never claim to auto-apply."""
    trades = _synth_trades(200)
    curve = calibration.calibration_curve(trades)
    result = {
        "aggregate": {"n_trades": len(trades),
                        "brier_score": 0.3,
                        "expected_calibration_err": 0.15},
        "trades": trades, "score_buckets": patterns.score_bucket_accuracy(trades),
        "sector_performance": pd.DataFrame(), "industry_performance": pd.DataFrame(),
        "dimension_correlations": pd.DataFrame(),
        "stop_loss_stats": {}, "target_stats": {},
        "calibration_curve": curve,
        "sector_calibration": pd.DataFrame(),
    }
    sugg = suggestions.generate(result)
    for s in sugg:
        # No suggestion should include the word "auto-apply" or similar
        combined = str(s).lower()
        _check(f"suggestion {s['id']} does not claim auto-apply",
                "auto-apply" not in combined and "automatically applied" not in combined)


def main() -> int:
    print("=" * 70)
    print("  DEV025 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_calibration_curve(); print()
    test_brier_score(); print()
    test_ece(); print()
    test_score_bucket_accuracy(); print()
    test_sector_performance(); print()
    test_dimension_correlations(); print()
    test_stop_loss_stats(); print()
    test_target_stats(); print()
    test_suggestions_generation(); print()
    test_no_auto_learning(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
