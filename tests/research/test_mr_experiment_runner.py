"""M-R · shadow experiment runner property tests."""
from backend.research.mr_experiment_runner import (
    rule_E1_confidence_anti_signal,
    rule_E2_top3_rank_inversion,
    rule_E4_band_boundary,
    rule_E5_stop_policy,
    rule_E3_negative_alpha_compound,
    EXPERIMENT_RULES,
)


def test_E1_fires_only_on_R1_with_conf_70_85():
    r = {"runner":"R1", "confidence_pct": 78, "status":"ACTIVE"}
    d, fired, _ = rule_E1_confidence_anti_signal(r)
    assert fired is True
    assert d == "WARN"


def test_E1_doesnt_fire_on_R2():
    r = {"runner":"R2", "confidence_pct": 78, "status":"ACTIVE"}
    d, fired, _ = rule_E1_confidence_anti_signal(r)
    assert fired is False


def test_E1_doesnt_fire_outside_anti_band():
    for conf in (50, 40, 90, 20):
        r = {"runner":"R1", "confidence_pct": conf, "status":"ACTIVE"}
        d, fired, _ = rule_E1_confidence_anti_signal(r)
        assert fired is False, f"conf={conf} should not fire"


def test_E2_keeps_top3_when_ma20_in_range():
    r = {"runner":"R1","rank":2,"ma20_dist_pct":+2.5,"status":"ACTIVE"}
    d, fired, _ = rule_E2_top3_rank_inversion(r)
    assert fired is True
    assert d == "KEEP_TOP3"


def test_E2_demotes_top3_when_ma20_outside_range():
    r = {"runner":"R1","rank":1,"ma20_dist_pct":-3.0,"status":"ACTIVE"}
    d, fired, _ = rule_E2_top3_rank_inversion(r)
    assert fired is True
    assert d == "DEMOTE_TO_4_7"


def test_E2_ignores_non_top3():
    r = {"runner":"R1","rank":6,"ma20_dist_pct":+2.0,"status":"ACTIVE"}
    d, fired, _ = rule_E2_top3_rank_inversion(r)
    assert fired is False


def test_E4_reclassifies_OK_band():
    r = {"investability_band":"OK","confidence_pct":60,"status":"ACTIVE"}
    d, fired, _ = rule_E4_band_boundary(r)
    assert fired is True
    assert d == "SHADOW_MARGINAL"


def test_E4_ignores_non_OK_band():
    r = {"investability_band":"MARGINAL","confidence_pct":60,"status":"ACTIVE"}
    d, fired, _ = rule_E4_band_boundary(r)
    assert fired is False


def test_E5_advises_time_exit_after_5days():
    r = {"recommended_date":"2026-08-01","status":"ACTIVE"}
    d, fired, _ = rule_E5_stop_policy(r)
    assert fired is True
    assert d == "TIME_EXIT_ADVISORY"


def test_E5_holds_recent_positions():
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=2)).isoformat()
    r = {"recommended_date":recent,"status":"ACTIVE"}
    d, fired, _ = rule_E5_stop_policy(r)
    assert fired is False


def test_E3_compound_fires_when_any_component_fires():
    r = {"runner":"R1","confidence_pct":78,"rank":10,"status":"ACTIVE"}
    d, fired, reason = rule_E3_negative_alpha_compound(r)
    assert fired is True
    assert "E1" in reason


def test_E3_compound_silent_when_no_component_fires():
    # Use today's date so the time-based E5 rule never fires · this test's
    # intent is that the compound stays silent when no component rule fires ·
    # the hardcoded 2026-08-25 was time-brittle (E5 fires at ~7 calendar days).
    from datetime import date as _d
    r = {"runner":"R2","confidence_pct":50,"rank":10,
         "investability_band":"QUALITY","recommended_date": _d.today().isoformat()}
    d, fired, _ = rule_E3_negative_alpha_compound(r)
    assert fired is False


def test_all_experiments_wired():
    ids = list(EXPERIMENT_RULES.keys())
    # CEO FINAL: 3 focused (E1/E2/E3) + 4 archived X-series + 5 superseded = 12 total
    # (archived/superseded stay so shadow rows keep producing evidence continuity)
    assert len(ids) == 12
    for i in ids:
        assert i.startswith("aegis_mr_experiment_")
