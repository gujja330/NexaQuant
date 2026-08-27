"""M-R2 · loss prevention property tests."""
from backend.research.mr_loss_prevention import (
    _anti_signal_flags, _stop_alternatives_helped, _timing_helped, classify,
)


def test_anti_signal_flags_india_top3_high_conf():
    r = {"rsi_14": 75, "vol_20d_pct": 3.5, "trend": "BELOW_MA200",
         "investability_band": "OK", "confidence_pct": 78, "rank": 2,
         "ma20_dist_pct": -6}
    flags = _anti_signal_flags(r, "india")
    assert "RSI_OVERBOUGHT" in flags
    assert "HIGH_VOL_GE3PCT" in flags
    assert "BELOW_MA200" in flags
    assert "BAND_OK" in flags
    assert "INDIA_CONFIDENCE_ANTI_SIGNAL_70_85" in flags
    assert "INDIA_TOP3_RANK_INVERSION" in flags
    assert "DEEP_BELOW_MA20" in flags


def test_anti_signal_flags_usa_ignores_india_only_flags():
    r = {"confidence_pct": 78, "rank": 2}
    flags = _anti_signal_flags(r, "usa")
    assert "INDIA_CONFIDENCE_ANTI_SIGNAL_70_85" not in flags
    assert "INDIA_TOP3_RANK_INVERSION" not in flags


def test_stop_helped_when_mfe_high_before_deep_mae():
    r = {"mfe_pct": 3.0, "mae_pct": -6.0}
    assert _stop_alternatives_helped(r) == "TRAILING_STOP_WOULD_HAVE_BANKED_GAINS"


def test_stop_helped_when_mae_deep():
    r = {"mfe_pct": 0.5, "mae_pct": -8.0}
    assert _stop_alternatives_helped(r) == "FIXED_5_WOULD_HAVE_CAPPED_LOSS"


def test_timing_helped_when_day1_dropped_then_recovered():
    r = {"fwd_1d_pct": -2.5, "fwd_3d_pct": -1.0, "fwd_5d_pct": +1.5}
    assert _timing_helped(r) == "WAITING_5D_WOULD_HAVE_CAPTURED_BOUNCE"


def test_classify_bear_regime_flags_market_wide():
    r = {"fwd_5d_pct": -2, "confidence_pct": 40}
    c = classify(r, "india", "BEAR")
    assert c["classification"] == "MARKET_WIDE"


def test_classify_high_conf_multi_anti_signal_is_preventable():
    r = {"rsi_14": 75, "vol_20d_pct": 3.5, "trend": "BELOW_MA200",
         "investability_band": "OK", "confidence_pct": 78, "rank": 2}
    c = classify(r, "india", "BULL")
    assert c["classification"] == "PREVENTABLE_HIGH_CONF"


def test_classify_no_flags_returns_unavoidable():
    r = {"rsi_14": 50, "vol_20d_pct": 1.5, "trend": "ABOVE_MA200",
         "investability_band": "QUALITY", "confidence_pct": 55, "rank": 10,
         "fwd_5d_pct": -1.5, "fwd_1d_pct": -0.5, "fwd_3d_pct": -1.0,
         "mfe_pct": 0.3, "mae_pct": -1.8}
    c = classify(r, "india", "BULL")
    assert c["classification"] == "UNAVOIDABLE"
