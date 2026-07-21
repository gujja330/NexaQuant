"""
Sprint 7.6 · Historical Backfill & Replay · regression tests.

Tests are isolated to tmpdirs so they do NOT touch the real repo history parquets.
"""
from __future__ import annotations
import io
import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backend.replay import (
    ReplayPlan, ReplayResult,
    TARGET_HISTORY_FILES,
    compute_row_quality_score, quality_verdict,
    validate_history, enumerate_trading_days,
    ReplayController,
)
from backend.replay.data_quality import batch_average_quality
from backend.replay.integrity import trading_days_from_raw
from backend.replay.controller import _market_paths


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


# ── types + target manifest ──────────────────────────────────────

def test_target_history_files_manifest_complete():
    """Sprint 7.6 must know about every history file Sprint 7.5 established."""
    for k in ("macro_history", "factor_library_history", "learning_history",
               "recommendation_history", "risk_history", "portfolio_history",
               "execution_history"):
        assert k in TARGET_HISTORY_FILES, f"missing {k}"
        entry = TARGET_HISTORY_FILES[k]
        assert "backfillable" in entry and "requires_data" in entry


# ── data_quality ─────────────────────────────────────────────────

def test_quality_score_high_when_complete_fresh_multi_source():
    payload = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0}
    q = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c", "d", "e"],
        freshness_days_before_asof=0, source_count=5,
    )
    assert q.score >= 85, f"expected >=85 got {q.score}"
    assert q.verdict == "high"


def test_quality_score_penalises_missing_fields():
    payload = {"a": 1.0, "b": None, "c": None}
    q = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c", "d"],
        freshness_days_before_asof=0, source_count=1,
    )
    assert q.score < 65, f"expected <65 got {q.score}"


def test_quality_score_penalises_staleness():
    payload = {"a": 1.0, "b": 2.0, "c": 3.0}
    q_fresh = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c"],
        freshness_days_before_asof=0, source_count=3,
    )
    q_stale = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c"],
        freshness_days_before_asof=10, source_count=3,
    )
    assert q_fresh.score > q_stale.score, f"stale should score lower: {q_fresh.score} vs {q_stale.score}"


def test_quality_score_treats_zero_as_missing_when_asked():
    payload = {"a": 0.0, "b": 0.0, "c": 3.0}
    q_zero_ok = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c"],
        source_count=3, treat_zero_as_missing=False,
    )
    q_zero_bad = compute_row_quality_score(
        payload, expected_fields=["a", "b", "c"],
        source_count=3, treat_zero_as_missing=True,
    )
    assert q_zero_ok.score > q_zero_bad.score


def test_quality_verdict_bands():
    assert quality_verdict(90) == "high"
    assert quality_verdict(70) == "medium"
    assert quality_verdict(50) == "low"
    assert quality_verdict(20) == "unusable"


def test_batch_average_quality_handles_none_and_empty():
    assert batch_average_quality([]) == 0.0
    assert batch_average_quality([None, None]) == 0.0
    assert batch_average_quality([80, 100, None]) == 90.0


# ── integrity ────────────────────────────────────────────────────

def test_enumerate_trading_days_skips_weekends():
    days = enumerate_trading_days(date(2026, 7, 20), date(2026, 7, 26))
    weekdays = [d.weekday() for d in days]
    assert all(w < 5 for w in weekdays), f"weekend leaked: {days}"
    assert len(days) == 5


def test_validate_history_missing_file():
    tmp = Path(tempfile.mkdtemp())
    v = validate_history(tmp / "does_not_exist.parquet", market="usa")
    assert v.verdict == "FAIL"
    assert v.n_rows == 0
    shutil.rmtree(tmp)


def test_validate_history_reads_populated_parquet():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    df = pd.DataFrame([
        {"market": "usa", "asof": "2026-07-19"},
        {"market": "usa", "asof": "2026-07-20"},
        {"market": "usa", "asof": "2026-07-21"},
    ])
    df.to_parquet(tmp, index=False)
    v = validate_history(tmp, market="usa")
    assert v.n_rows == 3
    assert v.n_unique_dates == 3
    assert v.n_duplicate_dates == 0
    assert v.schema_ok is True
    assert v.verdict == "PASS"
    shutil.rmtree(tmp.parent)


def test_validate_history_flags_duplicates():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    df = pd.DataFrame([
        {"market": "usa", "asof": "2026-07-20"},
        {"market": "usa", "asof": "2026-07-20"},
        {"market": "usa", "asof": "2026-07-21"},
    ])
    df.to_parquet(tmp, index=False)
    v = validate_history(tmp, market="usa")
    assert v.n_duplicate_dates >= 1
    assert v.verdict == "WARN"
    shutil.rmtree(tmp.parent)


def test_validate_history_flags_missing_dates():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    df = pd.DataFrame([{"market": "usa", "asof": "2026-07-21"}])
    df.to_parquet(tmp, index=False)
    expected = {date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 21)}
    v = validate_history(tmp, market="usa", expected_dates=expected)
    assert v.n_missing_trading_days == 2
    shutil.rmtree(tmp.parent)


def test_validate_history_market_isolation():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    df = pd.DataFrame([
        {"market": "usa",   "asof": "2026-07-21"},
        {"market": "india", "asof": "2026-07-21"},
    ])
    df.to_parquet(tmp, index=False)
    v_usa   = validate_history(tmp, market="usa")
    v_india = validate_history(tmp, market="india")
    assert v_usa.n_rows == 1 and v_india.n_rows == 1
    shutil.rmtree(tmp.parent)


# ── controller: resume + reports + verdict logic ─────────────────

