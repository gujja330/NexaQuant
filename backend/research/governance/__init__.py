"""AEGIS Governance Layer · Signal Silence + Minimum Viable Signal.

Two governance triggers (pasted-plan §9):

  Signal Silence  · fires when a runner produces zero qualifying positions
                    for N ≥ 10 trading days while trailing baseline suggests
                    it normally produces more · never fires when all runners
                    are simultaneously silent (that may be genuine).

  MVS Floor       · composite layer requires >= 3 qualifying signals per day ·
                    below floor, GATE RELAXED (bounded), rerun, operator flagged.

  Relaxation cap  · at most 15 gate-relaxation days per rolling 90-day window ·
                    hard cap · prevents silent panic-overrides.
"""
from backend.research.governance.signal_silence import (
    evaluate_signal_silence, evaluate_mvs_floor, RelaxationTracker,
)

__all__ = [
    "evaluate_signal_silence",
    "evaluate_mvs_floor",
    "RelaxationTracker",
]
