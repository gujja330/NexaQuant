"""AEGIS Outcome Dataset · substrate for every P0-P5 experiment.

Reads Registry + Signal Ledger + optional Fundamentals snapshot and
emits one row per historical position with everything needed for
retrospective replay / calibration / walk-forward evaluation.
"""
from backend.research.outcome_dataset.build import (
    build_outcome_dataset, load_outcome_dataset,
)

__all__ = ["build_outcome_dataset", "load_outcome_dataset"]
