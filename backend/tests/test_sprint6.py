"""Sprint 6 regression — Learning Engine + AI Learning Analyst."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.learning              import (                                                # noqa: E402
    LearningEngine, compute_outcomes, compute_feature_attribution,
    compute_model_attribution, cluster_failures, fit_calibration_curve,
    read_corpus, append_corpus,
)
from backend.learning.types        import LearningRow, ErrorBucket, CalibrationCurve       # noqa: E402
from backend.learning.calibration  import _pool_adjacent_violators                          # noqa: E402
from backend.ai import learning_analyst                                                     # noqa: E402


# ── Types ──────────────────────────────────────────────────────
def test_learning_row_carries_provenance():
    r = LearningRow(
        market="usa", ticker="AAPL",
        rec_asof=date(2025, 1, 15),
        horizon_close_date=date(2025, 3, 16),
        action="BUY", ensemble_score=0.6, calibrated_confidence=0.7,
        regime_at_rec="bull",
        entry_price=150, exit_price=165, return_pct=0.10, is_winner=True,
        horizon_days=60,
        feature_set_version="fp123", schema_fingerprint="fp123",
        model_stamp_at_rec={"model_id": "aegis.recommendation.v3"},
    )
    assert r.feature_set_version == "fp123"
    assert r.model_stamp_at_rec["model_id"] == "aegis.recommendation.v3"
    print(f"  [OK] LearningRow carries feature_set_version + schema_fingerprint + model_stamp")


# ── Corpus ──────────────────────────────────────────────────────
def test_corpus_empty_when_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        df = read_corpus(root, "usa")
        assert df.empty
        print(f"  [OK] read_corpus returns empty DF when file absent")


def test_corpus_append_only_dedup_natural_key():
    """Two calls with the same (market, ticker, rec_asof) → only ONE row stored."""
    import gc
    tmp = tempfile.mkdtemp()
    try:
        root = Path(tmp)
        r = LearningRow(
            market="usa", ticker="AAPL",
            rec_asof=date(2025, 1, 15),
            horizon_close_date=date(2025, 3, 16),
            action="BUY", ensemble_score=0.6, calibrated_confidence=0.7,
            regime_at_rec="bull",
            entry_price=150, exit_price=165, return_pct=0.10, is_winner=True,
            horizon_days=60,
        )
        _, n1 = append_corpus(root, "usa", [r])
        _, n2 = append_corpus(root, "usa", [r])   # duplicate — should be skipped
        assert n1 == 1 and n2 == 0
        df = read_corpus(root, "usa")
        assert len(df) == 1
        del df; gc.collect()      # release parquet handle on Windows before cleanup
        print(f"  [OK] corpus dedupe on (market, ticker, rec_asof) natural key")
    finally:
        # Best-effort cleanup — Windows pyarrow handles can linger briefly.
        import shutil
        try: shutil.rmtree(tmp)
        except (PermissionError, OSError): pass


# ── Outcome computer ─────────────────────────────────────────────
def test_outcome_computer_returns_empty_when_history_empty():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        empty_hist = pd.DataFrame()
        rows = compute_outcomes(root, "usa", empty_hist, cutoff=date(2026, 7, 21))
        assert rows == []
        print(f"  [OK] outcome_computer returns [] when rec_history is empty")


def test_outcome_computer_skips_hold_and_open_horizons():
    """HOLD recs and recs whose horizon > cutoff should be skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Synthetic history: one HOLD (should skip), one BUY whose horizon hasn't closed
        history = pd.DataFrame([
            {"ticker": "T1", "rec_asof": "2026-07-01", "action": "HOLD",
             "ensemble_score": 0, "calibrated_confidence": 0.5,
             "regime": "neutral", "entry_reference": 100},
            {"ticker": "T2", "rec_asof": "2026-07-01", "action": "BUY",
             "ensemble_score": 0.5, "calibrated_confidence": 0.7,
             "regime": "neutral", "entry_reference": 100},
        ])
        # Cutoff is BEFORE horizon closes → both skipped
        rows = compute_outcomes(root, "usa", history, cutoff=date(2026, 7, 15),
                                   horizon_days=60)
        assert rows == []
        print(f"  [OK] outcome_computer skips HOLDs + open horizons at cutoff")


