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


# 5 · ASSOCIATIONS ARE DISPOSITIONED BY DATE DEPTH, NOT BY rho ────────
def test_associations_are_blocked_at_shallow_date_depth():
    """A cross-sectional correlation at one outcome date describes that
    morning. It must be computed (so the machinery is auditable) and then
    blocked - never reported as a relationship."""
    from backend.research.r3_program.historical_replay import family_associations
    df = pd.DataFrame({
        "market": ["india"] * 40, "prediction_as_of": ["2026-09-15"] * 40,
        "ticker": ["T%d" % i for i in range(40)],
        "rsi_14": list(range(40)),
        "fwd_1d": [i * 0.1 for i in range(40)],
    })
    fa = family_associations(df, "fwd_1d")
    assert fa["status"] == "DESCRIPTIVE_ONLY"
    assert fa["effective_outcome_dates"] == 1
    tech = fa["families"]["technical"]
    # a perfect monotone relationship still does not become a finding
    assert abs(tech["strongest"][0]["spearman_rho"]) > 0.99
    assert tech["disposition"] == "BLOCKED_INSUFFICIENT_DATE_DEPTH"
    assert "NOT findings" in fa["warning"]


def test_associations_never_emit_a_p_value():
    from backend.research.r3_program.historical_replay import family_associations
    df = pd.DataFrame({
        "market": ["usa"] * 30, "prediction_as_of": ["2026-09-15"] * 30,
        "ticker": ["T%d" % i for i in range(30)],
        "macro_vix": list(range(30)), "fwd_1d": [i * 0.2 for i in range(30)]})
    fa = family_associations(df, "fwd_1d")
    blob = str(fa).lower()
    assert "p_value" not in blob and "raw_p" not in blob


def test_family_of_maps_columns_to_the_right_family():
    from backend.research.r3_program.historical_replay import family_of
    assert family_of("rsi_14") == "technical"
    assert family_of("macro_vix") == "macro"
    assert family_of("sector_rank") == "sector"
    assert family_of("fund_market_cap_log") == "fundamental"
    assert family_of("confidence_pct") == "portfolio"
    assert family_of("totally_unknown_column") is None


# 6 · UNINFORMATIVE COLUMNS ARE NOT BUCKETED ─────────────────────────
def test_a_constant_column_is_not_treated_as_a_grouping():
    """`sector` is the literal string 'Unknown' on all 516 USA rows and null on
    all 456 India rows. Bucketing on it would invent groups."""
    from backend.research.r3_program.historical_replay import _informative
    assert not _informative(pd.Series(["Unknown"] * 100))
    assert not _informative(pd.Series([None] * 100))
    assert not _informative(pd.Series(["IT"] * 100))
    assert _informative(pd.Series(["IT", "BANK", "IT"]))
