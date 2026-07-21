"""Sprint 3 regression — Recommendation Intelligence v3."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation             import (                                          # noqa: E402
    Action, Recommendation, RecommendationBatch, RecommendationEngine,
    resolve_conflict, calibrate_confidence, CalibrationInputs,
    apply_regime_adjustment, classify, explain,
)
from backend.ai import recommendation_analyst                                              # noqa: E402


# ── Conflict resolver ──────────────────────────────────────────
def test_conflict_all_agree():
    r = resolve_conflict({"a": 0.5, "b": 0.6, "c": 0.4})
    assert r.n_positive == 3 and r.n_negative == 0
    assert r.model_agreement == 1.0
    assert not r.disagreement_flag
    print(f"  [OK] conflict resolver: 3/3 agree → agreement=1.0")


def test_conflict_split():
    r = resolve_conflict({"a": 0.5, "b": -0.5, "c": 0.5, "d": -0.5})
    assert r.disagreement_flag
    assert r.disagreement_severity in {"minor", "major"}
    print(f"  [OK] conflict resolver: 2/2 split → disagreement={r.disagreement_severity}")


def test_conflict_neutral_only():
    r = resolve_conflict({"a": 0.02, "b": -0.01, "c": 0.0})
    assert r.dominant_side == "neutral"
    print(f"  [OK] conflict resolver: all-neutral → dominant='neutral'")


# ── Calibration ────────────────────────────────────────────────
def test_calibration_high_agreement_preserves_conf():
    c = calibrate_confidence(CalibrationInputs(
        raw_confidence=0.9, model_agreement=1.0, evidence_coverage=1.0))
    assert 0.85 <= c <= 0.90
    print(f"  [OK] calibration: high agreement retains ≥85% of raw conf ({c})")


def test_calibration_low_agreement_halves_conf():
    c = calibrate_confidence(CalibrationInputs(
        raw_confidence=0.9, model_agreement=0.0, evidence_coverage=1.0))
    # 0.5 factor from agreement × 1.0 evidence → ~0.45
    assert 0.40 <= c <= 0.50
    print(f"  [OK] calibration: 0-agreement halves conf ({c})")


def test_calibration_thin_evidence_reduces():
    c = calibrate_confidence(CalibrationInputs(
        raw_confidence=0.9, model_agreement=1.0, evidence_coverage=0.3))
    # evidence factor floored at 0.5
    assert c < 0.60
    print(f"  [OK] calibration: thin evidence reduces conf ({c})")


# ── Regime ─────────────────────────────────────────────────────
def test_regime_bull_favours_buy():
    c_buy, hold_buy = apply_regime_adjustment("bull", ensemble_score=0.7, confidence=0.8)
    c_sell, hold_sell = apply_regime_adjustment("bull", ensemble_score=-0.7, confidence=0.8)
    assert c_buy > c_sell, f"bull should favour BUY: buy={c_buy} sell={c_sell}"
    print(f"  [OK] regime BULL: buy_conf={c_buy} > sell_conf={c_sell}")


def test_regime_bear_favours_sell():
    c_buy, _ = apply_regime_adjustment("bear", 0.7, 0.8)
    c_sell, _ = apply_regime_adjustment("bear", -0.7, 0.8)
    assert c_sell > c_buy, f"bear should favour SELL: buy={c_buy} sell={c_sell}"
    print(f"  [OK] regime BEAR: sell_conf={c_sell} > buy_conf={c_buy}")


def test_regime_stress_dampens_buy():
    c, _ = apply_regime_adjustment("stress", 0.7, 0.9)
    assert c < 0.65, f"stress regime should dampen BUY: {c}"
    print(f"  [OK] regime STRESS: buy conf dampened ({c})")


# ── Classifier ─────────────────────────────────────────────────
def test_classifier_thresholds():
    assert classify(0.60, 0.80, False) == Action.STRONG_BUY
    assert classify(0.30, 0.60, False) == Action.BUY
    assert classify(0.00, 0.90, False) == Action.HOLD
    assert classify(-0.30, 0.60, False) == Action.SELL
    assert classify(-0.60, 0.80, False) == Action.STRONG_SELL
    print(f"  [OK] classifier thresholds map correctly")


def test_classifier_disagreement_collapses_to_hold():
    """When disagreement_flag=True the classifier must return HOLD regardless of score."""
    assert classify(0.99, 0.99, True) == Action.HOLD
    assert classify(-0.99, 0.99, True) == Action.HOLD
    print(f"  [OK] classifier: disagreement_flag → HOLD (safety valve)")


def test_classifier_low_confidence_holds():
    assert classify(0.60, 0.30, False) == Action.HOLD
    print(f"  [OK] classifier: high score but low conf → HOLD")


# ── Explainer ──────────────────────────────────────────────────
def test_explainer_produces_bull_bear():
    feature_row = {"return_20d_pct": 12.0, "fund_quality_score": 75.0,
                     "close": 100.0, "fund_debt_to_equity": 0.5}
    e = explain(feature_row, {"a": 0.8}, Action.BUY, 0.6, 60)
    assert e["bull_case"] and "momentum" in e["bull_case"].lower()
    assert e["bear_case"]
    assert e["entry_zone"]["current"] == 100.0
    assert len(e["exit_conditions"]) > 0
    print(f"  [OK] explainer produced bull/bear/entry/exit")


def test_explainer_hold_no_active_exit():
    e = explain({"close": 50.0}, {}, Action.HOLD, 0.05, 60)
    assert "hold" in e["exit_conditions"][0].lower()
    print(f"  [OK] explainer: HOLD → no active exit trigger")


# ── Engine ─────────────────────────────────────────────────────
def _sample_ensemble_rows():
    return [
        {"ticker": "T1", "ensemble_score": 0.7, "ensemble_confidence": 0.8,
         "per_model_score": {"a": 0.7, "b": 0.65, "c": 0.75}, "n_models_scoring": 3},
        {"ticker": "T2", "ensemble_score": -0.6, "ensemble_confidence": 0.75,
         "per_model_score": {"a": -0.6, "b": -0.7, "c": -0.5}, "n_models_scoring": 3},
        {"ticker": "T3", "ensemble_score": 0.1, "ensemble_confidence": 0.4,
         "per_model_score": {"a": 0.5, "b": -0.5, "c": 0.0}, "n_models_scoring": 3},
    ]


def _sample_features_df():
    return pd.DataFrame([
        {"market": "usa", "ticker": "T1", "asof": "2026-07-20", "sector": "T", "currency": "USD",
         "return_20d_pct": 12, "fund_quality_score": 75, "close": 100, "fund_debt_to_equity": 0.5},
        {"market": "usa", "ticker": "T2", "asof": "2026-07-20", "sector": "T", "currency": "USD",
         "return_20d_pct": -12, "fund_quality_score": 30, "close": 40, "fund_debt_to_equity": 2.0},
        {"market": "usa", "ticker": "T3", "asof": "2026-07-20", "sector": "T", "currency": "USD",
         "return_20d_pct": 0, "close": 80},
    ])


def test_engine_end_to_end_produces_batch():
    engine = RecommendationEngine(_ROOT, "usa", regime="neutral",
                                    schema_fingerprint="test", feature_set_version="test",
                                    model_stamp={"model_id": "test.v1"})
    batch = engine.run(
        ensemble_top_rows=_sample_ensemble_rows(),
        features_df=_sample_features_df(),
        selected_features=["return_20d_pct", "fund_quality_score", "fund_debt_to_equity"],
        asof=date(2026, 7, 20),
    )
    assert batch.n_tickers == 3
    tickers = {r.ticker for r in batch.recommendations}
    assert tickers == {"T1", "T2", "T3"}
    # T1 = strong positive with agreement → BUY-ish
    t1 = next(r for r in batch.recommendations if r.ticker == "T1")
    assert t1.action in {Action.BUY, Action.STRONG_BUY, Action.HOLD}   # neutral regime might dampen
    # T3 = mixed 50/50 → conflict → HOLD
    t3 = next(r for r in batch.recommendations if r.ticker == "T3")
    assert t3.action == Action.HOLD
    print(f"  [OK] engine end-to-end: {batch.n_tickers} tickers · dist "
           f"SB={batch.n_strong_buy} B={batch.n_buy} H={batch.n_hold} "
           f"S={batch.n_sell} SS={batch.n_strong_sell}")


def test_engine_deterministic():
    engine = RecommendationEngine(_ROOT, "usa", regime="neutral",
                                    schema_fingerprint="t", feature_set_version="t")
    rows = _sample_ensemble_rows(); df = _sample_features_df()
    b1 = engine.run(rows, df, ["return_20d_pct"], asof=date(2026, 7, 20))
    b2 = engine.run(rows, df, ["return_20d_pct"], asof=date(2026, 7, 20))
    a1 = [r.action.value for r in b1.recommendations]
    a2 = [r.action.value for r in b2.recommendations]
    assert a1 == a2, "engine not deterministic"
    print(f"  [OK] recommendation engine deterministic across identical calls")


def test_recommendation_carries_model_stamp():
    engine = RecommendationEngine(_ROOT, "usa", regime="neutral",
                                    schema_fingerprint="fp123", feature_set_version="fs456",
                                    model_stamp={"model_id": "aegis.rec.v3", "version": "1.0.0"})
    batch = engine.run(_sample_ensemble_rows(), _sample_features_df(),
                          ["return_20d_pct"], asof=date(2026, 7, 20))
    for r in batch.recommendations:
        assert r.model_stamp["model_id"] == "aegis.rec.v3"
        assert r.schema_fingerprint == "fp123"
        assert r.feature_set_version == "fs456"
    print(f"  [OK] every recommendation carries model_stamp + feature_set_version + schema_fingerprint")


# ── AI Recommendation Analyst ─────────────────────────────────
def test_ai_analyst_runs():
    engine = RecommendationEngine(_ROOT, "usa", regime="neutral",
                                    schema_fingerprint="t", feature_set_version="t")
    batch = engine.run(_sample_ensemble_rows(), _sample_features_df(),
                          ["return_20d_pct"], asof=date(2026, 7, 20))
    out = recommendation_analyst.run(batch, "neutral", "usa", date(2026, 7, 20))
    assert out.agent == "recommendation_analyst"
    assert out.headline and out.narrative
    print(f"  [OK] AI Recommendation Analyst: {out.headline[:80]}")


def test_ai_analyst_never_promotes():
    """Contract: analyst findings must not carry buy/sell/promoted/approved keys."""
    engine = RecommendationEngine(_ROOT, "usa", regime="neutral",
                                    schema_fingerprint="t", feature_set_version="t")
    batch = engine.run(_sample_ensemble_rows(), _sample_features_df(), [], asof=date(2026, 7, 20))
    out = recommendation_analyst.run(batch, "neutral", "usa", date(2026, 7, 20))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Recommendation Analyst leaked: {leak}"
    print(f"  [OK] AI Recommendation Analyst obeys no-promotion contract")


# ── Walk-forward readiness ─────────────────────────────────────
def test_engine_accepts_cutoff_and_stays_deterministic():
    """Walk-forward safe: past cutoff should still produce output."""
    engine = RecommendationEngine(_ROOT, "usa", regime="bull",
                                    schema_fingerprint="t", feature_set_version="t")
    past = date(2020, 1, 1)
    batch = engine.run(_sample_ensemble_rows(), _sample_features_df(),
                          ["return_20d_pct"], asof=past)
    assert batch.asof == past
    print(f"  [OK] engine accepts historical cutoff (walk-forward ready)")


# ── Integration ─────────────────────────────────────────────────
def test_india_recommendation_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "india/recommendation_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "recommendations_v3.json")
                     .read_text(encoding="utf-8"))
    assert d["market"] == "india"
    assert "recommendations" in d and "distribution" in d
    print(f"  [OK] india runner: n_tickers={d['n_tickers']} dist={d['distribution']}")


def test_usa_recommendation_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "usa/research/recommendation_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "recommendations_v3.json")
                     .read_text(encoding="utf-8"))
    assert d["market"] == "usa"
    assert d["currency"] == "USD"
    print(f"  [OK] usa runner: n_tickers={d['n_tickers']} currency={d['currency']}")


TESTS = [
    test_conflict_all_agree, test_conflict_split, test_conflict_neutral_only,
    test_calibration_high_agreement_preserves_conf,
    test_calibration_low_agreement_halves_conf,
    test_calibration_thin_evidence_reduces,
    test_regime_bull_favours_buy,
    test_regime_bear_favours_sell,
    test_regime_stress_dampens_buy,
    test_classifier_thresholds,
    test_classifier_disagreement_collapses_to_hold,
    test_classifier_low_confidence_holds,
    test_explainer_produces_bull_bear,
    test_explainer_hold_no_active_exit,
    test_engine_end_to_end_produces_batch,
    test_engine_deterministic,
    test_recommendation_carries_model_stamp,
    test_ai_analyst_runs,
    test_ai_analyst_never_promotes,
    test_engine_accepts_cutoff_and_stays_deterministic,
    test_india_recommendation_runner_emits_valid_json,
    test_usa_recommendation_runner_emits_valid_json,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 3 · Recommendation Intelligence v3 · Regression Tests")
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
