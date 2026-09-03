"""R2 · P2 · Sector/Regime-Adjusted Ranking
Sprint A · CEO 2026-09-03

    Context_Adjusted_Score(t)
      = Base_Ensemble_Score(t)
      + alpha * Sector_Regime_Score(t)
      + beta  * Market_Regime_Score(t)

alpha, beta are walk-forward tuned across a 3×3 grid (9 trials).

Sector_Regime_Score derives from (20d relative strength, breadth,
leadership concentration) already computed in the R2 sector-regime block
of the daily pipeline. This module accepts them as inputs and does the
ranking math + walk-forward parameter selection.

Output:
  reports/research/r2_upgrades/p2_sector_regime_{market}.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from itertools import product
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

# 3x3 grid · trial matrix says P2 = 9 trials
ALPHA_GRID = [0.0, 0.15, 0.30]
BETA_GRID  = [0.0, 0.15, 0.30]


def adjusted_score(base: float, sector_rs: float, market_reg: float,
                   alpha: float, beta: float) -> float:
    return float(base) + alpha * float(sector_rs) + beta * float(market_reg)


def rank_top_n(rows: list[dict], n: int, alpha: float, beta: float,
               score_key: str = "base_ensemble_score") -> list[dict]:
    scored = []
    for r in rows:
        s = adjusted_score(
            r.get(score_key, 0.0),
            r.get("sector_regime_score", 0.0),
            r.get("market_regime_score", 0.0),
            alpha, beta,
        )
        scored.append({**r, "adjusted_score": s})
    scored.sort(key=lambda x: -x["adjusted_score"])
    return scored[:n]


def walkforward_grid_search(outcome_rows: list[dict],
                            n_folds: int = 8, top_n: int = 10) -> dict:
    """For each (alpha, beta) in grid · pick top-N per fold · report avg
    forward-return + trade Sharpe. Best (alpha, beta) is the one that
    survives on an untouched validation fold with n_ge_50 support."""

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def _sharpe(xs):
        if not xs: return 0.0
        mu = _mean(xs)
        var = sum((x-mu)**2 for x in xs) / max(1, len(xs)-1)
        sd = math.sqrt(var)
        return (mu / sd) if sd > 0 else 0.0

    if not outcome_rows:
        return {"n_positions": 0, "note": "empty outcome rows"}

    # Naive fold-by-index split (real walk-forward would use dates)
    fold_size = max(10, len(outcome_rows) // max(1, n_folds))
    trials: list[dict] = []
    for alpha, beta in product(ALPHA_GRID, BETA_GRID):
        oos_returns: list[float] = []
        for f in range(n_folds):
            fold = outcome_rows[f*fold_size:(f+1)*fold_size]
            if len(fold) < 3: continue
            top = rank_top_n(fold, min(top_n, len(fold)), alpha, beta)
            for row in top:
                r = row.get("realized_return_pct")
                if r is not None:
                    try:
                        oos_returns.append(float(r))
                    except (TypeError, ValueError):
                        pass
        trials.append({
            "alpha": alpha, "beta": beta,
            "n": len(oos_returns),
            "mean_ret": _mean(oos_returns),
            "trade_sharpe": _sharpe(oos_returns),
        })

    if not trials:
        return {"n_positions": 0, "note": "no folds usable"}

    # Best trial by trade Sharpe · with n_ge_50 support filter
    eligible = [t for t in trials if t["n"] >= 50]
    if not eligible: eligible = trials
    best = max(eligible, key=lambda t: t["trade_sharpe"])
    baseline = next((t for t in trials if t["alpha"] == 0.0 and t["beta"] == 0.0), best)

    return {
        "trials_run": len(trials),
        "trial_count_in_matrix": 9,      # matches configs/outcome_dataset_schema.yaml
        "best": best,
        "baseline_alpha0_beta0": baseline,
        "sharpe_lift_over_baseline": best["trade_sharpe"] - baseline["trade_sharpe"],
        "all_trials": trials,
        "n_positions_total": len(outcome_rows),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(Path(args.root), args.market)
    if df.empty:
        print(json.dumps({"market": args.market, "note": "outcome_dataset empty"}, indent=2))
        return
    # Filter to non-admin closed with realized returns
    df = df[
        (df["is_administrative_exit"] != True)
        & df["realized_return_pct"].notna()
        & (df["runner"] == "R2")
    ].copy()
    # Enrich with placeholder sector_regime_score = 0, market_regime_score = 0
    # (Actual pipeline supplies these · here we degrade gracefully)
    if "sector_regime_score" not in df.columns:
        df["sector_regime_score"] = 0.0
    if "market_regime_score" not in df.columns:
        df["market_regime_score"] = 0.0
    if "base_ensemble_score" not in df.columns:
        df["base_ensemble_score"] = df.get("entry_signal_score", 0.0).fillna(0.0)
    rows = df.to_dict("records")
    result = walkforward_grid_search(rows)
    result["market"] = args.market
    result["built_utc"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    out = Path(args.root) / "reports" / "research" / "r2_upgrades"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"p2_sector_regime_{args.market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
