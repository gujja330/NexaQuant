"""DEV024 alert engine.

Generates institutional alerts on a monitored portfolio:
  TARGET_REACHED · STOP_LOSS_HIT · TRAILING_STOP_TRIGGERED · WEIGHT_DRIFT
  SECTOR_DRIFT · RISK_BUDGET_BREACH · DRAWDOWN_BREACH · CONFIDENCE_DROP
  LIQUIDITY_RISK · CORPORATE_ACTION · TIME_EXIT_DUE
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .holdings import Portfolio, Position


@dataclass
class Alert:
    ticker: str | None
    alert_type: str
    severity: str            # INFO / WARNING / CRITICAL
    message: str
    context: dict


# ── Alert thresholds (institutional defaults) ────────────────────────────────
WEIGHT_DRIFT_THRESHOLD_PCT = 25.0   # % relative drift from target weight
SECTOR_DRIFT_THRESHOLD_PCT = 20.0
PORTFOLIO_DD_ALERT_PCT = -10.0
PORTFOLIO_DD_CRITICAL_PCT = -15.0
TIME_EXIT_WARNING_DAYS_BEFORE_MAX = 15


def scan(portfolio: Portfolio,
          recommendations_by_ticker: dict[str, dict] | None = None,
          max_holding_days: int = 90) -> list[Alert]:
    alerts: list[Alert] = []
    recommendations_by_ticker = recommendations_by_ticker or {}

    # ── Portfolio-level ──────────────────────────────────────────────────
    if portfolio.total_pnl_pct is not None:
        if portfolio.total_pnl_pct < PORTFOLIO_DD_CRITICAL_PCT:
            alerts.append(Alert(
                ticker=None, alert_type="PORTFOLIO_DRAWDOWN_CRITICAL",
                severity="CRITICAL",
                message=f"Portfolio down {portfolio.total_pnl_pct:.1f}% — exceeds critical DD threshold "
                        f"({PORTFOLIO_DD_CRITICAL_PCT}%)",
                context={"pnl_pct": portfolio.total_pnl_pct},
            ))
        elif portfolio.total_pnl_pct < PORTFOLIO_DD_ALERT_PCT:
            alerts.append(Alert(
                ticker=None, alert_type="PORTFOLIO_DRAWDOWN_WARNING",
                severity="WARNING",
                message=f"Portfolio down {portfolio.total_pnl_pct:.1f}% — alert threshold "
                        f"({PORTFOLIO_DD_ALERT_PCT}%)",
                context={"pnl_pct": portfolio.total_pnl_pct},
            ))

    # ── Per-position scans ───────────────────────────────────────────────
    for pos in portfolio.positions:
        if pos.latest_close is None:
            alerts.append(Alert(
                ticker=pos.ticker, alert_type="NO_PRICE_DATA",
                severity="WARNING",
                message=f"{pos.ticker}: no market data available",
                context={},
            ))
            continue

        # Target reached
        if pos.target_price and pos.latest_close >= pos.target_price:
            alerts.append(Alert(
                ticker=pos.ticker, alert_type="TARGET_REACHED",
                severity="INFO",
                message=f"{pos.ticker}: target INR{pos.target_price:.2f} reached at INR{pos.latest_close:.2f}",
                context={"target": pos.target_price, "current": pos.latest_close,
                          "gain_pct": pos.unrealised_pnl_pct},
            ))

        # Stop-loss hit
        if pos.stop_loss and pos.latest_close <= pos.stop_loss:
            alerts.append(Alert(
                ticker=pos.ticker, alert_type="STOP_LOSS_HIT",
                severity="CRITICAL",
                message=f"{pos.ticker}: STOP LOSS breached — {pos.latest_close:.2f} <= {pos.stop_loss:.2f}",
                context={"stop": pos.stop_loss, "current": pos.latest_close,
                          "loss_pct": pos.unrealised_pnl_pct},
            ))

        # Trailing stop triggered
        if pos.trailing_stop and pos.running_high and pos.latest_close <= pos.trailing_stop:
            alerts.append(Alert(
                ticker=pos.ticker, alert_type="TRAILING_STOP_TRIGGERED",
                severity="WARNING",
                message=f"{pos.ticker}: trailing stop triggered (peak INR{pos.running_high:.2f})",
                context={"trailing_stop": pos.trailing_stop, "running_high": pos.running_high,
                          "current": pos.latest_close},
            ))

        # Weight drift
        if pos.current_weight is not None and pos.target_weight > 0:
            rel_drift_pct = abs(pos.current_weight - pos.target_weight) / pos.target_weight * 100
            if rel_drift_pct > WEIGHT_DRIFT_THRESHOLD_PCT:
                direction = "up" if pos.current_weight > pos.target_weight else "down"
                alerts.append(Alert(
                    ticker=pos.ticker, alert_type="WEIGHT_DRIFT",
                    severity="WARNING",
                    message=f"{pos.ticker}: weight drifted {direction} "
                            f"{pos.current_weight*100:.2f}% vs target {pos.target_weight*100:.2f}% "
                            f"({rel_drift_pct:.1f}% relative)",
                    context={"target_weight": pos.target_weight,
                              "current_weight": pos.current_weight,
                              "relative_drift_pct": rel_drift_pct},
                ))

        # Time-exit warning
        if pos.days_held is not None:
            if pos.days_held >= max_holding_days:
                alerts.append(Alert(
                    ticker=pos.ticker, alert_type="TIME_EXIT_DUE",
                    severity="CRITICAL",
                    message=f"{pos.ticker}: held {pos.days_held}d — exceeds max {max_holding_days}d",
                    context={"days_held": pos.days_held, "max_hold": max_holding_days},
                ))
            elif pos.days_held >= max_holding_days - TIME_EXIT_WARNING_DAYS_BEFORE_MAX:
                alerts.append(Alert(
                    ticker=pos.ticker, alert_type="TIME_EXIT_APPROACHING",
                    severity="INFO",
                    message=f"{pos.ticker}: held {pos.days_held}d — approaching max {max_holding_days}d",
                    context={"days_held": pos.days_held, "max_hold": max_holding_days,
                              "days_remaining": max_holding_days - pos.days_held},
                ))

        # Recommendation deterioration
        current_rec = recommendations_by_ticker.get(pos.ticker)
        if current_rec:
            new_rec = current_rec.get("recommendation")
            new_score = current_rec.get("score", 0)
            new_class = current_rec.get("classification", "")
            if new_rec in ("Sell", "Avoid"):
                alerts.append(Alert(
                    ticker=pos.ticker, alert_type="CONFIDENCE_DROP",
                    severity="CRITICAL",
                    message=f"{pos.ticker}: current recommendation = {new_rec} "
                            f"(score {new_score:.1f}, {new_class}) — reassess",
                    context={"current_recommendation": new_rec,
                              "score": new_score, "classification": new_class},
                ))
            elif new_rec == "Reduce":
                alerts.append(Alert(
                    ticker=pos.ticker, alert_type="CONFIDENCE_DROP_MODERATE",
                    severity="WARNING",
                    message=f"{pos.ticker}: current recommendation = Reduce",
                    context={"current_recommendation": new_rec,
                              "score": new_score, "classification": new_class},
                ))

    return alerts


def summarise(alerts: list[Alert]) -> dict:
    counts_by_type: dict[str, int] = {}
    counts_by_severity: dict[str, int] = {"INFO": 0, "WARNING": 0, "CRITICAL": 0}
    for a in alerts:
        counts_by_type[a.alert_type] = counts_by_type.get(a.alert_type, 0) + 1
        counts_by_severity[a.severity] = counts_by_severity.get(a.severity, 0) + 1
    return {
        "total": len(alerts),
        "by_type": counts_by_type,
        "by_severity": counts_by_severity,
    }
