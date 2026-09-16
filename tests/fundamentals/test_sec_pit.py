"""SEC fundamental lake — PIT, taxonomy and restatement contract.

THE TEST THAT MATTERS
---------------------
    Given an as-of date T, no observation filed after T may be visible.

Everything else here supports that one guarantee. The failure this guards
against is not loud: an adapter that consumes SEC rows as returned looks
correct, produces plausible numbers, and silently leaks restated figures
backward into earlier simulation dates. On the 12-company validation set 23,279
of 36,899 facts are revisions — 63%. Without first-filing resolution, most of
the lake would be information the market did not have.

These tests run offline against fixtures, so they do not depend on SEC
availability or rate limits.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.fundamentals.sec_adapter import (
    CONCEPT_MAP, ACCEPTED_FORMS, PIT_VERIFIED, PIT_UNVERIFIED,
    normalize, first_known, revisions, visible_at, manifest)

ROOT = Path(__file__).resolve().parents[2]


def _facts(rows, concept="Revenues", unit="USD"):
    return {"facts": {"us-gaap": {concept: {"units": {unit: rows}}}}}


# 1 · THE LEAKAGE TEST ────────────────────────────────────────────────
def test_no_observation_filed_after_asof_is_visible():
    rows = [
        {"start": "2020-01-01", "end": "2020-03-31", "val": 100,
         "filed": "2020-05-01", "form": "10-Q", "accn": "a1"},
        {"start": "2020-04-01", "end": "2020-06-30", "val": 200,
         "filed": "2020-08-01", "form": "10-Q", "accn": "a2"},
        {"start": "2020-07-01", "end": "2020-09-30", "val": 300,
         "filed": "2020-11-01", "form": "10-Q", "accn": "a3"},
    ]
    f = normalize(1, _facts(rows), ticker="T")
    vis = visible_at(f, date(2020, 8, 15))
    assert {x.period_end for x in vis} == {"2020-03-31", "2020-06-30"}
    assert all(x.filed_date <= "2020-08-15" for x in vis)
    # the decisive assertion: the Q3 fact is invisible even though its PERIOD
    # end (2020-09-30) is only weeks away
    assert "2020-09-30" not in {x.period_end for x in vis}


def test_leakage_holds_at_every_as_of_in_range():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-%02d" % d, "form": "10-Q", "accn": "x%d" % d}
            for d in range(1, 28)]
    f = normalize(1, _facts(rows), ticker="T")
    for day in range(1, 28):
        asof = date(2020, 5, day)
        for x in visible_at(f, asof):
            assert date.fromisoformat(x.filed_date) <= asof


# 2 · RESTATEMENT / FIRST-FILING ──────────────────────────────────────
def test_first_filing_wins_and_revisions_are_kept_not_merged():
    rows = [
        {"start": "2020-01-01", "end": "2020-03-31", "val": 100,
         "filed": "2020-05-01", "form": "10-Q", "accn": "orig"},
        {"start": "2020-01-01", "end": "2020-03-31", "val": 111,
         "filed": "2021-05-01", "form": "10-K", "accn": "restated"},
    ]
    f = normalize(1, _facts(rows), ticker="T")
    fk = first_known(f)
    assert len(fk) == 1
    assert fk[0].value == 100, "the RESTATED value leaked into the PIT series"
    assert fk[0].filed_date == "2020-05-01"
    rev = revisions(f)
    assert len(rev) == 1 and rev[0].value == 111
    assert rev[0].revision_sequence == 1


def test_restatement_is_invisible_before_it_was_filed():
    rows = [
        {"start": "2020-01-01", "end": "2020-03-31", "val": 100,
         "filed": "2020-05-01", "form": "10-Q", "accn": "orig"},
        {"start": "2020-01-01", "end": "2020-03-31", "val": 111,
         "filed": "2021-05-01", "form": "10-K", "accn": "restated"},
    ]
    f = normalize(1, _facts(rows), ticker="T")
    mid = visible_at(f, date(2020, 9, 1))
    assert [x.value for x in mid] == [100]
    later = visible_at(f, date(2021, 9, 1))
    assert sorted(x.value for x in later) == [100, 111]


# 3 · TAXONOMY DRIFT ──────────────────────────────────────────────────
def test_concept_drift_does_not_create_a_hole():
    """The real AAPL case: Revenues 2016-2018, then a different concept."""
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            {"start": "2016-01-01", "end": "2016-03-31", "val": 10,
             "filed": "2016-05-01", "form": "10-Q", "accn": "r1"}]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"start": "2019-01-01", "end": "2019-03-31", "val": 20,
             "filed": "2019-05-01", "form": "10-Q", "accn": "r2"}]}},
    }}}
    f = [x for x in normalize(1, facts, ticker="T") if x.metric == "revenue"]
    ends = {x.period_end for x in f}
    assert ends == {"2016-03-31", "2019-03-31"}, "concept drift created a hole"
    assert {x.source_concept for x in f} == {
        "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"}


def test_incompatible_concepts_are_not_merged():
    """GrossProfit is not revenue. Mapping must stay auditable."""
    assert "GrossProfit" not in CONCEPT_MAP["revenue"]
    assert CONCEPT_MAP["gross_profit"] == ["GrossProfit"]
    for metric, concepts in CONCEPT_MAP.items():
        assert len(concepts) == len(set(concepts)), "%s has duplicates" % metric


def test_every_fact_records_its_source_concept():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "10-Q", "accn": "a"}]
    for f in normalize(1, _facts(rows), ticker="T"):
        assert f.source_concept and f.source and f.source_version


# 4 · CHRONOLOGY / DATA QUALITY ───────────────────────────────────────
def test_filed_before_period_end_is_not_pit_verified():
    """One real row in 13,620 (WMT cash, end 2012-12-31, filed 2012-03-27)."""
    rows = [{"start": None, "end": "2012-12-31", "val": 5,
             "filed": "2012-03-27", "form": "10-K", "accn": "bad"}]
    f = normalize(1, _facts(rows, concept="CashAndCashEquivalentsAtCarryingValue"),
                  ticker="T")
    assert f, "row was dropped instead of flagged"
    assert f[0].pit_status == PIT_UNVERIFIED
    assert f[0].data_quality == "IMPOSSIBLE_CHRONOLOGY"


def test_available_from_is_never_before_filed_date():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "10-Q", "accn": "a"}]
    for f in normalize(1, _facts(rows), ticker="T"):
        assert f.available_from >= f.filed_date


def test_no_assumed_lag_is_added_when_a_real_date_exists():
    """The mandate forbids assuming a 45-day lag where filing dates exist."""
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "10-Q", "accn": "a"}]
    f = normalize(1, _facts(rows), ticker="T")[0]
    assert f.available_from == "2020-05-01"


# 5 · FORM FILTER + PERIOD IDENTITY ───────────────────────────────────
def test_non_report_forms_are_excluded():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "8-K", "accn": "a"}]
    assert normalize(1, _facts(rows), ticker="T") == []
    assert "8-K" not in ACCEPTED_FORMS


def test_quarter_and_ytd_ending_same_day_are_not_collapsed():
    """Same end date, different start: a quarter and a year-to-date figure are
    different quantities and must not resolve to one another."""
    rows = [
        {"start": "2020-07-01", "end": "2020-09-30", "val": 100,
         "filed": "2020-11-01", "form": "10-Q", "accn": "q3"},
        {"start": "2020-01-01", "end": "2020-09-30", "val": 300,
         "filed": "2020-11-01", "form": "10-Q", "accn": "ytd"},
    ]
    f = first_known(normalize(1, _facts(rows), ticker="T"))
    assert len(f) == 2, "quarter and YTD were collapsed into one period"
    assert sorted(x.value for x in f) == [100, 300]


# 6 · DETERMINISM + MANIFEST ──────────────────────────────────────────
def test_normalization_is_deterministic():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "10-Q", "accn": "a"},
            {"start": "2020-04-01", "end": "2020-06-30", "val": 2,
             "filed": "2020-08-01", "form": "10-Q", "accn": "b"}]
    a = normalize(1, _facts(rows), ticker="T")
    b = normalize(1, _facts(rows), ticker="T")
    assert [x.__dict__ for x in a] == [x.__dict__ for x in b]


def test_manifest_records_the_evidence_ledger_fields():
    rows = [{"start": "2020-01-01", "end": "2020-03-31", "val": 1,
             "filed": "2020-05-01", "form": "10-Q", "accn": "a"}]
    m = manifest(normalize(1, _facts(rows), ticker="T"), "run-1")
    for k in ("run_id", "source", "companies", "facts_total",
              "facts_first_filing", "facts_revisions", "distinct_periods",
              "pit_verified", "pit_unverified", "first_filing_lag_days",
              "concept_map_version", "manifest_hash"):
        assert k in m, "manifest missing %s" % k


# 7 · THE ACQUIRED LAKE, IF PRESENT ───────────────────────────────────
def test_acquired_lake_has_no_leakage_and_real_depth():
    import pandas as pd
    p = ROOT / "data/fundamentals/pit/sec_first_known.parquet"
    if not p.exists():
        pytest.skip("SEC lake not acquired in this checkout")
    df = pd.read_parquet(p)
    assert (df["available_from"] >= df["filed_date"]).all()
    assert df["is_first_filing"].all(), "revisions leaked into the PIT file"
    lag = (pd.to_datetime(df["filed_date"]) - pd.to_datetime(df["period_end"])).dt.days
    bad = df[lag < 0]
    assert (bad["pit_status"] == PIT_UNVERIFIED).all(), \
        "a filed-before-period-end row is still marked PIT_VERIFIED"
    # depth: the whole point of the exercise
    per_co = df.groupby("cik")["period_end"].nunique()
    assert per_co.median() >= 40, "median depth %s periods is not 10y" % per_co.median()
