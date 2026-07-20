"""Sprint 2.7 regression — Model Factory + 11 models + Ensemble + AI Model Analyst."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.model_factory              import (                                              # noqa: E402
    ModelFactory, ensemble_predict, evaluate_model, EnsembleWeights,
    list_registered_models,
)
from backend.model_factory.model_base   import BaseModel, ModelType                          # noqa: E402
from backend.model_factory.models       import ALL_MODELS                                   # noqa: E402
from backend.ai import model_analyst                                                          # noqa: E402


def _sample_features() -> pd.DataFrame:
    """Synthetic feature snapshot for 20 tickers with a realistic subset of columns."""
    rng = np.random.default_rng(42)
    n = 20
    return pd.DataFrame({
        "market":   ["usa"] * n,
        "ticker":   [f"T{i:02d}" for i in range(n)],
        "asof":     ["2026-07-20"] * n,
        "sector":   ["Tech"] * n,
        "currency": ["USD"] * n,
        # tech
        "return_5d_pct":       rng.normal(0, 3, n),
        "return_20d_pct":      rng.normal(2, 5, n),
        "return_60d_pct":      rng.normal(4, 8, n),
        "price_above_sma20":   rng.integers(0, 2, n).astype(float),
        "price_above_sma50":   rng.integers(0, 2, n).astype(float),
        "price_above_sma200":  rng.integers(0, 2, n).astype(float),
        "rsi_14":              rng.uniform(20, 80, n),
        "adx_14":              rng.uniform(15, 45, n),
        "distance_from_52w_high_pct": rng.uniform(-30, 0, n),
        "distance_from_52w_low_pct":  rng.uniform(0, 40, n),
        "max_drawdown_60d_pct":       rng.uniform(-20, 0, n),
        # fund
        "fund_trailing_pe":     rng.uniform(10, 60, n),
        "fund_price_to_book":   rng.uniform(1, 8, n),
        "fund_roe":             rng.uniform(0.05, 0.35, n),
        "fund_profit_margin":   rng.uniform(0.02, 0.30, n),
        "fund_debt_to_equity":  rng.uniform(0.2, 3.0, n),
        "fund_earnings_growth": rng.uniform(-0.1, 0.4, n),
        "fund_quality_score":   rng.uniform(20, 80, n),
        # news
        "news_sentiment":       rng.uniform(-0.5, 0.5, n),
        "news_n_headlines":     rng.integers(0, 20, n).astype(float),
        "news_polarity_ratio":  rng.uniform(-0.5, 0.5, n),
        # event
        "earn_days_to_next":    rng.integers(0, 90, n).astype(float),
        "earn_last_surprise_pct": rng.uniform(-15, 15, n),
        "insider_net_90d":      rng.uniform(-1e8, 1e8, n),
        # sector
        "sector_return_1m_pct": rng.uniform(-8, 8, n),
        "sector_is_leader":     rng.integers(0, 2, n).astype(float),
        "sector_is_laggard":    rng.integers(0, 2, n).astype(float),
        # macro (broadcast)
        "macro_10y":            [4.25] * n,
        "macro_vix":            [18.5] * n,
        "mi_composite_score":   [50.0] * n,
    })


# ── Framework ──────────────────────────────────────────────────
def test_all_11_model_types_registered():
    types = {m.METADATA.model_type for m in [cls() for cls in ALL_MODELS]}
    expected = set(ModelType)
    assert types == expected, f"missing types: {expected - types}"
    print(f"  [OK] all 11 model types registered ({len(types)} types)")


def test_every_model_has_business_rationale_and_intuition():
    for cls in ALL_MODELS:
        m = cls()
        assert m.metadata.business_rationale.strip(), \
            f"{cls.__name__} missing business_rationale"
        assert m.metadata.economic_intuition.strip(), \
            f"{cls.__name__} missing economic_intuition"
    print(f"  [OK] all {len(ALL_MODELS)} models carry business_rationale + economic_intuition")


def test_every_model_has_feature_dependencies():
    for cls in ALL_MODELS:
        m = cls()
        if m.metadata.model_type == ModelType.AI_HYBRID:
            # Hybrid depends on other models' outputs, not features directly
            assert m.metadata.feature_dependencies == []
        else:
            assert len(m.metadata.feature_dependencies) > 0, \
                f"{cls.__name__} declares no feature dependencies"
    print(f"  [OK] every model declares feature_dependencies")


# ── Prediction ─────────────────────────────────────────────────
def test_factory_predicts_all_11_models():
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    factory.train_all(df, None, date(2026, 7, 20))
    preds = factory.predict_all(df, cutoff=date(2026, 7, 20))
    assert len(preds) == 11
    for p in preds:
        assert p.n_scored == len(df)
        assert "score" in p.predictions.columns
        assert "confidence" in p.predictions.columns
        # scores must be in [-1, +1]
        assert p.predictions["score"].between(-1, 1).all(), \
            f"{p.model_id} produced out-of-range scores"
    print(f"  [OK] factory ran 11 models × 20 tickers, all scores in [-1, +1]")


def test_predictions_deterministic():
    """Same features + same cutoff → identical predictions."""
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    p1 = factory.predict_all(df, cutoff=date(2026, 7, 20))
    p2 = factory.predict_all(df, cutoff=date(2026, 7, 20))
    for a, b in zip(p1, p2):
        assert (a.predictions["score"].values == b.predictions["score"].values).all(), \
            f"{a.model_id} not deterministic"
    print(f"  [OK] all model predictions deterministic across identical calls")


# ── Ensemble ────────────────────────────────────────────────────
def test_ensemble_combines_predictions():
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    preds = factory.predict_all(df, cutoff=date(2026, 7, 20))
    ens = ensemble_predict(preds, market="usa", asof=date(2026, 7, 20))
    assert ens.n_models == 11
    assert len(ens.predictions) == len(df)
    assert ens.predictions["ensemble_score"].between(-1, 1).all()
    print(f"  [OK] ensemble combines {ens.n_models} models → {len(ens.predictions)} tickers")


def test_ensemble_weights_normalize():
    w = EnsembleWeights(weights={"a": 2.0, "b": 6.0, "c": 2.0}, strategy="manual")
    norm = w.normalize()
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    assert abs(norm["b"] - 0.6) < 1e-9
    print(f"  [OK] ensemble weights normalize correctly")


def test_empty_ensemble_returns_empty():
    ens = ensemble_predict([], market="usa", asof=date.today())
    assert ens.n_models == 0
    assert ens.predictions.empty
    print(f"  [OK] empty ensemble handled cleanly")


# ── Metrics ────────────────────────────────────────────────────
def test_evaluate_model_computes_metrics():
    from backend.model_factory.models.momentum import MomentumModel
    m = MomentumModel()
    df = _sample_features()
    p = m.predict(df, cutoff=date(2026, 7, 20))
    metrics = evaluate_model(p, learning_corpus_path=None)
    assert metrics.n_scored == len(df)
    # No learning corpus → status should be insufficient_history
    assert metrics.status == "insufficient_history"
    assert metrics.avg_score is not None
    print(f"  [OK] evaluate_model: n_scored={metrics.n_scored} status={metrics.status}")


# ── AI Model Analyst ────────────────────────────────────────────
def test_ai_model_analyst_runs():
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    preds = factory.predict_all(df, cutoff=date(2026, 7, 20))
    metrics_list = [evaluate_model(p) for p in preds]
    desc = factory.describe_all()
    out = model_analyst.run(desc, metrics_list, ensemble_summary=None,
                              market_name="usa", asof=date(2026, 7, 20))
    assert out.agent == "model_analyst"
    assert out.headline and out.narrative
    assert len(out.findings) >= 11    # at least one per model
    print(f"  [OK] AI Model Analyst produced narrative for {len(desc)} models")


def test_ai_model_analyst_never_promotes():
    """Contract: findings must not contain buy/sell/target/promoted/approved keys."""
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    preds = factory.predict_all(df, cutoff=date(2026, 7, 20))
    metrics = [evaluate_model(p) for p in preds]
    desc = factory.describe_all()
    out = model_analyst.run(desc, metrics, None, "usa", date(2026, 7, 20))
    forbidden = {"buy", "sell", "target_price", "recommendation", "action",
                  "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Model Analyst leaked: {leak}"
    print(f"  [OK] AI Model Analyst obeys no-promotion contract")


# ── Walk-forward readiness ─────────────────────────────────────
def test_models_accept_cutoff_parameter():
    """Every model.predict() must accept a cutoff date."""
    factory = ModelFactory(_ROOT, "usa")
    df = _sample_features()
    d = date(2020, 1, 1)   # deep past — must not crash
    preds = factory.predict_all(df, cutoff=d)
    for p in preds:
        assert p.asof == d
    print(f"  [OK] all 11 models accept cutoff dates (walk-forward ready)")


# ── Integration ─────────────────────────────────────────────────
def test_india_model_factory_runner():
    r = subprocess.run(
        [sys.executable, "india/model_factory/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:800]}"
    summary = json.loads((_ROOT / "reports" / "model_factory.json").read_text(encoding="utf-8"))
    assert summary["market"] == "india"
    assert summary["n_models"] == 11
    print(f"  [OK] india model factory: {summary['n_models']} models emitted")


def test_usa_model_factory_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/model_factory/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:800]}"
    summary = json.loads((_ROOT / "usa" / "reports" / "model_factory.json").read_text(encoding="utf-8"))
    assert summary["market"] == "usa"
    ens = json.loads((_ROOT / "usa" / "reports" / "ensemble.json").read_text(encoding="utf-8"))
    assert ens["n_models"] == 11
    assert len(ens["top_10"]) > 0
    print(f"  [OK] usa model factory: {summary['n_models']} models · ensemble top_10 populated")


TESTS = [
    test_all_11_model_types_registered,
    test_every_model_has_business_rationale_and_intuition,
    test_every_model_has_feature_dependencies,
    test_factory_predicts_all_11_models,
    test_predictions_deterministic,
    test_ensemble_combines_predictions,
    test_ensemble_weights_normalize,
    test_empty_ensemble_returns_empty,
    test_evaluate_model_computes_metrics,
    test_ai_model_analyst_runs,
    test_ai_model_analyst_never_promotes,
    test_models_accept_cutoff_parameter,
    test_india_model_factory_runner,
    test_usa_model_factory_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 2.7 · Model Factory + 11 Models + Ensemble + AI Analyst")
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
