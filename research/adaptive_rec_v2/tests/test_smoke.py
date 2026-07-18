"""Adaptive Rec v2.0 smoke tests. Deterministic synthetic data."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from adaptive_rec_v2.lib import features, model, metrics, reliability                  # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _make_synthetic(n=500, seed=42):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "entry_date":       pd.date_range("2022-01-01", periods=n, freq="B"),
        "exit_date":        pd.date_range("2022-01-10", periods=n, freq="B"),
        "ticker":           [f"T{i:03d}" for i in range(n)],
        "sector":           rng.choice(["Pharma", "Banks", "IT"], n),
        "industry":         rng.choice(["Pharma-Large", "Pharma-Mid", "PSU-Bank",
                                             "Priv-Bank", "IT-Services"], n),
        "dim_momentum":     rng.uniform(0, 100, n),
        "dim_trend":        rng.uniform(0, 100, n),
        "dim_rs_nifty":     rng.uniform(0, 100, n),
        "dim_volatility":   rng.uniform(0, 100, n),
        "dim_drawdown":     rng.uniform(0, 100, n),
        "dim_position_52w": rng.uniform(0, 100, n),
        "score_at_entry":   rng.uniform(50, 100, n),
        "confidence":       rng.uniform(0.7, 0.95, n),
        "return_pct":       rng.normal(0.05, 0.15, n),
    })
    # Inject signal: high-momentum + Pharma-Large wins more often
    df["is_winner"] = ((df["dim_momentum"] > 60) & (df["industry"] == "Pharma-Large")).astype(int)
    # Add noise so the model isn't perfect
    flip = rng.random(n) < 0.2
    df.loc[flip, "is_winner"] = 1 - df.loc[flip, "is_winner"]
    return df


def test_load_and_split():
    df = _make_synthetic(500)
    train, test = features.time_train_test_split(df, 0.7)
    _check("split preserves order", train.sum() == 350 and test.sum() == 150)


def test_feature_matrix_shape():
    df = _make_synthetic(500)
    X, y, names = features.build_feature_matrix(df)
    _check("y matches n rows", len(y) == 500)
    _check("X has numeric + categorical columns",
            X.shape[1] >= len(features.NUMERIC_FEATURES) + 2,
            detail=f"{X.shape[1]} columns")
    _check("feature_names has 'confidence'", "confidence" in names)


def test_impute_deterministic():
    df = _make_synthetic(200)
    X, _, names = features.build_feature_matrix(df)
    # inject NaN
    X[0, 0] = np.nan
    X1, meds1 = features.impute(X.copy(), names)
    X2, meds2 = features.impute(X.copy(), names)
    _check("impute deterministic", np.allclose(X1, X2))
    _check("no NaN after impute", not np.any(np.isnan(X1)))


def test_baseline_model():
    df = _make_synthetic(400)
    X, y, names = features.build_feature_matrix(df)
    X, _ = features.impute(X, names)
    conf_idx = names.index("confidence")
    m = model.fit_baseline(X, y, names, conf_idx)
    p = m.predict(X)
    _check("baseline pred equals confidence column", np.allclose(p, X[:, conf_idx]))


def test_hgb_finds_injected_signal():
    df = _make_synthetic(600)
    X, y, names = features.build_feature_matrix(df)
    X, _ = features.impute(X, names)
    tr, te = features.time_train_test_split(df, 0.7)
    conf_idx = names.index("confidence")

    m = model.fit_hgb(X[tr], y[tr], names)
    p = m.predict(X[te])
    p10 = metrics.precision_at_k(p, y[te], 10)
    base_wr = float(y[te].mean())
    _check("HGB Precision@10 beats base rate on synthetic signal",
            p10 > base_wr + 0.10,
            detail=f"P@10 {p10:.3f} vs base {base_wr:.3f}")


def test_hgb_deterministic():
    df = _make_synthetic(400)
    X, y, names = features.build_feature_matrix(df)
    X, _ = features.impute(X, names)
    m1 = model.fit_hgb(X, y, names)
    m2 = model.fit_hgb(X, y, names)
    _check("HGB fits deterministically",
            np.allclose(m1.predict(X), m2.predict(X)))


def test_metrics_full_panel():
    p = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05])
    y = np.array([1,   1,   0,   1,   0,   0,   1,   0,   0,   0])
    panel = metrics.full_panel(p, y, returns=None)
    _check("brier is a number", isinstance(panel["brier"], float))
    _check("precision_at_5 exists", "precision_at_5" in panel)
    _check("precision_at_1 = 1", panel["precision_at_1"] == 1.0)


def test_reliability_curve():
    p = np.linspace(0, 1, 200)
    y = (p > 0.5).astype(int)
    curve = reliability.reliability_curve(p, y, n_bins=10)
    _check("reliability curve has 10 bins", len(curve) == 10)


def test_tier_discrimination():
    p = np.linspace(0, 1, 500)[::-1]  # highest first not needed; tier code sorts
    y = np.concatenate([np.ones(250), np.zeros(250)]).astype(int)
    tiers = reliability.tier_discrimination(p, y)
    _check("Strong-Buy tier exists", "Strong-Buy" in tiers)
    check = reliability.discrimination_summary(tiers)
    _check("perfectly-ordered p produces monotone discrimination",
            check["monotone_decreasing"] is True)


def main() -> int:
    print("=" * 72); print("  ADAPTIVE REC v2.0 · SMOKE TESTS"); print("=" * 72)
    test_load_and_split(); print()
    test_feature_matrix_shape(); print()
    test_impute_deterministic(); print()
    test_baseline_model(); print()
    test_hgb_finds_injected_signal(); print()
    test_hgb_deterministic(); print()
    test_metrics_full_panel(); print()
    test_reliability_curve(); print()
    test_tier_discrimination(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
