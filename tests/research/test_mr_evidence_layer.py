"""Tests for the evidence & learning layer."""
from backend.research.mr_evidence_layer import (
    _rsi_bucket, _ma20_bucket, _rank_bucket, _outcome_label,
    _mfe_capture_ratio, _avoidable_loss, _research_signals,
)


def test_rsi_bucket_boundaries():
    assert _rsi_bucket(29) == "OVERSOLD"
    assert _rsi_bucket(30) == "WEAK"
    assert _rsi_bucket(44) == "WEAK"
    assert _rsi_bucket(45) == "NEUTRAL"
    assert _rsi_bucket(69) == "STRONG"
    assert _rsi_bucket(70) == "OVERBOUGHT"
    assert _rsi_bucket(None) is None


def test_ma20_bucket_boundaries():
    assert _ma20_bucket(-6) == "lt-5"
    assert _ma20_bucket(-3) == "-5_-1"
    assert _ma20_bucket(0) == "-1_+1"
    assert _ma20_bucket(3) == "+1_+5"
    assert _ma20_bucket(6) == "ge+5"


def test_rank_bucket():
    assert _rank_bucket(1) == "top3"
    assert _rank_bucket(4) == "rank_4_7"
    assert _rank_bucket(15) == "rank_8_15"
    assert _rank_bucket(16) == "rank_16plus"
    assert _rank_bucket(None) is None
    assert _rank_bucket("bad") is None


def test_outcome_label():
    assert _outcome_label(+2.0) == "WIN"
    assert _outcome_label(-2.0) == "LOSS"
    assert _outcome_label(0.0) == "FLAT"
    assert _outcome_label(None) is None


def test_mfe_capture_ratio():
    assert _mfe_capture_ratio(2.0, 4.0) == 0.5
    assert _mfe_capture_ratio(0, 0) is None
    assert _mfe_capture_ratio(None, 4.0) is None
    assert _mfe_capture_ratio(2.0, 0) is None


def test_avoidable_loss_deep_mae():
    r = {"fwd_5d_pct": -2.0, "mae_pct": -4.0, "loss_classification": None}
    assert _avoidable_loss(r) is True


def test_avoidable_loss_preventable_classification():
    r = {"fwd_5d_pct": -1.0, "mae_pct": -2.0,
         "loss_classification": "PREVENTABLE_HIGH_CONF"}
    assert _avoidable_loss(r) is True


def test_avoidable_loss_not_a_loss():
    r = {"fwd_5d_pct": +1.0, "mae_pct": -2.0}
    assert _avoidable_loss(r) is None


def test_research_signals_e2_boost():
    r = {"runner":"R2","rank":5,"rsi_14":62}
    signals = _research_signals(r)
    assert any(s.startswith("E2_BOOST_R2_STRONG") for s in signals)


def test_research_signals_e1_filter():
    r = {"runner":"R1","confidence_pct":78,"rank":10}
    signals = _research_signals(r)
    assert any(s.startswith("E1_REJECT_R1_WEAK") for s in signals)
