"""Wave 2C · seven-filter research gates.

These tests defend the three properties that make the wave honest: the
filter set does not overclaim, the unit of analysis is the one that
actually varies, and the incremental test refuses or kills rather than
reporting a number it cannot support.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.research.cohort import seven_filter_ai as sf

ROOT = Path(__file__).resolve().parents[2]


# ── honesty about what is computable ────────────────────────────────────

def test_only_five_filters_claimed():
    assert len(sf.FILTERS) == 5
    assert set(sf.NOT_COMPUTABLE) == {"reasonable_pe", "no_governance_concerns"}


def test_pe_and_governance_are_never_silently_scored():
    for k in sf.NOT_COMPUTABLE:
        assert k not in sf.FILTERS


# ── level / trend / acceleration ────────────────────────────────────────

def _q(rev, ni, eq, debt=None, ocf=None):
    n = len(rev)
    return [{"revenue": rev[i], "net_income": ni[i], "total_equity": eq[i],
             "total_debt": (debt or [None] * n)[i],
             "operating_cashflow": (ocf or [None] * n)[i]} for i in range(n)]


def test_rising_roe_below_threshold_is_flagged_as_the_exception():
    # ROE 12 -> 16 -> 21 on flat equity · the CEO's worked example.
    st = sf.filter_state(_q([100, 110, 120], [12, 16, 21], [100, 100, 100]))
    assert st["roe_gt15"] == 1          # 21% passes at the LEVEL today
    assert st["roe_trend_pp"] > 0
    st2 = sf.filter_state(_q([100, 110, 120], [10, 12, 14], [100, 100, 100]))
    assert st2["roe_gt15"] == 0
    assert st2["roe_rising_but_failing"] == 1


def test_falling_roe_above_threshold_is_flagged():
    st = sf.filter_state(_q([100, 100, 100], [24, 20, 16], [100, 100, 100]))
    assert st["roe_gt15"] == 1
    assert st["roe_trend_pp"] < 0
    assert st["roe_passing_but_falling"] == 1


def test_sparse_balance_sheet_uses_last_known_value_and_records_staleness():
    # Newest period has revenue/NI but no equity - the real provider shape.
    st = sf.filter_state(_q([100, 110, 120], [10, 11, 12], [100, None, None]))
    assert st["roe_pct"] is not None, "must not discard the row"
    assert st["staleness_periods"]["equity"] == 2


def test_missing_metric_yields_none_not_a_false_pass():
    st = sf.filter_state(_q([100, 110], [10, 11], [None, None]))
    assert st["roe_gt15"] is None and st["de_lt05"] is None
    assert st["n_filters_available"] < len(sf.FILTERS)


# ── the unit-of-analysis correction · the core of this wave ─────────────

def test_ticker_constant_predicate_is_detected():
    rows = [{"ticker": "A", "fwd": 1.0, "f": 1}, {"ticker": "A", "fwd": 2.0, "f": 1},
            {"ticker": "B", "fwd": 0.0, "f": 0}, {"ticker": "B", "fwd": -1.0, "f": 0}]
    assert sf._ticker_constant(rows, lambda r: r["f"] == 1) is True


def test_time_varying_predicate_is_not_flagged_constant():
    rows = [{"ticker": "A", "fwd": 1.0, "f": 1}, {"ticker": "A", "fwd": 2.0, "f": 0},
            {"ticker": "B", "fwd": 0.0, "f": 0}, {"ticker": "B", "fwd": -1.0, "f": 1}]
    assert sf._ticker_constant(rows, lambda r: r["f"] == 1) is False


def test_ticker_level_test_counts_names_not_rows():
    # One name repeated 100 times must not become 100 units of evidence.
    rows = ([{"ticker": "A", "fwd": 5.0, "f": 1}] * 100
            + [{"ticker": f"B{i}", "fwd": 0.0, "f": 0} for i in range(10)])
    tl = sf._ticker_level_test(rows, lambda r: r["f"] == 1)
    assert tl["n_tickers_with"] == 1
    assert tl["n_tickers_without"] == 10


def test_row_level_p_is_replaced_when_predicate_is_ticker_constant():
    """The defect this wave exists to prevent · row p=0.0 -> ticker p=0.39."""
    rep = sf.load(ROOT, "india")
    if not rep:
        pytest.skip("india report not generated")
    dt = rep["by_lag"]["45"].get("dimension_tests") or {}
    for k, v in dt.items():
        if v.get("ticker_constant"):
            assert "row_level_p_invalid_because" in v
            assert v["mannwhitney_p"] == (
                v["ticker_level"].get("mannwhitney_p_ticker_level"))


# ── kill switches ───────────────────────────────────────────────────────

def test_incremental_refuses_below_the_event_gate():
    rows = [{"ticker": f"T{i%5}", "fwd": -9.0 if i < 5 else 1.0} for i in range(60)]
    g = sf.incremental_over_r2(rows, -5.0)
    assert g["verdict"].startswith("REFUSED")
    assert "auc_r2_features_only" not in g


def test_incremental_kills_when_ci_spans_zero():
    rep = sf.load(ROOT, "usa")
    if not rep:
        pytest.skip("usa report not generated")
    g = rep["by_lag"]["45"]["incremental_over_r2"]
    if g.get("ci_excludes_zero") is False:
        assert g["verdict"].startswith("KILL MODEL")


def test_bootstrap_resamples_tickers_not_rows():
    src = Path(sf.__file__).read_text(encoding="utf-8")
    assert "idx_by_t" in src and "rng.choice(len(names)" in src


# ── PIT lag sensitivity is part of the wave, not an afterthought ────────

def test_all_three_lags_are_evaluated():
    assert sf.LAGS == [30, 45, 60]


def test_report_states_which_conclusions_flip_with_the_lag():
    for m in ("india", "usa"):
        rep = sf.load(ROOT, m)
        if not rep:
            continue
        ls = rep["lag_sensitivity"]
        assert "dimensions_that_flip_sign" in ls
        assert "per_dimension" in ls
        for k, v in ls["per_dimension"].items():
            assert set(v["delta_mean_pp_by_lag"]) == {"30", "45", "60"}


def test_horizon_mismatch_is_stated():
    rep = sf.load(ROOT, "usa")
    if not rep:
        pytest.skip("usa report not generated")
    c = rep["by_lag"]["45"]["baseline_caveat"]
    assert "MULTI-YEAR" in c and "ten" in c.lower()


# ── research isolation ──────────────────────────────────────────────────

def test_module_touches_no_production_surface():
    src = Path(sf.__file__).read_text(encoding="utf-8")
    for banned in ("dynamic_risk", "detail_xlsx", "telegram",
                   "canonical_daily_lifecycle", "adaptive_rec"):
        assert banned not in src, f"research module must not import {banned}"


def test_reports_declare_research_only():
    for m in ("india", "usa"):
        rep = sf.load(ROOT, m)
        if rep:
            assert "RESEARCH ONLY" in rep["status"]
