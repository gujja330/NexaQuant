"""CEO cycle 4 tests · snapshot persistence + evolution deltas + ceo_summary.

Covers the foundation for every downstream Performance & Evolution feature:
 · Snapshot archive is idempotent per date · never rewrites history
 · load_previous_snapshot returns strictly-earlier newest snapshot
 · Evolution block detects action/rank/confidence/lifecycle changes
 · CEO summary picks correct top opportunity / top risk / recommendation
 · First-ever run degrades gracefully (no prior snapshot)
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.snapshot.store import (  # noqa: E402
    archive_snapshot, load_previous_snapshot, load_snapshot_for_date,
    load_snapshot_range, list_snapshot_dates, snapshot_to_ticker_map,
    SCHEMA_FINGERPRINT,
)
from backend.recommendation.investor_actionable import (  # noqa: E402
    enrich_batch, build_ceo_summary,
)


# ── Snapshot store ─────────────────────────────────────────
def _mk_payload(asof: str, tickers: list[str]) -> dict:
    return {
        "engine":          "aegis.recommendation.ssot.v1",
        "asof":            asof,
        "market":          "test",
        "recommendations": [
            {"ticker": t, "ensemble_score": 0.1, "rank": i + 1,
              "percentile_action": "HOLD", "calibrated_confidence": 0.02,
              "position_plan": {"suggested_allocation_pct": 3.0}}
            for i, t in enumerate(tickers)
        ],
    }


def test_archive_snapshot_creates_dated_file(tmp_path):
    p = archive_snapshot(_mk_payload("2026-07-20", ["AAA", "BBB"]),
                            tmp_path, "test", asof="2026-07-20")
    assert p.exists()
    assert p.name == "2026-07-20.json"
    body = json.loads(p.read_text(encoding="utf-8"))
    assert body["snapshot_engine"] == "aegis.recommendation.snapshot.v1"
    assert body["snapshot_schema_fingerprint"] == SCHEMA_FINGERPRINT


def test_archive_snapshot_is_idempotent_per_date(tmp_path):
    archive_snapshot(_mk_payload("2026-07-20", ["AAA"]), tmp_path, "test")
    archive_snapshot(_mk_payload("2026-07-20", ["AAA", "BBB"]), tmp_path, "test")
    body = load_snapshot_for_date(tmp_path, "test", "2026-07-20")
    assert len(body["recommendations"]) == 2   # second write wins for SAME date


def test_load_previous_snapshot_returns_newest_before(tmp_path):
    for d in ("2026-07-18", "2026-07-19", "2026-07-20"):
        archive_snapshot(_mk_payload(d, ["AAA"]), tmp_path, "test", asof=d)
    prev = load_previous_snapshot(tmp_path, "test", "2026-07-21")
    assert prev is not None
    assert prev["asof"] == "2026-07-20"
    # Strictly before request date
    prev2 = load_previous_snapshot(tmp_path, "test", "2026-07-20")
    assert prev2["asof"] == "2026-07-19"


def test_load_previous_snapshot_returns_none_when_empty(tmp_path):
    assert load_previous_snapshot(tmp_path, "test", "2026-07-20") is None


def test_list_snapshot_dates_sorted_oldest_first(tmp_path):
    for d in ("2026-07-20", "2026-07-18", "2026-07-19"):
        archive_snapshot(_mk_payload(d, ["AAA"]), tmp_path, "test", asof=d)
    dates = list_snapshot_dates(tmp_path, "test")
    assert dates == [date(2026, 7, 18), date(2026, 7, 19), date(2026, 7, 20)]


def test_load_snapshot_range_returns_window(tmp_path):
    for d in ("2026-07-10", "2026-07-15", "2026-07-20"):
        archive_snapshot(_mk_payload(d, ["AAA"]), tmp_path, "test", asof=d)
    got = load_snapshot_range(tmp_path, "test", lookback_days=7,
                                 end_asof="2026-07-20")
    # window 2026-07-13 to 2026-07-20 → snapshots 2026-07-15 and 2026-07-20
    assert [s["asof"] for s in got] == ["2026-07-15", "2026-07-20"]


def test_snapshot_ignores_non_date_files(tmp_path):
    hdir = tmp_path / "recommendations_history" / "test"
    hdir.mkdir(parents=True)
    (hdir / "readme.txt").write_text("noise")
    (hdir / "not-a-date.json").write_text('{"asof":"nope"}')
    archive_snapshot(_mk_payload("2026-07-20", ["A"]), tmp_path, "test",
                        asof="2026-07-20")
    assert list_snapshot_dates(tmp_path, "test") == [date(2026, 7, 20)]


# ── Evolution block ────────────────────────────────────────
def test_evolution_flags_fresh_rec_when_no_prior():
    recs = [{"ticker": "NEW", "percentile_action": "BUY",
              "ensemble_score": 0.1, "calibrated_confidence": 0.02,
              "rank": 1, "entry_zone": {"current": 100.0}}]
    enrich_batch(recs, previous_ticker_map={}, asof="2026-07-29")
    ev = recs[0]["evolution"]
    assert ev["is_new"] is True
    assert ev["days_recommended"] == 1
    assert ev["previous_asof"] is None
    assert "NEW recommendation" in ev["narrative"]


def test_evolution_detects_action_change():
    prev = {"ticker": "AAPL", "percentile_action": "HOLD",
             "ensemble_score": 0.05, "calibrated_confidence": 0.01,
             "rank": 5, "asof": "2026-07-28",
             "position_plan": {"suggested_allocation_pct": 0.0}}
    today = [{"ticker": "AAPL", "percentile_action": "STRONG_BUY",
                "ensemble_score": 0.30, "calibrated_confidence": 0.05,
                "rank": 1, "entry_zone": {"current": 200.0},
                "signal_quality": "STRONG"}]
    enrich_batch(today, previous_ticker_map={"AAPL": prev}, asof="2026-07-29")
    ev = today[0]["evolution"]
    assert ev["is_new"] is False
    assert ev["action_change"] == "HOLD → STRONG_BUY"
    assert ev["rank_change"] == -4    # rank IMPROVED from 5 → 1 = -4
    assert ev["score_change"] is not None
    assert ev["score_change"] > 0
    assert ev["allocation_change_pct"] is not None
    assert ev["allocation_change_pct"] > 0
    assert "action HOLD → STRONG_BUY" in ev["narrative"]


def test_evolution_detects_lifecycle_change():
    prev = {"ticker": "T", "lifecycle_state": {"current_state": "BUY"}}
    today = [{"ticker": "T", "percentile_action": "HOLD",
                "lifecycle_state": {"current_state": "HOLD"},
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, previous_ticker_map={"T": prev}, asof="2026-07-29",
                    lifecycle_records={"T": {"current_state": "HOLD", "events": []}})
    ev = today[0]["evolution"]
    assert ev["lifecycle_change"] == "BUY → HOLD"


def test_evolution_narrative_stable_when_nothing_changed():
    prev = {"ticker": "SAME", "percentile_action": "HOLD",
             "ensemble_score": 0.05, "calibrated_confidence": 0.01,
             "rank": 5, "position_plan": {"suggested_allocation_pct": 0.0}}
    today = [{"ticker": "SAME", "percentile_action": "HOLD",
                "ensemble_score": 0.05, "calibrated_confidence": 0.01,
                "rank": 5, "entry_zone": {"current": 100.0}}]
    enrich_batch(today, previous_ticker_map={"SAME": prev}, asof="2026-07-29")
    ev = today[0]["evolution"]
    assert ev["action_change"] is None
    assert ev["lifecycle_change"] is None
    assert "no material change" in ev["narrative"]


def test_evolution_days_recommended_uses_history_asof_map():
    prev = {"ticker": "OLD", "percentile_action": "HOLD"}
    today = [{"ticker": "OLD", "percentile_action": "HOLD"}]
    enrich_batch(today,
                    previous_ticker_map={"OLD": prev},
                    asof="2026-07-29",
                    history_asof_map={"OLD": "2026-07-20"})
    assert today[0]["evolution"]["days_recommended"] == 10   # 20-29 inclusive


# ── CEO Summary block ──────────────────────────────────────
def test_ceo_summary_picks_top_opportunity():
    recs = [
        {"ticker": "BEST",  "ensemble_score": 0.30, "percentile_action": "STRONG_BUY",
          "entry_zone": {"current": 100.0}},
        {"ticker": "OTHER", "ensemble_score": 0.05, "percentile_action": "HOLD",
          "entry_zone": {"current": 100.0}},
    ]
    enrich_batch(recs)
    summary = build_ceo_summary(recs, market="test")
    assert summary["top_opportunity"] is not None
    assert summary["top_opportunity"]["ticker"] == "BEST"
    assert summary["actionable_count"] >= 1


def test_ceo_summary_picks_top_risk_when_exit_needed():
    recs = [
        {"ticker": "GOODCO", "ensemble_score": 0.20, "percentile_action": "BUY",
          "entry_zone": {"current": 100.0}},
        {"ticker": "BADCO",  "ensemble_score": -0.30, "percentile_action": "STRONG_SELL",
          "entry_zone": {"current": 50.0}},
    ]
    enrich_batch(recs)
    summary = build_ceo_summary(recs, market="test")
    assert summary["top_risk"] is not None
    assert summary["top_risk"]["ticker"] == "BADCO"
    assert summary["top_risk"]["if_holding"] == "EXIT"


def test_ceo_summary_recommends_rotation_when_available():
    recs = [
        {"ticker": "OWNED", "ensemble_score": -0.20, "percentile_action": "HOLD",
          "entry_zone": {"current": 100.0}},
        {"ticker": "STAR",  "ensemble_score": 0.30, "percentile_action": "STRONG_BUY",
          "entry_zone": {"current": 200.0}},
    ]
    enrich_batch(recs)
    summary = build_ceo_summary(recs, market="test")
    assert "Rotate" in summary["recommended_action"]
    assert summary["rotations_count"] >= 1


def test_ceo_summary_handles_empty_recs():
    summary = build_ceo_summary([], market="test")
    assert summary["top_opportunity"] is None
    assert summary["top_risk"] is None
    assert summary["actionable_count"] == 0


def test_ceo_summary_uses_provided_regime_and_health():
    recs = [{"ticker": "A", "percentile_action": "HOLD",
              "entry_zone": {"current": 100.0}}]
    enrich_batch(recs)
    summary = build_ceo_summary(recs, market="test",
                                    macro_regime="risk_off",
                                    portfolio_cash_pct=40.0,
                                    portfolio_health_score=84)
    assert summary["market_regime"] == "risk_off"
    assert summary["cash_pct"] == 40.0
    assert summary["portfolio_health"] == 84


# ── SSoT wiring guardrail ──────────────────────────────────
def test_ssot_run_wires_snapshot_and_ceo_summary():
    """Regression guard for cycle 4 wiring."""
    src = (_ROOT / "backend" / "recommendation" / "ssot" / "run.py").read_text(encoding="utf-8")
    for needle in ("archive_snapshot", "load_previous_snapshot",
                     "build_ceo_summary", "ceo_summary"):
        assert needle in src, f"ssot/run.py missing cycle-4 wiring: {needle}"
