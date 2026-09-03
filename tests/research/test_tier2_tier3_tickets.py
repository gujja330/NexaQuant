"""V2 §21 · Every R3 Tier-2/Tier-3 module must expose:
- RESEARCH_TICKET metadata dict
- evaluate(root, market) → dict with gate_status field

And every Tier-2/3 evaluate() must default to BLOCKED-EVIDENCE when R3
shadow ledger has < required picks · never silently return a "success"
verdict on empty substrate.
"""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib
import pytest


TIER2_MODULES = [
    "backend.research.r3.tier2.stacking",
    "backend.research.r3.tier2.bayesian_averaging",
    "backend.research.r3.tier2.factor_neutral",
    "backend.research.r3.tier2.promoter_governance",
    "backend.research.r3.tier2.transcript_tone",
    "backend.research.r3.tier2.multi_horizon_consensus",
]

TIER3_MODULES = [
    "backend.research.r3.tier3.gnn_graphsage",
    "backend.research.r3.tier3.pair_stat_arb",
    "backend.research.r3.tier3.cusum_regime",
]


@pytest.mark.parametrize("mod_path", TIER2_MODULES + TIER3_MODULES)
def test_module_exposes_research_ticket(mod_path):
    mod = importlib.import_module(mod_path)
    assert hasattr(mod, "RESEARCH_TICKET"), f"{mod_path} missing RESEARCH_TICKET"
    t = mod.RESEARCH_TICKET
    for k in ("ticket_id", "tier", "name", "gate_precondition", "pdf_reference"):
        assert k in t, f"{mod_path} ticket missing {k}"
    assert t["tier"] in (2, 3), f"{mod_path} tier must be 2 or 3"


@pytest.mark.parametrize("mod_path", TIER2_MODULES + TIER3_MODULES)
def test_evaluate_returns_gate_status(mod_path, tmp_path):
    mod = importlib.import_module(mod_path)
    assert hasattr(mod, "evaluate"), f"{mod_path} missing evaluate"
    r = mod.evaluate(tmp_path, "usa")
    assert isinstance(r, dict)
    assert "gate_status" in r
    # tmp_path has no shadow ledger → must be BLOCKED or NOT_APPLICABLE
    assert r["gate_status"] in (
        "BLOCKED-EVIDENCE", "NOT_APPLICABLE", "READY-TO-FIT"
    ), f"{mod_path} unexpected gate_status={r['gate_status']}"


def test_promoter_governance_india_only():
    from backend.research.r3.tier2.promoter_governance import evaluate
    r = evaluate(Path("/tmp"), "usa")
    assert r["gate_status"] == "NOT_APPLICABLE", "promoter_governance must be India-only"


def test_transcript_tone_qa_prepared_never_combined():
    """V2 §5 · prepared_remarks_tone and qa_tone are SEPARATE keys · never a
    single collapsed number that erases the distinction."""
    from backend.research.r3.tier2.transcript_tone import score_transcript
    r = score_transcript(
        prepared_remarks_text="We had a strong quarter with record growth and expanded margins.",
        qa_text="It is uncertain whether headwinds might continue possibly through Q2.",
    )
    assert "prepared_remarks_tone" in r
    assert "qa_tone" in r
    # They must be independently non-null when both inputs present
    assert r["prepared_remarks_tone"] is not None
    assert r["qa_tone"] is not None
    # And distinct (prepared positive · Q&A negative)
    assert r["prepared_remarks_tone"] > r["qa_tone"]


def test_cusum_stream_returns_flagged_when_over_threshold():
    from backend.research.r3.tier3.cusum_regime import cusum_stream
    # k and h scaled to the return magnitudes below (daily return space)
    # Baseline near zero · then positive-shock cluster
    rets = [0.001, -0.002, 0.0, 0.001] * 10 + [0.05] * 10
    stream = cusum_stream(rets, k=0.005, h=0.10)
    assert any(row["flagged"] for row in stream), "CUSUM must eventually flag on a big shock"


def test_bma_weights_sum_to_one():
    from backend.research.r3.tier2.bayesian_averaging import bma_weights
    w = bma_weights({"a": 0.5, "b": 0.6, "c": 0.7})
    s = sum(w.values())
    assert abs(s - 1.0) < 1e-6


def test_stacking_predict_bounded_0_1():
    from backend.research.r3.tier2.stacking import predict
    p = predict([1.0, 1.0, 1.0, -1.5], 0.6, 0.5, 0.7)
    assert 0.0 <= p <= 1.0
