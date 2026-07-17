"""DEV030 · publish — 7 outputs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def build_and_publish(result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    # ── champion_strategy.json ─────────────────────────────────────
    with (PUBLISH_DIR / "champion_strategy.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "code_sha":        result["code_sha"],
            "dev_version":     result["dev_version"],
            "champion":        result["champion"],
            "current_regime":  result["current_regime"],
            "calibration_note": result.get("calibration_note", {}),
            "governance":      "Advisory only; no mutation to recommendation engine.",
        }), f, indent=2, default=str)

    # ── challenger_scoreboard.json ─────────────────────────────────
    with (PUBLISH_DIR / "challenger_scoreboard.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":                result["run_utc"],
            "n_strategies":           result["n_strategies"],
            "champion":               result["champion"]["strategy"],
            "leaderboard":            result["leaderboard"],
            "challengers":            result["challengers"],
            "challenger_portfolios_n": result.get("challenger_portfolios_n", 0),
        }), f, indent=2, default=str)

    # ── head_to_head_matrix.json ───────────────────────────────────
    with (PUBLISH_DIR / "head_to_head_matrix.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":  result["run_utc"],
            "pairs":    result["head_to_head"],
        }), f, indent=2, default=str)

    # ── regime_comparison.json ─────────────────────────────────────
    with (PUBLISH_DIR / "regime_comparison.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":            result["run_utc"],
            "current_regime":     result["current_regime"],
            "regime_report":      result["regime_comparison"],
        }), f, indent=2, default=str)

    # ── drift_report.json ──────────────────────────────────────────
    with (PUBLISH_DIR / "drift_report.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       result["run_utc"],
            "metric_drift":  result["metric_drift"],
            "rank_drift":    result["rank_drift"],
        }), f, indent=2, default=str)

    # ── promotion_recommendation.json ──────────────────────────────
    with (PUBLISH_DIR / "promotion_recommendation.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":     result["run_utc"],
            "code_sha":    result["code_sha"],
            "promotion":   result["promotion"],
            "governance":  "Advisory only; promotion is a recommendation, not an action.",
        }), f, indent=2, default=str)

    # ── strategy_leaderboard.parquet ───────────────────────────────
    scored: pd.DataFrame = result["_scored"]
    if not scored.empty:
        # sanitise object columns for parquet
        out_df = scored.copy()
        for col in out_df.columns:
            if out_df[col].dtype == object:
                out_df[col] = out_df[col].astype(str)
        out_df.to_parquet(PUBLISH_DIR / "strategy_leaderboard.parquet", index=False)

    return {
        "champion":            result["champion"]["strategy"],
        "n_strategies":        result["n_strategies"],
        "promotion_decision":  result["promotion"]["decision"],
    }
