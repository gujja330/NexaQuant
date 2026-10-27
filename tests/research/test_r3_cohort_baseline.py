"""The R2 admission-cohort baseline must not flatter itself.

This is the number every future R3 specialist has to beat, so the ways it
could be quietly inflated matter more than the number itself:

  * counting an UNRESOLVED horizon as 0% return
  * calling it "R3 performance" when R3 abstained on all 1,724 India and
    2,300 USA observations (TAKE 0 / AVOID 0)
  * reporting a row-level mean as if rows were independent, when names
    admitted on one morning share that morning's market. India's 5d row
    mean is -0.124% while its DATE-level mean is -0.904% - the row figure
    is flattered by crowded good days.
  * including ACTIVE/ACTIVE+ observations, which are positions already
    held rather than admission decisions (India: 1,557 ACTIVE+ vs 143 NEW)
  * presenting an assumed transaction cost as a measured one
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.research.r3_program import cohort_baseline as cb

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


@pytest.mark.parametrize("market", MARKETS)
def test_only_admission_decisions_are_evaluated(market):
    """ACTIVE / ACTIVE+ are held positions, not decisions."""
    from backend.research.r3_program import shadow
    led = shadow.load_ledger(ROOT, market)
    if not led:
        pytest.skip("no ledger for %s" % market)
    adm = cb.admissions(ROOT, market)
    n_new = sum(1 for r in led if str(r.get("r2_signal")) == "NEW")
    assert len(adm) == n_new, (
        "evaluated %d rows but only %d are NEW admissions - including "
        "ACTIVE/ACTIVE+ inflates the sample with non-decisions"
        % (len(adm), n_new))
    assert len(adm) < len(led), "every row cannot be an admission"


@pytest.mark.parametrize("market", MARKETS)
def test_unresolved_horizons_are_excluded_not_zeroed(market):
    rep = cb.evaluate(ROOT, market)
    if not rep["n_admissions"]:
        pytest.skip("no admissions")
    for h in ("5", "10", "20"):
        b = rep["horizons"][h]
        assert b["n_resolved"] + b["n_unresolved"] == b["n_eligible"], (
            "%s %sd: resolved %d + unresolved %d != eligible %d - a horizon "
            "has been silently dropped or double-counted"
            % (market, h, b["n_resolved"], b["n_unresolved"],
               b["n_eligible"]))
        assert b["strategy"].get("n", 0) == b["n_resolved"], (
            "%s %sd computes statistics over %s values but only %d are "
            "resolved - an unresolved horizon must never enter the mean"
            % (market, h, b["strategy"].get("n"), b["n_resolved"]))


@pytest.mark.parametrize("market", MARKETS)
def test_coverage_is_reported_against_eligible(market):
    rep = cb.evaluate(ROOT, market)
    if not rep["n_admissions"]:
        pytest.skip("no admissions")
    for h in ("5", "10", "20"):
        b = rep["horizons"][h]
        exp = round(100.0 * b["n_resolved"] / b["n_eligible"], 1)
        assert b["coverage_pct"] == exp, (
            "coverage must be resolved/eligible, not resolved/resolved - "
            "otherwise a two-trade sample reads as 100%")


@pytest.mark.parametrize("market", MARKETS)
def test_date_level_inference_is_reported(market):
    """Rows within a date are not independent observations."""
    rep = cb.evaluate(ROOT, market)
    b = rep["horizons"]["5"]
    if not b["strategy"].get("n"):
        pytest.skip("nothing resolved")
    dl = b.get("date_level")
    assert dl and "mean_of_date_means_pct" in dl, (
        "the date-level mean is missing · a row-level mean treats every "
        "name admitted on one morning as an independent observation")
    assert dl["n_dates"] <= b["n_resolved"]


def test_the_report_states_it_is_not_R3_performance():
    rep = cb.evaluate(ROOT, "india")
    assert "NOT" in rep and "R3" in rep["NOT"], (
        "the disclaimer is gone · R3 abstained on every observation, so "
        "this cohort's return is R2's, and mislabelling it is the most "
        "misleading thing this programme could publish")
    assert rep["cohort"].startswith("R2 ADMISSIONS")
    assert rep["production_authority"] is False


def test_transaction_cost_is_labelled_an_assumption():
    rep = cb.evaluate(ROOT, "india")
    assert rep["cost_is_an_assumption"] is True
    b = rep["horizons"]["5"]
    if b["net_of_assumed_cost"]:
        assert "ASSUMED" in b["net_of_assumed_cost"]["note"]
        assert "no actual fills" in b["net_of_assumed_cost"]["note"]


@pytest.mark.parametrize("market", MARKETS)
def test_repeated_tickers_are_surfaced(market):
    """A name admitted three times is three correlated observations."""
    rep = cb.evaluate(ROOT, market)
    if not rep["n_admissions"]:
        pytest.skip("no admissions")
    assert "repeated_tickers" in rep
    assert rep["n_unique_tickers"] <= rep["n_admissions"]


@pytest.mark.parametrize("market", MARKETS)
def test_data_quality_exposes_gaps_and_duplicates(market):
    rep = cb.evaluate(ROOT, market)
    dq = rep["data_quality"]
    for k in ("admission_date_gaps_over_3_business_days",
              "duplicate_outcome_keys",
              "unmatched_admissions_all_horizons"):
        assert k in dq, "%s missing from data_quality" % k
    assert dq["duplicate_outcome_keys"] == 0, (
        "duplicate outcome keys would double-weight a decision")


def test_benchmark_is_matched_from_the_bar_after_admission():
    """Including the admission day's close is look-ahead."""
    idx = pd.bdate_range(start="2026-01-05", periods=9)
    df = pd.DataFrame({"close": [100.0, 110.0, 121.0, 121.0, 121.0,
                                 121.0, 121.0, 121.0, 121.0]}, index=idx)
    v = cb._bench_fwd(df, idx[0].strftime("%Y-%m-%d"), 1)
    assert round(v, 6) == round(100.0 * (121.0 - 110.0) / 110.0, 6), (
        "benchmark entry must be the bar AFTER as-of")


