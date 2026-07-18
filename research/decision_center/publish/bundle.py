"""Decision Center · publish."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


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
    REPORTS.mkdir(parents=True, exist_ok=True)

    # 1. Full state (what the dashboard consumes)
    headline = {
        "run_utc":            result["run_utc"],
        "code_sha":           result["code_sha"],
        "engine":             result["engine"],
        "version":            result["version"],
        "date":               result["date"],
        "yesterday_date":     result["yesterday_date"],
        "overnight_summary":  result["overnight_summary"],
        "action_counts_today":    (result["diff"] or {}).get("action_counts") or {},
        "action_counts_yesterday":(result["diff"] or {}).get("action_counts_yesterday") or {},
        "counts_by_kind":     (result["diff"] or {}).get("counts_by_kind") or {},
        "n_changes":          (result["diff"] or {}).get("n_changes") or 0,
        "first_run":          (result["diff"] or {}).get("first_run", False),
        "changes":            (result["diff"] or {}).get("changes") or [],
        "watchlist":          result["watchlist"],
        "exit_center":        result["exit_center"],
        "notifications":      result["notifications"],
        "governance":         result["governance"],
    }
    with (REPORTS / "decision_center_today.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(headline), f, indent=2, default=str)

    # 2. Notifications-only (for the Telegram / email layer to consume)
    with (REPORTS / "decision_center_notifications.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":        result["run_utc"],
            "date":           result["date"],
            "notifications":  result["notifications"],
            "n_critical":     sum(1 for n in result["notifications"] if n["priority"] == "CRITICAL"),
            "n_high":         sum(1 for n in result["notifications"] if n["priority"] == "HIGH"),
            "n_medium":       sum(1 for n in result["notifications"] if n["priority"] == "MEDIUM"),
            "n_low":          sum(1 for n in result["notifications"] if n["priority"] == "LOW"),
        }), f, indent=2, default=str)

    return {
        "written": [
            "decision_center_today.json",
            "decision_center_notifications.json",
        ],
        "n_changes":       (result["diff"] or {}).get("n_changes", 0),
        "n_watchlist":     len(result["watchlist"]),
        "n_exit_center":   len(result["exit_center"]),
        "n_notifications": len(result["notifications"]),
    }
