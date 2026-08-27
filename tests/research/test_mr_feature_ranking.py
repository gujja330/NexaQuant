"""M-R2 · feature ranking property tests."""
from backend.research.mr_feature_ranking import (
    _score_feature, _rsi_bucket, _confidence_bucket, _rank_bucket,
    MIN_BUCKET_N, WR_SPREAD_THRESHOLD_PP,
)


def _rows(bucket_returns: dict) -> list:
    """bucket_returns: {bucket_key: [fwd_5d_pct, ...]}"""
    out = []
    for k, rets in bucket_returns.items():
        for r in rets:
            out.append({"_bucket": k, "fwd_5d_pct": r})
    return out


def test_score_feature_flags_high_spread_as_production_candidate():
    rets_A = [1.0] * 60   # all winners
    rets_B = [-2.0] * 60  # all losers
    rows = _rows({"A": rets_A, "B": rets_B})
    s = _score_feature(rows, lambda r: r.get("_bucket"))
    assert s["wr_spread_pp"] >= WR_SPREAD_THRESHOLD_PP
    assert s["verdict"] == "PRODUCTION_CANDIDATE"


def test_score_feature_returns_insufficient_below_min_bucket_n():
    rows = _rows({"A": [1.0]*10, "B": [-1.0]*10})
    s = _score_feature(rows, lambda r: r.get("_bucket"))
    assert s["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_rsi_bucket_boundaries():
    assert _rsi_bucket(29) == "OVERSOLD"
    assert _rsi_bucket(30) == "WEAK"
    assert _rsi_bucket(44) == "WEAK"
    assert _rsi_bucket(45) == "NEUTRAL"
    assert _rsi_bucket(54) == "NEUTRAL"
    assert _rsi_bucket(55) == "STRONG"
    assert _rsi_bucket(69) == "STRONG"
    assert _rsi_bucket(70) == "OVERBOUGHT"


def test_confidence_bucket_boundaries():
    assert _confidence_bucket(29) == "conf_lt30"
    assert _confidence_bucket(30) == "conf_30_50"
    assert _confidence_bucket(85) == "conf_ge85"


def test_rank_bucket_boundaries():
    assert _rank_bucket(1) == "rank_top3"
    assert _rank_bucket(3) == "rank_top3"
    assert _rank_bucket(4) == "rank_4_7"
    assert _rank_bucket(7) == "rank_4_7"
    assert _rank_bucket(15) == "rank_8_15"
    assert _rank_bucket(16) == "rank_16plus"
    assert _rank_bucket(None) is None


def test_score_feature_handles_missing_bucket_gracefully():
    rows = _rows({"A": [1.0]*30})
    s = _score_feature(rows, lambda r: r.get("_missing"))
    assert s["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert s.get("n_used", 0) == 0
