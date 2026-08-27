"""Tests for CEO close-out · 3 focused shadow experiment rules."""
from backend.research.mr_experiment_runner import (
    rule_X1_r1_r2_ranking, rule_X2_stop_loss_time_5d,
    rule_X3_usa_mid_cap_tilt, rule_XA_technical_filter,
    FOCUSED_EXPERIMENTS,
)

# Retain the technical-filter rule under new name for archived experiment
rule_X3_technical_filter = rule_XA_technical_filter


def test_X1_demotes_r1_top3_with_bad_ma20():
    r = {"runner":"R1","rank":2,"ma20_dist_pct":-3.0,"confidence_pct":50}
    d, fired, reason = rule_X1_r1_r2_ranking(r)
    assert fired is True
    assert d == "DEMOTE_TO_4_7"


def test_X1_keeps_r1_top3_with_good_ma20():
    r = {"runner":"R1","rank":2,"ma20_dist_pct":+2.5,"confidence_pct":50}
    d, fired, _ = rule_X1_r1_r2_ranking(r)
    # Good ma20 · no confidence anti-signal · no fires
    assert fired is False


def test_X1_warns_r1_conf_70_85():
    r = {"runner":"R1","rank":8,"ma20_dist_pct":+2.5,"confidence_pct":78}
    d, fired, _ = rule_X1_r1_r2_ranking(r)
    assert fired is True
    assert d == "WARN_CONFIDENCE"


def test_X1_ignores_r2():
    r = {"runner":"R2","rank":1,"ma20_dist_pct":-3.0,"confidence_pct":78}
    d, fired, _ = rule_X1_r1_r2_ranking(r)
    assert fired is False


def test_X2_wraps_E5():
    r = {"recommended_date":"2026-08-01"}
    d, fired, _ = rule_X2_stop_loss_time_5d(r)
    assert fired is True
    assert d == "TIME_EXIT_ADVISORY"


def test_X3_positive_filter_oversold_rsi():
    r = {"rsi_14": 25, "ma20_dist_pct": 0.5}
    d, fired, _ = rule_X3_technical_filter(r)
    assert fired is True
    assert d == "POSITIVE_FILTER"


def test_X3_positive_filter_ma20_in_1_5_band():
    r = {"rsi_14": 50, "ma20_dist_pct": 3.0}
    d, fired, _ = rule_X3_technical_filter(r)
    assert fired is True
    assert d == "POSITIVE_FILTER"


def test_X3_negative_filter_weak_rsi():
    r = {"rsi_14": 35, "ma20_dist_pct": 0.5}
    d, fired, _ = rule_X3_technical_filter(r)
    assert fired is True
    assert d == "NEGATIVE_FILTER"


def test_X3_mixed_filter_conflicting_signals():
    r = {"rsi_14": 25, "ma20_dist_pct": -3.0}  # positive RSI, negative MA20 (India)
    d, fired, _ = rule_X3_technical_filter(r)
    assert fired is True
    assert d == "MIXED_FILTER"


def test_X3_no_filter_when_nothing_stands_out():
    r = {"rsi_14": 50, "ma20_dist_pct": 0.5}
    d, fired, _ = rule_X3_technical_filter(r)
    assert fired is False


def test_focused_experiments_are_3():
    assert len(FOCUSED_EXPERIMENTS) == 3
    # CEO FINAL: focused set is now E1/E2/E3 · X-series is archived
    for i in FOCUSED_EXPERIMENTS:
        assert "e1" in i or "e2" in i or "e3" in i
