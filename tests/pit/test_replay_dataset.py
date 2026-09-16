"""R3 replay dataset — admission, identity and leakage contract.

THE DEFECT THIS LOCKS DOWN
--------------------------
The decisions sidecar is keyed by `position_id`, not by `ticker`. On 2026-09-15
five USA names (CRM, GRMN, VLO, PLTR, BMY) and two India names (KOTAKBANK,
COALINDIA) were held simultaneously by a legacy R1 position and an R2 one. A
left merge on ticker therefore fanned one feature row into two and the USA
matrix produced 521 rows from 516 tickers.

That inflation is quiet and dangerous: it does not raise an error, it does not
look wrong in a head(), and it silently doubles the weight of exactly the names
that carry two engines' worth of history. Every rate computed downstream would
have been biased toward them.

So the row-count identity below is not a sanity check, it is the contract:
one sealed feature row in, one replay row out.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.research.r3_program.replay_dataset import (
    build, build_date, HORIZONS)
from backend.memory.daily_snapshot import snapshot_dir

ROOT = Path(__file__).resolve().parents[2]


def _sealed(market: str) -> list[str]:
    d = ROOT / "history" / market
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir()
                  if p.is_dir() and (p / "SEALED").exists())


@pytest.fixture(scope="module")
def built():
    return build(ROOT)


# 1 · THE FAN-OUT REGRESSION ──────────────────────────────────────────
def test_one_sealed_feature_row_yields_exactly_one_replay_row(built):
    _, man = built
    admitted = [p for p in man["per_date"] if p["admitted"]]
    if not admitted:
        pytest.skip("no admitted date")
    for p in admitted:
        assert p["rows"] == p["technical_rows"], (
            "%s/%s fanned %d feature rows into %d replay rows"
            % (p["market"], p["as_of"], p["technical_rows"], p["rows"]))


def test_ticker_is_unique_within_each_as_of(built):
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    d = df.groupby(["market", "as_of"])["ticker"].agg(["count", "nunique"])
    bad = d[d["count"] != d["nunique"]]
    assert bad.empty, "duplicate tickers within an as_of:\n%s" % bad


def test_a_name_held_by_both_engines_appears_once_with_a_flag(built):
    """The exact case that caused the inflation."""
    df, _ = built
    if df.empty or "legacy_r1_open" not in df.columns:
        pytest.skip("empty dataset")
    both = df[(df["in_sealed_decisions"] == 1) & (df["legacy_r1_open"] == 1)]
    if both.empty:
        pytest.skip("no dual-engine name in the sealed window")
    for (m, a, t), g in both.groupby(["market", "as_of", "ticker"]):
        assert len(g) == 1, "%s/%s %s appears %d times" % (m, a, t, len(g))


# 2 · ADMISSION IS GATED BY THE SEAL, NOT BY FILE PRESENCE ────────────
def test_a_date_that_fails_the_replay_gate_contributes_no_rows(built):
    df, man = built
    refused = {(r["market"], r["as_of"]) for r in man["dates_refused"]}
    if not refused:
        pytest.skip("every sealed date was admitted")
    if df.empty:
        return
    present = set(map(tuple, df[["market", "as_of"]].drop_duplicates().values))
    assert not (refused & present), \
        "a refused date leaked rows into the dataset: %s" % (refused & present)


def test_refusal_always_carries_a_named_reason(built):
    _, man = built
    for r in man["dates_refused"]:
        assert r["reason"], "%s/%s refused without a reason" % (r["market"], r["as_of"])


def test_unsealed_date_is_refused_not_rebuilt():
    df, prov = build_date(ROOT, "india", "2019-01-04")
    assert df.empty
    assert prov["admitted"] is False
    assert prov.get("refused") == "GATE_NOT_MET"


# 3 · LEAKAGE ─────────────────────────────────────────────────────────
def test_forward_outcomes_use_only_bars_after_the_asof(built):
    """Recompute one row's fwd_1d independently and require the same answer
    from a strictly-after window."""
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    have = df[df["fwd_1d"].notna()]
    if have.empty:
        pytest.skip("no closed forward window yet")
    r = have.iloc[0]
    from backend.research.r3_program.replay_dataset import _bars
    b = _bars(ROOT, r["market"], r["ticker"])
    a = pd.Timestamp(r["as_of"])
    past, fut = b[b.index <= a], b[b.index > a]
    assert fut.index.min() > a, "the outcome window starts on or before the as_of"
    p0 = float(past["close"].iloc[-1])
    expect = 100.0 * (float(fut["close"].iloc[0]) - p0) / p0
    assert abs(float(r["fwd_1d"]) - expect) < 1e-6


def test_an_unclosed_horizon_is_null_never_a_shorter_window(built):
    """A 20-day return must not be a 1-day return wearing a 20-day label."""
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    for h in HORIZONS:
        col = "fwd_%dd" % h
        filled = df[df[col].notna()]
        assert (filled["n_fwd_bars"] >= h).all(), \
            "%s is populated on rows with fewer than %d forward bars" % (col, h)


def test_outcome_coverage_is_reported_not_assumed(built):
    _, man = built
    if man["rows"] == 0:
        pytest.skip("empty dataset")
    for h in HORIZONS:
        assert "fwd_%dd" % h in man["outcome_coverage"]


# 4 · EFFECTIVE UNITS ─────────────────────────────────────────────────
def test_effective_units_counts_dates_not_rows(built):
    """The constraint that has blocked every R3 wave. 972 rows across 3 dates
    is 3 units, and the manifest must say so."""
    df, man = built
    assert man["effective_units"] == man["dates_admitted"]
    if not df.empty:
        assert man["effective_units"] == len(
            df[["market", "as_of"]].drop_duplicates())
        assert man["effective_units"] < man["rows"], \
            "effective units must never be confused with row count"


def test_provenance_records_the_schema_fingerprint(built):
    _, man = built
    for p in man["per_date"]:
        if p["admitted"]:
            assert p.get("feature_schema_fingerprint"), \
                "%s/%s admitted without a schema fingerprint" % (p["market"], p["as_of"])


# 5 · SUBSTRATE HOLES ARE REPORTED, NOT ABSORBED ─────────────────────
def test_empty_columns_are_reported_as_holes_not_treated_as_signal(built):
    """`sma_200` and the `sector_*` relatives are 100% null in BOTH markets'
    sealed memory. A wave that reads such a column gets nulls, and "no
    relationship" must never be reported when the truth is "no data"."""
    df, man = built
    if df.empty:
        pytest.skip("empty dataset")
    holes = man.get("substrate_holes") or {}
    assert holes, "manifest omitted the substrate-hole census"
    for m, g in df.groupby("market"):
        empty = {c for c in g.columns if g[c].isna().all()}
        assert empty == set(holes[str(m)]["fully_empty_columns"]), \
            "%s hole census disagrees with the data" % m


