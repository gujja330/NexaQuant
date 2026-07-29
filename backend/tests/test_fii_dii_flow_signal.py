"""Regression: india.fii_dii.flow_signal must not crash when the historical
parquet is missing FII_net / DII_net columns.

Prior bug (2026-07-24 ledger, ingest_fii_dii FAILURE 3× in a row):
    AttributeError: 'int' object has no attribute 'add'
Caused by `df.get("FII_net", 0).add(...)` — `df.get` returns the scalar 0
when the column is absent, and int has no .add() method. This killed the
India daily pipeline every day the parquet was structurally malformed.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import india.fii_dii as fii_dii   # noqa: E402


def _patched_out(monkey_target, df: pd.DataFrame, tmp: Path) -> None:
    df.to_parquet(tmp)
    monkey_target.OUT = tmp


def test_flow_signal_returns_one_when_parquet_missing(tmp_path):
    orig = fii_dii.OUT
    try:
        fii_dii.OUT = tmp_path / "does_not_exist.parquet"
        assert fii_dii.flow_signal() == 1.0
    finally:
        fii_dii.OUT = orig


def test_flow_signal_returns_one_when_history_too_short(tmp_path):
    orig = fii_dii.OUT
    try:
        p = tmp_path / "short.parquet"
        pd.DataFrame({"date": ["2026-01-01"],
                        "FII_net": [10.0], "DII_net": [5.0]}).to_parquet(p)
        fii_dii.OUT = p
        assert fii_dii.flow_signal(window=5) == 1.0
    finally:
        fii_dii.OUT = orig


def test_flow_signal_does_not_crash_when_columns_missing(tmp_path):
    """The exact bug the 2026-07-24 pipeline hit."""
    orig = fii_dii.OUT
    try:
        p = tmp_path / "no_cols.parquet"
        # 10 rows, but no FII_net / DII_net — historically triggered AttributeError
        pd.DataFrame({"date": [f"2026-01-{i:02d}" for i in range(1, 11)]}).to_parquet(p)
        fii_dii.OUT = p
        # Must return a float, not raise
        result = fii_dii.flow_signal(window=5)
        assert isinstance(result, float)
        assert 0.0 < result <= 1.0
    finally:
        fii_dii.OUT = orig


def test_flow_signal_computes_normally_when_columns_present(tmp_path):
    orig = fii_dii.OUT
    try:
        p = tmp_path / "healthy.parquet"
        # 10 days · balanced positive+negative flows
        pd.DataFrame({
            "date":    [f"2026-01-{i:02d}" for i in range(1, 11)],
            "FII_net": [100, -50, 80, -30, 60, -40, 90, -20, 110, -60],
            "DII_net": [30, 20, 40, 50, 25, 35, 45, 15, 55, 20],
        }).to_parquet(p)
        fii_dii.OUT = p
        result = fii_dii.flow_signal(window=5)
        assert isinstance(result, float)
        assert result in (0.7, 0.85, 1.0)
    finally:
        fii_dii.OUT = orig