def test_benchmark_returns_none_when_window_is_immature():
    idx = pd.bdate_range(start="2026-01-05", periods=3)
    df = pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=idx)
    assert cb._bench_fwd(df, idx[0].strftime("%Y-%m-%d"), 20) is None


@pytest.mark.parametrize("market", MARKETS)
def test_artifact_is_machine_readable(market, tmp_path):
    rep = cb.evaluate(ROOT, market)
    p = cb.write(tmp_path, market, rep)
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["schema_version"] == cb.SCHEMA_VERSION
    assert back["market"] == market
    assert set(back["horizons"]) == {"5", "10", "20"}


# ── Phase 4 · statistical defensibility ──────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_n_weighted_date_mean_recovers_the_row_mean(market):
    """The aggregation check that proves neither figure is a bug.

    India 5d shows row -0.124% vs date -0.904%. That gap is real:
    busy admission days did better, so equal-weighting dates upweights
    the thin bad ones. If the n-weighted date mean did NOT reproduce the
    row mean, one of the two would simply be miscomputed.
    """
    rep = cb.evaluate(ROOT, market)
    for h in ("5", "10", "20"):
        b = rep["horizons"][h]
        dl = b.get("date_level")
        if not dl:
            continue
        assert abs(dl["n_weighted_date_mean_pct"]
                   - b["strategy"]["mean_pct"]) < 0.01, (
            "%s %sd: n-weighted date mean %.4f != row mean %.4f - the two "
            "aggregations disagree, so one is wrong"
            % (market, h, dl["n_weighted_date_mean_pct"],
               b["strategy"]["mean_pct"]))


@pytest.mark.parametrize("market", MARKETS)
def test_uncertainty_resamples_dates_not_rows(market):
    rep = cb.evaluate(ROOT, market)
    for h in ("5", "10", "20"):
        u = rep["horizons"][h].get("uncertainty")
        if not u:
            continue
        assert "date-block" in u["method"], (
            "resampling rows would understate the interval · rows inside a "
            "date share that date's market move")
        ci = u["ci95_row_mean_pct"]
        assert ci and ci[0] <= rep["horizons"][h]["strategy"]["mean_pct"] \
            <= ci[1], "the point estimate must lie inside its own CI"


@pytest.mark.parametrize("market", MARKETS)
def test_thin_samples_are_labelled_exploratory(market):
    """A 4-date sample must not read as confirmatory however it looks."""
    rep = cb.evaluate(ROOT, market)
    for h in ("5", "10", "20"):
        b = rep["horizons"][h]
        dl, ec = b.get("date_level"), b.get("evidence_class")
        if not dl:
            continue
        assert ec in ("EXPLORATORY", "CONFIRMATORY-ELIGIBLE")
        if dl["n_dates"] < cb.MIN_DATES_CONFIRMATORY:
            assert ec == "EXPLORATORY", (
                "%s %sd has %d dates, below the %d floor, but is labelled %s"
                % (market, h, dl["n_dates"], cb.MIN_DATES_CONFIRMATORY, ec))


@pytest.mark.parametrize("market", MARKETS)
def test_single_admission_dates_are_counted(market):
    """They dominate an equal-weighted date mean."""
    rep = cb.evaluate(ROOT, market)
    for h in ("5", "10", "20"):
        dl = rep["horizons"][h].get("date_level")
        if dl:
            assert "n_single_admission_dates" in dl
            assert dl["n_single_admission_dates"] <= dl["n_dates"]


def test_cost_sensitivity_is_monotonic_and_assumption_labelled():
    rep = cb.evaluate(ROOT, "india")
    cs = rep["horizons"]["5"].get("cost_sensitivity")
    assert cs, "cost sensitivity missing"
    vals = [cs["mean_net_at_%.2f_pct" % c] for c in cb.COST_GRID_PCT]
    assert vals == sorted(vals, reverse=True), (
        "a higher assumed cost must not improve the result")
    assert rep["cost_is_an_assumption"] is True


@pytest.mark.parametrize("market", MARKETS)
def test_alpha_is_computed_on_the_same_observations_as_strategy(market):
    rep = cb.evaluate(ROOT, market)
    for h in ("5", "10", "20"):
        b = rep["horizons"][h]
        if not b["strategy"].get("n"):
            continue
        assert b["alpha"]["n"] == b["benchmark"]["n"], (
            "alpha and benchmark disagree on sample size")
        assert b["alpha"]["n"] == b["n_benchmark_matched"]
