"""NEG-PNL-CONTROL-60D · additive research family · CEO 2026-09-03.

Purpose:
    Take the most recent 60 CALENDAR days of AEGIS output and investigate
    whether an earlier, more disciplined control/exit rule could have
    reduced negative P&L WITHOUT destroying positions that subsequently
    recovered or won.

Governance rules (immutable):
    - DOES NOT replace P0.
    - DOES NOT declare that stops should be tightened.
    - DOES NOT change R2.
    - DOES NOT lower any PDF gate.
    - Every control variant tested counts as a trial · deflated Sharpe /
      Reality Check applied when a "best" variant is picked.
    - Every result reports BOTH protection and damage metrics · a control
      cannot win by simply cutting everything.
    - Recent-60d evidence generates observations/hypotheses · the full
      Outcome Dataset stays the production validation base.

18 tests declared (T1..T18). This package implements the core trajectory
diagnostic that runs against currently available substrate. Tests that
require yet-unwired substrate (T4 static-vs-dynamic contrast, T7 signal-
deterioration history, T9 cap×sector×investability interaction) are
scaffolded and defer to their enrichers as those land.
"""
from backend.research.neg_pnl_control_60d.dataset import build_60d_dataset
from backend.research.neg_pnl_control_60d.trajectory import analyze_trajectories
from backend.research.neg_pnl_control_60d.counterfactual import (
    run_counterfactual_controls, CONTROL_THRESHOLDS_PCT, CONTROL_TIMINGS_DAYS,
)
from backend.research.neg_pnl_control_60d.panel import build_panel

__all__ = [
    "build_60d_dataset", "analyze_trajectories",
    "run_counterfactual_controls", "CONTROL_THRESHOLDS_PCT", "CONTROL_TIMINGS_DAYS",
    "build_panel",
]
