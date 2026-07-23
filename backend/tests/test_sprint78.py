"""
Sprint 7.8 · Recommendation Benchmark Report · regression tests.
"""
from __future__ import annotations
import io
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backend.benchmark import (
    build_benchmark_report, build_comparison,
    SIGNIFICANCE_MIN_SAMPLES, INSTITUTIONAL_MIN_SAMPLES,
    wilson_confidence_interval, mean_confidence_interval, sample_size_verdict,
)
from backend.benchmark.report import (
    _compute_metrics_on_slice, _bucket_confidence,
    _compute_consecutive_streaks, _strong_buy_vs_buy,
)


_passed = 0
_failed = 0

def _ok(msg):
    global _passed; _passed += 1
    print(f"  [OK] {msg}")

def _fail(msg, e):
    global _failed; _failed += 1
    print(f"  [FAIL] {msg}: {e}")

def _run(label, fn):
    try:
        fn(); _ok(label)
    except AssertionError as e:
        _fail(label, e)
    except Exception as e:
        _fail(label, e)


# ── statistical significance ─────────────────────────────────────

def test_wilson_ci_wide_for_small_n():
    """5 wins out of 10 → Wilson CI must be WIDE (not the naive [0.5, 0.5])."""
    p, lo, hi = wilson_confidence_interval(5, 10)
    assert p == 0.5
    assert hi - lo > 0.4, f"CI should be wide for n=10, got [{lo}, {hi}]"


def test_wilson_ci_tighter_for_large_n():
    p1, lo1, hi1 = wilson_confidence_interval(50, 100)
    p2, lo2, hi2 = wilson_confidence_interval(500, 1000)
    assert (hi2 - lo2) < (hi1 - lo1), "CI must tighten as n grows"


def test_wilson_ci_handles_zero_n():
    p, lo, hi = wilson_confidence_interval(0, 0)
    assert lo == 0.0 and hi == 1.0


def test_mean_ci_wide_for_small_n():
    _, lo, hi = mean_confidence_interval(mean=0.5, std=2.0, n=5)
    assert hi - lo > 3.0, "small-n mean CI must be wide"


def test_sample_size_verdict_bands():
    assert sample_size_verdict(3)   == "INSUFFICIENT_DATA"
    assert sample_size_verdict(10)  == "DIRECTIONAL_ONLY"
    assert sample_size_verdict(50)  == "STATISTICALLY_MEANINGFUL"
    assert sample_size_verdict(500) == "INSTITUTIONAL_GRADE"


# ── helpers ──────────────────────────────────────────────────────

def test_bucket_confidence_bands():
    assert _bucket_confidence(None) == "unknown"
    assert _bucket_confidence(0.45) == "≤0.50"
    assert _bucket_confidence(0.65) == "0.60-0.70"
    assert _bucket_confidence(0.95) == "0.90-1.00"


def test_consecutive_streaks_basic():
    s = pd.Series([True, True, False, False, False, True, False, False])
    r = _compute_consecutive_streaks(s)
    assert r["max_consecutive_wins"] == 2
    assert r["max_consecutive_losses"] == 3


def test_consecutive_streaks_empty():
    r = _compute_consecutive_streaks(pd.Series([], dtype=bool))
    assert r == {"max_consecutive_wins": 0, "max_consecutive_losses": 0}


# ── metrics on a slice ───────────────────────────────────────────

def test_metrics_on_empty_slice():
    m = _compute_metrics_on_slice(pd.DataFrame(), market="india", runner="runner1")
    assert m.n_closed_positions == 0
    assert m.significance.verdict == "INSUFFICIENT_DATA"


