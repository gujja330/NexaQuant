"""DEV022 smoke tests. Fast; no network."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from portfolio_construction.lib import allocators, constraints, stress_tests            # noqa: E402
from portfolio_construction.compute import risk_analytics                                # noqa: E402


PASS = 0
FAIL = 0


def _check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _synthetic_price_data(n_days=300, n_tickers=8, seed=42):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n_days, freq="B")
    out = {}
    for i in range(n_tickers):
        rets = rng.normal(0.0005, 0.015, n_days)
        price = 100 * (1 + pd.Series(rets, index=idx)).cumprod()
        out[f"T{i}"] = price
    return out


def _synthetic_candidates(n=8, base_score=70.0):
    return [{"ticker": f"T{i}", "score": base_score - i * 2,
              "confidence": 0.9, "sector": "S" + str(i % 3),
              "industry": "I" + str(i % 4)} for i in range(n)]


def test_equal_weight():
    cands = _synthetic_candidates(5)
    w = allocators.equal_weight(cands)
    _check("equal has 5 positions", len(w) == 5)
    _check("equal sums to 1", abs(sum(w.values()) - 1.0) < 1e-9)
    _check("equal all same weight", len(set(round(v, 6) for v in w.values())) == 1)


def test_score_weight():
    cands = _synthetic_candidates(5)
    w = allocators.score_weight(cands, min_score=50.0)
    _check("score sums to 1", abs(sum(w.values()) - 1.0) < 1e-9)
    # highest-score has highest weight
    w0 = w.get("T0", 0)
    w4 = w.get("T4", 0)
    _check("score gives T0 > T4", w0 > w4, detail=f"T0={w0:.4f} T4={w4:.4f}")


def test_confidence_weight():
    cands = _synthetic_candidates(5)
    for i, c in enumerate(cands):
        c["confidence"] = 0.5 + i * 0.1
    w = allocators.confidence_weight(cands)
    _check("confidence sums to 1", abs(sum(w.values()) - 1.0) < 1e-9)
    _check("higher conf gets higher weight",
            w["T4"] > w["T0"], detail=f"T0={w['T0']:.4f} T4={w['T4']:.4f}")


def test_inverse_vol():
    price = _synthetic_price_data(300, 5)
    cands = _synthetic_candidates(5)
    w = allocators.inverse_volatility_weight(cands, price_data=price)
    _check("inv_vol produces weights", len(w) > 0)
    _check("inv_vol sums to 1", abs(sum(w.values()) - 1.0) < 1e-6)


def test_hrp():
    price = _synthetic_price_data(300, 6)
    cands = _synthetic_candidates(6)
    w = allocators.hierarchical_risk_parity(cands, price_data=price)
    _check("HRP produces weights", len(w) > 0)
    _check("HRP sums to 1", abs(sum(w.values()) - 1.0) < 1e-3,
            detail=f"sum={sum(w.values()):.6f}")


def test_min_variance():
    price = _synthetic_price_data(300, 5)
    cands = _synthetic_candidates(5)
    w = allocators.minimum_variance(cands, price_data=price)
    _check("min-var produces weights", len(w) > 0)
    _check("min-var sums to 1", abs(sum(w.values()) - 1.0) < 1e-4)
    _check("min-var all positive", all(v >= -1e-6 for v in w.values()))


def test_max_sharpe():
    price = _synthetic_price_data(300, 5)
    cands = _synthetic_candidates(5)
    w = allocators.maximum_sharpe(cands, price_data=price)
    _check("max-sharpe produces weights", len(w) > 0)
    _check("max-sharpe no position > 30%",
            all(v <= 0.31 for v in w.values()),
            detail=f"max weight = {max(w.values()):.4f}")


def test_constraints_cap():
    # 4 stocks, sectors + industries diverse enough that stock cap can be enforced
    # without secondary sector/industry conflicts
    weights = {"A": 0.5, "B": 0.3, "C": 0.15, "D": 0.05}
    tk_sec = {"A": "S1", "B": "S2", "C": "S3", "D": "S4"}       # all different sectors
    tk_ind = {"A": "I1", "B": "I2", "C": "I3", "D": "I4"}
    constr = constraints.Constraints(max_stock_weight=0.30, max_sector_exposure=1.0,
                                       max_industry_exposure=1.0)
    adj, viols = constraints.apply(weights, tk_sec, tk_ind, constr)
    _check("max stock cap applied", max(adj.values()) <= 0.301,
            detail=f"max={max(adj.values()):.4f}")
    _check("constraints sum ~= 1 when caps allow",
            abs(sum(adj.values()) - 1.0) < 1e-3,
            detail=f"sum={sum(adj.values()):.4f}")


def test_constraints_sector_cap():
    weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    tk_sec = {"A": "S1", "B": "S1", "C": "S1", "D": "S2"}   # 75% in S1
    tk_ind = {"A": "I1", "B": "I1", "C": "I2", "D": "I3"}
    constr = constraints.Constraints(max_sector_exposure=0.35)
    adj, viols = constraints.apply(weights, tk_sec, tk_ind, constr)
    s1_total = sum(v for t, v in adj.items() if tk_sec[t] == "S1")
    _check("sector cap enforced (S1 <= 0.35)",
            s1_total <= 0.351, detail=f"S1 total = {s1_total:.4f}")
    _check("sector constraint recorded",
            any("scaled_sector" in v for v in viols))
    # In this degenerate case (all sectors of the shortfall have no headroom), the
    # remaining allocation stays unassigned — cash-like — and violations records it
    _check("shortfall recorded when unallocatable",
            any("unallocated_excess" in v for v in viols)
            or abs(sum(adj.values()) - 1.0) < 1e-3)


def test_stress_test_stub():
    price = _synthetic_price_data(300, 3, seed=7)
    weights = {"T0": 0.4, "T1": 0.4, "T2": 0.2}
    result = stress_tests.stress_test_portfolio(weights, price)
    _check("stress returns windows", "stress_windows" in result)
    _check("stress has 5 windows", len(result["stress_windows"]) == 5)
    # Each window has a status
    for w in result["stress_windows"]:
        _check(f"stress window {w['window_key']} has status", "status" in w)


def test_risk_analytics():
    price = _synthetic_price_data(300, 4, seed=11)
    portfolio = {
        "positions": [
            {"ticker": "T0", "weight": 0.25, "sector": "S1", "industry": "I1"},
            {"ticker": "T1", "weight": 0.25, "sector": "S1", "industry": "I2"},
            {"ticker": "T2", "weight": 0.25, "sector": "S2", "industry": "I3"},
            {"ticker": "T3", "weight": 0.25, "sector": "S2", "industry": "I4"},
        ]
    }
    bench = 100 * (1 + pd.Series(np.random.default_rng(3).normal(0.0004, 0.01, 300),
                                     index=pd.date_range("2024-01-01", periods=300, freq="B"))).cumprod()
    risk = risk_analytics.analyse(portfolio, price, bench)
    _check("risk has vol", "annualised_volatility_pct" in risk and risk["annualised_volatility_pct"] is not None)
    _check("risk has beta", "beta_vs_nifty" in risk and risk["beta_vs_nifty"] is not None)
    _check("risk has HHI",
            risk["concentration"]["stock_hhi"] is not None)
    _check("effective_n_stocks = 4 for equal weight",
            abs(risk["concentration"]["effective_n_stocks"] - 4.0) < 0.1,
            detail=f"got {risk['concentration']['effective_n_stocks']}")


def main() -> int:
    print("=" * 70)
    print("  DEV022 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_equal_weight(); print()
    test_score_weight(); print()
    test_confidence_weight(); print()
    test_inverse_vol(); print()
    test_hrp(); print()
    test_min_variance(); print()
    test_max_sharpe(); print()
    test_constraints_cap(); print()
    test_constraints_sector_cap(); print()
    test_stress_test_stub(); print()
    test_risk_analytics(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
