"""Tests for CEO 2026-08-27 · 8-field card contract + dated archive buckets."""
from backend.research.mr_research_topology import (
    CEO_CARD_CONTRACT, CEO_DATED_ARCHIVE_BUCKETS, _ceo_card_contract,
)


def test_ceo_card_contract_has_8_fields():
    assert set(CEO_CARD_CONTRACT) == {
        "question", "hypothesis", "data_period", "sample_size",
        "result", "confidence", "decision", "production_status",
        "next_validation",
    }


def test_ceo_dated_archive_has_seven_buckets():
    # CEO 2026-08-27 · added ai_audits
    assert set(CEO_DATED_ARCHIVE_BUCKETS) == {
        "validated", "promising", "failed",
        "insufficient_data", "superseded", "evidence",
        "ai_audits",
    }


def test_ceo_card_active_shadow_says_locked_out():
    exp = {
        "hypothesis": "R2 rank_4_7 + RSI STRONG has 72.73% WR",
        "title":      "E2 · India R2 boost",
        "min_sample_size": 100,
    }
    card = _ceo_card_contract(exp, hist_effect_pp=+46.96,
                              historical_n=22, forward_n=0,
                              status="ACTIVE_SHADOW")
    for k in ("question","hypothesis","data_period","sample_size","result",
              "confidence","decision","production_status","next_validation"):
        assert k in card
    assert "LOCKED_OUT" in card["production_status"]
    assert card["decision"] == "OBSERVED"
    assert card["sample_size"]["target_n"] == 100


def test_ceo_card_promotable_when_passed():
    exp = {"hypothesis": "h", "title": "t", "min_sample_size": 100}
    card = _ceo_card_contract(exp, +5.0, 500, 500, "PASSED")
    assert card["decision"] == "PROMOTABLE"
    assert "PROMOTABLE" in card["production_status"]


def test_ceo_card_rejected_when_failed():
    exp = {"hypothesis": "h", "title": "t", "min_sample_size": 100}
    card = _ceo_card_contract(exp, +5.0, 500, 120, "FAILED")
    assert "REJECTED" in card["production_status"]


def test_ceo_card_retired_when_superseded():
    exp = {"hypothesis": "h", "title": "t", "min_sample_size": 100,
           "superseded_by": "aegis_e1"}
    card = _ceo_card_contract(exp, +5.0, 500, 5, "SUPERSEDED_BY")
    assert "RETIRED" in card["production_status"]
    assert "aegis_e1" in card["production_status"]


def test_ceo_card_sample_size_reports_all_three():
    exp = {"hypothesis": "h", "title": "t", "min_sample_size": 100}
    card = _ceo_card_contract(exp, +5.0, 500, 50, "ACTIVE_SHADOW")
    assert card["sample_size"]["historical_n"] == 500
    assert card["sample_size"]["forward_n"] == 50
    assert card["sample_size"]["target_n"] == 100
