"""DEV026 report loaders — single source of truth for the assistant's evidence.

Loads every DEV017-025 report file. Missing reports are handled gracefully.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


@dataclass
class AegisState:
    """Snapshot of every DEV17-25 output — the AI assistant's grounding corpus."""
    global_context:       dict | None = None
    sector_context:       dict | None = None
    industry_context:     dict | None = None
    company_context:      dict | None = None
    backtest_summary:     dict | None = None
    strategy_comparison:  dict | None = None
    performance_metrics:  dict | None = None
    portfolio:            dict | None = None
    risk_report:          dict | None = None
    allocation_report:    dict | None = None
    stress_test:          dict | None = None
    portfolio_leaderboard: dict | None = None
    recommendations:      dict | None = None
    watchlist:            dict | None = None
    trade_summary:        dict | None = None
    execution_plan:       dict | None = None
    portfolio_monitor:    dict | None = None
    rebalance_plan:       dict | None = None
    performance_report:   dict | None = None
    alerts:               dict | None = None
    portfolio_health:     dict | None = None
    learning_summary:     dict | None = None
    recommendation_accuracy: dict | None = None
    confidence_calibration: dict | None = None
    pattern_discovery:    dict | None = None
    improvement_suggestions: dict | None = None


def _load(name: str) -> dict | None:
    p = REPORTS / name
    if not p.exists():
        return None
    try:
        return json.load(p.open("r", encoding="utf-8"))
    except Exception:
        return None


def load_all() -> AegisState:
    return AegisState(
        global_context=_load("global_context.json"),
        sector_context=_load("sector_context.json"),
        industry_context=_load("industry_context.json"),
        company_context=_load("company_context.json"),
        backtest_summary=_load("backtest_summary.json"),
        strategy_comparison=_load("strategy_comparison.json"),
        performance_metrics=_load("performance_metrics.json"),
        portfolio=_load("portfolio.json"),
        risk_report=_load("risk_report.json"),
        allocation_report=_load("allocation_report.json"),
        stress_test=_load("stress_test.json"),
        portfolio_leaderboard=_load("portfolio_leaderboard.json"),
        recommendations=_load("recommendations.json"),
        watchlist=_load("watchlist.json"),
        trade_summary=_load("trade_summary.json"),
        execution_plan=_load("execution_plan.json"),
        portfolio_monitor=_load("portfolio_monitor.json"),
        rebalance_plan=_load("rebalance_plan.json"),
        performance_report=_load("performance_report.json"),
        alerts=_load("alerts.json"),
        portfolio_health=_load("portfolio_health.json"),
        learning_summary=_load("learning_summary.json"),
        recommendation_accuracy=_load("recommendation_accuracy.json"),
        confidence_calibration=_load("confidence_calibration.json"),
        pattern_discovery=_load("pattern_discovery.json"),
        improvement_suggestions=_load("improvement_suggestions.json"),
    )


def state_summary(state: AegisState) -> dict:
    """Report what data is available for the assistant."""
    return {
        "global_context":      state.global_context is not None,
        "sector_context":      state.sector_context is not None,
        "industry_context":    state.industry_context is not None,
        "company_context":     state.company_context is not None,
        "portfolio":           state.portfolio is not None,
        "recommendations":     state.recommendations is not None,
        "portfolio_monitor":   state.portfolio_monitor is not None,
        "learning":            state.learning_summary is not None,
        "improvement_suggestions": state.improvement_suggestions is not None,
    }


# ── Convenience lookups ─────────────────────────────────────────────────────

def find_company(state: AegisState, ticker: str) -> dict | None:
    if state.company_context is None:
        return None
    for c in state.company_context.get("companies", []):
        if c.get("ticker") == ticker and c.get("status") == "computed":
            return c
    return None


def find_recommendation(state: AegisState, ticker: str) -> dict | None:
    if state.recommendations is None:
        return None
    for r in state.recommendations.get("recommendations", []):
        if r.get("ticker") == ticker:
            return r
    return None


def find_sector(state: AegisState, sector_display: str) -> dict | None:
    if state.sector_context is None:
        return None
    target = sector_display.lower()
    for s in state.sector_context.get("sectors", []):
        if s.get("display_name", "").lower() == target and s.get("status") == "computed":
            return s
    return None


def find_industry(state: AegisState, industry_display: str) -> dict | None:
    if state.industry_context is None:
        return None
    target = industry_display.lower()
    for i in state.industry_context.get("industries", []):
        if i.get("display_name", "").lower() == target and i.get("status") == "computed":
            return i
    return None
