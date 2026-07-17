"""DEV024 publish — 6 outputs (5 JSON + 1 parquet)."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
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


def build_and_publish(result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    portfolio = result["portfolio"]
    exposures = result["exposures"]
    attribution = result["attribution"]
    alerts = result["alerts"]
    rebal_plan = result["rebalance_plan"]
    health = result["health"]

    # Convert alerts (dataclass) to dicts
    alerts_serialised = [asdict(a) for a in alerts]

    # Convert portfolio positions to dicts
    positions_serialised = [asdict(p) for p in portfolio.positions]

    portfolio_dict = {
        "portfolio_id":            portfolio.portfolio_id,
        "created_date":            portfolio.created_date,
        "days_active":             portfolio.days_active,
        "cash":                    portfolio.cash,
        "total_equity_value":      portfolio.total_equity_value,
        "total_portfolio_value":   portfolio.total_portfolio_value,
        "total_invested_capital":  portfolio.total_invested_capital,
        "total_pnl_abs":           portfolio.total_pnl_abs,
        "total_pnl_pct":           portfolio.total_pnl_pct,
        "positions":               positions_serialised,
    }

    # ── portfolio_monitor.json ──
    monitor_bundle = _sanitize({
        "run_utc":       result["run_utc"],
        "code_sha":      result["code_sha"],
        "dev_version":   "DEV024 v0.1",
        "portfolio":     portfolio_dict,
        "exposures":     exposures,
        "health":        health,
    })
    with (PUBLISH_DIR / "portfolio_monitor.json").open("w", encoding="utf-8") as f:
        json.dump(monitor_bundle, f, indent=2, default=str)

    # ── rebalance_plan.json ──
    rebal_bundle = _sanitize({
        "run_utc":         result["run_utc"],
        "portfolio_id":    portfolio.portfolio_id,
        "n_actions":       len(rebal_plan),
        "governance_note": "Advisory only. Operator reviews and executes manually.",
        "plan":            rebal_plan,
    })
    with (PUBLISH_DIR / "rebalance_plan.json").open("w", encoding="utf-8") as f:
        json.dump(rebal_bundle, f, indent=2, default=str)

    # ── performance_report.json ──
    perf_bundle = _sanitize({
        "run_utc":         result["run_utc"],
        "portfolio_id":    portfolio.portfolio_id,
        "portfolio_value": portfolio.total_portfolio_value,
        "pnl_abs":         portfolio.total_pnl_abs,
        "pnl_pct":         portfolio.total_pnl_pct,
        "days_active":     portfolio.days_active,
        "attribution":     attribution,
    })
    with (PUBLISH_DIR / "performance_report.json").open("w", encoding="utf-8") as f:
        json.dump(perf_bundle, f, indent=2, default=str)

    # ── alerts.json ──
    from portfolio_monitor.lib import alerts as al_module
    alerts_bundle = _sanitize({
        "run_utc":       result["run_utc"],
        "portfolio_id":  portfolio.portfolio_id,
        "summary":       al_module.summarise(alerts),
        "alerts":        alerts_serialised,
    })
    with (PUBLISH_DIR / "alerts.json").open("w", encoding="utf-8") as f:
        json.dump(alerts_bundle, f, indent=2, default=str)

    # ── portfolio_health.json ──
    health_bundle = _sanitize({
        "run_utc":  result["run_utc"],
        "health":   health,
        "exposures": exposures,
    })
    with (PUBLISH_DIR / "portfolio_health.json").open("w", encoding="utf-8") as f:
        json.dump(health_bundle, f, indent=2, default=str)

    # ── portfolio_monitor.parquet (flat per-position table) ──
    rows = []
    for pos in portfolio.positions:
        rows.append({
            "portfolio_id":       portfolio.portfolio_id,
            "ticker":             pos.ticker,
            "shares":             pos.shares,
            "avg_cost":           pos.avg_cost,
            "latest_close":       pos.latest_close,
            "current_value":      pos.current_value,
            "current_weight":     pos.current_weight,
            "target_weight":      pos.target_weight,
            "unrealised_pnl_abs": pos.unrealised_pnl_abs,
            "unrealised_pnl_pct": pos.unrealised_pnl_pct,
            "days_held":          pos.days_held,
            "target_price":       pos.target_price,
            "stop_loss":          pos.stop_loss,
            "trailing_stop":      pos.trailing_stop,
            "running_high":       pos.running_high,
            "recommendation_type": pos.recommendation_type,
        })
    if rows:
        pd.DataFrame(rows).to_parquet(PUBLISH_DIR / "portfolio_monitor.parquet", index=False)

    return {
        "portfolio":  portfolio,
        "n_alerts":   len(alerts),
        "n_actions":  len(rebal_plan),
        "health_score": health["health_score"],
    }
