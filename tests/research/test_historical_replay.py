"""R3 historical replay — gate behaviour at low date depth.

The interesting property of a replay harness is not what it reports when the
evidence is plentiful. It is what it refuses to report when the evidence is
thin. These tests pin the refusals.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.research.r3_program.historical_replay import (
    oos_gate, tier_for, quality_gate, _sector_excl_mean,
    MIN_DATES_FOR_OOS, EMBARGO_DAYS)


# 1 · LEAVE-TARGET-OUT ────────────────────────────────────────────────
def test_a_stock_never_contributes_to_its_own_sector_aggregate():
    """Otherwise a large name partly predicts itself and the 'sector effect'
    is that name's own return wearing a sector label."""
    df = pd.DataFrame({
        "market": ["india"] * 4,
        "prediction_as_of": ["2026-09-15"] * 4,
        "sector": ["IT", "IT", "IT", "BANK"],
        "v": [10.0, 20.0, 30.0, 99.0],
    })
    got = _sector_excl_mean(df, "sector", "v")
    # IT row 0 must see the mean of {20,30} = 25, not {10,20,30} = 20
    assert got.iloc[0] == pytest.approx(25.0)
    assert got.iloc[1] == pytest.approx(20.0)
    assert got.iloc[2] == pytest.approx(15.0)
    # a lone member of its sector has no leave-one-out aggregate at all
    assert pd.isna(got.iloc[3])


def test_leave_target_out_differs_from_the_naive_mean():
    df = pd.DataFrame({
        "market": ["usa"] * 3, "prediction_as_of": ["2026-09-15"] * 3,
        "sector": ["X"] * 3, "v": [1.0, 2.0, 60.0]})
    excl = _sector_excl_mean(df, "sector", "v")
    naive = df["v"].mean()
    assert excl.iloc[2] != pytest.approx(naive), \
        "the outlier is still inside the aggregate it is compared against"


# 2 · THE OOS REFUSAL ─────────────────────────────────────────────────
def test_oos_is_refused_below_the_date_floor():
    g = oos_gate(3)
    assert g["attempted"] is False
    assert g["disposition"] == "BLOCKED_INSUFFICIENT_DATE_DEPTH"
    assert g["reason"]
    assert g["embargo_days"] == EMBARGO_DAYS


def test_oos_floor_is_not_silently_lowered():
    assert MIN_DATES_FOR_OOS >= 20
    assert oos_gate(MIN_DATES_FOR_OOS - 1)["attempted"] is False
    assert oos_gate(MIN_DATES_FOR_OOS)["attempted"] is True


# 3 · THE CLOCK COUNTS DATES, NOT ROWS ────────────────────────────────
def test_tier_advances_on_dates_only():
    assert tier_for(3) == "OBSERVATION"
    assert tier_for(5) == "HYPOTHESIS"
    assert tier_for(15) == "RESEARCH SIGNAL"
    assert tier_for(30) == "STRONGER EVIDENCE"
    assert tier_for(50) == "VALIDATION CANDIDATE"


# 4 · THE QUALITY GATE MEASURES, IT DOES NOT ASSERT ───────────────────
def test_quality_gate_reports_effective_units_not_rows():
    df = pd.DataFrame({
        "market": ["india"] * 100,
        "prediction_as_of": ["2026-09-15"] * 100,
        "ticker": ["T%d" % i for i in range(100)],
        "feature_schema_version": ["abc"] * 100,
        "fwd_1d": [0.1] * 100,
        "fwd_1d_outcome_date": ["2026-09-16"] * 100,
    })
    q = quality_gate(df)
    assert q["rows"] == 100
    assert q["effective_date_units"] == 1, \
        "100 rows from one morning must count as one unit"
    assert q["pit_violations"] == 0


def test_quality_gate_catches_an_outcome_dated_before_its_prediction():
    df = pd.DataFrame({
        "market": ["usa"], "prediction_as_of": ["2026-09-15"], "ticker": ["AAPL"],
        "feature_schema_version": ["abc"], "fwd_1d": [1.0],
        "fwd_1d_outcome_date": ["2026-09-14"],      # leaked
    })
    q = quality_gate(df)
    assert q["pit_violations"] == 1
    assert q["verdict"] == "FAIL"
