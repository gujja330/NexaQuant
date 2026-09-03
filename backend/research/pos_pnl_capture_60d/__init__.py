"""POS-PNL-CAPTURE-60D · additive research family · CEO 2026-09-03.

Mirror of NEG-PNL-CONTROL-60D · asks the opposite question:

    "During the latest 60 calendar days of AEGIS output, which profitable
    opportunities were missed, why were they missed, and can the new
    AEGIS techniques recover those opportunities without materially
    increasing losses, drawdown, turnover, concentration, or sacrificing
    existing winners?"

Governance rules (immutable):
    - Additive · NOT a P0 replacement · NOT a NEG-PNL replacement.
    - PIT everything · Future returns are OUTCOME LABELS only.
    - No look-ahead in feature extraction · reconstruct universe per date.
    - Winner thresholds are PREDECLARED before inspecting results.
    - Every technique tested counts as a trial · deflated Sharpe applies.
    - Reports BOTH selection metrics AND portfolio consequences.
    - Missed winners CANNOT all be classified as AEGIS errors — bucket L
      (correct risk rejection) is a valid outcome.

18 tests declared in the CEO master prompt. This package implements the
core (T1 dataset + T3 winner definition + T4 missed-winner funnel A-F +
T5 selection metrics + T6 joint pos+neg accounting). Deferred tests
require additional enricher wiring; each documented at call site.
"""
from backend.research.pos_pnl_capture_60d.dataset import build_pos_capture_dataset
from backend.research.pos_pnl_capture_60d.winner_genome import WINNER_GENOME_FIELDS
from backend.research.pos_pnl_capture_60d.missed_winner_funnel import (
    classify_missed_winner, MISS_CATEGORIES,
)
from backend.research.pos_pnl_capture_60d.panel import build_capture_panel

__all__ = [
    "build_pos_capture_dataset", "WINNER_GENOME_FIELDS",
    "classify_missed_winner", "MISS_CATEGORIES", "build_capture_panel",
]
