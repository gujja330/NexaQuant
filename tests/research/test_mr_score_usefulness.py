"""M-R2 · score usefulness property tests."""
from backend.research.mr_score_usefulness import (
    _monotonicity, _verdict, audit_score,
)


def test_monotonicity_up_when_strictly_increasing():
    assert _monotonicity([10, 20, 30, 40, 50]) == "MONOTONIC_UP"


def test_monotonicity_down_when_strictly_decreasing():
    assert _monotonicity([50, 40, 30, 20, 10]) == "MONOTONIC_DOWN"


def test_monotonicity_mixed():
    m = _monotonicity([10, 30, 20, 40, 25])
    assert m in ("MIXED", "MIXED_UP", "MIXED_DOWN", "FLAT")


def test_verdict_keep_when_high_spread_and_correct_direction():
    v = _verdict(20.0, "MONOTONIC_UP", "MONOTONIC_UP")
    assert v == "KEEP"


def test_verdict_anti_signal_when_reversed():
    v = _verdict(20.0, "MONOTONIC_DOWN", "MONOTONIC_UP")
    assert v == "ANTI_SIGNAL"


def test_verdict_prune_when_low_spread():
    v = _verdict(3.0, "MONOTONIC_UP", "MONOTONIC_UP")
    assert v == "PRUNE"


def test_verdict_weak_keep_when_moderate_spread():
    v = _verdict(10.0, "MONOTONIC_UP", "MONOTONIC_UP")
    assert v == "WEAK_KEEP"


def test_audit_score_flags_anti_signal_confidence():
    # High conf → all losers; low conf → all winners
    rows = ([{"confidence_pct": 20, "fwd_5d_pct": +2.0}] * 40
            + [{"confidence_pct": 40, "fwd_5d_pct": +1.5}] * 40
            + [{"confidence_pct": 60, "fwd_5d_pct": +0.5}] * 40
            + [{"confidence_pct": 78, "fwd_5d_pct": -1.5}] * 40
            + [{"confidence_pct": 90, "fwd_5d_pct": -2.0}] * 40)
    from backend.research.mr_score_usefulness import _confidence_key
    a = audit_score(
        rows, "confidence_pct", _confidence_key,
        ["conf_lt30","conf_30_50","conf_50_70","conf_70_85","conf_ge85"],
        "MONOTONIC_UP",
    )
    assert a["verdict"] == "ANTI_SIGNAL"
    assert a["monotonicity"] == "MONOTONIC_DOWN"
