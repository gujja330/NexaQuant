"""Tests for the refactored XLSX sheet column contracts + helpers."""
from backend.research.mr_evidence_layer import (
    HISTORY_SHEET_COLS, PORTFOLIO_SHEET_COLS, EXIT_SHEET_COLS,
    _signal_applicable, _experiment_tag, _enrich_history_for_sheet,
)


def test_history_sheet_has_ceo_required_columns():
    for c in ("prediction_date","ticker","market","runner","rank",
              "entry_price","fwd_5d_pct","fwd_10d_pct","outcome_label_5d",
              "mfe_pct","mae_pct","stop_hit_within_20d","sector","cap_bucket",
              "rsi_bucket","ma20_bucket","investability_band",
              "confidence_pct","e1_applicable","e2_applicable",
              "e3_applicable","experiment_tag"):
        assert c in HISTORY_SHEET_COLS, f"missing col {c}"


def test_portfolio_sheet_is_operator_slim():
    # Operator view · slim · Research Signal is compact
    assert "research_signal" in PORTFOLIO_SHEET_COLS
    assert len(PORTFOLIO_SHEET_COLS) <= 15


def test_exit_sheet_carries_e3_counterfactual():
    for c in ("what_e3_would_have_done",
              "e3_hypothetical_return_pct",
              "e3_delta_vs_realized_pct",
              "mfe_pct","mae_pct","entry_to_exit_pct","holding_days"):
        assert c in EXIT_SHEET_COLS


def test_signal_applicable_matches_prefix():
    assert _signal_applicable(["E2_BOOST_R2_STRONG"], "E2_") is True
    assert _signal_applicable(["E2_BOOST_R2_STRONG"], "E1_") is False
    assert _signal_applicable([], "E1_") is False
    assert _signal_applicable(None, "E1_") is False


def test_experiment_tag_condenses():
    tag = _experiment_tag(["E1_REJECT_R1_WEAK","E3_TIME_EXIT_ADVISORY"])
    assert "E1_FILTER" in tag
    assert "E3_TIME_EXIT" in tag
    assert "|" in tag


def test_experiment_tag_returns_dash_when_empty():
    assert _experiment_tag([]) == "—"
    assert _experiment_tag(None) == "—"


def test_enrich_history_adds_all_flags():
    rows = [{"research_signals": ["E1_REJECT_R1_WEAK"]}]
    out = _enrich_history_for_sheet(rows)
    assert out[0]["e1_applicable"] is True
    assert out[0]["e2_applicable"] is False
    assert out[0]["e3_applicable"] is False
    assert out[0]["experiment_tag"] == "E1_FILTER"
