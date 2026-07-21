"""Statistics — SINGLE source of truth for performance metrics.

Every downstream engine (execution, walk-forward, AI auditor) MUST import
Sharpe/Sortino/Calmar/etc from HERE. No duplicate implementations.

Deterministic. NumPy-only. No random state.
"""
from backend.statistics.metrics import (                                                    # noqa: F401
    sharpe_ratio, sortino_ratio, calmar_ratio, information_ratio,
    max_drawdown, recovery_factor, cagr,
    profit_factor, hit_rate, expected_value,
    avg_winner, avg_loser, avg_holding_period_days, turnover,
    tracking_error, alpha_beta,
    METRICS_VERSION,
)
