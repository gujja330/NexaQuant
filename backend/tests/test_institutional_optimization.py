"""Institutional Optimization tests · percentile classifier + permutation
importance + adaptive weights."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.percentile_classifier import (  # noqa: E402
    classify_by_percentile, SCHEMA_FINGERPRINT as PC_FP,
)
from backend.certification.permutation_importance import (  # noqa: E402
    compute_permutation_importance, SCHEMA_FINGERPRINT as PI_FP,
)
from backend.certification.adaptive_weights import (  # noqa: E402
    compute_adaptive_weights, SCHEMA_FINGERPRINT as AW_FP,
    MIN_MODEL_WEIGHT, MAX_MODEL_WEIGHT,
    load_ensemble_weights_config, write_ensemble_weights_config,
)


# ── Percentile Classifier ────────────────────────────────────
def test_percentile_produces_action_distribution():
    # 20 recs uniform score · expect 2-4 STRONG_BUY + few BUY + majority HOLD + few SELL/STRONG_SELL
    recs = [{"ticker": f"T{i:02d}", "ensemble_score": i * 0.01, "calibrated_confidence": 0.5}
             for i in range(20)]
    rep = classify_by_percentile(recs)
    assert rep.n_recs == 20
    dist = rep.action_distribution
    # Top 10% = 2 recs → STRONG_BUY
    assert dist["STRONG_BUY"] >= 1
    # Bottom 10% → STRONG_SELL
    assert dist["STRONG_SELL"] >= 1
    # Middle 60% → HOLD
    assert dist["HOLD"] >= 8


def test_percentile_never_forces_action_below_confidence():
    recs = [{"ticker": f"T{i:02d}", "ensemble_score": i * 0.01,
              "calibrated_confidence": 0.0}   # confidence below min gate
             for i in range(20)]
    rep = classify_by_percentile(recs, min_conf=0.5)
    assert rep.action_distribution["STRONG_BUY"] == 0
    assert rep.action_distribution["STRONG_SELL"] == 0
    assert rep.action_distribution["HOLD"] == 20


def test_percentile_top_gets_best_action():
    recs = [{"ticker": "BEST", "ensemble_score": +0.9, "calibrated_confidence": 0.5},
            {"ticker": "MID",  "ensemble_score":  0.0, "calibrated_confidence": 0.5},
            {"ticker": "WORST","ensemble_score": -0.9, "calibrated_confidence": 0.5}]
    rep = classify_by_percentile(recs, strong_buy_pct=0.5, strong_sell_pct=0.5)
    ba = next(d for d in rep.decisions if d["ticker"] == "BEST")["action"]
    wa = next(d for d in rep.decisions if d["ticker"] == "WORST")["action"]
    assert ba in ("STRONG_BUY", "BUY")
    assert wa in ("STRONG_SELL", "SELL")


def test_percentile_handles_none_ensemble_score_uses_score_fallback():
    """2026-08-11 regression · USA legacy recommendations.json shape:
    every rec has ensemble_score=None but `score` populated 0..100.
    Pre-fix: crashed with TypeError('float() argument ... NoneType').
    Post-fix: `_num_or` treats None as missing and walks to `score`."""
    # 3 recs, legacy shape · ensemble_score=None, score set
    recs = [
        {"ticker": "HIGH", "ensemble_score": None, "score": 95.0, "confidence": 0.5},
        {"ticker": "MID",  "ensemble_score": None, "score": 50.0, "confidence": 0.5},
        {"ticker": "LOW",  "ensemble_score": None, "score":  5.0, "confidence": 0.5},
    ]
    rep = classify_by_percentile(recs, strong_buy_pct=0.5, strong_sell_pct=0.5)
    assert rep.n_recs == 3
    high = next(d for d in rep.decisions if d["ticker"] == "HIGH")
    low  = next(d for d in rep.decisions if d["ticker"] == "LOW")
    # HIGH must rank above LOW · confirms `score` was actually consumed
    assert high["ensemble_score"] == 95.0
    assert low["ensemble_score"]  == 5.0
    assert high["action"] in ("STRONG_BUY", "BUY")
    assert low["action"]  in ("STRONG_SELL", "SELL")


def test_percentile_handles_both_keys_missing_defaults_to_zero():
    """Both ensemble_score AND score absent → default 0.0, no crash, all HOLD-ish."""
    recs = [{"ticker": f"T{i}", "confidence": 0.5} for i in range(5)]
    rep = classify_by_percentile(recs)
    assert rep.n_recs == 5
    # All identical scores → ranking is ambiguous but no exception
    assert sum(rep.action_distribution.values()) == 5


def test_percentile_handles_nan_score_treats_as_missing():
    """NaN score → falls through to fallback key."""
    recs = [
        {"ticker": "A", "ensemble_score": float("nan"), "score": 80.0, "confidence": 0.5},
        {"ticker": "B", "ensemble_score": float("nan"), "score": 20.0, "confidence": 0.5},
    ]
    rep = classify_by_percentile(recs, strong_buy_pct=0.5, strong_sell_pct=0.5)
    a = next(d for d in rep.decisions if d["ticker"] == "A")
    b = next(d for d in rep.decisions if d["ticker"] == "B")
    assert a["ensemble_score"] == 80.0
    assert b["ensemble_score"] == 20.0


def test_percentile_fingerprint():
    rep = classify_by_percentile([{"ticker":"X","ensemble_score":0.0,"calibrated_confidence":0.5}])
    assert rep.schema_fingerprint == PC_FP


def test_percentile_deterministic():
    recs = [{"ticker": f"T{i}", "ensemble_score": (i-5)*0.02, "calibrated_confidence": 0.5}
             for i in range(10)]
    r1 = classify_by_percentile(recs)
    r2 = classify_by_percentile(recs)
    r1.run_utc = "F"; r2.run_utc = "F"
    assert r1 == r2


# ── Permutation Importance ──────────────────────────────────
def test_permutation_importance_identifies_predictive_feature():
    import pandas as pd
    import numpy as np
    n = 500
    rng = np.random.default_rng(42)
    strong = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "dim_strong": strong,
        "dim_noise":  rng.normal(0, 1, n),
        "return_pct": strong + rng.normal(0, 0.5, n),   # strong is highly predictive
    })
    rep = compute_permutation_importance(df, n_permutations=20)
    strong_imp = rep.per_feature_importance["dim_strong"]["importance"]
    noise_imp = rep.per_feature_importance["dim_noise"]["importance"]
    assert strong_imp > noise_imp
    assert strong_imp > 0.05


def test_permutation_importance_fingerprint():
    import pandas as pd
    df = pd.DataFrame({"return_pct": [1.0, -1.0], "dim_x": [1, 2]})
    rep = compute_permutation_importance(df, n_permutations=5)
    assert rep.schema_fingerprint == PI_FP


def test_permutation_importance_handles_empty():
    import pandas as pd
    rep = compute_permutation_importance(pd.DataFrame(), n_permutations=5)
    assert rep.n_trades == 0
    assert not rep.per_feature_importance


def test_permutation_importance_significance_flag():
    import pandas as pd
    import numpy as np
    n = 500
    rng = np.random.default_rng(42)
    strong = rng.normal(0, 1, n)
    df = pd.DataFrame({
        "dim_strong": strong,
        "return_pct": strong * 0.9 + rng.normal(0, 0.3, n),  # very strong signal
    })
    rep = compute_permutation_importance(df, n_permutations=30)
    assert rep.per_feature_importance["dim_strong"]["significant"] is True


# ── Adaptive Weights ─────────────────────────────────────────
def test_adaptive_weights_sum_to_one():
    alpha_report = {
        "engine": "test", "n_trades": 100,
        "dimension_analysis": {
            "dim_momentum":     {"ic_pearson": +0.08},
            "dim_rs_nifty":     {"ic_pearson": -0.05},
            "dim_trend":        {"ic_pearson": +0.03},
        }
    }
    aw = compute_adaptive_weights(alpha_report)
    total = sum(aw.adaptive_weights.values())
    assert abs(total - 1.0) < 0.01


def test_adaptive_weights_respect_min_max_guardrails():
    alpha_report = {"n_trades": 100, "dimension_analysis": {
        "dim_momentum": {"ic_pearson": +0.5}   # extremely strong
    }}
    aw = compute_adaptive_weights(alpha_report)
    for w in aw.adaptive_weights.values():
        assert MIN_MODEL_WEIGHT - 0.01 <= w <= MAX_MODEL_WEIGHT + 0.01


def test_adaptive_weights_fingerprint():
    aw = compute_adaptive_weights({"n_trades": 100})
    assert aw.schema_fingerprint == AW_FP


def test_adaptive_weights_high_ic_boosts_model():
    # dim_momentum has stronger IC than dim_trend
    aw = compute_adaptive_weights({"n_trades": 100, "dimension_analysis": {
        "dim_momentum": {"ic_pearson": +0.10},
        "dim_trend":    {"ic_pearson": +0.02},
    }})
    mom_weight = aw.adaptive_weights["aegis.momentum.v1"]
    trend_weight = aw.adaptive_weights["aegis.trend.v1"]
    assert mom_weight > trend_weight


# ── Loader / round-trip (learning-loop closure test) ────────
def test_load_ensemble_weights_returns_none_on_missing(tmp_path):
    assert load_ensemble_weights_config(tmp_path / "does_not_exist.yaml") is None


def test_load_ensemble_weights_returns_none_on_malformed(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("this-is-not-json", encoding="utf-8")
    assert load_ensemble_weights_config(p) is None


def test_load_ensemble_weights_returns_none_on_fingerprint_mismatch(tmp_path):
    import json
    p = tmp_path / "wrong.yaml"
    p.write_text(json.dumps({"schema_fingerprint": "OTHER", "weights": {"a": 0.5, "b": 0.5}}),
                   encoding="utf-8")
    assert load_ensemble_weights_config(p) is None


def test_load_ensemble_weights_round_trip(tmp_path):
    # Write then read · must recover identical dict
    original = {"aegis.momentum.v1": 0.15, "aegis.trend.v1": 0.10, "aegis.value.v1": 0.05}
    p = tmp_path / "roundtrip.yaml"
    write_ensemble_weights_config(original, p)
    loaded = load_ensemble_weights_config(p)
    assert loaded is not None
    assert loaded == original


def test_load_ensemble_weights_strips_negative_and_nonnumeric(tmp_path):
    import json
    p = tmp_path / "dirty.yaml"
    p.write_text(json.dumps({
        "schema_fingerprint": AW_FP,
        "weights": {"good": 0.5, "bad_neg": -0.1, "bad_str": "abc", "ok_zero": 0.0},
    }), encoding="utf-8")
    loaded = load_ensemble_weights_config(p)
    assert loaded == {"good": 0.5, "ok_zero": 0.0}


def test_adaptive_weights_wired_into_india_runner():
    """Guardrail against future regression: verify india runner imports the loader."""
    src = (Path(__file__).resolve().parents[2] / "india" / "model_factory" / "run.py").read_text(encoding="utf-8")
    assert "load_ensemble_weights_config" in src, "india runner missing adaptive-weights loader import"
    assert "adaptive_ic_weighted" in src, "india runner not passing adaptive weights to ensemble_predict"


def test_adaptive_weights_wired_into_usa_runner():
    src = (Path(__file__).resolve().parents[2] / "usa" / "research" / "model_factory" / "run.py").read_text(encoding="utf-8")
    assert "load_ensemble_weights_config" in src, "usa runner missing adaptive-weights loader import"
    assert "adaptive_ic_weighted" in src, "usa runner not passing adaptive weights to ensemble_predict"
