from datetime import date, datetime

import pytest

from scripts.check_data_freshness import completed_nse_session


@pytest.mark.parametrize(("now", "expected"), [
    ("2026-11-24T18:00:00+05:30", date(2026, 11, 23)),
    ("2026-11-25T10:30:00+05:30", date(2026, 11, 23)),
    ("2026-11-25T16:00:00+05:30", date(2026, 11, 25)),
])
def test_nse_session_excludes_holidays_and_live_bars(now, expected):
    assert completed_nse_session(datetime.fromisoformat(now)) == expected


def test_missing_vendor_equity_bar_is_appended_from_nse_once(tmp_path, monkeypatch):
    from io import BytesIO
    from unittest.mock import Mock
    from zipfile import ZipFile

    import pandas as pd
    import requests

    from india import refresh_data

    raw = tmp_path / "data" / "raw" / "india"
    raw.mkdir(parents=True)
    saved = pd.DataFrame({"open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5],
                          "tick_volume": [20], "spread": [0.0]},
                         index=pd.DatetimeIndex(["2026-11-23"], name="time"))
    path = raw / "XYZ_D1.parquet"
    saved.to_parquet(path)
    saved.to_parquet(raw / "MISSING_D1.parquet")
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("BhavCopy.csv", "TckrSymb,SctySrs,TradDt,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol,ISIN\n"
                         "XYZ,EQ,2026-11-25,10,12,9,11,100,INE001\n"
                         "XYZ,BE,2026-11-25,1,2,1,1,100,INE001\n")
    response = Mock(content=archive.getvalue())
    fetch = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", fetch)
    monkeypatch.setattr(refresh_data, "ROOT", tmp_path)
    monkeypatch.setattr(refresh_data, "RAW", raw)
    session = pd.Timestamp("2026-11-25")

    exceptions = {}
    assert refresh_data._nse_final_fallback(["XYZ", "MISSING"], session, exceptions) == ["XYZ"]
    assert "NSE final EQ row absent" in exceptions["MISSING"]
    pd.testing.assert_frame_equal(pd.read_parquet(raw / "MISSING_D1.parquet"), saved)
    records = pd.read_parquet(path)
    pd.testing.assert_frame_equal(records.iloc[:-1], saved)
    assert records.loc[session, "close"] == 11.0
    assert refresh_data._nse_final_fallback(["XYZ"], session) == []
    assert fetch.call_count == 1