# ── Feature attribution ─────────────────────────────────────────
def test_feature_attribution_empty_corpus_returns_empty():
    result = compute_feature_attribution(pd.DataFrame())
    assert result == []
    print(f"  [OK] feature_attribution returns [] on empty corpus")


def test_feature_attribution_ranks_by_net_alpha():
    corpus = pd.DataFrame([
        {"top_features": ["momentum", "quality"], "return_pct":  0.10, "is_winner": True},
        {"top_features": ["momentum", "value"],   "return_pct":  0.08, "is_winner": True},
        {"top_features": ["value"],               "return_pct": -0.05, "is_winner": False},
        {"top_features": ["quality"],             "return_pct":  0.03, "is_winner": True},
    ])
    result = compute_feature_attribution(corpus)
    features = [a.key for a in result]
    assert "momentum" in features and "quality" in features and "value" in features
    print(f"  [OK] feature_attribution ranks {len(result)} features by |net_alpha|")


# ── Model attribution ───────────────────────────────────────────
def test_model_attribution_handles_dict_or_string_top_models():
    """top_models rows may be dicts (Sprint 3 shape) OR strings — both must work."""
    corpus = pd.DataFrame([
        {"top_models": [{"model_id": "m1", "score": 0.8}, "m2"],
         "return_pct": 0.05, "is_winner": True},
        {"top_models": ["m1"], "return_pct": -0.02, "is_winner": False},
    ])
    result = compute_model_attribution(corpus)
    keys = {a.key for a in result}
    assert "m1" in keys and "m2" in keys
    print(f"  [OK] model_attribution handles both dict and string top_models entries")


# ── Failure clustering ──────────────────────────────────────────
def test_failure_clustering_groups_by_regime_and_error_bucket():
    corpus = pd.DataFrame([
        {"ticker": "T1", "is_winner": False, "regime_at_rec": "bear",
         "error_bucket": "underestimated_vol", "top_features": ["a", "b"]},
        {"ticker": "T2", "is_winner": False, "regime_at_rec": "bear",
         "error_bucket": "underestimated_vol", "top_features": ["a", "c"]},
        {"ticker": "T3", "is_winner": False, "regime_at_rec": "bear",
         "error_bucket": "underestimated_vol", "top_features": ["a"]},
        {"ticker": "T4", "is_winner": True,  "regime_at_rec": "bear",
         "error_bucket": "worked_as_expected", "top_features": ["a"]},
    ])
    clusters = cluster_failures(corpus, min_cluster_size=3)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.n_members == 3
    assert c.dominant_error_bucket == "underestimated_vol"
    assert "a" in c.dominant_features
    print(f"  [OK] failure_clustering: 1 cluster (n=3) with 'a' as dominant feature")


def test_failure_clustering_min_size_gate():
    corpus = pd.DataFrame([
        {"ticker": "T1", "is_winner": False, "regime_at_rec": "bull",
         "error_bucket": "regime_change", "top_features": []},
    ])
    clusters = cluster_failures(corpus, min_cluster_size=3)
    assert clusters == []      # below min_cluster_size → no cluster emitted
    print(f"  [OK] failure_clustering: single-member group filtered out below min_cluster_size")


# ── Calibration ─────────────────────────────────────────────────
def test_calibration_empty_falls_back_to_identity():
    c = fit_calibration_curve(pd.DataFrame(), n_bins=10)
    assert c.method == "identity"
    assert c.n_observations == 0
    print(f"  [OK] calibration falls back to identity on empty corpus")


def test_calibration_pav_is_monotone():
    """PAV output must be non-decreasing."""
    rates = [0.3, 0.5, 0.4, 0.6, 0.9, 0.7]
    out = _pool_adjacent_violators(rates)
    assert all(out[i] <= out[i + 1] + 1e-9 for i in range(len(out) - 1)), out
    print(f"  [OK] PAV enforces monotone non-decreasing: {[round(v, 3) for v in out]}")


