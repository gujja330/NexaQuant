"""Tests for the Investor-Actionable enrichment engine.

Covers:
 · Dual-decision mapping across all 5 institutional levels
 · Horizon buckets (swing / position / long_term)
 · Entry zone math for BUY, SELL, HOLD
 · Allocation dampening on WEAK signal_quality
 · Missing / malformed inputs
 · Round-trip determinism
 · SSoT chain wiring guardrail
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.investor_actionable import (  # noqa: E402
    enrich_recommendation, enrich_batch,
    SCHEMA_FINGERPRINT, ENTRY_MAP, IF_HOLDING_MAP, HORIZON_BUCKETS,
)
from backend.recommendation.investor_actionable.engine import (  # noqa: E402
    _entry_zone, _horizon_bucket, _top_reasons, _top_risks, _risk_level,
    DEFAULT_STOP_PCT, PER_TICKER_CAP_PCT, summarize_batch,
)


# ── Dual-decision mapping ────────────────────────────────────
def test_all_five_actions_map_to_valid_entry_decisions():
    valid_entries = {"BUY", "WAIT", "AVOID"}
    for src in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"):
        assert ENTRY_MAP[src] in valid_entries, f"{src} → invalid entry"


def test_all_five_actions_map_to_valid_if_holding_decisions():
    valid = {"ADD", "HOLD", "REDUCE", "EXIT"}
    for src in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"):
        assert IF_HOLDING_MAP[src] in valid, f"{src} → invalid if_holding"


def test_strong_buy_recommends_buy_and_add():
    rec = {"ticker": "T", "percentile_action": "STRONG_BUY",
             "ensemble_score": 0.05, "calibrated_confidence": 0.03,
             "entry_zone": {"current": 100.0}, "signal_quality": "STRONG"}
    out = enrich_recommendation(dict(rec))
    ia = out["investor_action"]
    assert ia["entry"] == "BUY"
    assert ia["if_holding"] == "ADD"
    assert ia["is_actionable_entry"] is True


def test_hold_recommends_wait_and_hold():
    rec = {"ticker": "T", "percentile_action": "HOLD",
             "ensemble_score": 0.001, "calibrated_confidence": 0.01,
             "entry_zone": {"current": 100.0}, "signal_quality": "WEAK"}
    out = enrich_recommendation(dict(rec))
    ia = out["investor_action"]
    assert ia["entry"] == "WAIT"
    assert ia["if_holding"] == "HOLD"
    assert ia["is_actionable_entry"] is False
    assert ia["is_actionable_if_holding"] is False


def test_strong_sell_recommends_avoid_and_exit():
    rec = {"ticker": "T", "percentile_action": "STRONG_SELL",
             "ensemble_score": -0.05, "calibrated_confidence": 0.02,
             "entry_zone": {"current": 100.0}, "signal_quality": "STRONG"}
    out = enrich_recommendation(dict(rec))
    ia = out["investor_action"]
    assert ia["entry"] == "AVOID"
    assert ia["if_holding"] == "EXIT"
    assert ia["is_actionable_if_holding"] is True


def test_sell_is_never_interpreted_as_short_recommendation():
    """Retail advisory-only platform: SELL means exit if holding · never short."""
    rec = {"ticker": "T", "percentile_action": "SELL",
             "entry_zone": {"current": 100.0}}
    out = enrich_recommendation(dict(rec))
    assert out["investor_action"]["entry"] == "AVOID"   # not "SHORT"
    assert out["investor_action"]["if_holding"] == "REDUCE"
    assert "short" not in out["investor_action"]["user_facing_label"].lower()


def test_fallback_to_legacy_action_when_percentile_missing():
    rec = {"ticker": "T", "action": "BUY", "entry_zone": {"current": 100.0}}
    out = enrich_recommendation(dict(rec))
    assert out["investor_action"]["entry"] == "BUY"


def test_unknown_action_falls_back_to_wait_and_hold():
    rec = {"ticker": "T", "percentile_action": "GIBBERISH",
             "entry_zone": {"current": 100.0}}
    out = enrich_recommendation(dict(rec))
    assert out["investor_action"]["entry"] == "WAIT"
    assert out["investor_action"]["if_holding"] == "HOLD"


# ── Horizon buckets ─────────────────────────────────────────
def test_horizon_bucket_swing():
    name, _desc = _horizon_bucket(10)
    assert name == "swing"


def test_horizon_bucket_position():
    name, _desc = _horizon_bucket(45)
    assert name == "position"


def test_horizon_bucket_long_term():
    name, _desc = _horizon_bucket(180)
    assert name == "long_term"


def test_horizon_bucket_defaults_when_none():
    name, _desc = _horizon_bucket(None)
    assert name == "position"


def test_horizon_bucket_handles_garbage():
    name, _desc = _horizon_bucket("not-a-number")
    assert name == "position"


# ── Entry zone math ─────────────────────────────────────────
def test_buy_entry_zone_has_stops_and_targets():
    z = _entry_zone(100.0, "BUY")
    assert z["current_price"] == 100.0
    assert z["stop_loss"] == 94.0                              # 6% below
    assert z["target_1"] == 112.0                              # 1:2 R:R
    assert z["target_2"] == 124.0                              # 1:4 R:R
    assert z["ideal_buy_low"] < z["current_price"] < z["ideal_buy_high"]
    assert z["risk_per_share_pct"] == round(DEFAULT_STOP_PCT * 100, 2)


def test_sell_entry_zone_shows_exit_range_no_targets():
    z = _entry_zone(100.0, "SELL")
    assert "exit_range_low" in z
    assert "exit_range_high" in z
    assert "target_1" not in z
    assert "stop_loss" not in z


def test_hold_entry_zone_is_neutral():
    z = _entry_zone(100.0, "HOLD")
    assert z["current_price"] == 100.0
    assert "target_1" not in z
    assert "stop_loss" not in z


def test_entry_zone_gracefully_handles_missing_price():
    z = _entry_zone(None, "BUY")
    assert z["current_price"] is None
    z2 = _entry_zone(0.0, "BUY")
    assert z2["current_price"] is None
    z3 = _entry_zone("garbage", "BUY")
    assert z3["current_price"] is None


# ── Allocation logic ────────────────────────────────────────
def test_weak_signal_halves_allocation():
    rec_strong = {"ticker": "S", "percentile_action": "STRONG_BUY",
                    "signal_quality": "STRONG", "entry_zone": {"current": 100.0}}
    rec_weak = dict(rec_strong); rec_weak["signal_quality"] = "WEAK"
    a_strong = enrich_recommendation(rec_strong)["position_plan"]["suggested_allocation_pct"]
    a_weak = enrich_recommendation(rec_weak)["position_plan"]["suggested_allocation_pct"]
    assert a_weak < a_strong


def test_allocation_never_exceeds_per_ticker_cap():
    rec = {"ticker": "T", "percentile_action": "STRONG_BUY",
             "signal_quality": "STRONG", "entry_zone": {"current": 100.0}}
    a = enrich_recommendation(rec)["position_plan"]["suggested_allocation_pct"]
    assert a <= PER_TICKER_CAP_PCT


def test_hold_allocates_zero():
    rec = {"ticker": "T", "percentile_action": "HOLD",
             "entry_zone": {"current": 100.0}}
    assert enrich_recommendation(rec)["position_plan"]["suggested_allocation_pct"] == 0.0


# ── Why block ───────────────────────────────────────────────
def test_top_reasons_extracts_semicolon_separated_bull_case():
    reasons = _top_reasons("momentum +54%; ROE +24%; sector strength", 0.05, None)
    assert len(reasons) >= 3
    assert any("momentum" in r for r in reasons)
    assert any("ROE" in r for r in reasons)


def test_top_risks_extracts_bear_case_and_key_risks_and_disagreement():
    risks = _top_risks("overbought RSI; stretched valuation", ["macro shock"], True)
    assert any("overbought" in r for r in risks)
    assert any("valuation" in r for r in risks)
    assert any("macro" in r for r in risks)
    assert any("disagreement" in r for r in risks)


def test_top_reasons_caps_at_five():
    long_bull = "; ".join([f"reason_{i}" for i in range(15)])
    reasons = _top_reasons(long_bull, 0.05, None)
    assert len(reasons) <= 5


# ── Determinism ─────────────────────────────────────────────
def test_enrichment_is_deterministic():
    rec = {"ticker": "T", "percentile_action": "BUY",
             "ensemble_score": 0.03, "calibrated_confidence": 0.02,
             "entry_zone": {"current": 500.0},
             "bull_case": "momentum strong; RSI healthy",
             "bear_case": "sector rotation risk",
             "suggested_holding_period_days": 30,
             "signal_quality": "STRONG"}
    r1 = enrich_recommendation(dict(rec))
    r2 = enrich_recommendation(dict(rec))
    assert r1["investor_action"] == r2["investor_action"]
    assert r1["position_plan"] == r2["position_plan"]
    assert r1["why"] == r2["why"]


def test_fingerprint_is_stable():
    rec = {"ticker": "T", "percentile_action": "BUY"}
    enrich_recommendation(rec)
    # Fingerprint constant checked via re-import equality
    from backend.recommendation.investor_actionable import SCHEMA_FINGERPRINT as fp2
    assert SCHEMA_FINGERPRINT == fp2
    assert "investor_actionable.v1" in SCHEMA_FINGERPRINT


# ── Batch + summary ─────────────────────────────────────────
def test_enrich_batch_processes_all_and_summarizes():
    recs = [
        {"ticker": "A", "percentile_action": "STRONG_BUY", "entry_zone": {"current": 100.0}},
        {"ticker": "B", "percentile_action": "HOLD",       "entry_zone": {"current": 200.0}},
        {"ticker": "C", "percentile_action": "STRONG_SELL","entry_zone": {"current": 300.0}},
    ]
    enrich_batch(recs)
    for r in recs:
        assert "investor_action" in r
        assert "position_plan" in r
        assert "why" in r
    summ = summarize_batch(recs)
    assert summ["n_recs"] == 3
    assert summ["entry_decision_dist"].get("BUY") == 1
    assert summ["entry_decision_dist"].get("WAIT") == 1
    assert summ["entry_decision_dist"].get("AVOID") == 1


# ── SSoT chain wiring guardrail ─────────────────────────────
def test_ssot_chain_wired_into_ssot_run():
    """Regression guard: SSoT runner must invoke the investor enrichment."""
    src = (_ROOT / "backend" / "recommendation" / "ssot" / "run.py").read_text(encoding="utf-8")
    assert "investor_actionable" in src or "enrich_batch" in src, (
        "SSoT runner missing investor_actionable enrichment call · "
        "recommendations.json will not be investor-actionable"
    )


# ── CEO cycle 3 · Rotation Intelligence ─────────────────────
def test_rotation_intelligence_recommends_rotation_when_edge_large():
    recs = [
        {"ticker": "MID",   "percentile_action": "HOLD",       "ensemble_score": 0.02},
        {"ticker": "STAR",  "percentile_action": "STRONG_BUY", "ensemble_score": 0.30},
    ]
    enrich_batch(recs)
    ri_mid = recs[0]["rotation_intelligence"]
    assert ri_mid["should_rotate"] is True
    assert ri_mid["replacement_ticker"] == "STAR"
    assert ri_mid["edge"] > 0.05
    assert ri_mid["expected_alpha_delta_pct"] > 0


def test_rotation_intelligence_holds_when_edge_small():
    recs = [
        {"ticker": "MINE",  "percentile_action": "HOLD",       "ensemble_score": 0.10},
        {"ticker": "OTHER", "percentile_action": "BUY",        "ensemble_score": 0.12},
    ]
    enrich_batch(recs)
    ri_mine = recs[0]["rotation_intelligence"]
    assert ri_mine["should_rotate"] is False
    assert ri_mine["replacement_ticker"] is None


def test_rotation_intelligence_never_recommends_when_no_buy_candidates():
    recs = [
        {"ticker": "A", "percentile_action": "HOLD", "ensemble_score": 0.05},
        {"ticker": "B", "percentile_action": "HOLD", "ensemble_score": 0.04},
    ]
    enrich_batch(recs)
    for r in recs:
        assert r["rotation_intelligence"]["should_rotate"] is False
        assert "no BUY" in r["rotation_intelligence"]["reason"]


def test_rotation_intelligence_never_churns_out_of_top_bucket_on_small_edge():
    """Anti-churn: STRONG_BUY should not rotate to another STRONG_BUY unless
    edge is 2× threshold."""
    recs = [
        {"ticker": "A", "percentile_action": "STRONG_BUY", "ensemble_score": 0.25},
        {"ticker": "B", "percentile_action": "STRONG_BUY", "ensemble_score": 0.31},  # only 0.06 edge
    ]
    enrich_batch(recs)
    assert recs[0]["rotation_intelligence"]["should_rotate"] is False


def test_rotation_intelligence_will_rotate_from_top_bucket_when_edge_huge():
    recs = [
        {"ticker": "A", "percentile_action": "BUY",         "ensemble_score": 0.10},
        {"ticker": "B", "percentile_action": "STRONG_BUY",  "ensemble_score": 0.40},  # 0.30 edge >> 0.10
    ]
    enrich_batch(recs)
    assert recs[0]["rotation_intelligence"]["should_rotate"] is True


def test_rotation_intelligence_excludes_self_from_replacement():
    """Never suggest rotating a ticker to itself."""
    recs = [
        {"ticker": "SAME", "percentile_action": "HOLD", "ensemble_score": 0.05},
        {"ticker": "OTHR", "percentile_action": "BUY",  "ensemble_score": 0.20},
    ]
    enrich_batch(recs)
    for r in recs:
        ri = r["rotation_intelligence"]
        if ri["replacement_ticker"]:
            assert ri["replacement_ticker"] != r["ticker"]


# ── CEO cycle 3 · Lifecycle State ───────────────────────────
def test_lifecycle_untracked_when_no_records():
    rec = {"ticker": "T", "percentile_action": "HOLD"}
    enrich_batch([rec])
    assert rec["lifecycle_state"]["current_state"] == "UNTRACKED"
    assert rec["lifecycle_state"]["n_events"] == 0


def test_lifecycle_surface_reads_current_and_previous():
    rec = {"ticker": "AARTIIND.NS", "percentile_action": "HOLD"}
    lifecycle_records = {
        "AARTIIND.NS": {
            "ticker":        "AARTIIND.NS",
            "current_state": "HOLD",
            "events": [
                {"state": "DISCOVERED", "ts_utc": "2026-07-27T10:00:00+00:00", "reason": "bootstrap"},
                {"state": "HOLD",       "ts_utc": "2026-07-27T12:00:00+00:00", "reason": "daily rec"},
            ],
        },
    }
    enrich_batch([rec], lifecycle_records=lifecycle_records)
    ls = rec["lifecycle_state"]
    assert ls["current_state"] == "HOLD"
    assert ls["previous_state"] == "DISCOVERED"
    assert ls["n_events"] == 2
    assert ls["ts_last_transition"] == "2026-07-27T12:00:00+00:00"


# ── CEO cycle 3 · Dynamic holding wired ─────────────────────
def test_dynamic_holding_overrides_static_suggested_days():
    rec = {"ticker": "T", "percentile_action": "BUY",
             "suggested_holding_period_days": 60,   # fallback
             "entry_zone": {"current": 100.0}}
    dh = {"T": {"ticker": "T", "holding_days": 18,
                  "reason": "dynamic holding 18d = base 21 × drivers"}}
    enrich_batch([rec], dynamic_holding_decisions=dh)
    pp = rec["position_plan"]
    assert pp["time_horizon_days"] == 18                # NOT 60
    assert pp["time_horizon_bucket"] == "swing"          # 18d falls in swing
    assert "dynamic_holding_reason" in pp


def test_dynamic_holding_falls_back_when_engine_output_missing():
    rec = {"ticker": "T", "percentile_action": "BUY",
             "suggested_holding_period_days": 60}
    enrich_batch([rec])
    assert rec["position_plan"]["time_horizon_days"] == 60


def test_dynamic_holding_handles_malformed_days():
    rec = {"ticker": "T", "percentile_action": "BUY",
             "suggested_holding_period_days": 60}
    dh = {"T": {"holding_days": "not-a-number"}}
    enrich_batch([rec], dynamic_holding_decisions=dh)
    # Should fall back to 60, never crash
    assert rec["position_plan"]["time_horizon_days"] == 60


# ── Summary rollup ──────────────────────────────────────────
def test_summarize_includes_rotation_and_lifecycle_counts():
    from backend.recommendation.investor_actionable import summarize_batch
    recs = [
        {"ticker": "MID",  "percentile_action": "HOLD",       "ensemble_score": 0.01},
        {"ticker": "STAR", "percentile_action": "STRONG_BUY", "ensemble_score": 0.30},
    ]
    enrich_batch(recs)
    s = summarize_batch(recs)
    assert "n_rotation_suggestions" in s
    assert "lifecycle_state_dist" in s
    assert s["n_rotation_suggestions"] >= 1
    assert s["lifecycle_state_dist"].get("UNTRACKED") == 2
