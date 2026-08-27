"""Tests for the research topology + 6-field cards."""
from backend.research.mr_research_topology import (
    _statistical_confidence, _render_card_md, ACTIVE_MAP, TOPOLOGY,
)


def test_topology_has_ceo_exact_top_level():
    assert set(TOPOLOGY.keys()) == {"MR_V1", "archive", "historical"}


def test_mr_v1_has_ceo_subdirs():
    # CEO revised 2026-08-27 · added daily + decisions
    assert set(TOPOLOGY["MR_V1"].keys()) == {"frozen", "active", "evidence",
                                              "daily", "dashboards",
                                              "decisions", "reports"}


def test_active_has_three_experiment_slots():
    assert set(TOPOLOGY["MR_V1"]["active"].keys()) == {
        "E1_india_r1_filter", "E2_india_r2_boost", "E3_stop_loss"}


def test_archive_has_ceo_five_buckets():
    # CEO revised 2026-08-27 · added data_quality
    assert set(TOPOLOGY["archive"].keys()) == {
        "successful", "promising", "failed", "superseded", "data_quality"}


def test_historical_45d_present():
    assert "45d" in TOPOLOGY["historical"]


def test_active_map_maps_all_three_focused():
    assert len(ACTIVE_MAP) == 3
    slots = set(ACTIVE_MAP.values())
    assert slots == {"E1_india_r1_filter", "E2_india_r2_boost", "E3_stop_loss"}


def test_statistical_confidence_production_candidate_when_forward_100():
    v = _statistical_confidence(historical_n=500, forward_n=100,
                                 historical_effect_pp=+10.0)
    assert "PRODUCTION_CANDIDATE" in v


def test_statistical_confidence_historical_strong():
    v = _statistical_confidence(historical_n=500, forward_n=0,
                                 historical_effect_pp=+15.0)
    assert "HISTORICAL_STRONG" in v


def test_statistical_confidence_observation_only():
    v = _statistical_confidence(historical_n=15, forward_n=0,
                                 historical_effect_pp=+3.0)
    assert "OBSERVATION_ONLY" in v


def test_card_md_contains_all_six_fields():
    card = {
        "title":                 "T",
        "experiment_id":         "eid",
        "market":                "INDIA",
        "current_status":        "ACTIVE_SHADOW",
        "historical_evidence":   {"n": 100, "effect_pp": 5.0, "source": "s"},
        "forward_evidence":      {"n": 0, "target_n": 100, "wr_pct": None, "avg_pct": None, "source": "s"},
        "statistical_confidence": "HISTORICAL_MODERATE",
        "decision":              "PENDING",
        "reason":                "hyp",
        "revisit_condition":     "N>=100",
    }
    md = _render_card_md(card)
    assert "Historical evidence" in md
    assert "Forward evidence" in md
    assert "Statistical confidence" in md
    assert "Decision" in md
    assert "Reason" in md
    assert "Revisit condition" in md
