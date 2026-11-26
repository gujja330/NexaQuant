from datetime import date, datetime, timezone

import pandas as pd
import pytest

from usa.scripts.refresh_market_data import _completed_bar_date, _new_bars_on_saved_basis


def test_regular_session_uses_exchange_local_clock_and_dst():
    assert _completed_bar_date(datetime(2026, 11, 24, 20, 59, tzinfo=timezone.utc)) == date(2026, 11, 23)
    assert _completed_bar_date(datetime(2026, 11, 24, 21, 1, tzinfo=timezone.utc)) == date(2026, 11, 24)
    assert _completed_bar_date(datetime(2026, 7, 20, 20, 1, tzinfo=timezone.utc)) == date(2026, 7, 20)


def test_weekend_reuses_last_completed_session():
    assert _completed_bar_date(datetime(2026, 11, 22, 22, tzinfo=timezone.utc)) == date(2026, 11, 20)


def test_thanksgiving_and_early_close():
    assert _completed_bar_date(datetime(2026, 11, 26, 22, tzinfo=timezone.utc)) == date(2026, 11, 25)
    assert _completed_bar_date(datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc)) == date(2026, 11, 25)
    assert _completed_bar_date(datetime(2026, 11, 27, 18, 1, tzinfo=timezone.utc)) == date(2026, 11, 27)


def test_refresh_preserves_raw_history_across_dividend():
    days = pd.bdate_range("2026-11-12", periods=7)
    feed = pd.DataFrame({
        "close": [40.0, 41.0, 42.0, 41.0, 40.0, 39.0, 40.0],
        "adj close": [39.76, 40.754, 41.748, 40.754, 39.76, 39.0, 40.0],
    }, index=days)
    saved = feed[["close"]].iloc[:5].copy()
    result = _new_bars_on_saved_basis(feed, saved)
    pd.testing.assert_frame_equal(result.iloc[:5], saved)
    assert result["close"].iloc[-2:].tolist() == [39.0, 40.0]


def test_refresh_does_not_splice_conflicting_bases():
    days = pd.bdate_range("2026-11-12", periods=6)
    saved = pd.DataFrame({"close": [25.0] * 5}, index=days[:5])
    feed = pd.DataFrame({"close": [50.0] * 6, "adj close": [49.0] * 6}, index=days)
    with pytest.raises(ValueError, match="close basis disagrees"):
        _new_bars_on_saved_basis(feed, saved)
