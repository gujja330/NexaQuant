"""
Sprint 7.7 · Runner 1 (legacy audit-trail) ingest + walk-forward regression tests.
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

from backend.replay.runner1_ingest import (
    ingest_legacy_ledger, compute_runner1_outcomes,
    _safe_float, _norm_action, ACTION_MAP,
)
from backend.replay.walk_forward import run_walk_forward_runner1


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


# ── helpers ─────────────────────────────────────────────────────

def test_safe_float_handles_garbage():
    assert _safe_float(None) is None
    assert _safe_float("not a number") is None
    assert _safe_float("Insufficient evidence (<5 cases)") is None
    assert _safe_float(3.14) == 3.14
    assert _safe_float("2.5") == 2.5


def test_norm_action_covers_legacy_labels():
    """Legacy uses 'STRONG BUY' with a space; normalisation must produce 'STRONG_BUY'."""
    assert _norm_action("STRONG BUY") == "STRONG_BUY"
    assert _norm_action("BUY") == "BUY"
    assert _norm_action("ACCUMULATE") == "BUY", "ACCUMULATE maps to BUY (smaller position)"
    assert _norm_action("WATCH") == "HOLD"
    assert _norm_action(None) == "HOLD"


# ── ingest end-to-end (in tmp dir) ──────────────────────────────

def _make_tmp_repo_with_ledger():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data").mkdir()
    (tmp / "reports").mkdir()
    (tmp / "data" / "raw" / "india").mkdir(parents=True)
    return tmp


def test_ingest_no_source_returns_no_source():
    tmp = _make_tmp_repo_with_ledger()
    r = ingest_legacy_ledger(repo_root=tmp, market="india")
    assert r["status"] == "no-source"
    assert r["rows_written"] == 0
    shutil.rmtree(tmp)


def test_ingest_writes_grouped_by_date():
    tmp = _make_tmp_repo_with_ledger()
    df = pd.DataFrame([
        {"recommended_date": "2026-06-26", "symbol": "AAPL", "sector": "Tech",
         "action": "STRONG BUY", "score": 75, "horizon": "3M", "entry": 100.0,
         "target": 120.0, "review_date": "2026-07-16", "expiry_date": "2026-09-26",
         "confidence": 78, "weight": 9.0, "status": "LIVE"},
        {"recommended_date": "2026-06-26", "symbol": "MSFT", "sector": "Tech",
         "action": "BUY", "score": 60, "horizon": "3M", "entry": 300.0,
         "target": 340.0, "review_date": "2026-07-16", "expiry_date": "2026-09-26",
         "confidence": 65, "weight": 5.0, "status": "LIVE"},
        {"recommended_date": "2026-07-03", "symbol": "AAPL", "sector": "Tech",
         "action": "STRONG BUY", "score": 80, "horizon": "3M", "entry": 105.0,
         "target": 125.0, "review_date": "2026-07-23", "expiry_date": "2026-10-03",
         "confidence": 82, "weight": 9.5, "status": "LIVE"},
    ])
    df.to_csv(tmp / "data" / "aegis_recommendation_db.csv", index=False)

    r = ingest_legacy_ledger(repo_root=tmp, market="india")
    assert r["status"] == "ingested"
    assert r["rows_written"] == 2, f"expected 2 grouped-by-date rows, got {r['rows_written']}"
    assert r["unique_dates"] == 2
    assert r["total_recommendations"] == 3
    assert r["action_totals"]["STRONG_BUY"] == 2
    assert r["action_totals"]["BUY"] == 1

    # Verify parquet structure
    hist = pd.read_parquet(tmp / "reports" / "recommendation_history_runner1.parquet")
    assert len(hist) == 2
    assert set(hist["asof"]) == {"2026-06-26", "2026-07-03"}
    shutil.rmtree(tmp)


def test_ingest_handles_bad_float_gracefully():
    """Legacy 'target' column sometimes contains 'Insufficient evidence' — must not crash."""
    tmp = _make_tmp_repo_with_ledger()
    df = pd.DataFrame([{
        "recommended_date": "2026-06-26", "symbol": "AAPL", "sector": "Tech",
        "action": "STRONG BUY", "score": 75, "horizon": "3M", "entry": 100.0,
        "target": "Insufficient evidence (<5 cases)",   # <-- the real world
        "review_date": "2026-07-16", "expiry_date": "2026-09-26",
        "confidence": 78, "weight": 9.0, "status": "LIVE",
    }])
    df.to_csv(tmp / "data" / "aegis_recommendation_db.csv", index=False)
    r = ingest_legacy_ledger(repo_root=tmp, market="india")
    assert r["status"] == "ingested"
    hist = pd.read_parquet(tmp / "reports" / "recommendation_history_runner1.parquet")
    recs = json.loads(hist.iloc[0]["recommendations"])
    assert recs[0]["target"] is None                    # bad float coerced to None
    assert recs[0]["ticker"] == "AAPL"
    assert recs[0]["action"] == "STRONG_BUY"
    shutil.rmtree(tmp)


def test_ingest_dedupes_on_replay():
    """Re-ingesting the same source must not double the rows."""
    tmp = _make_tmp_repo_with_ledger()
    df = pd.DataFrame([{
        "recommended_date": "2026-06-26", "symbol": "AAPL", "sector": "Tech",
        "action": "STRONG BUY", "score": 75, "horizon": "3M", "entry": 100.0,
        "target": 120.0, "review_date": "2026-07-16", "expiry_date": "2026-09-26",
        "confidence": 78, "weight": 9.0, "status": "LIVE",
    }])
    df.to_csv(tmp / "data" / "aegis_recommendation_db.csv", index=False)
    ingest_legacy_ledger(repo_root=tmp, market="india")
    ingest_legacy_ledger(repo_root=tmp, market="india")   # re-run
    hist = pd.read_parquet(tmp / "reports" / "recommendation_history_runner1.parquet")
    assert len(hist) == 1, f"dedupe failed: got {len(hist)} rows"
    shutil.rmtree(tmp)


# ── outcomes computation ────────────────────────────────────────

def test_compute_outcomes_no_history_returns_no_history():
    tmp = _make_tmp_repo_with_ledger()
    r = compute_runner1_outcomes(repo_root=tmp, market="india")
    assert r["status"] == "no-history"
    assert r["n_outcomes"] == 0
    shutil.rmtree(tmp)


def test_compute_outcomes_uses_nearest_trading_day():
    """Calendar-day close_asof may not exist in price parquet; must find nearest >= that date."""
    tmp = _make_tmp_repo_with_ledger()
    # Build a synthetic price parquet for one ticker
    dates = pd.date_range("2026-06-01", "2026-07-31", freq="B")   # business days only
    prices = pd.DataFrame({"close": range(100, 100 + len(dates))}, index=dates)
    prices.to_parquet(tmp / "data" / "raw" / "india" / "AAPL_D1.parquet")

    # Build a rec history row
    hist_row = {
        "engine": "adaptive_rec_v2.legacy", "version": "runner1", "market": "india",
        "run_utc": "2026-06-26T00:00:00+00:00", "asof": "2026-06-26",
        "currency": "INR", "n_tickers": 1,
        "distribution": json.dumps({"STRONG_BUY": 1, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG_SELL": 0}),
        "recommendations": json.dumps([{
            "ticker": "AAPL", "action": "STRONG_BUY", "score": 75,
            "confidence": 0.78, "regime_adjusted_confidence": 0.78,
            "sector": "Tech",
        }]),
        "notes": "", "history_schema_version": "1.0.0",
        "appended_utc": "2026-06-26T00:00:00+00:00",
    }
    pd.DataFrame([hist_row]).to_parquet(
        tmp / "reports" / "recommendation_history_runner1.parquet", index=False)

    r = compute_runner1_outcomes(
        repo_root=tmp, market="india", horizon_days=20,
        wall_clock=date(2026, 7, 31),
    )
    assert r["status"] == "computed"
    assert r["n_outcomes"] == 1
    # Verify corpus contents
    corp = pd.read_parquet(tmp / "reports" / "learning_corpus_runner1.parquet")
    assert len(corp) == 1
    assert corp.iloc[0]["ticker"] == "AAPL"
    assert corp.iloc[0]["return_pct"] > 0    # closes higher than entry
    shutil.rmtree(tmp)


def test_compute_outcomes_skips_open_horizons():
    tmp = _make_tmp_repo_with_ledger()
    dates = pd.date_range("2026-06-01", "2026-07-31", freq="B")
    pd.DataFrame({"close": range(100, 100 + len(dates))}, index=dates).to_parquet(
        tmp / "data" / "raw" / "india" / "AAPL_D1.parquet")
    hist_row = {
        "engine": "adaptive_rec_v2.legacy", "version": "runner1", "market": "india",
        "run_utc": "2026-07-20T00:00:00+00:00",
        "asof": "2026-07-20",     # rec at 07-20, horizon 20d → close 08-09 (future)
        "currency": "INR", "n_tickers": 1,
        "distribution": json.dumps({"STRONG_BUY": 1, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG_SELL": 0}),
        "recommendations": json.dumps([{"ticker": "AAPL", "action": "STRONG_BUY"}]),
        "notes": "", "history_schema_version": "1.0.0",
        "appended_utc": "2026-07-20T00:00:00+00:00",
    }
    pd.DataFrame([hist_row]).to_parquet(
        tmp / "reports" / "recommendation_history_runner1.parquet", index=False)

    r = compute_runner1_outcomes(
        repo_root=tmp, market="india", horizon_days=20,
        wall_clock=date(2026, 7, 25),      # only 5 days after entry
    )
    assert r["n_outcomes"] == 0
    assert r["n_open_positions"] == 1
    shutil.rmtree(tmp)


# ── walk-forward on Runner 1 ────────────────────────────────────

def test_walk_forward_runner1_no_data_returns_no_data():
    tmp = _make_tmp_repo_with_ledger()
    r = run_walk_forward_runner1(
        repo_root=tmp, market="india",
        date_from=date(2026, 6, 1), date_to=date(2026, 7, 31),
    )
    assert r["verdict"] == "NO_DATA"


def test_walk_forward_runner1_pass_with_closed_positions():
    tmp = _make_tmp_repo_with_ledger()
    # rec history
    hist_row = {
        "engine": "adaptive_rec_v2.legacy", "version": "runner1", "market": "india",
        "run_utc": "2026-06-26T00:00:00+00:00", "asof": "2026-06-26",
        "currency": "INR", "n_tickers": 5, "distribution": "{}",
        "recommendations": "[]", "notes": "",
        "history_schema_version": "1.0.0",
        "appended_utc": "2026-06-26T00:00:00+00:00",
    }
    pd.DataFrame([hist_row]).to_parquet(
        tmp / "reports" / "recommendation_history_runner1.parquet", index=False)
    # 5 closed positions, mixed outcomes
    corpus = pd.DataFrame([
        {"market": "india", "ticker": f"T{i}", "asof": "2026-06-26",
         "rec_asof": "2026-06-26", "close_asof": "2026-07-16",
         "action": "BUY", "return_pct": v, "is_winner": v > 0,
         "horizon_days": 20, "sector": "Tech", "runner": "runner1"}
        for i, v in enumerate([3.0, -2.0, 5.0, 1.5, -1.0])
    ])
    corpus.to_parquet(tmp / "reports" / "learning_corpus_runner1.parquet", index=False)

    r = run_walk_forward_runner1(
        repo_root=tmp, market="india",
        date_from=date(2026, 6, 1), date_to=date(2026, 7, 31),
    )
    assert r["summary"]["verdict"] == "PASS"
    m = r["metrics"]
    assert m["n_closed_positions"] == 5
    assert m["win_rate_pct"] == 60.0
    assert m["profit_factor"] > 1.0
    shutil.rmtree(tmp)


TESTS = [
    ("_safe_float handles garbage strings", test_safe_float_handles_garbage),
    ("_norm_action maps 'STRONG BUY' → 'STRONG_BUY', 'ACCUMULATE' → 'BUY'", test_norm_action_covers_legacy_labels),
    ("ingest returns no-source when CSV missing", test_ingest_no_source_returns_no_source),
    ("ingest groups by date, one history row per day", test_ingest_writes_grouped_by_date),
    ("ingest coerces bad float ('Insufficient evidence...') to None", test_ingest_handles_bad_float_gracefully),
    ("ingest dedupes on replay (same (market,asof) never duplicates)", test_ingest_dedupes_on_replay),
    ("outcomes: no history → no-history status", test_compute_outcomes_no_history_returns_no_history),
    ("outcomes: uses nearest trading day for close price", test_compute_outcomes_uses_nearest_trading_day),
    ("outcomes: skips open horizons (wall_clock < close_asof)", test_compute_outcomes_skips_open_horizons),
    ("walk-forward Runner 1: NO_DATA when no ingest", test_walk_forward_runner1_no_data_returns_no_data),
    ("walk-forward Runner 1: PASS verdict with ≥5 closed positions", test_walk_forward_runner1_pass_with_closed_positions),
]


def main():
    print("=" * 70)
    print("  SPRINT 7.7 · Runner 1 (legacy audit-trail) · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
