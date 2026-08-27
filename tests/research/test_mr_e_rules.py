"""CEO FINAL · tests for E1/E2/E3 focused rules."""
from backend.research.mr_experiment_runner import (
    rule_E1_india_r1_filter,
    rule_E2_india_r2_rank_4_7_boost,
    rule_E3_stop_loss_cross_market,
    FOCUSED_EXPERIMENTS,
)


def test_e1_fires_on_r1_top3_bad_ma20():
    r = {"runner":"R1","rank":2,"ma20_dist_pct":-3.0}
    d, fired, _ = rule_E1_india_r1_filter(r)
    assert fired is True
    assert d == "REJECT_R1_WEAK"


def test_e1_fires_on_r1_conf_anti_signal():
    r = {"runner":"R1","rank":10,"confidence_pct":78}
    d, fired, _ = rule_E1_india_r1_filter(r)
    assert fired is True
    assert d == "REJECT_R1_WEAK"


def test_e1_keeps_r1_healthy():
    r = {"runner":"R1","rank":2,"ma20_dist_pct":2.5,"confidence_pct":50}
    d, fired, _ = rule_E1_india_r1_filter(r)
    assert fired is False
    assert d == "KEEP_R1"


def test_e1_ignores_r2():
    r = {"runner":"R2","rank":1,"ma20_dist_pct":-3.0}
    d, fired, _ = rule_E1_india_r1_filter(r)
    assert fired is False
    assert d == "NOT_R1_SCOPE"


def test_e2_boosts_r2_rank47_rsi_strong():
    r = {"runner":"R2","rank":5,"rsi_14":62}
    d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
    assert fired is True
    assert d == "BOOST_R2_STRONG"


def test_e2_boundaries_of_rank_and_rsi():
    for rank in (4,5,6,7):
        r = {"runner":"R2","rank":rank,"rsi_14":60}
        d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
        assert fired is True, f"rank {rank} should fire"
    # rank 3 and 8 should NOT fire
    for rank in (3,8):
        r = {"runner":"R2","rank":rank,"rsi_14":60}
        d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
        assert fired is False
    # RSI at 55 and 69 should fire, 54 and 70 should not
    for rsi in (55, 62, 69):
        r = {"runner":"R2","rank":5,"rsi_14":rsi}
        d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
        assert fired is True, f"rsi {rsi} should fire"
    for rsi in (54, 70):
        r = {"runner":"R2","rank":5,"rsi_14":rsi}
        d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
        assert fired is False


def test_e2_ignores_r1():
    r = {"runner":"R1","rank":5,"rsi_14":62}
    d, fired, _ = rule_E2_india_r2_rank_4_7_boost(r)
    assert fired is False


def test_e3_india_time_stop_advisory():
    r = {"recommended_date":"2026-08-01"}
    d, fired, _ = rule_E3_stop_loss_cross_market(r)
    assert fired is True
    assert d == "TIME_EXIT_ADVISORY"


def test_e3_usa_trailing_10_armed():
    r = {"market":"USA", "recommended_date":"2026-08-27"}
    d, fired, _ = rule_E3_stop_loss_cross_market(r)
    assert fired is True
    assert d == "TRAILING_10_ARMED"


def test_focused_experiments_are_e1_e2_e3():
    assert len(FOCUSED_EXPERIMENTS) == 3
    ids = FOCUSED_EXPERIMENTS
    assert any("e1_india_r1_filter" in x for x in ids)
    assert any("e2_india_r2_rank_4_7_boost" in x for x in ids)
    assert any("e3_stop_loss_cross_market" in x for x in ids)
