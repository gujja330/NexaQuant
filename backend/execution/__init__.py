"""Sprint 7 · Execution Simulator — turns portfolio_diff.json into realistic fills.

Reads Sprint 5's trade instructions, applies:
  - Slippage (linear-impact + vol-adjusted)
  - Commissions (per-market schedule)
  - Partial fills (multi-day when order > max daily participation × ADV)
  - Overnight gap handling (± threshold)
  - Corporate action adjustments (dividends / splits)

Emits execution_ledger.parquet (append-only fills) + equity_curve.parquet
+ performance_metrics.json (Sharpe/Sortino/Calmar/etc via backend.statistics).

Contracts:
  - Deterministic
  - Walk-forward safe (accepts cutoff)
  - Append-only ledger (natural key: market + ticker + fill_date + txn_id)
  - Empty-but-valid artifacts when no trades — explicitly labelled honest_empty
  - Model registry stamp on every fill
  - AI Execution Analyst never promotes
"""
from backend.execution.types             import (                                            # noqa: F401
    Fill, ExecutionState, EquityPoint, ExecutionSummary,
)
from backend.execution.slippage_model    import compute_slippage_bps                          # noqa: F401
from backend.execution.commissions       import commission_bps                                # noqa: F401
from backend.execution.fill_engine       import simulate_fills                                # noqa: F401
from backend.execution.gap_handler       import gap_stop_out                                  # noqa: F401
from backend.execution.corp_action_adjuster import apply_corporate_actions                   # noqa: F401
from backend.execution.equity_curve      import compute_equity_curve                          # noqa: F401
from backend.execution.engine            import ExecutionEngine                              # noqa: F401