def test_metrics_computes_win_rate_and_ci():
    df = pd.DataFrame([
        {"return_pct": 3.0, "action": "BUY", "rec_asof": "2026-06-01", "sector": "Tech"},
        {"return_pct": -2.0, "action": "BUY", "rec_asof": "2026-06-02", "sector": "Tech"},
        {"return_pct": 5.0, "action": "STRONG_BUY", "rec_asof": "2026-06-03", "sector": "Pharma"},
        {"return_pct": 1.5, "action": "STRONG_BUY", "rec_asof": "2026-06-04", "sector": "Pharma"},
        {"return_pct": -1.0, "action": "BUY", "rec_asof": "2026-06-05", "sector": "Tech"},
    ])
    m = _compute_metrics_on_slice(df, market="india", runner="runner1")
    assert m.n_closed_positions == 5
    assert m.win_rate_pct == 60.0
    assert m.win_rate_ci_95 is not None and len(m.win_rate_ci_95) == 2
    assert m.profit_factor is not None and m.profit_factor > 1.0
    assert m.expectancy_per_trade_pct is not None
    assert m.reward_risk_ratio is not None
    assert m.max_consecutive_losses is not None


def test_metrics_max_drawdown_ordering():
    """Two identical-returns sets must produce identical drawdowns when ordering matches."""
    rows = [{"return_pct": r, "rec_asof": f"2026-06-{i+1:02d}"} for i, r in enumerate([5, -3, -4, 2, -1])]
    df = pd.DataFrame(rows)
    m = _compute_metrics_on_slice(df, market="india", runner="test")
    # cumulative product of [1.05, 0.97, 0.96, 1.02, 0.99]
    # from peak 1.05 down through 1.05*0.97*0.96 = 0.978 → dd ≈ -6.9%
    assert m.max_drawdown_pct is not None
    assert m.max_drawdown_pct < -5.0


def test_strong_buy_vs_buy_directional_when_small():
    df = pd.DataFrame([
        {"return_pct": 5.0, "action": "STRONG_BUY"},
        {"return_pct": 3.0, "action": "STRONG_BUY"},
        {"return_pct": -1.0, "action": "BUY"},
        {"return_pct": 2.0, "action": "BUY"},
    ])
    r = _strong_buy_vs_buy(df, market="india", runner="runner1")
    assert r["available"] is True
    assert r["verdict"] == "DIRECTIONAL_ONLY", "small sample must be directional-only"
    assert r["n_STRONG_BUY"] == 2
    assert r["n_BUY"] == 2


def test_strong_buy_vs_buy_verdict_with_large_samples():
    """When both groups have >= 30 trades, verdict is one of the outcome enums, not DIRECTIONAL_ONLY."""
    rows = []
    for _ in range(30):
        rows.append({"return_pct": 3.0, "action": "STRONG_BUY"})
        rows.append({"return_pct": -1.0, "action": "BUY"})
    df = pd.DataFrame(rows)
    r = _strong_buy_vs_buy(df, market="india", runner="runner1")
    assert r["verdict"] in (
        "STRONG_BUY_OUTPERFORMS_BUY",
        "STRONG_BUY_UNDERPERFORMS_BUY",
        "NO_MEANINGFUL_DIFFERENCE",
    )
    assert r["verdict"] == "STRONG_BUY_OUTPERFORMS_BUY"


# ── build_benchmark_report end-to-end ────────────────────────────

def _make_tmp_corpus(runner: str = "runner1") -> Path:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "reports").mkdir()
    rows = [
        {"market": "india", "ticker": "T1", "return_pct": 3.0, "action": "STRONG_BUY",
         "rec_asof": "2026-06-15", "horizon_days": 20, "sector": "Pharma",
         "confidence": 0.78, "regime_at_entry": "bull"},
        {"market": "india", "ticker": "T2", "return_pct": -2.0, "action": "BUY",
         "rec_asof": "2026-06-16", "horizon_days": 20, "sector": "Financials",
         "confidence": 0.62, "regime_at_entry": "bear"},
        {"market": "india", "ticker": "T3", "return_pct": 5.0, "action": "STRONG_BUY",
         "rec_asof": "2026-06-17", "horizon_days": 20, "sector": "Pharma",
         "confidence": 0.85, "regime_at_entry": "bull"},
    ]
    name = "learning_corpus_runner1.parquet" if runner == "runner1" else "learning_corpus.parquet"
    pd.DataFrame(rows).to_parquet(tmp / "reports" / name, index=False)
    return tmp


