"""M-R · USA MID-cap tilt (X3) rule property tests."""
from backend.research.mr_experiment_runner import rule_X3_usa_mid_cap_tilt


def test_x3_boosts_mid_cap():
    r = {"cap_bucket": "MID"}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is True
    assert d == "BOOST_TO_MID_TILT"


def test_x3_demotes_large_cap():
    r = {"cap_bucket": "LARGE"}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is True
    assert d == "DEMOTE_FROM_LARGE_TILT"


def test_x3_holds_small_cap():
    r = {"cap_bucket": "SMALL"}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is False
    assert d == "HOLD_SMALL"


def test_x3_silent_when_cap_unknown():
    r = {"cap_bucket": None}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is False
    assert d == "NO_CAP_INFO"


def test_x3_ignores_when_market_field_shows_india():
    r = {"cap_bucket": "MID", "market": "INDIA"}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is False
    assert d == "NOT_USA_SCOPE"


def test_x3_fires_on_usa_market_hint():
    r = {"cap_bucket": "MID", "market": "USA"}
    d, fired, _ = rule_X3_usa_mid_cap_tilt(r)
    assert fired is True
    assert d == "BOOST_TO_MID_TILT"