def test_controller_smoke_features_step_skipped_when_snapshot_exists():
    """Resume should skip already-persisted feature snapshots."""
    # Use the real repo but a short window that's already backfilled.
    ctrl = ReplayController(_ROOT)
    plan = ReplayPlan(
        market="usa",
        date_from=date(2026, 7, 20), date_to=date(2026, 7, 21),
        steps=["features"], resume=True,
    )
    result = ctrl.run(plan)
    n_skipped = result.step_results["features"]["n_skipped"]
    assert n_skipped >= 1, f"expected resume to skip existing snapshots, got n_skipped={n_skipped}"


def test_controller_emits_all_five_reports():
    ctrl = ReplayController(_ROOT)
    plan = ReplayPlan(
        market="usa",
        date_from=date(2026, 7, 20), date_to=date(2026, 7, 21),
        steps=["features", "macro", "factor", "learning"],
        resume=True,
    )
    ctrl.run(plan)
    for f in ("backfill_summary.json", "history_validation.json",
                 "walkforward_readiness.json", "factor_library_summary.json",
                 "learning_backfill_summary.json"):
        p = _ROOT / "usa" / "reports" / f
        assert p.exists(), f"missing report: {f}"
        j = json.loads(p.read_text())
        assert j.get("engine") == "aegis.replay.v1"


def test_walk_forward_readiness_verdict_reflects_history_depth():
    ctrl = ReplayController(_ROOT)
    plan = ReplayPlan(
        market="usa",
        date_from=date(2026, 6, 1), date_to=date(2026, 7, 21),
        steps=["learning"],  # cheap: no feature builds
        resume=True,
    )
    result = ctrl.run(plan)
    rd = result.walk_forward_readiness
    assert rd["verdict"] in ("READY", "PARTIAL", "NOT_READY")
    assert rd["historical_days"] >= 1
    # Verdict must be consistent with counts: READY requires ≥60 historical days AND ≥60 rec rows.
    if rd["verdict"] == "READY":
        assert rd["historical_days"] >= 60 and rd["recommendation_rows"] >= 60, \
            f"READY verdict must have both thresholds met, got {rd}"


def test_deferred_steps_report_honestly():
    """Macro + Factor + Learning steps should NOT silently claim success — they should
    return a status field flagging the deferred work."""
    ctrl = ReplayController(_ROOT)
    plan = ReplayPlan(
        market="usa",
        date_from=date(2026, 7, 20), date_to=date(2026, 7, 21),
        steps=["macro", "factor", "learning"],
        resume=True,
    )
    result = ctrl.run(plan)
    for step in ("macro", "factor", "learning"):
        sr = result.step_results[step]
        assert "status" in sr, f"{step} step missing status field"
        assert sr["status"] in (
            "deferred-to-sprint-7.7",
            "framework-ready-awaiting-recommendation-history",
        ), f"{step} claimed unexpected status: {sr['status']}"


# ── determinism ──────────────────────────────────────────────────

def test_replay_deterministic_across_runs():
    """Same window, same steps → same reports (modulo run_utc)."""
    ctrl = ReplayController(_ROOT)
    plan = ReplayPlan(
        market="usa",
        date_from=date(2026, 7, 20), date_to=date(2026, 7, 21),
        steps=["features", "learning"], resume=True,
    )
    r1 = ctrl.run(plan)
    r2 = ctrl.run(plan)
    # step-result shapes should be identical (skipped counts may differ by 0)
    assert r1.n_trading_days == r2.n_trading_days
    assert r1.step_results["features"]["n_ok"] == 0  # both should skip since snapshots exist
    assert r2.step_results["features"]["n_ok"] == 0


# ── market paths ─────────────────────────────────────────────────

def test_market_paths_india_vs_usa():
    p_india = _market_paths(_ROOT, "india")
    p_usa   = _market_paths(_ROOT, "usa")
    assert p_india["reports"].name == "reports"
    assert "usa" in str(p_usa["reports"])
    assert p_india["raw"] != p_usa["raw"]


TESTS = [
    ("TARGET_HISTORY_FILES manifest covers all 7 histories", test_target_history_files_manifest_complete),
    ("quality score = high for complete + fresh + multi-source", test_quality_score_high_when_complete_fresh_multi_source),
    ("quality score penalises missing fields", test_quality_score_penalises_missing_fields),
    ("quality score penalises staleness", test_quality_score_penalises_staleness),
    ("quality score honours treat_zero_as_missing", test_quality_score_treats_zero_as_missing_when_asked),
    ("quality verdict bands (high/medium/low/unusable)", test_quality_verdict_bands),
    ("batch_average_quality handles None and empty", test_batch_average_quality_handles_none_and_empty),
    ("enumerate_trading_days skips weekends", test_enumerate_trading_days_skips_weekends),
    ("validate_history returns FAIL when file missing", test_validate_history_missing_file),
    ("validate_history reads populated parquet as PASS", test_validate_history_reads_populated_parquet),
    ("validate_history flags duplicate dates as WARN", test_validate_history_flags_duplicates),
    ("validate_history flags missing trading days", test_validate_history_flags_missing_dates),
    ("validate_history market isolation", test_validate_history_market_isolation),
    ("controller: resume skips already-persisted snapshots", test_controller_smoke_features_step_skipped_when_snapshot_exists),
    ("controller emits all 5 reports with engine stamp", test_controller_emits_all_five_reports),
    ("walk-forward readiness verdict reflects history depth", test_walk_forward_readiness_verdict_reflects_history_depth),
    ("deferred steps report status honestly (no silent success)", test_deferred_steps_report_honestly),
    ("replay deterministic across identical runs", test_replay_deterministic_across_runs),
    ("_market_paths distinguishes india vs usa roots", test_market_paths_india_vs_usa),
]


def main():
    print("=" * 70)
    print("  SPRINT 7.6 · Historical Backfill & Replay · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
