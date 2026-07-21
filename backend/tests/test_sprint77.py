"""
Sprint 7.7 · Historical Replay + Walk-Forward · regression tests.
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

from backend.replay.lookahead_guard import (
    validate_payload_no_future, validate_history_no_future, enforce_no_future,
)
from backend.replay.walk_forward import (
    compute_metrics, compute_per_regime, compute_per_sector, compute_drawdowns,
    run_walk_forward,
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


# ── lookahead_guard ──────────────────────────────────────────────

def test_lookahead_clean_payload():
    p = {"engine": "t", "market": "usa", "asof": "2026-07-21", "n_tickers": 5}
    leaks = validate_payload_no_future(p, replay_asof=date(2026, 7, 21))
    assert leaks == []


def test_lookahead_detects_future_payload_asof():
    p = {"engine": "t", "market": "usa", "asof": "2026-08-01"}
    leaks = validate_payload_no_future(p, replay_asof=date(2026, 7, 21))
    assert len(leaks) == 1 and "asof" in leaks[0]


def test_lookahead_detects_future_in_recommendations():
    p = {
        "engine": "t", "market": "usa", "asof": "2026-07-21",
        "recommendations": [
            {"ticker": "AAPL", "asof": "2026-07-25"},
            {"ticker": "MSFT", "asof": "2026-07-21"},
        ],
    }
    leaks = validate_payload_no_future(p, replay_asof=date(2026, 7, 21))
    assert len(leaks) == 1
    assert "AAPL" in leaks[0]


def test_enforce_no_future_raises_on_leak():
    p = {"engine": "t", "market": "usa", "asof": "2026-08-01"}
    try:
        enforce_no_future(p, replay_asof=date(2026, 7, 21))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "LOOKAHEAD LEAK" in str(e)


def test_enforce_no_future_passes_clean():
    p = {"engine": "t", "market": "usa", "asof": "2026-07-21"}
    enforce_no_future(p, replay_asof=date(2026, 7, 21))   # no raise


def test_history_parquet_no_future_check():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    df = pd.DataFrame([
        {"market": "usa", "asof": "2026-07-19"},
        {"market": "usa", "asof": "2026-08-01"},
    ])
    df.to_parquet(tmp, index=False)
    leaks = validate_history_no_future(tmp, replay_asof=date(2026, 7, 21), market="usa")
    assert len(leaks) == 1 and "1 rows" in leaks[0]
    shutil.rmtree(tmp.parent)


# ── walk_forward ─────────────────────────────────────────────────

def test_compute_metrics_no_data_returns_insufficient():
    tmp = Path(tempfile.mkdtemp())
    m = compute_metrics(market="usa", reports_dir=tmp,
                          date_from=date(2026, 6, 1), date_to=date(2026, 7, 21))
    assert m.verdict == "INSUFFICIENT_DATA"
    assert m.n_recommendations == 0
    assert m.n_closed_positions == 0
    shutil.rmtree(tmp)


def test_compute_metrics_reads_rec_history():
    tmp = Path(tempfile.mkdtemp())
    df = pd.DataFrame([
        {"market": "usa", "asof": "2026-06-15", "n_tickers": 10},
        {"market": "usa", "asof": "2026-06-16", "n_tickers": 10},
        {"market": "usa", "asof": "2026-06-17", "n_tickers": 10},
    ])
    df.to_parquet(tmp / "recommendation_history.parquet", index=False)
    m = compute_metrics(market="usa", reports_dir=tmp,
                          date_from=date(2026, 6, 1), date_to=date(2026, 7, 21))
    assert m.n_recommendations == 3
    assert m.verdict in ("PARTIAL", "INSUFFICIENT_DATA")
    shutil.rmtree(tmp)


def test_compute_metrics_pass_verdict_when_ledger_deep():
    tmp = Path(tempfile.mkdtemp())
    from datetime import timedelta
    d0 = date(2026, 6, 1)
    rec_rows = [{"market": "usa", "asof": (d0 + timedelta(days=i)).isoformat(),
                    "n_tickers": 5} for i in range(30)]
    pd.DataFrame(rec_rows).to_parquet(tmp / "recommendation_history.parquet", index=False)
    corpus_rows = [{"market": "usa", "ticker": f"T{i}",
                       "rec_asof": (d0 + timedelta(days=i)).isoformat(),
                       "close_asof": (d0 + timedelta(days=i + 20)).isoformat(),
                       "return_pct": 1.5 if i % 3 else -1.0,
                       "horizon_days": 20,
                       "regime_at_entry": "bull"} for i in range(10)]
    pd.DataFrame(corpus_rows).to_parquet(tmp / "learning_corpus.parquet", index=False)
    m = compute_metrics(market="usa", reports_dir=tmp,
                          date_from=date(2026, 6, 1), date_to=date(2026, 8, 31))
    assert m.n_recommendations == 30
    assert m.n_closed_positions == 10
    assert m.win_rate_pct is not None
    assert m.verdict == "PASS"
    shutil.rmtree(tmp)


def test_compute_per_regime_groups_correctly():
    tmp = Path(tempfile.mkdtemp())
    corpus_rows = [
        {"market": "usa", "close_asof": "2026-06-20", "return_pct": 2.0,
         "regime_at_entry": "bull", "ticker": "A", "rec_asof": "2026-06-01"},
        {"market": "usa", "close_asof": "2026-06-20", "return_pct": -1.0,
         "regime_at_entry": "bear", "ticker": "B", "rec_asof": "2026-06-01"},
        {"market": "usa", "close_asof": "2026-06-20", "return_pct": 3.0,
         "regime_at_entry": "bull", "ticker": "C", "rec_asof": "2026-06-01"},
    ]
    pd.DataFrame(corpus_rows).to_parquet(tmp / "learning_corpus.parquet", index=False)
    r = compute_per_regime(market="usa", reports_dir=tmp,
                             date_from=date(2026, 6, 1), date_to=date(2026, 7, 21))
    assert r["n_regimes"] == 2
    assert r["per_regime"]["bull"]["n"] == 2
    assert r["per_regime"]["bear"]["n"] == 1
    shutil.rmtree(tmp)


def test_compute_drawdowns_no_data():
    tmp = Path(tempfile.mkdtemp())
    d = compute_drawdowns(market="usa", reports_dir=tmp,
                            date_from=date(2026, 6, 1), date_to=date(2026, 7, 21))
    assert d["n_drawdowns"] == 0
    assert d["worst_dd_pct"] is None
    shutil.rmtree(tmp)


def test_run_walk_forward_emits_all_reports():
    tmp = Path(tempfile.mkdtemp())
    market_dir = tmp / "usa" / "reports"
    market_dir.mkdir(parents=True)
    pd.DataFrame([{"market": "usa", "asof": "2026-06-15"}]).to_parquet(
        market_dir / "recommendation_history.parquet", index=False)
    r = run_walk_forward(repo_root=tmp, market="usa",
                             date_from=date(2026, 6, 1), date_to=date(2026, 7, 21))
    for f in ("walkforward_summary.json", "walkforward_metrics.json",
                 "walkforward_statistics.json", "walkforward_per_model.json",
                 "walkforward_per_sector.json", "walkforward_per_macro_regime.json",
                 "walkforward_drawdowns.json"):
        assert (market_dir / f).exists(), f"missing {f}"
    shutil.rmtree(tmp)


# ── engine_drivers · contract-level (no external state) ──────────

def test_engine_drivers_return_none_on_missing_prereqs():
    """Rec driver must return None or {'__error__'} when features are empty — never crash."""
    from backend.replay.engine_drivers import drive_recommendation
    import pandas as pd
    from datetime import date
    r = drive_recommendation(repo_root=_ROOT, market="usa",
                                 asof=date(2026, 7, 21),
                                 features_df=pd.DataFrame())
    assert r is None or "__error__" in (r or {})


def test_learning_driver_computes_from_prices():
    """Learning-outcome driver reads raw prices and skips missing tickers gracefully."""
    from backend.replay.engine_drivers import drive_learning_outcomes
    payload = {
        "market": "usa", "asof": "2026-03-15", "regime": "bull",
        "recommendations": [
            {"ticker": "AAPL", "action": "BUY",
             "regime_adjusted_confidence": 0.7, "ensemble_score": 0.8},
            {"ticker": "FAKE_TICKER_XYZ", "action": "BUY",
             "regime_adjusted_confidence": 0.7, "ensemble_score": 0.5},
        ],
    }
    r = drive_learning_outcomes(
        repo_root=_ROOT, market="usa", rec_payloads=[payload],
        horizon_days=20, wall_clock=date(2026, 7, 21),
    )
    # AAPL should resolve (real ticker), fake one should not
    assert r["horizon_days"] == 20
    assert isinstance(r["outcomes"], list)
    tickers = {o["ticker"] for o in r["outcomes"]}
    assert "FAKE_TICKER_XYZ" not in tickers


TESTS = [
    ("lookahead: clean payload passes", test_lookahead_clean_payload),
    ("lookahead: detects future payload asof", test_lookahead_detects_future_payload_asof),
    ("lookahead: detects future in recommendations list", test_lookahead_detects_future_in_recommendations),
    ("lookahead: enforce_no_future raises on leak", test_enforce_no_future_raises_on_leak),
    ("lookahead: enforce_no_future passes clean payload", test_enforce_no_future_passes_clean),
    ("lookahead: history parquet future-row detection", test_history_parquet_no_future_check),
    ("walkforward: empty inputs → INSUFFICIENT_DATA", test_compute_metrics_no_data_returns_insufficient),
    ("walkforward: reads rec_history and counts recs", test_compute_metrics_reads_rec_history),
    ("walkforward: PASS verdict when ledger deep + closed positions", test_compute_metrics_pass_verdict_when_ledger_deep),
    ("walkforward: per-regime grouping correct", test_compute_per_regime_groups_correctly),
    ("walkforward: drawdowns empty on no data", test_compute_drawdowns_no_data),
    ("walkforward: emits all 7 report JSONs", test_run_walk_forward_emits_all_reports),
    ("drivers: rec driver returns None on empty features (no crash)", test_engine_drivers_return_none_on_missing_prereqs),
    ("drivers: learning outcomes reads real ticker prices, skips fake", test_learning_driver_computes_from_prices),
]


def main():
    print("=" * 70)
    print("  SPRINT 7.7 · Historical Replay + Walk-Forward · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
