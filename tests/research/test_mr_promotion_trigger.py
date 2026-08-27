"""Tests for the automatic promotion trigger evaluator."""
from backend.research.mr_promotion_trigger import (
    _accept_e1, _accept_e2, _accept_e3, ACCEPT_MAP,
)


def test_e1_pass_when_delta_ge_5pp():
    r = {"wr_pct": 30.0, "baseline_wr_pct": 20.81}
    v, reason = _accept_e1(r)
    assert v == "PASS"


def test_e1_fail_when_delta_le_neg3():
    r = {"wr_pct": 15.0, "baseline_wr_pct": 20.81}
    v, reason = _accept_e1(r)
    assert v == "FAIL"


def test_e1_borderline_in_between():
    r = {"wr_pct": 22.0, "baseline_wr_pct": 20.81}
    v, reason = _accept_e1(r)
    assert v == "BORDERLINE"


def test_e1_borderline_when_missing_data():
    r = {"wr_pct": None, "baseline_wr_pct": 20.0}
    v, reason = _accept_e1(r)
    assert v == "BORDERLINE"


def test_e2_pass_when_wr_ge_55_and_avg_gt_0_5():
    r = {"wr_pct": 60.0, "avg_pct": 1.0}
    v, reason = _accept_e2(r)
    assert v == "PASS"


def test_e2_fail_when_wr_lt_40():
    r = {"wr_pct": 35.0, "avg_pct": 0.0}
    v, reason = _accept_e2(r)
    assert v == "FAIL"


def test_e2_borderline_between_40_and_55():
    r = {"wr_pct": 50.0, "avg_pct": 0.2}
    v, reason = _accept_e2(r)
    assert v == "BORDERLINE"


def test_e3_india_pass_when_delta_ge_0_3():
    r = {"avg_pct": -0.5, "dominant_market": "INDIA"}
    # baseline India CURRENT = -0.886 · delta = -0.5 - (-0.886) = +0.386 >= 0.3
    v, reason = _accept_e3(r)
    assert v == "PASS"


def test_e3_usa_pass_when_delta_ge_0_5():
    r = {"avg_pct": 0.0, "dominant_market": "USA"}
    # baseline USA CURRENT = -0.630 · delta = +0.630 >= 0.5
    v, reason = _accept_e3(r)
    assert v == "PASS"


def test_e3_borderline_below_threshold():
    r = {"avg_pct": -0.8, "dominant_market": "INDIA"}
    # delta = -0.8 - (-0.886) = +0.086 < 0.3
    v, reason = _accept_e3(r)
    assert v == "BORDERLINE"


def test_accept_map_has_all_three_e_experiments():
    assert len(ACCEPT_MAP) == 3
    for k in ACCEPT_MAP:
        assert "e1_" in k or "e2_" in k or "e3_" in k
