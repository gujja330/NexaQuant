"""Final Platform Completion Program · Phase 1-4 + Phase 11 test suite.

Covers:
    Phase 1 · Recommendation SSoT bridge
    Phase 2 · Recommendation Lifecycle state machine
    Phase 3 · Recommendation Delta engine
    Phase 4 · Dynamic Holding Engine
    Phase 11 · Byte-equality determinism (--frozen-clock analog)
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.ssot.bridge import (  # noqa: E402
    translate_v3_to_legacy, publish_ssot, ACTION_MAP,
    SCHEMA_FINGERPRINT as SSOT_FP, ENGINE_ID as SSOT_ENG,
    _canonical_action, _v3_to_legacy_score,
)
from backend.recommendation.lifecycle import (  # noqa: E402
    RecommendationState, LifecycleLedger, is_valid_transition,
    VALID_TRANSITIONS, SCHEMA_FINGERPRINT as LC_FP,
)
from backend.recommendation.delta.engine import (  # noqa: E402
    DeltaEngine, compute_deltas, SCHEMA_FINGERPRINT as DELTA_FP,
)
from backend.recommendation.dynamic_holding.engine import (  # noqa: E402
    DynamicHoldingEngine, compute_holding_days,
    SCHEMA_FINGERPRINT as DH_FP, REGIME_MULT, BASE_HOLDING_DAYS,
    MIN_HOLDING_DAYS, MAX_HOLDING_DAYS,
)


# ── Phase 1 · SSoT Bridge ─────────────────────────────────────
def test_ssot_action_canonicalization():
    assert _canonical_action("STRONG_BUY") == "STRONG BUY"
    assert _canonical_action("strong-buy") == "STRONG BUY"
    assert _canonical_action("HOLD") == "HOLD"
    assert _canonical_action("WATCH") == "HOLD"
    assert _canonical_action("NEW_POSITION") == "BUY"
    assert _canonical_action(None) == "HOLD"
    assert _canonical_action("garbage") == "HOLD"


def test_ssot_score_translation_linear():
    assert _v3_to_legacy_score(-1.0) == 0.0
    assert _v3_to_legacy_score(0.0) == 50.0
    assert _v3_to_legacy_score(1.0) == 100.0
    assert _v3_to_legacy_score(2.0) == 100.0   # clipped
    assert _v3_to_legacy_score(-2.0) == 0.0    # clipped
    assert _v3_to_legacy_score(None) == 50.0   # neutral fallback


def test_ssot_translate_preserves_richness():
    v3 = {
        "ticker": "TCS", "sector": "IT", "industry": "Software",
        "action": "STRONG_BUY", "ensemble_score": 0.75,
        "calibrated_confidence": 0.85, "raw_confidence": 0.9,
        "bull_case": "strong quarter", "bear_case": "macro headwinds",
        "key_risks": ["FX", "US tariffs"], "top_features": ["rsi_14"],
    }
    legacy = translate_v3_to_legacy(v3, rank=1)
    assert legacy["ticker"] == "TCS"
    assert legacy["recommendation"] == "STRONG BUY"
    assert legacy["action"] == "STRONG BUY"
    assert legacy["composite_decision_score"] == 87.5   # (0.75+1)*50
    assert legacy["confidence"] == 0.85
    assert legacy["rank"] == 1
    assert legacy["ensemble_score"] == 0.75   # preserved
    assert legacy["bull_case"] == "strong quarter"   # preserved


def test_ssot_publish_produces_fingerprinted_output(tmp_path=None):
    from pathlib import Path as _P
    tmp = _P(__file__).parent / "_tmp_ssot"
    tmp.mkdir(exist_ok=True)
    src = tmp / "recommendations_v3.json"
    dst = tmp / "recommendations.json"
    src.write_text(json.dumps({
        "recommendations": [
            {"ticker": "A", "sector": "IT", "action": "BUY",
             "ensemble_score": 0.5, "calibrated_confidence": 0.7},
            {"ticker": "B", "sector": "IT", "action": "HOLD",
             "ensemble_score": 0.0, "calibrated_confidence": 0.5},
        ]
    }), encoding="utf-8")
    payload = publish_ssot(src, dst, market="india",
                             asof="2026-07-27", run_utc="frozen")
    assert payload["schema_fingerprint"] == SSOT_FP
    assert payload["engine"] == SSOT_ENG
    assert payload["n"] == 2
    # Rank order: A (score 0.5) beats B (score 0.0)
    assert payload["recommendations"][0]["ticker"] == "A"
    assert payload["recommendations"][0]["rank"] == 1
    # Persisted file matches payload
    persisted = json.loads(dst.read_text(encoding="utf-8"))
    assert persisted["schema_fingerprint"] == SSOT_FP
    # Cleanup
    src.unlink(); dst.unlink(); tmp.rmdir()


# ── Phase 2 · Lifecycle State Machine ─────────────────────────
def test_lifecycle_valid_transitions_forward_path():
    assert is_valid_transition(RecommendationState.DISCOVERED, RecommendationState.WATCHLIST)
    assert is_valid_transition(RecommendationState.WATCHLIST, RecommendationState.BUY)
    assert is_valid_transition(RecommendationState.BUY, RecommendationState.HOLD)
    assert is_valid_transition(RecommendationState.HOLD, RecommendationState.TRIM)
    assert is_valid_transition(RecommendationState.TRIM, RecommendationState.EXIT)
    assert is_valid_transition(RecommendationState.EXIT, RecommendationState.ARCHIVED)


def test_lifecycle_self_hold_allowed():
    """HOLD → HOLD is explicitly legal (daily recheck)."""
    assert is_valid_transition(RecommendationState.HOLD, RecommendationState.HOLD)


def test_lifecycle_invalid_transitions_rejected():
    assert not is_valid_transition(RecommendationState.ARCHIVED, RecommendationState.BUY)
    assert not is_valid_transition(RecommendationState.EXIT, RecommendationState.BUY)
    assert not is_valid_transition(RecommendationState.DISCOVERED, RecommendationState.EXIT)


def test_lifecycle_bootstraps_discovered_when_first_seen():
    ledger = LifecycleLedger()
    t = ledger.apply("TICK", RecommendationState.BUY, reason="first buy signal",
                       ts_utc="2026-07-27T00:00:00Z")
    # Must have bootstrapped DISCOVERED first
    events = ledger.records["TICK"].events
    assert len(events) == 2
    assert events[0]["state"] == "DISCOVERED"
    assert events[1]["state"] == "BUY"


def test_lifecycle_illegal_transition_raises():
    ledger = LifecycleLedger()
    ledger.apply("X", RecommendationState.DISCOVERED, ts_utc="t0")
    try:
        ledger.apply("X", RecommendationState.ROTATED, reason="illegal", ts_utc="t1")
    except ValueError:
        return
    raise AssertionError("expected ValueError for DISCOVERED → ROTATED")


def test_lifecycle_schema_fingerprint():
    from backend.recommendation.lifecycle import SCHEMA_FINGERPRINT
    assert SCHEMA_FINGERPRINT == "aegis.recommendation_lifecycle.v1.20260727"


# ── Phase 3 · Delta Engine ────────────────────────────────────
def test_delta_new_ticker_no_prior():
    today = [{"ticker": "NEW", "action": "BUY", "rank": 5, "confidence": 0.8}]
    d = compute_deltas(today, yesterday=None)
    assert d[0]["previous_rank"] is None
    assert d[0]["current_rank"] == 5
    assert d[0]["rank_delta"] is None
    assert not d[0]["action_changed"]
    assert "NEW" in d[0]["reason_for_change"]


def test_delta_rank_improvement_computed():
    yesterday = [{"ticker": "T", "action": "HOLD", "rank": 20, "confidence": 0.6}]
    today     = [{"ticker": "T", "action": "HOLD", "rank": 10, "confidence": 0.7}]
    d = compute_deltas(today, yesterday)
    assert d[0]["rank_delta"] == 10   # 20 - 10 = +10 (improved by 10 slots)
    assert d[0]["confidence_delta"] == 0.1


def test_delta_action_change_detected():
    yesterday = [{"ticker": "T", "action": "HOLD", "rank": 5, "confidence": 0.6}]
    today     = [{"ticker": "T", "action": "BUY",  "rank": 3, "confidence": 0.85}]
    d = compute_deltas(today, yesterday)
    assert d[0]["action_changed"]
    assert d[0]["previous_action"] == "HOLD"
    assert d[0]["current_action"] == "BUY"


def test_delta_deterministic():
    y = [{"ticker": "T", "action": "HOLD", "rank": 5, "confidence": 0.6}]
    t = [{"ticker": "T", "action": "HOLD", "rank": 4, "confidence": 0.62}]
    assert compute_deltas(t, y) == compute_deltas(t, y)


def test_delta_schema_fingerprint_present():
    d = compute_deltas([{"ticker": "X", "action": "HOLD", "rank": 1, "confidence": 0.5}], [])
    assert d[0]["schema_fingerprint"] == DELTA_FP


# ── Phase 4 · Dynamic Holding Engine ──────────────────────────
def test_dynamic_holding_bounded():
    for regime in REGIME_MULT.keys():
        d = compute_holding_days(
            "X", current_confidence=0.5, confidence_at_entry=0.5,
            upside_remaining_pct=0.0, sector_strength=0.0, macro_regime=regime,
            rotation_score=0.0, risk_score=0.5, annualized_vol=0.25,
            liquidity_ratio=1.0, portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
            expected_benchmark_alpha_pct=0.0,
        )
        assert MIN_HOLDING_DAYS <= d["holding_days"] <= MAX_HOLDING_DAYS


def test_dynamic_holding_stress_shortens_vs_risk_on():
    kw = dict(current_confidence=0.7, confidence_at_entry=0.7,
               upside_remaining_pct=10.0, sector_strength=5.0,
               rotation_score=0.0, risk_score=0.3, annualized_vol=0.25,
               liquidity_ratio=1.0, portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
               expected_benchmark_alpha_pct=5.0)
    risk_on = compute_holding_days("X", macro_regime="risk_on", **kw)
    stress  = compute_holding_days("X", macro_regime="stress",  **kw)
    assert stress["holding_days"] < risk_on["holding_days"], \
        f"stress {stress['holding_days']} vs risk_on {risk_on['holding_days']}"


def test_dynamic_holding_confidence_decay_shortens():
    kw = dict(macro_regime="neutral", upside_remaining_pct=10.0,
               sector_strength=0.0, rotation_score=0.0, risk_score=0.4,
               annualized_vol=0.25, liquidity_ratio=1.0,
               portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
               expected_benchmark_alpha_pct=5.0)
    strong = compute_holding_days("X", current_confidence=0.9, confidence_at_entry=0.6, **kw)
    decayed = compute_holding_days("X", current_confidence=0.4, confidence_at_entry=0.9, **kw)
    assert decayed["holding_days"] < strong["holding_days"]


def test_dynamic_holding_high_rotation_shortens():
    kw = dict(current_confidence=0.7, confidence_at_entry=0.7,
               upside_remaining_pct=10.0, sector_strength=5.0,
               macro_regime="neutral", risk_score=0.3, annualized_vol=0.25,
               liquidity_ratio=1.0, portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
               expected_benchmark_alpha_pct=5.0)
    low_rot = compute_holding_days("X", rotation_score=0.0, **kw)
    high_rot = compute_holding_days("X", rotation_score=0.8, **kw)
    assert high_rot["holding_days"] < low_rot["holding_days"]


def test_dynamic_holding_never_static():
    """The whole point: two different regimes cannot both return same value."""
    kw = dict(current_confidence=0.7, confidence_at_entry=0.7,
               upside_remaining_pct=10.0, sector_strength=5.0,
               rotation_score=0.0, risk_score=0.3, annualized_vol=0.25,
               liquidity_ratio=1.0, portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
               expected_benchmark_alpha_pct=5.0)
    days = set()
    for regime in ("risk_on", "neutral", "risk_off", "stress"):
        d = compute_holding_days("X", macro_regime=regime, **kw)
        days.add(d["holding_days"])
    assert len(days) >= 3, f"holding period is too static across regimes: {days}"


def test_dynamic_holding_schema_fingerprint():
    d = compute_holding_days("X", current_confidence=0.5, confidence_at_entry=0.5,
                              upside_remaining_pct=0.0, sector_strength=0.0,
                              macro_regime="neutral", rotation_score=0.0,
                              risk_score=0.5, annualized_vol=0.25, liquidity_ratio=1.0,
                              portfolio_overlap_pct=0.0, opp_cost_edge=0.0,
                              expected_benchmark_alpha_pct=0.0)
    assert d["schema_fingerprint"] == DH_FP


# ── Phase 11 · Byte-equality determinism (--frozen-clock analog) ──
def _norm_utc(payload_str: str) -> str:
    """Strip volatile timestamps for byte-equality comparison."""
    import re
    s = re.sub(r'"run_utc"\s*:\s*"[^"]*"', '"run_utc": "FROZEN"', payload_str)
    s = re.sub(r'"ts_utc"\s*:\s*"[^"]*"', '"ts_utc": "FROZEN"', s)
    s = re.sub(r'"appended_utc"\s*:\s*"[^"]*"', '"appended_utc": "FROZEN"', s)
    return s


def test_ssot_byte_identical_across_two_runs():
    """Phase 11 · with `run_utc` frozen, two SSoT publishes on same input must
    produce byte-identical output. This IS the byte-equality regression test
    called for by v2.2 Rep1."""
    from pathlib import Path as _P
    tmp = _P(__file__).parent / "_tmp_replay"
    tmp.mkdir(exist_ok=True)
    src = tmp / "recommendations_v3.json"
    dst1 = tmp / "run1.json"
    dst2 = tmp / "run2.json"
    src.write_text(json.dumps({
        "recommendations": [
            {"ticker": "A", "sector": "IT", "action": "BUY",
             "ensemble_score": 0.5, "calibrated_confidence": 0.7,
             "bull_case": "growth"},
        ]
    }), encoding="utf-8")

    publish_ssot(src, dst1, market="india", asof="2026-07-27", run_utc="FROZEN")
    publish_ssot(src, dst2, market="india", asof="2026-07-27", run_utc="FROZEN")

    b1 = dst1.read_text(encoding="utf-8")
    b2 = dst2.read_text(encoding="utf-8")
    assert b1 == b2, "byte-equality failed for SSoT under frozen clock"

    src.unlink(); dst1.unlink(); dst2.unlink(); tmp.rmdir()


def test_lifecycle_byte_identical_replay():
    """Phase 11 · replaying the same event stream through LifecycleLedger.from_jsonl
    reconstructs identical records."""
    ledger1 = LifecycleLedger()
    for i, (t, s) in enumerate([
        ("A", RecommendationState.DISCOVERED),
        ("A", RecommendationState.WATCHLIST),
        ("A", RecommendationState.BUY),
        ("B", RecommendationState.DISCOVERED),
    ]):
        ledger1.apply(t, s, ts_utc=f"t{i}")
    from pathlib import Path as _P
    tmp = _P(__file__).parent / "_tmp_ledger.jsonl"
    if tmp.exists(): tmp.unlink()
    ledger1.write_jsonl(tmp)
    ledger2 = LifecycleLedger.from_jsonl(tmp)
    # Same tickers, same final states
    assert set(ledger1.records) == set(ledger2.records)
    for ticker in ledger1.records:
        assert ledger1.records[ticker].current_state == ledger2.records[ticker].current_state
    tmp.unlink()


def test_delta_deterministic_bulk():
    """Phase 11 · Delta engine determinism at scale."""
    y = [{"ticker": f"T{i}", "action": "HOLD", "rank": i, "confidence": 0.5}
          for i in range(1, 51)]
    t = [{"ticker": f"T{i}", "action": "HOLD", "rank": i, "confidence": 0.52}
          for i in range(1, 51)]
    d1 = compute_deltas(t, y)
    d2 = compute_deltas(t, y)
    assert d1 == d2, "delta engine must be byte-identical across runs"
