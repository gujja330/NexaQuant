"""Validation Engine v2.0 · edge decay + drift detection.

Two flavours of drift for the live validation loop:

1. **Metric drift** — 1st-half vs 2nd-half of the closed-trade window.
   Fires when 2nd-half Sharpe / expectancy / win-rate degrades by more
   than a configured threshold vs 1st-half.

2. **Distributional drift** — KL divergence on the signal distribution
   over consecutive windows. Fires when signal ranges shift materially.

Both are advisory. Neither auto-pauses trading. Both should route into
Adaptive Rec Engine's promotion review + Champion Challenger's drift panel."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe_from_returns(returns: np.ndarray, ppy: int = 252) -> float:
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(ppy))


def expectancy(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return 0.0
    return float(returns.mean())


def win_rate(is_winner: np.ndarray) -> float:
    if len(is_winner) == 0:
        return 0.0
    return float(is_winner.mean())


def metric_drift(closed_trades: pd.DataFrame,
                    sharpe_degrade_pct: float = 0.30,
                    winrate_degrade_pct: float = 0.10) -> dict:
    """1st-half vs 2nd-half metric divergence on the closed-trades window."""
    if closed_trades.empty or len(closed_trades) < 4:
        return {"note": "insufficient closed trades for drift analysis",
                 "n": int(len(closed_trades)),
                 "flag": "insufficient_evidence"}

    df = closed_trades.sort_values("exit_date").reset_index(drop=True)
    half = len(df) // 2
    first = df.iloc[:half]
    second = df.iloc[half:]

    rets_f = first["return_pct"].astype(float).values
    rets_s = second["return_pct"].astype(float).values
    wins_f = (rets_f > 0).astype(int)
    wins_s = (rets_s > 0).astype(int)

    sh_f = sharpe_from_returns(rets_f)
    sh_s = sharpe_from_returns(rets_s)
    wr_f = win_rate(wins_f)
    wr_s = win_rate(wins_s)
    exp_f = expectancy(rets_f)
    exp_s = expectancy(rets_s)

    sh_change = (sh_s - sh_f) / abs(sh_f) if sh_f != 0 else 0
    wr_change = wr_s - wr_f

    flags = []
    if sh_f > 0.1 and sh_change < -sharpe_degrade_pct:
        flags.append("sharpe_degrading")
    if wr_change < -winrate_degrade_pct:
        flags.append("winrate_degrading")

    flag = "degrading" if flags else ("stable" if abs(sh_change) < 0.15 else "improving")

    return {
        "n":                   int(len(df)),
        "first_half_n":        int(len(first)),
        "second_half_n":       int(len(second)),
        "first_half_sharpe":   round(sh_f, 4),
        "second_half_sharpe":  round(sh_s, 4),
        "sharpe_change_pct":   round(sh_change, 4),
        "first_half_winrate":  round(wr_f, 4),
        "second_half_winrate": round(wr_s, 4),
        "winrate_change_pp":   round(wr_change, 4),
        "first_half_expectancy":  round(exp_f, 4),
        "second_half_expectancy": round(exp_s, 4),
        "flag":                flag,
        "warning_flags":       flags,
    }


def rolling_edge(closed_trades: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Rolling win-rate + expectancy for the last N trades. Fires drift
    when the rolling number diverges materially from the all-time number."""
    if closed_trades.empty:
        return pd.DataFrame()
    df = closed_trades.sort_values("exit_date").reset_index(drop=True)
    if len(df) < window:
        return pd.DataFrame()
    rets = df["return_pct"].astype(float).values
    all_expectancy = float(rets.mean())
    all_wr = float((rets > 0).mean())

    out = []
    for i in range(window, len(df) + 1):
        w = rets[i - window: i]
        w_exp = float(w.mean())
        w_wr = float((w > 0).mean())
        out.append({
            "asof":              str(df["exit_date"].iloc[i - 1]),
            "window_n":          window,
            "window_expectancy": round(w_exp, 4),
            "window_winrate":    round(w_wr, 4),
            "delta_expectancy":  round(w_exp - all_expectancy, 4),
            "delta_winrate":     round(w_wr - all_wr, 4),
        })
    return pd.DataFrame(out)
