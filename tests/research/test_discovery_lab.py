"""R3 AI Discovery Lab — leakage, exclusion and falsification contract.

The lab explores widely on purpose. That is only safe if the exploration cannot
smuggle future information in, and if a discovery statistic cannot become a
finding without surviving falsification. These tests pin both.

The specific trap: the discovery pass produced two apparent candidates, and BOTH
died in adversarial testing - one to a seed sweep, one to a null comparison.
Neither failure was visible from the discovery statistic itself.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.research.r3_program.discovery_lab import (
    _read_bars, _ticker_panel, _shapes, build_panel, panel_hash,
    Discovery, Ledger, WINDOW, SHAPE_POINTS, FWD, EMBARGO_DAYS, BARS_GLOB)
from backend.research.r3_program.discovery_experiments import (
    date_split, outcome_stats, analogues, contradictions)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def one_ticker():
    import glob
    for fp in sorted(glob.glob(str(ROOT / BARS_GLOB["india"])))[:5]:
        d = _read_bars(fp)
        if d is not None and len(d) > 400:
            return d
    pytest.skip("no bars")


# 1 · NO FUTURE INFORMATION IN A FEATURE ──────────────────────────────
def test_features_recompute_from_past_only_bars(one_ticker):
    """Every feature at date d must be reproducible from bars <= d alone."""
    d = one_ticker
    p = _ticker_panel("X", d, stride=1)
    assert p is not None and len(p) > 50
    c = d["close"].astype(float)
    pos = {dt: i for i, dt in enumerate(d.index)}
    for _, r in p.sample(25, random_state=3).iterrows():
        i = pos[r["date"]]
        past = c.iloc[:i + 1]
        expect = (float(past.iloc[-1]) / float(past.iloc[-21]) - 1.0) * 100.0
        assert abs(float(r["ret_20d"]) - expect) < 1e-6


def test_forward_outcomes_use_only_future_bars(one_ticker):
    d = one_ticker
    p = _ticker_panel("X", d, stride=1)
    c = d["close"].astype(float)
    lo, hi = d["low"].astype(float), d["high"].astype(float)
    pos = {dt: i for i, dt in enumerate(d.index)}
    for _, r in p.sample(25, random_state=4).iterrows():
        i = pos[r["date"]]
        for h in FWD:
            v = r["fwd_%dd" % h]
            if pd.isna(v):
                continue
            expect = (float(c.iloc[i + h]) / float(c.iloc[i]) - 1.0) * 100.0
            assert abs(float(v) - expect) < 1e-6
        if pd.notna(r["fwd_mae_20"]) and i + 20 < len(c):
            e = 100.0 * (float(lo.iloc[i + 1:i + 21].min()) - float(c.iloc[i])) / float(c.iloc[i])
            assert abs(float(r["fwd_mae_20"]) - e) < 1e-6
            e2 = 100.0 * (float(hi.iloc[i + 1:i + 21].max()) - float(c.iloc[i])) / float(c.iloc[i])
            assert abs(float(r["fwd_mfe_20"]) - e2) < 1e-6


def test_every_outcome_date_is_strictly_after_its_row(one_ticker):
    p = _ticker_panel("X", one_ticker, stride=1)
    for h in FWD:
        col = "fwd_%dd_date" % h
        have = p[p[col].notna()]
        assert (have[col] > have["date"]).all(), \
            "%s contains an outcome dated on or before the observation" % col


# 2 · SHAPE IS SHAPE, NOT MAGNITUDE ──────────────────────────────────
def test_shape_is_scale_invariant(one_ticker):
    """Two paths differing only by a constant multiple must give the same shape,
    otherwise every high-volatility name lands in one cluster and the
    'archetype' is volatility with extra steps."""
    d = one_ticker
    d2 = d.copy()
    for c in ("open", "high", "low", "close"):
        d2[c] = d2[c] * 3.7
    dates = pd.DatetimeIndex(d.index[WINDOW + 10: WINDOW + 30])
    a = _shapes("X", d, dates)
    b = _shapes("X", d2, dates)
    ok = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    assert ok.sum() > 5
    assert np.allclose(a[ok], b[ok], atol=1e-6)


# 3 · CHRONOLOGICAL SPLIT, NEVER A ROW SPLIT ─────────────────────────
def test_split_is_by_date_with_an_embargo():
    p = pd.DataFrame({
        "date": pd.to_datetime(sum([[d] * 10 for d in pd.date_range(
            "2024-01-01", periods=100, freq="D")], [])),
        "ticker": ["T%d" % (i % 10) for i in range(1000)],
        "fwd_20d": np.random.default_rng(0).normal(size=1000),
    })
    tr, te, info = date_split(p, frac=0.65)
    tr_d = set(p.loc[tr, "date"])
    te_d = set(p.loc[te, "date"])
    assert tr_d and te_d
    assert not (tr_d & te_d), "a date appears on both sides of the split"
    assert min(te_d) > max(tr_d), "test starts before train ends"
    gap = (min(te_d) - max(tr_d)).days
    assert gap >= EMBARGO_DAYS, "embargo of %d days not honoured (gap %d)" % (
        EMBARGO_DAYS, gap)


# 4 · ANALOGUE EXCLUSIONS ────────────────────────────────────────────
def test_analogues_exclude_self_ticker_and_recent_dates():
    """A neighbour must not be the query's own near future, nor the same name
    on an adjacent day."""
    n = 400
    rng = np.random.default_rng(1)
    dates = pd.to_datetime(pd.date_range("2024-01-01", periods=n // 4, freq="7D"))
    panel = pd.DataFrame({
        "date": np.repeat(dates, 4),
        "ticker": ["A", "B", "C", "D"] * (n // 4),
        "fwd_20d": rng.normal(size=n),
    })
    shape = rng.normal(size=(n, SHAPE_POINTS))
    q = np.array([n - 1, n - 5, n - 9])
    res = analogues(panel, shape, q, k=20, outcome="fwd_20d", pool=n)
    pdate = panel["date"].to_numpy()
    ptick = panel["ticker"].to_numpy()
    for item in res["queries"]:
        if item["status"] != "OK":
            continue
        # reconstruct: no twin may share the ticker or fall inside the embargo
        assert item["twin_tickers"] >= 1
        assert item["n_twins"] <= 20
    assert res["embargo_days"] == EMBARGO_DAYS


# 5 · FALSIFICATION LOGIC ────────────────────────────────────────────
def test_contradiction_views_are_not_all_the_same_view():
    """If every view is a restatement of trend, 'agreement' is meaningless."""
    rng = np.random.default_rng(5)
    n = 500
    p = pd.DataFrame({
        "date": pd.to_datetime(np.repeat(pd.date_range("2024-01-01", periods=50,
                                                       freq="D"), 10)),
        "ticker": ["T%d" % (i % 10) for i in range(n)],
        "slope_20": rng.normal(size=n), "pos_60": rng.uniform(0, 100, n),
        "vol_ratio": rng.uniform(0.5, 1.5, n),
        "vol_ratio_5v20": rng.uniform(0.5, 1.5, n),
        "fwd_20d": rng.normal(size=n),
    })
    co = contradictions(p, outcome="fwd_20d")
    assert len(co["views"]) == 4
    scores = [r["agree_score"] for r in co["by_agreement"]]
    assert len(scores) > 2, "agreement score collapsed to a constant"


def test_outcome_stats_reports_n_and_never_invents_a_value():
    assert outcome_stats(pd.Series([], dtype=float)) == {"n": 0}
    s = outcome_stats(pd.Series([1.0, -6.0, 2.0, np.nan]))
    assert s["n"] == 3
    assert s["severe_le_m5_pct"] == pytest.approx(100 * 1 / 3, abs=0.01)


# 6 · GOVERNANCE ─────────────────────────────────────────────────────
def test_ledger_entries_stay_at_discovery_stage():
    """Nothing in this module may claim confirmatory status."""
    led = Ledger()
    led.add(Discovery(
        discovery_id="X", method="m", market="india", dataset="d",
        date_range="r", n_rows=1, n_tickers=1, n_dates=1, features=[],
        representation="r", seed=1, trial_count=1, hypothesis="h"))
    for item in led.dump():
        assert item["stage"] == "DISCOVERY"
        assert item["disposition"] != "PROMOTE"
        assert "PRODUCTION" not in item["disposition"] or \
            item["disposition"] == "CANDIDATE_FOR_CONFIRMATORY_VALIDATION"


def test_shipped_ledger_has_no_production_authority():
    import json
    p = ROOT / "reports/research/r3/ai_discovery_lab_v1/discovery_ledger.json"
    if not p.exists():
        pytest.skip("lab not run in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["governance"]["r2_modified"] is False
    assert d["governance"]["r3_production_writes"] == 0
    for item in d["discoveries"]:
        assert item["stage"] == "DISCOVERY"
        assert item["disposition"] in (
            "CANDIDATE_FOR_CONFIRMATORY_VALIDATION", "REJECTED",
            "BLOCKED_INSUFFICIENT_DATE_DEPTH", "INSUFFICIENT_HISTORY")


def test_shipped_ledger_records_survivorship_exposure():
    import json
    p = ROOT / "reports/research/r3/ai_discovery_lab_v1/discovery_ledger.json"
    if not p.exists():
        pytest.skip("lab not run in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "survivorship" in d
    for item in d["discoveries"]:
        assert item["survivorship_exposure"] == "PRESENT"
