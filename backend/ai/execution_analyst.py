"""AI Execution Analyst v1.0 — descriptive audit of the day's execution."""
from __future__ import annotations

from datetime import date

from backend.ai.base import AgentOutput
from backend.execution.types import ExecutionSummary

VERSION = "v1.0"


def run(summary: ExecutionSummary, market_name: str,
         asof: date | None = None) -> AgentOutput:
    findings: list[dict] = []

    # Composition
    findings.append({
        "type":                        "execution_composition",
        "starting_aum":                summary.starting_aum,
        "n_trade_instructions":        summary.n_trade_instructions,
        "n_fills_generated":           summary.n_fills_generated,
        "n_fills_partial":             summary.n_fills_partial,
        "total_commission":            summary.total_commission,
        "total_slippage_currency":     summary.total_slippage,
        "equity_value_end":            summary.equity_value_end,
        "cash_end":                    summary.cash_end,
        "long_notional":               summary.long_notional,
        "short_notional":              summary.short_notional,
        "n_open_positions":            summary.n_open_positions,
        "n_closed_positions_today":    summary.n_closed_positions_today,
        "turnover_today":              summary.turnover_today,
    })

    # Honest-empty branch
    if summary.honest_empty:
        findings.append({
            "type":         "honest_empty",
            "reason":       summary.honest_empty_reason,
            "note":         ("Execution simulator ran successfully but produced no fills — "
                              "this reflects upstream state (portfolio produced 0 trades), "
                              "not a simulator defect. Empty artifacts are valid."),
        })

    # Perf metrics — only when multi-point curve exists
    if summary.sharpe_annualised is not None:
        findings.append({
            "type":                "performance_metrics_today",
            "sharpe_annualised":   summary.sharpe_annualised,
            "sortino_annualised":  summary.sortino_annualised,
            "calmar_ratio":        summary.calmar_ratio,
            "max_drawdown_pct":    summary.max_drawdown_pct,
            "profit_factor":       summary.profit_factor,
            "hit_rate":            summary.hit_rate,
        })
    else:
        findings.append({
            "type":         "insufficient_history_for_metrics",
            "note":         ("Sharpe / Sortino / Calmar / MDD require a multi-day equity curve. "
                              "Today's run is a single-day snapshot; those metrics populate "
                              "once the equity curve accumulates OR Sprint 8 walk-forward runs."),
        })

    head = (f"fills={summary.n_fills_generated} · trade_instructions={summary.n_trade_instructions} "
             f"· equity={summary.equity_value_end:.2f} · cash={summary.cash_end:.2f}"
             + (" · honest_empty" if summary.honest_empty else ""))
    narr = (head + ".\n\n"
             "Execution Simulator audit. This engine turns portfolio trade instructions into "
             "realistic fills (slippage + commission + partial fills + gaps + corp actions) "
             "and marks the book to market. Does NOT approve or promote — every fill is "
             "EXPERIMENTAL until promoted via backend.promotion.promotion_gate.approve_model.")

    return AgentOutput(
        agent="execution_analyst", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings,
        evidence={
            "starting_aum":       summary.starting_aum,
            "n_fills_generated":  summary.n_fills_generated,
            "n_trade_instructions": summary.n_trade_instructions,
            "honest_empty":       summary.honest_empty,
            "equity_value_end":   summary.equity_value_end,
        },
        citations=["backend/execution/engine.py", "configs/execution_config.yaml",
                    "backend/statistics/metrics.py"],
        confidence=0.85,
        caveats=[
            "single-day equity curve → Sharpe/Sortino/Calmar require Sprint 8 walk-forward",
            "descriptive only — never promotes",
        ],
        determinism="template",
    )
