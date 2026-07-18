"""DEV028 v1.5 feedback smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd

from recommendation_dna.lib import feedback                                             # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _fake_dna():
    return pd.DataFrame([
        {"dna_id": "D1", "ticker": "AAA", "sector": "Pharma", "industry": "Pharma-Mid",
          "classification": "Strong-Bullish", "company_score": 85.0},
        {"dna_id": "D2", "ticker": "BBB", "sector": "Pharma", "industry": "Pharma-Mid",
          "classification": "Strong-Bullish", "company_score": 82.0},
        {"dna_id": "D3", "ticker": "CCC", "sector": "Banks", "industry": "PSU",
          "classification": "Bullish", "company_score": 65.0},
    ])


def _fake_learning():
    return pd.DataFrame([
        {"ticker": "AAA", "is_winner": 1, "return_pct": 0.06},
        {"ticker": "AAA", "is_winner": 1, "return_pct": 0.04},
        {"ticker": "BBB", "is_winner": 1, "return_pct": 0.08},
        {"ticker": "BBB", "is_winner": 0, "return_pct": -0.03},
        {"ticker": "CCC", "is_winner": 0, "return_pct": -0.05},
        {"ticker": "CCC", "is_winner": 0, "return_pct": -0.02},
    ])


def test_join_outcomes_populates_history():
    dna = _fake_dna()
    learning = _fake_learning()
    joined = feedback.join_outcomes(dna, learning)
    _check("join adds hist_n_trades column", "hist_n_trades" in joined.columns)
    _check("AAA has 2 hist trades",
            int(joined[joined["ticker"] == "AAA"]["hist_n_trades"].iloc[0]) == 2)
    _check("AAA hist_win_rate is 1.0",
            float(joined[joined["ticker"] == "AAA"]["hist_win_rate"].iloc[0]) == 1.0)


def test_pattern_stats_ordered_by_winrate():
    dna = _fake_dna()
    joined = feedback.join_outcomes(dna, _fake_learning())
    pats = feedback.compute_pattern_stats(joined)
    _check("returns non-empty pattern list", len(pats) >= 2)
    # First pattern should have highest win rate
    wrs = [p["hist_win_rate"] for p in pats]
    _check("patterns sorted by win rate descending",
            wrs == sorted(wrs, reverse=True))


def test_per_rec_priors():
    dna = _fake_dna()
    joined = feedback.join_outcomes(dna, _fake_learning())
    current = [
        {"ticker": "ZZZ", "recommendation": "Buy",
          "sector": "Pharma", "industry": "Pharma-Mid",
          "classification": "Strong-Bullish", "company_score": 84.0},
        {"ticker": "YYY", "recommendation": "Buy",
          "sector": "Unknown-Sector", "industry": "X",
          "classification": "X", "company_score": 50.0},
    ]
    priors = feedback.compute_per_rec_priors(current, joined)
    _check("returns one prior per current rec", len(priors) == 2)

    zzz_prior = next(p for p in priors if p["ticker"] == "ZZZ")
    _check("ZZZ prior has historical evidence (matches Pharma pattern)",
            zzz_prior["hist_evidence"] is True)
    _check("ZZZ prior_win_rate uses historical avg",
            zzz_prior["prior_win_rate"] is not None)

    yyy_prior = next(p for p in priors if p["ticker"] == "YYY")
    _check("YYY prior has no historical evidence",
            yyy_prior["hist_evidence"] is False)


def test_deterministic():
    dna = _fake_dna(); learning = _fake_learning()
    j1 = feedback.join_outcomes(dna, learning)
    j2 = feedback.join_outcomes(dna, learning)
    p1 = feedback.compute_pattern_stats(j1)
    p2 = feedback.compute_pattern_stats(j2)
    _check("pattern stats deterministic",
            [x["pattern"] for x in p1] == [x["pattern"] for x in p2])


def main() -> int:
    print("=" * 72); print("  DEV028 v1.5 · DNA FEEDBACK SMOKE TESTS"); print("=" * 72)
    test_join_outcomes_populates_history(); print()
    test_pattern_stats_ordered_by_winrate(); print()
    test_per_rec_priors(); print()
    test_deterministic(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
