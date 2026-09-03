"""V2 §11 · Joint positive+negative P&L objective.

Every candidate strategy scored on BOTH sides simultaneously:
    winner_capture_lift  vs  winner_sacrifice
    loss_reduction       vs  loser_creation
    MFE_captured         vs  MFE_forfeited
    plus  drawdown / turnover / exposure / concentration / profit factor / Sharpe

A strategy that only captures more winners while creating disproportionate
losers is NOT a success. A strategy that reduces losses but destroys
profitable positions is NOT a success.
"""
from backend.research.joint_pnl.joint_score import (
    build_joint_score, joint_pnl_frontier,
)

__all__ = ["build_joint_score", "joint_pnl_frontier"]
