"""DEV027 publish — 6 outputs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
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
    return obj


def build_and_publish(result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    # ── strategy_doctor.json — top-level summary ──
    summary = _sanitize({
        "run_utc":            result["run_utc"],
        "code_sha":           result["code_sha"],
        "dev_version":        result["dev_version"],
        "n_trades":           result["n_trades"],
        "n_winners":          result["n_winners"],
        "n_losers":           result["n_losers"],
        "n_diagnoses_fired":  result["n_diagnoses_fired"],
        "top_failure_categories": result["failure_patterns"][:5],
        "governance_note":    "Advisory only. No production behaviour changed.",
    })
    with (PUBLISH_DIR / "strategy_doctor.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # ── root_cause_analysis.json — every diagnosis ──
    with (PUBLISH_DIR / "root_cause_analysis.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "n_diagnoses":     len(result["all_diagnoses"]),
            "diagnoses":       result["all_diagnoses"],
        }), f, indent=2, default=str)

    # ── failure_patterns.json ──
    with (PUBLISH_DIR / "failure_patterns.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":            result["run_utc"],
            "failure_categories": result["failure_patterns"],
            "failure_by_sector":  result["failure_by_sector"],
            "poor_diversification_cohorts": result["poor_div_cohorts"],
        }), f, indent=2, default=str)

    # ── success_patterns.json ──
    with (PUBLISH_DIR / "success_patterns.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":                result["run_utc"],
            "top_winning_sectors":    result["success_patterns"]["top_winning_sectors"],
            "top_winning_industries": result["success_patterns"]["top_winning_industries"],
        }), f, indent=2, default=str)

    # ── improvement_plan.json ──
    with (PUBLISH_DIR / "improvement_plan.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         result["run_utc"],
            "governance_note": "Advisory. Never auto-applied. ARCH001A Article V clause 5.1.",
            "n_items":         len(result["improvement_plan"]),
            "plan":            result["improvement_plan"],
        }), f, indent=2, default=str)

    # ── strategy_doctor.parquet — flat per-trade ──
    per_trade_df = pd.DataFrame(result["per_trade"])
    if not per_trade_df.empty:
        per_trade_df.to_parquet(PUBLISH_DIR / "strategy_doctor.parquet", index=False)

    return {"n_diagnoses": len(result["all_diagnoses"]),
             "n_improvements": len(result["improvement_plan"])}
