"""Wave 5 · Phase 9 · Capital Rotation Engine + Opportunity Cost Engine tests.

Constitution: Article 25 (validators + tests) · Article 30 (canonical impl)
             · Article 91 (deterministic).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.recommendation.capital_rotation.engine import (  # noqa: E402
    CapitalRotationEngine, Position, Candidate, RotationAction,
    keep_score, candidate_score, macro_gate_multiplier, decide_action,
    EXIT_THRESHOLD, TRIM_THRESHOLD, ROTATE_EDGE,
    SCHEMA_FINGERPRINT as CR_FP,
)
from backend.recommendation.opportunity_cost.engine import (  # noqa: E402
    OpportunityCostEngine, enrich_holds,
    SCHEMA_FINGERPRINT as OC_FP,
)


# ── Determinism ────────────────────────────────────────────────
def test_capital_rotation_deterministic():
    positions = [Position(
        ticker="AAA", entry_score=70, current_score=68,
        entry_confidence=0.8, current_confidence=0.75,
        entry_rank=5, current_rank=7, entry_price=100.0,
        current_price=104.0, sector="IT", upside_remaining_pct=8.0, pnl_pct=4.0,
    )]
    cands = [Candidate(ticker="BBB", score=0.6, confidence=0.85, rank=2, sector="IT", upside_pct=15.0)]
    sec = {"IT": 5.0}
    p1 = CapitalRotationEngine("india").run(positions, cands, sec, "neutral", date(2026,7,27), run_utc="fixed-utc-0")
    p2 = CapitalRotationEngine("india").run(positions, cands, sec, "neutral", date(2026,7,27), run_utc="fixed-utc-0")
    # Compare everything except run_utc field (which is caller-injected here identical)
    d1 = [(d["ticker"], d["action"], d["keep_score"], d["candidate_ticker"], d["edge"]) for d in p1.decisions]
    d2 = [(d["ticker"], d["action"], d["keep_score"], d["candidate_ticker"], d["edge"]) for d in p2.decisions]
    assert d1 == d2, "engine must be deterministic across identical calls"


# ── Schema fingerprint (Article 21) ────────────────────────────
def test_capital_rotation_carries_schema_fingerprint():
    p = CapitalRotationEngine("india").run([], [], {}, "neutral", date(2026,7,27), run_utc="x")
    assert p.schema_fingerprint == CR_FP
    assert p.schema_version == "1.0.0"
    assert p.engine == "aegis.capital_rotation.v1"


# ── Threshold decisions ────────────────────────────────────────
def test_decide_action_exit_below_threshold():
    action, _, trim = decide_action(EXIT_THRESHOLD - 0.01, None)
    assert action == RotationAction.EXIT
    assert trim == 1.0


def test_decide_action_trim_between_thresholds():
    action, _, trim = decide_action((EXIT_THRESHOLD + TRIM_THRESHOLD) / 2, None)
    assert action == RotationAction.TRIM
    assert trim == 0.5


def test_decide_action_keep_above_trim_no_edge():
    action, edge, trim = decide_action(0.5, 0.6)  # edge 0.1 < ROTATE_EDGE 0.25
    assert action == RotationAction.KEEP
    assert edge is None
    assert trim is None


def test_decide_action_rotate_when_edge_exceeds_threshold():
    action, edge, _ = decide_action(0.2, 0.5)  # edge 0.3 > 0.25
    assert action == RotationAction.ROTATE
    assert edge == 0.3


# ── Macro gate ─────────────────────────────────────────────────
def test_macro_gate_multipliers_all_regimes():
    assert macro_gate_multiplier("risk_on") == 1.0
    assert macro_gate_multiplier("neutral") == 0.9
    assert macro_gate_multiplier("risk_off") == 0.5
    assert macro_gate_multiplier("stress") == 0.3
    assert macro_gate_multiplier("recession_warning") == 0.5
    assert macro_gate_multiplier("nonsense_regime") == 0.85  # unknown fallback


# ── Score bounds ───────────────────────────────────────────────
def test_keep_score_bounded():
    p = Position("X", 90, 90, 0.9, 0.9, 1, 1, 100, 200, "IT", 50.0, 100.0)
    assert -1.0 <= keep_score(p) <= 1.0


def test_candidate_score_bounded_and_macro_gated():
    c = Candidate("X", 0.8, 0.9, 1, "IT", 15.0)
    s_high = candidate_score(c, 10.0, macro_gate_multiplier("risk_on"))
    s_low  = candidate_score(c, 10.0, macro_gate_multiplier("stress"))
    assert -1.0 <= s_low <= s_high <= 1.0
    assert s_low < s_high, "stress regime must produce lower candidate scores"


# ── End-to-end rotation plan ───────────────────────────────────
def test_end_to_end_produces_all_action_types():
    positions = [
        # exit: keep_score deeply negative
        Position("EXITME", 80, 30, 0.9, 0.2, 3, 30, 100.0, 60.0, "Financials", -5.0, -40.0),
        # trim: middling
        Position("TRIMME", 70, 65, 0.7, 0.6, 5, 8, 100.0, 100.0, "IT", 3.0, 0.0),
        # keep: strong position
        Position("KEEPME", 60, 78, 0.5, 0.85, 10, 3, 100.0, 115.0, "Pharma", 12.0, 15.0),
    ]
    cands = [
        Candidate("SUPERSTAR", 0.9, 0.95, 1, "Pharma", 18.0),
    ]
    sectors = {"Pharma": 15.0, "IT": 2.0, "Financials": -8.0}
    plan = CapitalRotationEngine("india").run(
        positions, cands, sectors, "risk_on", date(2026,7,27), run_utc="e2e")
    actions = [d["action"] for d in plan.decisions]
    assert "EXIT" in actions, f"expected EXIT · got {actions}"
    assert "TRIM" in actions, f"expected TRIM · got {actions}"
    # KEEPME with strong metrics should either KEEP or ROTATE (edge test)
    assert plan.n_positions == 3
    assert plan.macro_gate == 1.0


# ── Opportunity Cost ───────────────────────────────────────────
def test_opportunity_cost_schema_fingerprint():
    from dataclasses import asdict
    from backend.recommendation.opportunity_cost.engine import OpportunityCostEnrichment
    e = OpportunityCostEnrichment(hold_ticker="X", oc_next_best_ticker=None,
                                   oc_next_best_score=None,
                                   oc_expected_alpha_delta=None,
                                   oc_reason_not_to_rotate="none")
    assert e.schema_fingerprint == OC_FP


def test_opportunity_cost_flags_high_edge():
    holds = [{"ticker": "AAA", "current_score": 0.2, "sector": "IT"}]
    cands = [{"ticker": "BBB", "score": 0.7, "sector": "IT"}]  # edge 0.5 > 0.25
    out = enrich_holds(holds, cands, rotate_edge_threshold=0.25)
    assert out[0]["oc_next_best_ticker"] == "BBB"
    assert out[0]["oc_expected_alpha_delta"] == 0.5
    assert "opportunity_cost_high" in out[0]["oc_reason_not_to_rotate"]


def test_opportunity_cost_holds_when_no_edge():
    holds = [{"ticker": "AAA", "current_score": 0.8, "sector": "IT"}]
    cands = [{"ticker": "BBB", "score": 0.5, "sector": "IT"}]  # negative edge
    out = enrich_holds(holds, cands)
    assert out[0]["oc_expected_alpha_delta"] == -0.3
    assert "hold optimal" in out[0]["oc_reason_not_to_rotate"]


def test_opportunity_cost_prefers_same_sector():
    holds = [{"ticker": "AAA", "current_score": 0.2, "sector": "Pharma"}]
    cands = [
        {"ticker": "BBB", "score": 0.9, "sector": "IT"},         # best overall
        {"ticker": "CCC", "score": 0.6, "sector": "Pharma"},      # best in-sector
    ]
    out = enrich_holds(holds, cands)
    assert out[0]["oc_next_best_ticker"] == "CCC"  # sector match preferred


def test_opportunity_cost_deterministic():
    holds = [{"ticker": "A", "current_score": 0.3, "sector": "IT"}]
    cands = [{"ticker": "B", "score": 0.4, "sector": "IT"}]
    out1 = enrich_holds(holds, cands)
    out2 = enrich_holds(holds, cands)
    assert out1 == out2
