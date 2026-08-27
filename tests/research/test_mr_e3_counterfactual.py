"""Tests for the 'what would E3 have done?' counterfactual on exits."""
from backend.research.mr_evidence_layer import _what_e3_would_have_done


def test_e3_india_at_horizon_returns_fwd5d():
    r = {"market": "INDIA", "fwd_5d_pct": +1.5, "mfe_pct": 2.0, "mae_pct": -1.0}
    cf = _what_e3_would_have_done(r)
    assert cf["e3_action"] == "TIME_STOP_5D_EXIT_AT_HORIZON"
    assert cf["e3_hypothetical_return_pct"] == 1.5
    assert cf["e3_delta_pct"] == 0.0


def test_e3_usa_trail10_locks_when_mfe_high():
    r = {"market": "USA", "fwd_5d_pct": +5.0, "mfe_pct": +12.0, "mae_pct": -2.0}
    cf = _what_e3_would_have_done(r)
    assert cf["e3_action"] == "TRAIL_10_LOCKED_GAIN"
    # locked = 90% of MFE = 10.8
    assert cf["e3_hypothetical_return_pct"] == 10.8
    assert cf["e3_delta_pct"] == round(10.8 - 5.0, 3)


def test_e3_usa_trail10_stops_when_mae_deep():
    r = {"market": "USA", "fwd_5d_pct": -8.0, "mfe_pct": +1.0, "mae_pct": -12.0}
    cf = _what_e3_would_have_done(r)
    assert cf["e3_action"] == "TRAIL_10_STOPPED_OUT"
    assert cf["e3_hypothetical_return_pct"] == -10.0


def test_e3_usa_trail10_holds_normal_range():
    r = {"market": "USA", "fwd_5d_pct": +2.0, "mfe_pct": +3.0, "mae_pct": -1.5}
    cf = _what_e3_would_have_done(r)
    assert cf["e3_action"] == "TRAIL_10_HELD_TO_HORIZON"
    assert cf["e3_hypothetical_return_pct"] == 2.0


def test_e3_no_data_when_fwd_missing():
    r = {"market": "INDIA", "fwd_5d_pct": None}
    cf = _what_e3_would_have_done(r)
    assert cf["e3_action"] == "NO_DATA"
    assert cf["e3_delta_pct"] is None
