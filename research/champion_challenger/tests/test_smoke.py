"""DEV030 smoke tests. Deterministic synthetic strategies."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from champion_challenger.lib import scoring, head_to_head, promotion, drift          # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _make_strategies():
    return pd.DataFrame([
        {"strategy": "S_ALPHA",  "sharpe_ratio": 1.4, "sortino_ratio": 2.0,
          "calmar_ratio": 1.5, "cagr": 0.22, "max_dd_pct": -12.0,
          "information_ratio": 0.9, "win_rate": 0.62, "profit_factor": 2.1,
          "expectancy": 1.5, "n_trades": 120},
        {"strategy": "S_BETA",   "sharpe_ratio": 1.0, "sortino_ratio": 1.5,
          "calmar_ratio": 1.0, "cagr": 0.15, "max_dd_pct": -15.0,
          "information_ratio": 0.5, "win_rate": 0.55, "profit_factor": 1.6,
          "expectancy": 0.8, "n_trades": 100},
        {"strategy": "S_GAMMA",  "sharpe_ratio": 0.4, "sortino_ratio": 0.8,
          "calmar_ratio": 0.3, "cagr": 0.06, "max_dd_pct": -20.0,
          "information_ratio": 0.1, "win_rate": 0.48, "profit_factor": 1.1,
          "expectancy": 0.2, "n_trades": 80},
    ])


def test_scoring_ranks_alpha_first():
    df = _make_strategies()
    scored = scoring.score_strategies(df)
    _check("scoring returns dataframe", isinstance(scored, pd.DataFrame))
    _check("rank column present", "rank" in scored.columns)
    _check("composite_score column present", "composite_score" in scored.columns)
    _check("S_ALPHA is rank #1", scored.iloc[0]["strategy"] == "S_ALPHA")
    _check("S_GAMMA is rank #3", scored.iloc[-1]["strategy"] == "S_GAMMA")


def test_scoring_handles_empty():
    scored = scoring.score_strategies(pd.DataFrame())
    _check("empty df -> empty result", scored.empty)


def test_leaderboard_output_shape():
    scored = scoring.score_strategies(_make_strategies())
    lb = scoring.rank_summary(scored)
    _check("leaderboard is list", isinstance(lb, list))
    _check("leaderboard has 3 rows", len(lb) == 3)
    _check("row has rank/strategy/composite_score",
            all(k in lb[0] for k in ["rank", "strategy", "composite_score"]))


def test_head_to_head_matrix():
    scored = scoring.score_strategies(_make_strategies())
    pairs = head_to_head.build_matrix(scored)
    n = 3
    expected_pair_count = n * (n - 1) // 2
    _check(f"pairs count = {expected_pair_count}", len(pairs) == expected_pair_count)
    for p in pairs:
        _check(f"pair {p['a']} vs {p['b']} has winner",
                p.get("winner_by_composite") in (p["a"], p["b"]))


def test_promotion_hold_initial():
    scored = scoring.score_strategies(_make_strategies())
    lb = scoring.rank_summary(scored)
    decision = promotion.evaluate_promotion(None, lb, {})
    _check("initial run -> initial_champion",
            decision["decision"] == "initial_champion",
            detail=decision.get("decision"))
    _check("initial champion is S_ALPHA",
            decision["champion"] == "S_ALPHA")


def test_promotion_hold_when_incumbent_still_top():
    scored = scoring.score_strategies(_make_strategies())
    lb = scoring.rank_summary(scored)
    incumbent = lb[0]  # S_ALPHA
    decision = promotion.evaluate_promotion(incumbent, lb, {})
    _check("incumbent still #1 -> hold_champion",
            decision["decision"] == "hold_champion",
            detail=decision.get("decision"))


def test_promotion_gates_block_thin_margin():
    scored = scoring.score_strategies(_make_strategies())
    lb = scoring.rank_summary(scored)
    # Pretend S_BETA is incumbent (rank #2) — S_ALPHA (rank #1) is challenger
    incumbent = lb[1]
    decision = promotion.evaluate_promotion(incumbent, lb, {})
    _check("promotion decision returns known value",
            decision["decision"] in ("promote_challenger", "hold_champion"),
            detail=decision.get("decision"))
    _check("promotion gates recorded",
            isinstance(decision.get("gates"), dict))


def test_drift_metric_computes():
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    equity = pd.DataFrame({
        "S_STABLE":   np.linspace(1.0, 1.5, 500),
        "S_DEGRADED": np.concatenate([np.linspace(1.0, 1.6, 250),
                                        np.linspace(1.6, 1.55, 250)]),
    }, index=dates)
    r = drift.metric_drift(equity)
    _check("drift returns dict per strategy", "S_STABLE" in r and "S_DEGRADED" in r)
    _check("stability_flag present", "stability_flag" in r["S_STABLE"])


def test_determinism():
    df = _make_strategies()
    s1 = scoring.score_strategies(df)
    s2 = scoring.score_strategies(df)
    _check("scoring is deterministic",
            (s1["composite_score"].values == s2["composite_score"].values).all())


def main() -> int:
    print("=" * 70)
    print("  DEV030 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_scoring_ranks_alpha_first(); print()
    test_scoring_handles_empty(); print()
    test_leaderboard_output_shape(); print()
    test_head_to_head_matrix(); print()
    test_promotion_hold_initial(); print()
    test_promotion_hold_when_incumbent_still_top(); print()
    test_promotion_gates_block_thin_margin(); print()
    test_drift_metric_computes(); print()
    test_determinism(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
