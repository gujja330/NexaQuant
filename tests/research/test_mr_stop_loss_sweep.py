"""M-R · stop-loss simulator property tests."""
import pandas as pd
import pytest

from backend.research.mr_stop_loss_sweep import _simulate, POLICIES


def _mk_pair(closes):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="B").strftime("%Y-%m-%d")
    return (pd.DataFrame({"close": closes}, index=idx), "close")


def test_fixed_stop_triggers_exactly_at_threshold():
    df, col = _mk_pair([100, 99, 97.5, 94, 96, 99, 101])
    row = {"prediction_date": df.index[0], "entry_price_at_pred": 100.0,
           "stop_at_pred": None, "vol_20d_pct": 2.0}
    res = _simulate(row, (df, col), "FIXED_5")
    assert res["eligible"]
    assert res["stopped"], f"expected stop-hit, got {res}"
    assert res["final_pct"] <= -5.0 + 1e-6, res


def test_fixed_stop_never_triggers_if_never_drops():
    df, col = _mk_pair([100, 101, 102, 103, 104, 105])
    row = {"prediction_date": df.index[0], "entry_price_at_pred": 100.0,
           "stop_at_pred": None, "vol_20d_pct": 2.0}
    res = _simulate(row, (df, col), "FIXED_5")
    assert res["eligible"]
    assert not res["stopped"]
    assert res["final_pct"] > 0


def test_trailing_stop_catches_reversal():
    df, col = _mk_pair([100, 108, 110, 96, 95, 90])
    row = {"prediction_date": df.index[0], "entry_price_at_pred": 100.0,
           "stop_at_pred": None, "vol_20d_pct": 2.0}
    res = _simulate(row, (df, col), "TRAILING_10")
    assert res["eligible"]
    assert res["stopped"]


def test_time_stop_exits_at_horizon_no_matter_what():
    df, col = _mk_pair([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 100, 100, 100])
    row = {"prediction_date": df.index[0], "entry_price_at_pred": 100.0,
           "stop_at_pred": None, "vol_20d_pct": 2.0}
    res = _simulate(row, (df, col), "TIME_STOP_5D")
    assert res["eligible"]
    assert res["days_held"] == 5
    assert res["final_pct"] == round((95-100)/100*100, 3)


def test_all_policies_eligible_with_full_row():
    df, col = _mk_pair([100 + i*0.1 for i in range(30)])
    row = {"prediction_date": df.index[0], "entry_price_at_pred": 100.0,
           "stop_at_pred": 95.0, "vol_20d_pct": 2.0}
    for pol in POLICIES:
        r = _simulate(row, (df, col), pol)
        assert r["eligible"], f"{pol} should be eligible: {r}"
