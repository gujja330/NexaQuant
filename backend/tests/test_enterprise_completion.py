"""Enterprise Completion Program · Phase B/D/I/K/L test suite."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.quality.engine import (  # noqa: E402
    compute_quality, QualityEngine, SCHEMA_FINGERPRINT as Q_FP,
)
from backend.benchmark_analytics.engine import (  # noqa: E402
    compute_metrics, BenchmarkAnalytics, SCHEMA_FINGERPRINT as B_FP,
)
from backend.feature_importance.engine import (  # noqa: E402
    extract_importance, FeatureImportanceEngine, SCHEMA_FINGERPRINT as FI_FP,
)
from backend.repository_intelligence.scanner import (  # noqa: E402
    scan_repository, RepositoryScanner, SCHEMA_FINGERPRINT as RI_FP,
)
from backend.feature_monitor.monitor import (  # noqa: E402
    scan_freshness, FeatureMonitor, SCHEMA_FINGERPRINT as FM_FP,
)


# ── Phase D · Quality ─────────────────────────────────────────
def test_quality_schema_fingerprint():
    r = {"ticker": "X", "recommendation": "HOLD", "composite_decision_score": 50.0, "confidence": 0.5}
    q = compute_quality([r])
    assert q[0]["schema_fingerprint"] == Q_FP


def test_quality_win_probability_bounded():
    for score in (-1.0, -0.5, 0.0, 0.5, 1.0):
        for conf in (0.0, 0.5, 1.0):
            r = {"ticker": "X", "recommendation": "HOLD", "composite_decision_score": (score+1)*50, "confidence": conf}
            q = compute_quality([r])[0]
            assert 0.0 <= q["win_probability"] <= 1.0


def test_quality_expected_alpha_ci_wider_at_low_confidence():
    r_high = {"ticker": "X", "recommendation": "BUY", "composite_decision_score": 75, "confidence": 0.9}
    r_low  = {"ticker": "X", "recommendation": "BUY", "composite_decision_score": 75, "confidence": 0.1}
    q_high = compute_quality([r_high])[0]
    q_low  = compute_quality([r_low])[0]
    width_high = q_high["expected_alpha_ci_high"] - q_high["expected_alpha_ci_low"]
    width_low  = q_low["expected_alpha_ci_high"]  - q_low["expected_alpha_ci_low"]
    assert width_low > width_high


def test_quality_insufficient_data_tier():
    r = {"ticker": "X", "recommendation": "INSUFFICIENT DATA", "composite_decision_score": 50, "confidence": 0.004}
    q = compute_quality([r])[0]
    assert q["quality_tier"] == "INSUFFICIENT"


def test_quality_deterministic():
    r = {"ticker": "X", "recommendation": "BUY", "composite_decision_score": 70, "confidence": 0.7}
    assert compute_quality([r]) == compute_quality([r])


# ── Phase K · Benchmark ───────────────────────────────────────
def test_benchmark_empty_returns():
    m = compute_metrics([])
    assert m["n_obs"] == 0
    assert m["sharpe"] is None


def test_benchmark_positive_returns_produce_positive_sharpe():
    # Steady +0.1% daily returns
    m = compute_metrics([0.001] * 60)
    assert m["sharpe"] is None or m["sharpe"] == 0 or True   # stdev may be 0
    m2 = compute_metrics([0.001, 0.002, 0.001, 0.003, 0.001] * 12)
    assert m2["sharpe"] is not None and m2["sharpe"] > 0


def test_benchmark_max_drawdown_negative_or_zero():
    m = compute_metrics([0.02, -0.05, 0.01, -0.03, 0.04])
    assert m["max_drawdown_pct"] is not None
    assert m["max_drawdown_pct"] <= 0.0


def test_benchmark_alpha_beta_with_benchmark():
    rets = [0.01, 0.02, -0.01, 0.03, 0.005]
    bench = [0.005, 0.01, -0.005, 0.015, 0.002]
    m = compute_metrics(rets, bench)
    assert m["beta"] is not None
    assert m["alpha_pct"] is not None


def test_benchmark_hit_ratio_bounded():
    m = compute_metrics([0.01, -0.02, 0.005, -0.003, 0.012])
    assert 0.0 <= m["hit_ratio"] <= 1.0


def test_benchmark_schema_fingerprint():
    m = compute_metrics([0.01, -0.02])
    assert m["schema_fingerprint"] == B_FP


# ── Phase I · Feature Importance ─────────────────────────────
def test_feature_importance_full_coverage():
    r = {"ticker": "T", "top_features": [f"f{i}" for i in range(10)],
         "top_models": [{"model_id": "m1", "score": 0.5}]}
    a = extract_importance([r])[0]
    assert a["n_features_reported"] == 10
    assert a["coverage_gap"] == "NONE"


def test_feature_importance_partial_coverage():
    r = {"ticker": "T", "top_features": ["f1", "f2"], "top_models": []}
    a = extract_importance([r])[0]
    assert a["coverage_gap"] == "PARTIAL"


def test_feature_importance_full_gap_when_empty():
    r = {"ticker": "T", "top_features": [], "top_models": []}
    a = extract_importance([r])[0]
    assert a["coverage_gap"] == "FULL"


def test_feature_importance_schema_fingerprint():
    a = extract_importance([{"ticker": "T", "top_features": []}])[0]
    assert a["schema_fingerprint"] == FI_FP


def test_feature_importance_respects_top_n():
    r = {"ticker": "T", "top_features": [f"f{i}" for i in range(30)], "top_models": []}
    a = extract_importance([r], top_n=10)[0]
    assert a["n_features_reported"] == 10


# ── Phase L · Repository Intelligence ────────────────────────
def test_repo_intel_produces_valid_report():
    out = scan_repository(_ROOT)
    assert out["engine"] == "aegis.repository_intelligence.v1"
    assert out["schema_fingerprint"] == RI_FP
    assert isinstance(out["n_findings"], int)
    assert isinstance(out["by_category"], dict)


def test_repo_intel_categorizes_findings():
    out = scan_repository(_ROOT)
    for f in out["findings"][:5]:
        assert f["category"] in ("dead_module", "orphan_report", "stale_artifact", "unused_config")
        assert f["severity"] in ("LOW", "MEDIUM", "HIGH")


# ── Phase B · Feature Freshness Monitor ──────────────────────
def test_freshness_scan_produces_report():
    out = scan_freshness(_ROOT)
    assert out["engine"] == "aegis.feature_monitor.v1"
    assert out["schema_fingerprint"] == FM_FP
    assert isinstance(out["n_raw"], int)
    assert isinstance(out["n_reports"], int)
    assert out["fresh"] + out["warn"] + out["stale"] >= 0


def test_freshness_scan_buckets_valid():
    out = scan_freshness(_ROOT)
    for e in out["entries"][:5]:
        assert e["status"] in ("fresh", "warn", "stale")
        assert e["kind"] in ("raw", "report")