def test_build_report_no_corpus_returns_empty_with_caveat():
    tmp = Path(tempfile.mkdtemp())
    r = build_benchmark_report(repo_root=tmp, market="india", runner="runner1")
    assert r.overall.n_closed_positions == 0
    assert "no closed positions" in r.caveats[0].lower()
    shutil.rmtree(tmp)


def test_build_report_writes_json_with_caveats_for_small_sample():
    tmp = _make_tmp_corpus("runner1")
    r = build_benchmark_report(repo_root=tmp, market="india", runner="runner1")
    assert r.overall.n_closed_positions == 3
    # Should carry INSUFFICIENT_DATA caveat (n=3 < 5 min directional)
    assert r.overall.significance.verdict == "INSUFFICIENT_DATA"
    # JSON file must exist
    out = tmp / "reports" / "benchmark_runner1_india.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["engine"] == "aegis.benchmark.v1"
    assert data["overall"]["significance"]["verdict"] == "INSUFFICIENT_DATA"
    shutil.rmtree(tmp)


def test_build_report_segments_by_action_sector_confidence_regime():
    tmp = _make_tmp_corpus("runner1")
    r = build_benchmark_report(repo_root=tmp, market="india", runner="runner1")
    assert "STRONG_BUY" in r.by_action
    assert "Pharma"     in r.by_sector
    assert "bull"       in r.by_regime
    # Confidence buckets present
    assert any(k.startswith("0.") or k == "unknown" for k in r.by_confidence_bucket.keys())
    shutil.rmtree(tmp)


def test_comparison_refuses_verdict_below_threshold():
    """With small samples, comparison verdict must be CANNOT_COMPARE_INSUFFICIENT_DATA."""
    tmp = _make_tmp_corpus("runner1")
    _ = _make_tmp_corpus("runner2")   # separate tmp — doesn't matter, we pass one repo
    c = build_comparison(repo_root=tmp, market="india")
    assert c["verdict"] == "CANNOT_COMPARE_INSUFFICIENT_DATA"
    assert "need >= 30" in c["reason"]
    shutil.rmtree(tmp)


TESTS = [
    ("wilson CI is WIDE for small n", test_wilson_ci_wide_for_small_n),
    ("wilson CI tightens as n grows", test_wilson_ci_tighter_for_large_n),
    ("wilson CI handles n=0 safely", test_wilson_ci_handles_zero_n),
    ("mean CI is wide for small n", test_mean_ci_wide_for_small_n),
    ("sample-size verdict bands (INSUFF/DIR/STAT/INST)", test_sample_size_verdict_bands),
    ("confidence buckets partition 0.5-1.0 correctly", test_bucket_confidence_bands),
    ("consecutive streaks: basic W/L walk", test_consecutive_streaks_basic),
    ("consecutive streaks: empty series safe", test_consecutive_streaks_empty),
    ("metrics on empty slice → INSUFFICIENT_DATA", test_metrics_on_empty_slice),
    ("metrics compute win rate + CI + expectancy + R/R", test_metrics_computes_win_rate_and_ci),
    ("metrics compute max drawdown honoring order", test_metrics_max_drawdown_ordering),
    ("STRONG_BUY vs BUY = DIRECTIONAL_ONLY when small", test_strong_buy_vs_buy_directional_when_small),
    ("STRONG_BUY vs BUY produces outcome verdict when large", test_strong_buy_vs_buy_verdict_with_large_samples),
    ("build_report: no corpus → empty + caveat", test_build_report_no_corpus_returns_empty_with_caveat),
    ("build_report: writes JSON + INSUFFICIENT_DATA caveat", test_build_report_writes_json_with_caveats_for_small_sample),
    ("build_report: segments by action/sector/conf-bucket/regime", test_build_report_segments_by_action_sector_confidence_regime),
    ("comparison refuses verdict when either runner < 30 closed", test_comparison_refuses_verdict_below_threshold),
]


def main():
    print("=" * 70)
    print("  SPRINT 7.8 · Recommendation Benchmark Report · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
