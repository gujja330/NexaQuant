"""DEV030 · drift & stability tracking.

Two flavours of drift:

1. **Metric drift** — has this strategy's Sharpe/return degraded over time?
   Measured by comparing 1st-half vs 2nd-half of the backtest window.

2. **Rank drift** — has the composite ranking of a strategy changed run-over-run?
   Reads prior run's leaderboard from calibration_history-style parquet if
   available; otherwise reports None."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
HISTORY = _ROOT / "data" / "market_intelligence" / "derived" / "champion_challenger_history.parquet"


def _sharpe(rets: pd.Series) -> float:
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(252))


def _cagr(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    n_days = len(equity)
    if n_days < 2:
        return 0.0
    total = float(equity.iloc[-1] / equity.iloc[0])
    if total <= 0:
        return 0.0
    yrs = n_days / 252.0
    return float(total ** (1.0 / yrs) - 1.0)


def _max_dd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def metric_drift(equity_curves: pd.DataFrame) -> dict:
    """First-half vs second-half comparison per strategy."""
    if equity_curves.empty:
        return {}
    n = len(equity_curves)
    if n < 4:
        return {}
    half = n // 2
    result = {}
    for col in equity_curves.columns:
        curve = equity_curves[col].dropna()
        if len(curve) < 4:
            continue
        h = len(curve) // 2
        first = curve.iloc[:h]
        second = curve.iloc[h:]
        rets_first = first.pct_change().dropna()
        rets_second = second.pct_change().dropna()
        sharpe_first = _sharpe(rets_first)
        sharpe_second = _sharpe(rets_second)
        cagr_first = _cagr(first)
        cagr_second = _cagr(second)
        dd_first = _max_dd(first)
        dd_second = _max_dd(second)

        # Simple degradation flag: 2nd half sharpe more than 30% below 1st half
        flag = None
        if sharpe_first != 0 and abs(sharpe_first) > 0.01:
            change = (sharpe_second - sharpe_first) / abs(sharpe_first)
            if change < -0.30:
                flag = "degrading"
            elif change > 0.30:
                flag = "improving"
            else:
                flag = "stable"
        else:
            flag = "insufficient_signal"

        result[col] = {
            "first_half_sharpe":  round(sharpe_first, 4),
            "second_half_sharpe": round(sharpe_second, 4),
            "sharpe_change":      round(sharpe_second - sharpe_first, 4),
            "first_half_cagr":    round(cagr_first, 4),
            "second_half_cagr":   round(cagr_second, 4),
            "first_half_max_dd":  round(dd_first, 4),
            "second_half_max_dd": round(dd_second, 4),
            "stability_flag":     flag,
            "n_days_first_half":  int(len(first)),
            "n_days_second_half": int(len(second)),
        }
    return result


def rank_drift(current_leaderboard: list[dict]) -> dict:
    """Compare current composite ranks vs the previous run's from history parquet."""
    if not HISTORY.exists():
        return {"note": "no prior run to compare against", "changes": []}
    try:
        hist = pd.read_parquet(HISTORY)
    except Exception:
        return {"note": "history parquet unreadable", "changes": []}
    if hist.empty:
        return {"note": "history is empty", "changes": []}
    prior = hist.sort_values("run_utc").iloc[-1]
    prior_ranks = prior.get("leaderboard_ranks")
    if not isinstance(prior_ranks, (dict, list)) and not (isinstance(prior_ranks, str) and prior_ranks):
        return {"note": "prior run had no leaderboard_ranks column", "changes": []}
    if isinstance(prior_ranks, str):
        try:
            import json
            prior_ranks = json.loads(prior_ranks)
        except Exception:
            return {"note": "prior ranks not parseable", "changes": []}

    prior_map = {r["strategy"]: r["rank"] for r in prior_ranks} \
                    if isinstance(prior_ranks, list) else prior_ranks

    changes = []
    for row in current_leaderboard:
        strat = row["strategy"]
        curr_rank = int(row["rank"])
        prev_rank = int(prior_map.get(strat, -1))
        if prev_rank == -1:
            changes.append({"strategy": strat, "prior_rank": None,
                              "current_rank": curr_rank, "delta": None})
        else:
            changes.append({"strategy": strat, "prior_rank": prev_rank,
                              "current_rank": curr_rank, "delta": prev_rank - curr_rank})
    return {"prior_run_utc": str(prior.get("run_utc")), "changes": changes}


def append_history(row: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame([row])
    # JSON-serialise complex fields to avoid parquet nested-schema issues
    import json as _json
    for col in new_df.columns:
        val = new_df.at[0, col]
        if isinstance(val, (list, dict)):
            new_df.at[0, col] = _json.dumps(val, default=str)
    if HISTORY.exists():
        try:
            old = pd.read_parquet(HISTORY)
            combined = pd.concat([old, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df
    combined.to_parquet(HISTORY, index=False)
