"""DEV021 smoke tests. Fast; no network required."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from backtesting.lib import metrics, strategies, pit_scorer                            # noqa: E402
from backtesting.compute import attribution, failure_analysis                            # noqa: E402
from backtesting.publish import bundle                                                    # noqa: E402


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


def test_metrics_basic():
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    r = pd.Series([0.001] * 252, index=idx)                    # ~26% ann
    ann = metrics.cagr(r)
    _check("CAGR positive on positive series", ann > 0.2, detail=f"got {ann:.3f}")

    vol = metrics.annual_volatility(r)
    _check("Vol zero on constant returns", vol < 1e-6, detail=f"got {vol}")

    # Add noise
    rng = np.random.default_rng(seed=42)
    r_noisy = pd.Series(rng.normal(0.0005, 0.01, 252), index=idx)
    vol2 = metrics.annual_volatility(r_noisy)
    _check("Vol ~ 0.15 on noisy returns", 0.1 < vol2 < 0.25, detail=f"got {vol2:.3f}")

    sharpe = metrics.sharpe_ratio(r_noisy, rf=0.05)
    _check("Sharpe is finite", np.isfinite(sharpe))


def test_max_dd():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    # Positive then negative
    vals = [0.01] * 50 + [-0.02] * 50
    r = pd.Series(vals, index=idx)
    dd = metrics.max_drawdown(r)
    _check("Max DD is negative", dd["max_dd_pct"] < 0, detail=f"got {dd['max_dd_pct']:.2f}")
    _check("Max DD has trough_date", dd["trough_date"] is not None)
    _check("Max DD has peak_date",   dd["peak_date"] is not None)


def test_alpha_beta():
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    rng = np.random.default_rng(seed=7)
    bench = pd.Series(rng.normal(0.0005, 0.01, 252), index=idx)
    strat = bench * 1.5 + rng.normal(0.0002, 0.003, 252)
    strat.index = idx
    b = metrics.beta(strat, bench)
    _check("Beta close to 1.5 on scaled series", 1.2 < b < 1.8, detail=f"got {b:.2f}")
    a = metrics.alpha(strat, bench)
    _check("Alpha is a finite number", np.isfinite(a))
    ir = metrics.information_ratio(strat, bench)
    _check("Info Ratio is finite", np.isfinite(ir))


def test_strategies():
    scored = [(f"T{i}", float(90 - i)) for i in range(25)]
    p10 = strategies.top_n_equal_weight(scored, 10)
    _check("Top-10-EW has 10 positions", len(p10.weights) == 10)
    _check("Top-10-EW weights sum to 1", abs(sum(p10.weights.values()) - 1.0) < 1e-6)
    _check("Top-10-EW top pick is T0", "T0" in p10.weights)

    p_sw = strategies.top_n_score_weighted(scored, 10, min_score=50)
    # scored[i] = (T{i}, 90-i); score > 50 means i < 40; and we take top 10 by score
    # so tickers should be T0..T9 all with score > 50
    _check("Top-10-SW selects only score > 50",
            all(int(t[1:]) < 40 for t in p_sw.weights),
            detail=f"tickers: {sorted(p_sw.weights.keys(), key=lambda x: int(x[1:]))}")
    _check("Top-10-SW higher score gets higher weight",
            p_sw.weights.get("T0", 0) > p_sw.weights.get("T9", 0))

    p_ew = strategies.equal_weight_universe(scored)
    _check("EW universe has 25 positions", len(p_ew.weights) == 25)


def test_pit_scorer_no_lookahead():
    """Score computed at date T must not change when data after T is added."""
    idx = pd.date_range("2023-01-01", periods=200, freq="B")
    rng = np.random.default_rng(seed=11)
    closes = 100 * (1 + pd.Series(rng.normal(0.0006, 0.01, 200), index=idx)).cumprod()
    df = pd.DataFrame({"close": closes, "tick_volume": [1_000_000] * 200}, index=idx)
    df.attrs["ticker"] = "TEST"

    asof = idx[150]
    s1 = pit_scorer.score_ticker_at(df, asof)

    # Add "future" bars and re-score at the same asof
    fut = pd.date_range(idx[-1] + pd.Timedelta(days=1), periods=50, freq="B")
    df2 = pd.concat([df, pd.DataFrame({"close": [200.0] * 50, "tick_volume": [1_000_000] * 50},
                                          index=fut)])
    df2.attrs["ticker"] = "TEST"
    s2 = pit_scorer.score_ticker_at(df2, asof)

    _check("PIT scorer produces a score", s1 is not None and s2 is not None)
    if s1 and s2:
        _check("PIT score is identical when future is added (no look-ahead)",
                abs(s1.score - s2.score) < 1e-6,
                detail=f"s1={s1.score:.4f}  s2={s2.score:.4f}")


def test_pit_scorer_insufficient():
    idx = pd.date_range("2024-01-01", periods=50, freq="B")
    df = pd.DataFrame({"close": range(100, 150), "tick_volume": [1_000_000] * 50}, index=idx)
    df.attrs["ticker"] = "SHORT"
    s = pit_scorer.score_ticker_at(df, idx[-1])
    _check("PIT scorer returns None on short history", s is None)


def test_attribution():
    trade_log = [
        {"rebal_date": "2024-01-31", "next_date": "2024-02-29",
          "ticker": "HDFCBANK", "weight": 0.10, "return_pct": 5.0,
          "entry_px": 100, "exit_px": 105},
        {"rebal_date": "2024-01-31", "next_date": "2024-02-29",
          "ticker": "INFY", "weight": 0.10, "return_pct": -3.0,
          "entry_px": 100, "exit_px": 97},
    ]
    attr = attribution.attribute_trades(trade_log)
    _check("attribution has by_sector", "by_sector" in attr)
    _check("attribution has by_industry", "by_industry" in attr)
    _check("attribution rows have contribution",
            all("cumulative_contribution_pct" in r for r in attr["by_sector"]))


def test_failure_analysis():
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    rng = np.random.default_rng(seed=13)
    r = pd.Series(rng.normal(0.0, 0.02, 252), index=idx)
    trade_log = [
        {"rebal_date": f"2024-{m:02d}-01", "next_date": f"2024-{m+1:02d}-01",
          "ticker": f"T{i}", "weight": 0.05,
          "return_pct": float(rng.normal(1.0, 5.0)),
          "entry_px": 100.0, "exit_px": 100.0 + rng.normal(0, 5)}
        for m in range(1, 12) for i in range(20)
    ]
    fa = failure_analysis.analyse_failures(r, trade_log)
    _check("failure_analysis has worst_10_trades", len(fa["worst_10_trades"]) == 10)
    _check("failure_analysis has best_10_trades", len(fa["best_10_trades"]) == 10)
    _check("worst trades are sorted ascending",
            fa["worst_10_trades"][0]["return_pct"] <= fa["worst_10_trades"][-1]["return_pct"])
    _check("best trades are sorted descending",
            fa["best_10_trades"][0]["return_pct"] >= fa["best_10_trades"][-1]["return_pct"])


def main() -> int:
    print("=" * 70)
    print("  DEV021 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_metrics_basic(); print()
    test_max_dd(); print()
    test_alpha_beta(); print()
    test_strategies(); print()
    test_pit_scorer_no_lookahead(); print()
    test_pit_scorer_insufficient(); print()
    test_attribution(); print()
    test_failure_analysis(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
