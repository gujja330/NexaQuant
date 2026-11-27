"""One stock's old bars must not stop the India market. CEO 2026-11-27.

On 2026-11-27 the India refresh died in 10 seconds: a git merge brought
CI's copy of MM_D1.parquet, a different vendor partial for 2026-11-20/23,
and the hardcoded M&M correction RAISED because the bar matched neither its
known partial nor the NSE final. All 228 symbols stopped.
"""
from pathlib import Path

import pandas as pd
import pytest

import india.refresh_data as RD

COLS = ["open", "high", "low", "close", "tick_volume"]
FINAL_20 = (3487.9, 3570, 3479.2, 3545, 3534774)


def _write(tmp_path, bar_20):
    idx = pd.DatetimeIndex([pd.Timestamp("2026-11-19"), pd.Timestamp("2026-11-20")])
    df = pd.DataFrame([(3400, 3450, 3390, 3440, 1_000_000), bar_20], index=idx, columns=COLS)
    p = tmp_path / "MM_D1.parquet"
    df.to_parquet(p)
    return p


@pytest.fixture(autouse=True)
def _audit_root(tmp_path, monkeypatch):
    monkeypatch.setattr(RD, "ROOT", tmp_path / "root")


def _close(p):
    return float(pd.read_parquet(p).loc[pd.Timestamp("2026-11-20"), "close"])


def test_the_known_partial_is_replaced_with_the_nse_final(tmp_path):
    p = _write(tmp_path, (3487.9, 3538, 3479.2, 3510, 1263071))
    RD._reconcile_mm_final_sessions(p, {})
    assert _close(p) == 3545


def test_a_different_partial_of_the_same_session_is_replaced(tmp_path):
    """The 2026-11-27 case: CI's vendor copy, same open, other close."""
    p = _write(tmp_path, (3487.9, 3538, 3479.2, 3527.1, 1895814))
    ex = {}
    RD._reconcile_mm_final_sessions(p, ex)
    assert _close(p) == 3545 and not ex


def test_an_unidentifiable_bar_is_flagged_not_fatal(tmp_path):
    p = _write(tmp_path, (3300.0, 3320, 3290, 3310, 900_000))
    ex = {}
    RD._reconcile_mm_final_sessions(p, ex)          # must not raise
    assert _close(p) == 3310, "unknown data is never overwritten"
    assert "MM" in ex and "review" in ex["MM"]


def test_the_refresh_passes_its_exceptions_through():
    src = (Path(RD.__file__)).read_text(encoding="utf-8")
    assert '_reconcile_mm_final_sessions(RAW / "MM_D1.parquet", exceptions)' in src
