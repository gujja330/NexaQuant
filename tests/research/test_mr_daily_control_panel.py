"""M-R · daily control panel property tests."""
from backend.research.mr_daily_control_panel import (
    _verdict, _fmt_pct, _fmt_forward, TARGET_N,
)


def test_verdict_new_when_flagged():
    assert "🆕" in _verdict(0, has_baseline=False, is_new=True)


def test_verdict_researching_when_baseline_no_forward():
    assert "🔬" in _verdict(0, has_baseline=True, is_new=False)


def test_verdict_accumulating_when_forward_below_target():
    v = _verdict(TARGET_N - 1, has_baseline=True, is_new=False)
    assert "accumulating" in v


def test_verdict_ready_when_forward_at_or_above_target():
    v = _verdict(TARGET_N, has_baseline=True, is_new=False)
    assert "ready" in v.lower()


def test_fmt_pct_none():
    assert _fmt_pct(None) == "—"


def test_fmt_pct_value():
    assert _fmt_pct(25.77) == "25.77%"


def test_fmt_forward_zero_shows_progress():
    s = _fmt_forward(0)
    assert "0/" in s and str(TARGET_N) in s


def test_fmt_forward_shows_ratio():
    s = _fmt_forward(50)
    assert f"50/{TARGET_N}" in s