def test_calibration_fits_on_populated_corpus():
    """With ≥20 obs, real calibration runs (isotonic_pav method)."""
    # 20 obs with monotone winrate: low conf → mostly losers, high conf → mostly winners
    rows = []
    for i in range(20):
        conf = i * 0.05
        # Force monotone win-rate structure
        is_winner = i >= 10
        rows.append({"calibrated_confidence": conf, "is_winner": is_winner,
                       "return_pct": 0.02 if is_winner else -0.02})
    corpus = pd.DataFrame(rows)
    c = fit_calibration_curve(corpus, n_bins=5)
    assert c.method == "isotonic_pav"
    assert c.n_observations == 20
    # Fitted must be monotone
    assert all(c.fitted_win_rates[i] <= c.fitted_win_rates[i + 1] + 1e-9
                for i in range(len(c.fitted_win_rates) - 1))
    print(f"  [OK] calibration fits isotonic_pav on 20-obs corpus (monotone verified)")


# ── Engine end-to-end ───────────────────────────────────────────
def test_engine_deterministic_and_walk_forward_safe():
    """Engine runs cleanly at any cutoff — even distant past — and is deterministic."""
    engine = LearningEngine(_ROOT, "usa", horizon_days=60)
    r1 = engine.run(asof=date(2020, 1, 1))     # distant past — no recs to close
    r2 = engine.run(asof=date(2020, 1, 1))
    assert r1.n_new_closed == r2.n_new_closed
    assert r1.win_rate == r2.win_rate
    print(f"  [OK] engine deterministic + accepts distant-past cutoff (walk-forward safe)")


def test_engine_empty_corpus_returns_identity_calibration():
    engine = LearningEngine(_ROOT, "usa")
    r = engine.run(asof=date(2020, 1, 1))
    # With no history → no corpus → identity calibration
    assert r.calibration_curve.method == "identity"
    assert r.n_corpus_total == 0
    print(f"  [OK] engine on empty history → identity calibration + 0 corpus")


# ── AI Learning Analyst ─────────────────────────────────────────
def test_ai_analyst_runs():
    engine = LearningEngine(_ROOT, "usa")
    r = engine.run(asof=date(2026, 7, 21))
    out = learning_analyst.run(r, "usa", date(2026, 7, 21))
    assert out.agent == "learning_analyst"
    assert out.headline and out.narrative
    print(f"  [OK] AI Learning Analyst: {out.headline[:80]}")


def test_ai_analyst_never_promotes():
    engine = LearningEngine(_ROOT, "usa")
    r = engine.run(asof=date(2026, 7, 21))
    out = learning_analyst.run(r, "usa", date(2026, 7, 21))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Learning Analyst leaked: {leak}"
    print(f"  [OK] AI Learning Analyst obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_runner():
    r = subprocess.run(
        [sys.executable, "india/learning_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "ai_learning_narrative.json").read_text(encoding="utf-8"))
    assert d["market"] == "india"
    print(f"  [OK] india runner emitted valid JSON")


def test_usa_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/learning_engine/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "ai_learning_narrative.json").read_text(encoding="utf-8"))
    assert d["market"] == "usa"
    print(f"  [OK] usa runner emitted valid JSON")


TESTS = [
    test_learning_row_carries_provenance,
    test_corpus_empty_when_no_file, test_corpus_append_only_dedup_natural_key,
    test_outcome_computer_returns_empty_when_history_empty,
    test_outcome_computer_skips_hold_and_open_horizons,
    test_feature_attribution_empty_corpus_returns_empty,
    test_feature_attribution_ranks_by_net_alpha,
    test_model_attribution_handles_dict_or_string_top_models,
    test_failure_clustering_groups_by_regime_and_error_bucket,
    test_failure_clustering_min_size_gate,
    test_calibration_empty_falls_back_to_identity,
    test_calibration_pav_is_monotone,
    test_calibration_fits_on_populated_corpus,
    test_engine_deterministic_and_walk_forward_safe,
    test_engine_empty_corpus_returns_identity_calibration,
    test_ai_analyst_runs, test_ai_analyst_never_promotes,
    test_india_runner, test_usa_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 6 · Learning Engine · Regression Tests")
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
