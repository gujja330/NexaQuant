"""DEV025 publish — 6 outputs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"

sys.path.insert(0, str(_ROOT / "research"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    return obj


def _df_to_records(df) -> list[dict]:
    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    return _sanitize(df.to_dict(orient="records"))


def build_and_publish(result: dict, suggestions: list[dict]) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    # ── learning_summary.json ──
    summary = _sanitize({
        "run_utc":     result["run_utc"],
        "code_sha":    result["code_sha"],
        "dev_version": result["dev_version"],
        "top_n":       result["top_n"],
        "date_range":  {"start": result["start_date"], "end": result["end_date"]},
        "aggregate":   result["aggregate"],
        "n_suggestions_generated": len(suggestions),
        "governance_note": ("Advisory only. NO parameter auto-adjustment. "
                              "ARCH001A Article V clause 5.1."),
    })
    with (PUBLISH_DIR / "learning_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # ── recommendation_accuracy.json ──
    accuracy = _sanitize({
        "run_utc":              result["run_utc"],
        "aggregate":            result["aggregate"],
        "score_buckets":        _df_to_records(result["score_buckets"]),
        "sector_performance":   _df_to_records(result["sector_performance"]),
        "industry_performance": _df_to_records(result["industry_performance"]),
        "stop_loss_stats":      result["stop_loss_stats"],
        "target_stats":         result["target_stats"],
    })
    with (PUBLISH_DIR / "recommendation_accuracy.json").open("w", encoding="utf-8") as f:
        json.dump(accuracy, f, indent=2, default=str)

    # ── confidence_calibration.json ──
    calib = _sanitize({
        "run_utc":              result["run_utc"],
        "brier_score":          result["aggregate"]["brier_score"],
        "expected_calibration_error": result["aggregate"]["expected_calibration_err"],
        "calibration_curve":    _df_to_records(result["calibration_curve"]),
        "per_sector_calibration": _df_to_records(result["sector_calibration"]),
    })
    with (PUBLISH_DIR / "confidence_calibration.json").open("w", encoding="utf-8") as f:
        json.dump(calib, f, indent=2, default=str)

    # ── pattern_discovery.json ──
    patterns_out = _sanitize({
        "run_utc":              result["run_utc"],
        "dimension_correlations": _df_to_records(result["dimension_correlations"]),
        "score_bucket_effectiveness": _df_to_records(result["score_buckets"]),
        "best_sectors":         _df_to_records(result["sector_performance"].head(5))
                                  if hasattr(result["sector_performance"], "head") else [],
        "worst_sectors":        _df_to_records(result["sector_performance"].tail(5))
                                  if hasattr(result["sector_performance"], "head") else [],
        "best_industries":      _df_to_records(result["industry_performance"].head(5))
                                  if hasattr(result["industry_performance"], "head") else [],
    })
    with (PUBLISH_DIR / "pattern_discovery.json").open("w", encoding="utf-8") as f:
        json.dump(patterns_out, f, indent=2, default=str)

    # ── improvement_suggestions.json ──
    suggestions_out = _sanitize({
        "run_utc":     result["run_utc"],
        "n":           len(suggestions),
        "governance_note": ("Advisory only. Not auto-applied. Every suggestion "
                              "requires operator review per ARCH001A Article V."),
        "suggestions": suggestions,
    })
    with (PUBLISH_DIR / "improvement_suggestions.json").open("w", encoding="utf-8") as f:
        json.dump(suggestions_out, f, indent=2, default=str)

    # ── learning.parquet — per-trade rows ──
    trades = result.get("trades")
    if trades is not None and hasattr(trades, "empty") and not trades.empty:
        trades.to_parquet(PUBLISH_DIR / "learning.parquet", index=False)

    return {
        "n_trades":     result["aggregate"]["n_trades"],
        "n_suggestions": len(suggestions),
        "brier":        result["aggregate"]["brier_score"],
        "ece":          result["aggregate"]["expected_calibration_err"],
    }
