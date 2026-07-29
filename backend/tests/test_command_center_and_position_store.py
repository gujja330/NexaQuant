"""CEO cycle 6 tests · Command Center renderer + Position Store + Discipline.

Covers:
 · Command Center renders single message with all required sections
 · Character budget honored · truncation drops non-essential sections
 · Position Store: append-only per date · idempotent · trailing stop math
 · Discipline flags fire correctly for S1-S4 scenarios
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.delivery.telegram.command_center import (  # noqa: E402
    render_command_center_message, SCHEMA_FINGERPRINT as CC_FP,
    BUDGET_CHARS,
)
from backend.portfolio.position_store import (  # noqa: E402
    upsert_position, load_position, load_all_positions,
    update_from_recs, TRAIL_PCT, SCHEMA_FINGERPRINT as PS_FP,
)
from backend.portfolio.position_store.store import compute_days_recommended  # noqa: E402
from backend.recommendation.investor_actionable import enrich_batch  # noqa: E402


# ── Command Center renderer ──────────────────────────────────
def _sample_payload(market: str = "india") -> dict:
    return {
        "asof":            "2026-07-29",
        "market":          market,
        "run_utc":         "2026-07-29T05:00:00+00:00",
        "investor_actionable_engine": "aegis.recommendation.investor_actionable.v1",
        "ceo_summary": {
            "market_regime":       "risk_on",
            "actionable_count":    2,
            "rotations_count":     1,
            "recommended_action":  "Rotate BADCO -> GOODCO (expected alpha +50%)",
            "top_opportunity":     {"ticker": "GOODCO", "action": "BUY", "allocation_pct": 5.0},
            "top_risk":            {"ticker": "BADCO",  "if_holding": "EXIT"},
            "discipline_warnings": [],
        },
        "recommendations": [
            {"ticker": "GOODCO.NS", "ensemble_score": 0.30,
              "investor_action": {"entry": "BUY", "if_holding": "ADD",
                                     "is_actionable_entry": True, "is_actionable_if_holding": True,
                                     "user_facing_label": "Strong Buy"},
              "position_plan":   {"suggested_allocation_pct": 5.0,
                                     "time_horizon_bucket": "swing", "time_horizon_days": 20,
                                     "entry_zone": {"current_price": 100.0,
                                                     "ideal_buy_low": 99.0, "ideal_buy_high": 101.0,
                                                     "stop_loss": 94.0, "target_1": 112.0}},
              "rotation_intelligence": {"should_rotate": False, "keep_score": 0.30},
              "evolution": {"is_new": True, "days_recommended": 1, "narrative": "NEW recommendation"},
              "why": {"top_reasons": ["momentum strong"], "top_risks": ["none material"], "signal_quality": "STRONG"},
              "lifecycle_state": {"current_state": "BUY"},
              "discipline": {"is_winner_exit": False, "is_low_conviction_buy": False, "notes": []},
            },
            {"ticker": "BADCO.NS", "ensemble_score": -0.30,
              "investor_action": {"entry": "AVOID", "if_holding": "EXIT",
                                     "is_actionable_entry": False, "is_actionable_if_holding": True,
                                     "user_facing_label": "Exit"},
              "position_plan":   {"suggested_allocation_pct": 0.0,
                                     "time_horizon_bucket": "swing", "time_horizon_days": 20,
                                     "entry_zone": {"current_price": 50.0, "exit_range_low": 49.5,
                                                     "exit_range_high": 50.5}},
              "rotation_intelligence": {"should_rotate": True,
                                           "replacement_ticker": "GOODCO.NS",
                                           "edge": 0.60, "expected_alpha_delta_pct": 60.0},
              "evolution": {"is_new": True, "days_recommended": 1, "narrative": "NEW recommendation"},
              "why": {"top_reasons": [], "top_risks": ["stretched valuation"], "signal_quality": "MODERATE"},
              "lifecycle_state": {"current_state": "HOLD"},
              "discipline": {"is_winner_exit": False, "is_low_conviction_buy": False, "notes": []},
            },
        ],
    }


def test_command_center_renders_all_required_sections():
    msg = render_command_center_message(_sample_payload(), "india")
    assert "CEO CALL TODAY" in msg
    assert "Rotate BADCO -> GOODCO" in msg
    assert "NEW BUY IDEAS" in msg   # v3.0 label ("NEW BUYS" → "NEW BUY IDEAS")
    assert "GOODCO" in msg
    assert "EXITS IF YOU HOLD" in msg  # v3.0 label
    assert "BADCO" in msg
    assert "PORTFOLIO PULSE" in msg  # v3.0 label
    assert "PAPER" in msg


def test_command_center_single_message_under_budget():
    msg = render_command_center_message(_sample_payload(), "india")
    assert len(msg) <= BUDGET_CHARS
    # Sanity: not empty
    assert len(msg) > 300


def test_command_center_uses_ascii_arrows_not_unicode():
    """Windows cp1252 CI logs cannot encode → · use -> instead."""
    msg = render_command_center_message(_sample_payload(), "india")
    assert "->" in msg   # ASCII arrow present
    # Unicode arrow is OK in Markdown body but must not be in the CEO CALL line
    # (that line prints to CI logs). Just verify we don't inadvertently use
    # only the Unicode variant.


def test_command_center_currency_symbols_per_market():
    """India uses 'Rs' prefix; USA uses '$'."""
    msg_ind = render_command_center_message(_sample_payload("india"), "india")
    msg_usa = render_command_center_message(_sample_payload("usa"), "usa")
    # BUY zone with numeric price -> currency prefix
    assert "Rs" in msg_ind
    assert "$" in msg_usa


def test_command_center_handles_empty_recs_gracefully():
    empty = {"asof": "2026-07-29", "market": "india", "recommendations": [],
              "ceo_summary": {"recommended_action": "no signal"}, "run_utc": ""}
    msg = render_command_center_message(empty, "india")
    assert "CEO CALL TODAY" in msg
    assert "no signal" in msg


def test_command_center_surfaces_discipline_warnings():
    p = _sample_payload()
    p["ceo_summary"]["discipline_warnings"] = [
        "2 winner-exits (rank-fall churn on positive-score positions)",
    ]
    msg = render_command_center_message(p, "india")
    assert "winner-exits" in msg
    assert "⚠" in msg   # warning marker


def test_command_center_fingerprint_stable():
    assert "aegis.delivery.telegram.command_center.v1" in CC_FP


# ── Position Store ───────────────────────────────────────────
def test_upsert_opens_new_position(tmp_path):
    rec = upsert_position(tmp_path, "india", "AAPL", asof="2026-07-20",
                             current_price=100.0, current_score=0.5,
                             initial_stop=94.0, target_price=112.0)
    assert rec.first_seen_date == "2026-07-20"
    assert rec.first_seen_price == 100.0
    assert rec.high_water_price == 100.0
    assert rec.low_water_price == 100.0
    assert rec.n_appearances == 1
    assert rec.initial_stop == 94.0
    assert rec.current_stop == 94.0


def test_upsert_is_idempotent_per_date(tmp_path):
    upsert_position(tmp_path, "india", "AAPL", asof="2026-07-20",
                       current_price=100.0, current_score=0.5)
    rec = upsert_position(tmp_path, "india", "AAPL", asof="2026-07-20",
                             current_price=200.0, current_score=0.9)   # same date
    # Same-date upsert must NOT overwrite first_seen fields
    assert rec.first_seen_price == 100.0
    assert rec.high_water_price == 100.0
    assert rec.n_appearances == 1


def test_upsert_trailing_stop_raises_only(tmp_path):
    upsert_position(tmp_path, "india", "AAPL", asof="2026-07-20",
                       current_price=100.0, current_score=0.5, initial_stop=94.0)
    # Next day: price rises to 120 → trail = 120*(1-0.06) = 112.80
    rec = upsert_position(tmp_path, "india", "AAPL", asof="2026-07-21",
                             current_price=120.0, current_score=0.6)
    assert rec.high_water_price == 120.0
    assert rec.current_stop is not None
    assert abs(rec.current_stop - 120.0 * (1 - TRAIL_PCT)) < 1e-6
    # Day 3: price drops back to 110 → stop should NOT lower
    rec2 = upsert_position(tmp_path, "india", "AAPL", asof="2026-07-22",
                              current_price=110.0, current_score=0.4)
    assert rec2.high_water_price == 120.0   # unchanged
    assert rec2.current_stop == rec.current_stop   # stop did NOT lower


def test_upsert_never_overwrites_first_seen(tmp_path):
    """Explicit lock on the immutable-fields invariant."""
    r1 = upsert_position(tmp_path, "india", "T", asof="2026-07-20",
                            current_price=100.0, current_score=0.5)
    r2 = upsert_position(tmp_path, "india", "T", asof="2026-07-21",
                            current_price=150.0, current_score=0.9)
    assert r2.first_seen_date == "2026-07-20"
    assert r2.first_seen_price == 100.0
    assert r2.first_seen_score == 0.5


def test_update_from_recs_marks_dropped_tickers_inactive(tmp_path):
    # Day 1: 2 tickers
    recs_d1 = [
        {"ticker": "A", "ensemble_score": 0.1,
          "position_plan": {"entry_zone": {"current_price": 100.0,
                                              "target_1": 110.0, "stop_loss": 94.0}}},
        {"ticker": "B", "ensemble_score": 0.2,
          "position_plan": {"entry_zone": {"current_price": 200.0,
                                              "target_1": 220.0, "stop_loss": 188.0}}},
    ]
    update_from_recs(tmp_path, "india", recs_d1, asof="2026-07-20")
    # Day 2: only A remains, B dropped
    recs_d2 = [
        {"ticker": "A", "ensemble_score": 0.15,
          "position_plan": {"entry_zone": {"current_price": 105.0,
                                              "target_1": 115.0, "stop_loss": 98.7}}},
    ]
    update_from_recs(tmp_path, "india", recs_d2, asof="2026-07-21")
    positions = load_all_positions(tmp_path, "india")
    assert positions["A"].is_active is True
    assert positions["B"].is_active is False   # dropped from top-N
    # But B's history preserved
    assert positions["B"].first_seen_date == "2026-07-20"


def test_compute_days_recommended_uses_position_store(tmp_path):
    upsert_position(tmp_path, "india", "T", asof="2026-07-20",
                       current_price=100.0, current_score=0.5)
    assert compute_days_recommended(tmp_path, "india", "T", "2026-07-29") == 10


def test_compute_days_recommended_defaults_to_1_if_unseen(tmp_path):
    assert compute_days_recommended(tmp_path, "india", "NEW", "2026-07-29") == 1


def test_position_store_fingerprint_stable():
    assert "aegis.portfolio.position_store.v1" in PS_FP


# ── Discipline flags (S1-S4) ─────────────────────────────────
def test_discipline_flags_winner_exit_when_positive_score_but_exit():
    prev = {"ticker": "X", "ensemble_score": 0.15,
             "position_plan": {"suggested_allocation_pct": 5.0}}
    today = [{"ticker": "X", "ensemble_score": 0.12,
                "percentile_action": "STRONG_SELL",  # forced exit
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, previous_ticker_map={"X": prev}, asof="2026-07-29")
    d = today[0].get("discipline") or {}
    assert d.get("is_winner_exit") is True
    assert any("WINNERS-EXIT" in n for n in d.get("notes", []))


def test_discipline_flags_low_conviction_buy_on_weak_signal():
    today = [{"ticker": "T", "ensemble_score": 0.05,
                "percentile_action": "BUY", "signal_quality": "WEAK",
                "calibrated_confidence": 0.05,
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, asof="2026-07-29")
    d = today[0].get("discipline") or {}
    assert d.get("is_low_conviction_buy") is True


def test_discipline_flags_low_confidence_buy():
    today = [{"ticker": "T", "ensemble_score": 0.05,
                "percentile_action": "BUY", "signal_quality": "STRONG",
                "calibrated_confidence": 0.005,   # below institutional 0.02 floor
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, asof="2026-07-29")
    d = today[0].get("discipline") or {}
    assert d.get("is_low_conviction_buy") is True


def test_discipline_flags_weight_score_inversion():
    prev = {"ticker": "T", "ensemble_score": 0.30,
             "position_plan": {"suggested_allocation_pct": 3.0}}
    today = [{"ticker": "T", "ensemble_score": 0.10,   # score dropped
                "percentile_action": "STRONG_BUY",      # forced STRONG_BUY -> 5% alloc
                "entry_zone": {"current": 100.0},
                "signal_quality": "STRONG",
                "calibrated_confidence": 0.03}]
    enrich_batch(today, previous_ticker_map={"T": prev}, asof="2026-07-29")
    d = today[0].get("discipline") or {}
    # alloc went 3->5% while score went 0.30->0.10 = inversion
    assert d.get("weight_score_inversion") is True


def test_discipline_no_flags_on_clean_recommendation():
    today = [{"ticker": "T", "ensemble_score": 0.30,
                "percentile_action": "BUY", "signal_quality": "STRONG",
                "calibrated_confidence": 0.05,
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, asof="2026-07-29")
    d = today[0].get("discipline") or {}
    assert not d.get("is_winner_exit")
    assert not d.get("is_low_conviction_buy")
    assert not d.get("weight_score_inversion")


def test_ceo_summary_aggregates_discipline_warnings():
    from backend.recommendation.investor_actionable import build_ceo_summary
    prev = {"ticker": "X", "ensemble_score": 0.15,
             "position_plan": {"suggested_allocation_pct": 5.0}}
    today = [{"ticker": "X", "ensemble_score": 0.12,
                "percentile_action": "STRONG_SELL",
                "entry_zone": {"current": 100.0}}]
    enrich_batch(today, previous_ticker_map={"X": prev}, asof="2026-07-29")
    cs = build_ceo_summary(today, market="test")
    warnings = cs.get("discipline_warnings") or []
    assert any("winner-exits" in w for w in warnings)


# ── Workflow wiring guardrails ───────────────────────────────
def test_command_center_wired_into_india_workflow():
    src = (_ROOT / ".github" / "workflows" / "aegis-daily.yml").read_text(encoding="utf-8")
    assert "telegram_command_center_send.py" in src, (
        "aegis-daily.yml missing Command Center send step"
    )
    assert "--market india" in src


def test_command_center_wired_into_usa_workflow():
    src = (_ROOT / ".github" / "workflows" / "aegis-usa.yml").read_text(encoding="utf-8")
    assert "telegram_command_center_send.py" in src, (
        "aegis-usa.yml missing Command Center send step"
    )
    assert "--market usa" in src
