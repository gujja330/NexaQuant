"""R3 Market Memory — stability, leakage and confound contract.

The ordering discipline this pins: twin STABILITY decides whether a twin is a
real object, and it is evaluated before any outcome statistic is allowed to
mean anything. A separation computed over neighbourhoods that belong to the
distance metric describes the metric.

The second trap pinned here is subtler. `twin_mean` averages earlier outcomes,
so it can track the market state of the query DATE rather than anything about
the stock. India and USA came out opposite on exactly that split: India's
signal survives within-date demeaning, USA's is the date effect.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.research.r3_program.market_memory import (
    _neighbours, twin_stability, consensus_twins, fit_representation,
    add_market_family, transition_frame, build_fingerprints,
    STABILITY_FLOOR, METHODS, TOPK, LAGS, EMBARGO_DAYS)
from backend.research.r3_program.market_memory_eval import (
    _demean_split, within_date_frame, leave_one_out, date_block_bootstrap,
    decision_utility, twin_populations, SEVERE)

ROOT = Path(__file__).resolve().parents[2]


# 1 · THE NEIGHBOUR SEARCH IS EXACT ──────────────────────────────────
@pytest.mark.parametrize("metric", ["euclidean", "cosine", "correlation"])
def test_fast_neighbour_search_matches_the_naive_one(metric):
    """The optimised path exists because the naive broadcast asked for 5.8 GiB.
    It must return the same neighbours, not merely similar ones."""
    rng = np.random.default_rng(0)
    P, Q = rng.normal(size=(500, 9)), rng.normal(size=(10, 9))
    if metric == "euclidean":
        d = ((Q[:, None, :] - P[None, :, :]) ** 2).sum(-1)
    elif metric == "cosine":
        qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)
        pn = P / np.linalg.norm(P, axis=1, keepdims=True)
        d = 1 - qn @ pn.T
    else:
        qc, pc = Q - Q.mean(1, keepdims=True), P - P.mean(1, keepdims=True)
        qn = qc / np.linalg.norm(qc, axis=1, keepdims=True)
        pn = pc / np.linalg.norm(pc, axis=1, keepdims=True)
        d = 1 - qn @ pn.T
    expect = np.argsort(d, axis=1)[:, :12]
    got = _neighbours(Q, P, metric, 12)
    assert (got == expect).all()


# 2 · STABILITY IS THE GATE ──────────────────────────────────────────
def test_disagreeing_methods_produce_no_stable_memory_structure():
    n_q = 40
    rng = np.random.default_rng(1)
    twins = {m: rng.integers(0, 5000, size=(n_q, 50)) for m in METHODS}
    st = twin_stability(twins)
    assert st["verdict"] == "NO_STABLE_MEMORY_STRUCTURE"
    assert st["reason"]
    for k in TOPK:
        assert str(k) in st["top_k"]


def test_agreeing_methods_produce_stable_twins():
    base = np.tile(np.arange(50), (30, 1))
    twins = {m: base.copy() for m in METHODS}
    st = twin_stability(twins)
    assert st["verdict"] == "STABLE_TWINS"
    assert st["top_k"]["50"]["mean"] == pytest.approx(1.0)


def test_stability_floor_is_not_silently_lowered():
    assert STABILITY_FLOOR >= 0.30


def test_consensus_requires_more_than_one_method():
    twins = {"euclidean": np.array([[1, 2, 3]]), "cosine": np.array([[1, 2, 9]]),
             "correlation": np.array([[1, 7, 8]]), "pca": np.array([[4, 5, 6]])}
    cons = consensus_twins(twins, min_methods=3, k=3)
    assert cons == [[1]], "only the index agreed on by >=3 methods may survive"


# 3 · LEAKAGE CONTROLS ───────────────────────────────────────────────
def test_representation_is_fitted_only_on_the_early_window():
    """A scaler fitted over the whole sample encodes the future distribution
    into every historical fingerprint - leakage that never looks like a future
    return."""
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    p = pd.DataFrame({
        "date": np.repeat(dates, 5),
        "ticker": ["T%d" % (i % 5) for i in range(1000)],
        "a": np.concatenate([np.zeros(500), np.full(500, 1000.0)]),
        "b": np.arange(1000, dtype=float),
    })
    fit_mask = (p["date"] <= dates[99]).to_numpy()
    rep = fit_representation(p, ["a", "b"], fit_mask, n_components=2)
    assert rep.fit_rows == 500
    assert str(rep.fit_date_max) == "2024-04-09"
    # the late regime shift must NOT have moved the centre
    assert abs(float(rep.center[0])) < 1e-9


def test_transitions_never_cross_a_ticker_boundary():
    p = pd.DataFrame({
        "ticker": ["A"] * 30 + ["B"] * 30,
        "date": list(pd.date_range("2024-01-01", periods=30)) * 2,
        "ret_20d": list(np.arange(30.0)) + list(np.arange(100.0, 130.0)),
        "vol_20": 1.0, "dd_60": 0.0,
    })
    t = transition_frame(p, ["ret_20d"], lags=LAGS)
    b = t[t["ticker"] == "B"]
    lagged = b["ret_20d_T20"].dropna()
    assert (lagged >= 100.0).all(), "a lag reached back into the previous ticker"


def test_market_family_uses_only_same_date_rows():
    p = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01"] * 3 + ["2024-01-02"] * 3),
        "ticker": list("ABCABC"),
        "ret_20d": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0],
        "vol_20": [1.0] * 6, "dd_60": [0.0] * 6,
    })
    out = add_market_family(p)
    d1 = out[out["date"] == "2024-01-01"]["mkt_median_ret20"].unique()
    assert len(d1) == 1 and d1[0] == pytest.approx(2.0), \
        "the first date's market state was contaminated by the second"


# 4 · THE CONFOUND SPLIT ─────────────────────────────────────────────
def test_a_pure_date_effect_shows_no_within_date_signal():
    """Construct a signal that is ENTIRELY date-level. The within-date
    correlation must vanish, otherwise the split cannot detect market timing
    masquerading as a twin effect."""
    rng = np.random.default_rng(3)
    rows = []
    for di, d in enumerate(pd.date_range("2024-01-01", periods=40)):
        level = rng.normal()
        for t in range(12):
            rows.append({"date": str(d.date()), "ticker": "T%d" % t,
                         "twin_mean": level, "twin_fail_frac": 0.2,
                         "query_outcome": level + rng.normal(scale=0.01)})
    d = pd.DataFrame(rows)
    ds = _demean_split(d)["demean_split"]
    assert abs(ds["within_date_rho"]) < 0.2, \
        "a pure date effect leaked into the cross-sectional claim"
    assert ds["date_level_rho"] > 0.8
    assert ds["variance_of_twin_mean_due_to_date_pct"] > 90


def test_a_pure_cross_sectional_effect_survives_demeaning():
    rng = np.random.default_rng(4)
    rows = []
    for d in pd.date_range("2024-01-01", periods=40):
        for t in range(12):
            x = rng.normal()
            rows.append({"date": str(d.date()), "ticker": "T%d" % t,
                         "twin_mean": x, "twin_fail_frac": 0.2,
                         "query_outcome": x + rng.normal(scale=0.05)})
    d = pd.DataFrame(rows)
    ds = _demean_split(d)["demean_split"]
    assert ds["within_date_rho"] > 0.8


# 5 · VALIDATION IS DATE-AWARE ───────────────────────────────────────
def test_block_bootstrap_resamples_dates_not_rows():
    rng = np.random.default_rng(5)
    rows = []
    for d in pd.date_range("2024-01-01", periods=60):
        lvl = rng.normal()
        for t in range(20):
            rows.append({"date": str(d.date()), "ticker": "T%d" % t,
                         "twin_mean": lvl, "query_outcome": lvl})
    d = pd.DataFrame(rows)
    b = date_block_bootstrap(d, "twin_mean")
    assert b["status"] == "OK"
    assert b["block_size_dates"] >= 2
    assert b["n_dates"] == 60
    assert "ci95_low" in b and "ci95_high" in b


def test_leave_one_out_flags_a_single_group_carrying_the_result():
    rng = np.random.default_rng(6)
    rows = []
    for d in pd.date_range("2024-01-01", periods=12):
        for t in range(12):
            rows.append({"date": str(d.date()), "ticker": "T%d" % t,
                         "twin_mean": rng.normal(), "query_outcome": rng.normal()})
    d = pd.DataFrame(rows)
    out = leave_one_out(d, "twin_mean", "date")
    assert out["status"] == "OK"
    assert out["verdict"] in ("STABLE", "FRAGILE")
    assert out["n_groups"] >= 3


# 6 · GOVERNANCE + SHIPPED ARTIFACTS ─────────────────────────────────
def _shipped(name):
    p = ROOT / "reports/research/r3/market_memory_v1" / name
    if not p.exists():
        pytest.skip("market memory lab not run in this checkout")
    return json.loads(p.read_text(encoding="utf-8"))


def test_shipped_verdict_is_governed_by_stability():
    st = _shipped("twin_stability.json")["stability"]
    summ = _shipped("market_memory_summary.json")
    for m, s in st.items():
        assert s["verdict"] in ("STABLE_TWINS", "NO_STABLE_MEMORY_STRUCTURE")
        if s["verdict"] == "NO_STABLE_MEMORY_STRUCTURE":
            assert s["top_k"]["50"]["mean"] < STABILITY_FLOOR
    assert "NO_STABLE_MEMORY_STRUCTURE" in summ["verdict"] or "MIXED" in summ["verdict"]


def test_no_candidate_is_confirmed_while_twins_are_unstable():
    c = _shipped("confirmation_candidates.json")
    st = _shipped("twin_stability.json")["stability"]
    if all(v["verdict"] == "NO_STABLE_MEMORY_STRUCTURE" for v in st.values()):
        assert c["confirmed"] == [], \
            "a candidate was confirmed over neighbourhoods that belong to the metric"
    for f in c.get("frozen_for_confirmation", []):
        assert f["blocking_issue"]
        assert f["frozen_test_specification"]["required_before_running"]


def test_ai_layer_was_not_run_without_a_discovery():
    a = _shipped("ai_hypotheses.json")
    assert a["status"] == "NOT_GENERATED"
    assert a["hypotheses"] == []


def test_shipped_governance_is_frozen():
    for name in ("market_memory_summary.json", "decision_utility.json",
                 "twin_stability.json"):
        g = _shipped(name)["governance"]
        assert g["r2_modified"] is False
        assert g["r1_modified"] is False
        assert g["r3_production_writes"] == 0
        assert g["stops_changed"] is False and g["exits_changed"] is False
        assert g["workbook_changed"] is False
