"""DEV029 publish — 6 outputs."""
from __future__ import annotations

import json
import sys
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

    # ── confidence_calibration.json (overwrites the DEV025 one; superset) ──
    #     Note: DEV025 also writes this file; DEV029 supersedes with richer content.
    calib_bundle = _sanitize({
        "run_utc":                  result["run_utc"],
        "code_sha":                 result["code_sha"],
        "dev_version":              result["dev_version"],
        "n_trades_total":           result["n_trades_total"],
        "n_trades_train":           result["n_trades_train"],
        "n_trades_test":            result["n_trades_test"],
        "best_method":              result["best_method"],
        "best_method_params":       result["best_method_params"],
        "raw_metrics":              result["raw_metrics_all"],
        "calibrated_metrics":       result["calibrated_metrics_all"],
        "raw_reliability_curve":    result["raw_reliability"],
        "calibrated_reliability_curve": result["calibrated_reliability"],
        "governance":               "Retrain only when new data available; drift-based",
    })
    with (PUBLISH_DIR / "confidence_calibration.json").open("w", encoding="utf-8") as f:
        json.dump(calib_bundle, f, indent=2, default=str)

    # ── calibration_metrics.json (all methods scoreboard) ──
    with (PUBLISH_DIR / "calibration_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":     result["run_utc"],
            "scoreboard":  result["scoreboard"],
            "best_method": result["best_method"],
        }), f, indent=2, default=str)

    # ── reliability_diagram.json ──
    with (PUBLISH_DIR / "reliability_diagram.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":     result["run_utc"],
            "raw":         result["raw_reliability"],
            "calibrated":  result["calibrated_reliability"],
        }), f, indent=2, default=str)

    # ── confidence_bias.json ──
    with (PUBLISH_DIR / "confidence_bias.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       result["run_utc"],
            "bias_analysis": result["bias_analysis"],
            "warnings":      result["warnings"],
        }), f, indent=2, default=str)

    # ── calibration_history.json (load from parquet if exists) ──
    hist_p = _ROOT / "data" / "market_intelligence" / "derived" / "calibration_history.parquet"
    if hist_p.exists():
        try:
            hist = pd.read_parquet(hist_p)
            hist_rows = _sanitize(hist.to_dict(orient="records"))
        except Exception:
            hist_rows = []
    else:
        hist_rows = []
    with (PUBLISH_DIR / "calibration_history.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({"run_utc": result["run_utc"], "history": hist_rows}),
                  f, indent=2, default=str)

    # ── confidence_calibration.parquet — per-trade calibrated confidence ──
    per_trade_df = pd.DataFrame({
        "raw_confidence":        result["_all_conf"],
        "calibrated_confidence": result["_calibrated"],
        "is_winner":             result["_all_y"],
    })
    per_trade_df.to_parquet(PUBLISH_DIR / "confidence_calibration.parquet", index=False)

    return {
        "best_method":  result["best_method"],
        "raw_brier":    result["raw_metrics_all"]["brier_score"],
        "cal_brier":    result["calibrated_metrics_all"]["brier_score"],
        "raw_ece":      result["raw_metrics_all"]["ece"],
        "cal_ece":      result["calibrated_metrics_all"]["ece"],
    }
