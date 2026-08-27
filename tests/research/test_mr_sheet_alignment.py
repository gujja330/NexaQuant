"""Tests for CEO 2026-08-27 sheet alignment + 4-state lifecycle."""
from backend.research.mr_evidence_layer import (
    HISTORY_SHEET_COLS, PORTFOLIO_SHEET_COLS, EXIT_SHEET_COLS,
    _technical_context, _exit_type_from, _fwd_5d_price,
    _experiment_decision_for,
)
from backend.research.mr_research_topology import (
    LIFECYCLE_4STATE, _lifecycle_4state,
)


def test_history_has_all_ceo_columns():
    for c in ("experiment_id", "original_decision", "experiment_decision",
              "entry_price", "fwd_5d_price", "fwd_5d_pct",
              "outcome_label_5d", "mfe_pct", "mae_pct",
              "stop_hit_within_20d", "exit_type",
              "sector", "cap_bucket", "technical_context"):
        assert c in HISTORY_SHEET_COLS, f"missing {c}"


def test_portfolio_has_research_badge():
    assert "research_badge" in PORTFOLIO_SHEET_COLS
    assert "research_signal" in PORTFOLIO_SHEET_COLS


def test_exit_has_original_signal_and_attribution():
    assert "original_signal" in EXIT_SHEET_COLS
    assert "experiment_attribution" in EXIT_SHEET_COLS
    assert "what_e3_would_have_done" in EXIT_SHEET_COLS


def test_technical_context_string():
    r = {"rsi_bucket":"STRONG", "ma20_bucket":"+1_+5", "trend":"ABOVE_MA200"}
    assert _technical_context(r) == "RSI:STRONG · MA20:+1_+5 · trend:ABOVE_MA200"


def test_technical_context_dash_when_empty():
    assert _technical_context({}) == "—"


def test_exit_type_stop_hit():
    r = {"stop_hit_within_20d": True, "fwd_5d_pct": -3.0}
    assert _exit_type_from(r) == "STOP_HIT"


def test_exit_type_time_horizon():
    r = {"stop_hit_within_20d": False, "fwd_5d_pct": 1.5}
    assert _exit_type_from(r) == "TIME_HORIZON_5D"


def test_exit_type_open_when_no_data():
    assert _exit_type_from({}) == "OPEN"


def test_fwd_5d_price_computes():
    r = {"entry_price_at_pred": 100.0, "fwd_5d_pct": 2.5}
    assert _fwd_5d_price(r) == 102.5


def test_fwd_5d_price_none_when_missing():
    assert _fwd_5d_price({"entry_price_at_pred": 100.0}) is None
    assert _fwd_5d_price({"fwd_5d_pct": 1.0}) is None


def test_experiment_decision_e2_priority():
    r = {"research_signals": ["E1_REJECT_R1_WEAK", "E2_BOOST_R2_STRONG"]}
    assert _experiment_decision_for(r) == "E2_BOOST"


def test_experiment_decision_default_keep():
    assert _experiment_decision_for({"research_signals": []}) == "KEEP"


def test_lifecycle_4state_ladder():
    assert set(LIFECYCLE_4STATE) == {"OBSERVED","TESTED","VALIDATED","PROMOTABLE"}


def test_lifecycle_observed_when_no_forward():
    assert _lifecycle_4state(500, 0, "ACTIVE_SHADOW") == "OBSERVED"


def test_lifecycle_tested_when_forward_below_100():
    assert _lifecycle_4state(500, 50, "ACTIVE_SHADOW") == "TESTED"


def test_lifecycle_validated_when_forward_ge_100():
    assert _lifecycle_4state(500, 100, "ACTIVE_SHADOW") == "VALIDATED"


def test_lifecycle_promotable_when_passed():
    assert _lifecycle_4state(500, 500, "PASSED") == "PROMOTABLE"
