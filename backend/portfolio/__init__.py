"""Sprint 5 · Portfolio Engine — build the investable portfolio.

Takes Sprint 4's sized_positions.json and constructs:
  - The N-name investable portfolio with normalised weights
  - Cash policy (min-cash floor + stress-regime cash boost)
  - Rebalance diff against prior day's state (add/close/adjust/hold)
  - Diversification metrics (HHI, sector spread, effective N)

Contracts (locked · Sprint 5 must obey all):
  - Deterministic
  - Walk-forward safe (accepts cutoff)
  - Append-only history (portfolio_state_history.jsonl)
  - Human-in-the-loop for promotion (aegis.portfolio.v1 registered EXPERIMENTAL)
  - AI Portfolio Analyst never promotes
"""
from backend.portfolio.types           import (                                             # noqa: F401
    Position, PortfolioSnapshot, TradeInstruction, PortfolioDiff,
)
from backend.portfolio.construction    import build_portfolio                                # noqa: F401
from backend.portfolio.diversification import compute_diversification_metrics                # noqa: F401
from backend.portfolio.rebalance       import diff_portfolios                                # noqa: F401
from backend.portfolio.cash_manager    import compute_cash_reserve                           # noqa: F401
from backend.portfolio.state           import (                                              # noqa: F401
    load_prior_state, save_current_state, append_state_history,
)
from backend.portfolio.engine          import PortfolioEngine                                # noqa: F401
