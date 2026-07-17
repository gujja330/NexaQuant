"""DEV030 · Champion vs Challenger orchestration."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from champion_challenger.lib import strategies_io, scoring, head_to_head, regime, drift, promotion  # noqa: E402


CHAMPION_PARQUET = _ROOT / "data" / "market_intelligence" / "derived" / "champion_history.parquet"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _prior_champion_row() -> dict | None:
    """Load the last committed champion row from history parquet."""
    if not CHAMPION_PARQUET.exists():
        return None
    try:
        h = pd.read_parquet(CHAMPION_PARQUET)
    except Exception:
        return None
    if h.empty:
        return None
    prev = h.sort_values("run_utc").iloc[-1].to_dict()
    return prev


def _append_champion_history(row: dict) -> None:
    CHAMPION_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame([{k: v for k, v in row.items()
                              if not isinstance(v, (list, dict))}])
    if CHAMPION_PARQUET.exists():
        try:
            old = pd.read_parquet(CHAMPION_PARQUET)
            combined = pd.concat([old, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df
    combined.to_parquet(CHAMPION_PARQUET, index=False)


def run(verbose: bool = True) -> dict:
    strategies = strategies_io.load_backtested_strategies()
    if strategies.empty:
        return {"error": "backtest_summary.parquet missing — run DEV021 first"}

    if verbose:
        print(f"  loaded {len(strategies)} strategies from DEV021 backtest_summary.parquet")

    scored = scoring.score_strategies(strategies)
    leaderboard = scoring.rank_summary(scored)
    matrix = head_to_head.build_matrix(scored)

    equity = strategies_io.load_equity_curves()
    current_regime = strategies_io.load_current_regime()
    regime_report = regime.compare(equity, current_regime.get("global_posture", "Unknown"))

    drift_metric = drift.metric_drift(equity)
    drift_rank = drift.rank_drift(leaderboard)

    prior_champion = _prior_champion_row()
    prior_champion_row = None
    if prior_champion is not None:
        strat_name = prior_champion.get("champion")
        match = next((r for r in leaderboard if r["strategy"] == strat_name), None)
        if match is not None:
            prior_champion_row = match

    promo = promotion.evaluate_promotion(prior_champion_row, leaderboard, drift_metric)

    challenger_portfolios = strategies_io.load_challenger_portfolios()
    calib_summary = strategies_io.load_confidence_calibration_summary()

    # Extract champion after all gates
    if promo["decision"] == "promote_challenger":
        champion_name = promo["recommended_champion"]
    else:
        champion_name = leaderboard[0]["strategy"]

    champion_row = next((r for r in leaderboard if r["strategy"] == champion_name), leaderboard[0])
    challengers = [r for r in leaderboard if r["strategy"] != champion_name]

    now = datetime.now(timezone.utc).isoformat() + "Z"

    _append_champion_history({
        "run_utc":            now,
        "champion":           champion_name,
        "composite_score":    champion_row["composite_score"],
        "n_strategies":       len(leaderboard),
        "current_regime":     current_regime.get("global_posture", "Unknown"),
        "promotion_decision": promo["decision"],
        "code_sha":           _git_sha(),
    })

    # Drift history (JSON-encoded fields inside)
    try:
        drift.append_history({
            "run_utc":            now,
            "leaderboard_ranks":  [{"strategy": r["strategy"], "rank": r["rank"]}
                                     for r in leaderboard],
            "champion":           champion_name,
            "code_sha":           _git_sha(),
        })
    except Exception as e:
        if verbose:
            print(f"  warning: drift history append failed: {e}")

    if verbose:
        print(f"  champion:            {champion_name}")
        print(f"  composite_score:     {champion_row['composite_score']:.3f}")
        print(f"  promotion decision:  {promo['decision']}")
        print(f"  regime:              {current_regime.get('global_posture')}")

    return {
        "run_utc":                now,
        "code_sha":                _git_sha(),
        "dev_version":             "DEV030 v0.1",
        "n_strategies":            len(leaderboard),
        "champion":                {
            "strategy":            champion_name,
            "rank":                champion_row["rank"],
            "composite_score":     champion_row["composite_score"],
            "sharpe":              champion_row.get("sharpe"),
            "sortino":             champion_row.get("sortino"),
            "calmar":              champion_row.get("calmar"),
            "cagr":                champion_row.get("cagr"),
            "max_dd_pct":          champion_row.get("max_dd_pct"),
            "info_ratio":          champion_row.get("info_ratio"),
            "win_rate":            champion_row.get("win_rate"),
        },
        "current_regime":          current_regime,
        "leaderboard":             leaderboard,
        "challengers":             challengers,
        "head_to_head":            matrix,
        "regime_comparison":       regime_report,
        "metric_drift":            drift_metric,
        "rank_drift":              drift_rank,
        "promotion":               promo,
        "challenger_portfolios_n": int(len(challenger_portfolios)) if not challenger_portfolios.empty else 0,
        "calibration_note":        {
            "best_method":  calib_summary.get("best_method"),
            "raw_ece":      calib_summary.get("raw_metrics", {}).get("ece"),
            "cal_ece":      calib_summary.get("calibrated_metrics", {}).get("ece"),
        } if calib_summary else {},
        "_scored":                 scored,
        "_challenger_portfolios":  challenger_portfolios,
    }