def test_a_stacked_column_keeps_a_real_dtype(built):
    """India has no earnings/institutional/insider coverage, so those columns
    are all-None there. Stacking must not turn a numeric feature into object."""
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    import pandas as pd
    for c in ("inst_pct_owned", "earn_last_surprise_pct", "macro_vix"):
        if c not in df.columns:
            continue
        assert pd.api.types.is_numeric_dtype(df[c]), \
            "%s stacked to %s instead of a numeric dtype" % (c, df[c].dtype)


# 6 · THE TICKER-KEY REGRESSION ──────────────────────────────────────
def test_india_decisions_actually_join(built):
    """India's technical matrix stores AARTIIND.NS; the decisions sidecar stores
    AARTIIND. Joining on the raw column matched 0 of 56 India decisions and
    produced an empty portfolio link on every India date - while USA, which has
    no suffix, matched perfectly and made the join look correct.

    A silent 0-match join is indistinguishable downstream from "held nothing".
    """
    df, man = built
    if df.empty:
        pytest.skip("empty dataset")
    for p in man["per_date"]:
        if not p["admitted"] or not p.get("decision_rows_r2"):
            continue
        assert p["decision_match"] > 0, (
            "%s/%s joined 0 of %d R2 decisions - broken key, not an empty book"
            % (p["market"], p["as_of"], p["decision_rows_r2"]))
        got = int(df[(df["market"] == p["market"])
                     & (df["prediction_as_of"] == p["as_of"])]["in_sealed_decisions"].sum())
        assert got > 0, "%s/%s has %d sealed R2 decisions but 0 joined rows" % (
            p["market"], p["as_of"], p["decision_rows_r2"])


def test_join_key_is_suffix_invariant():
    from backend.research.r3_program.replay_dataset import _tkey
    assert _tkey("AARTIIND.NS") == _tkey("AARTIIND") == "AARTIIND"
    assert _tkey("acc.bo") == "ACC"
    assert _tkey(" CRM ") == "CRM"


# 7 · OUTCOME DATES ARE NEVER MERGED WITH PREDICTION DATES ───────────
def test_every_outcome_date_strictly_postdates_the_prediction(built):
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    for h in HORIZONS:
        c = "fwd_%dd_outcome_date" % h
        assert c in df.columns, "%s has no outcome_date column" % c
        have = df[df[c].notna()]
        if have.empty:
            continue
        assert (have[c].astype(str) > have["prediction_as_of"].astype(str)).all(), \
            "%s contains an outcome dated on or before its prediction" % c


def test_mae_mfe_report_their_own_window_length(built):
    """A 2-bar excursion must never be readable as a 60-bar one."""
    df, _ = built
    if df.empty:
        pytest.skip("empty dataset")
    have = df[df["mfe_pct"].notna()]
    if have.empty:
        pytest.skip("no forward window yet")
    assert (have["mae_mfe_window_bars"] > 0).all()
    assert (have["time_to_mfe_d"] <= have["mae_mfe_window_bars"]).all()
    assert (have["time_to_mae_d"] <= have["mae_mfe_window_bars"]).all()
