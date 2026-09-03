"""AEGIS Walk-Forward Engine

Shared math for every P0-P5 experiment.
  - Walk-forward folds (train=252, test=63, step=21, embargo=5)
  - Paired bootstrap (10k resamples)
  - Deflated Sharpe Ratio (Bailey & Lopez de Prado)
  - Likelihood-ratio test (nested models · P4)

Every experiment MUST route its statistical work through these functions
so trial accounting is uniform.
"""
from backend.research.walkforward.folds import walkforward_folds
from backend.research.walkforward.bootstrap import paired_bootstrap_ci
from backend.research.walkforward.deflated_sharpe import (
    deflated_sharpe_ratio, sharpe,
)
from backend.research.walkforward.lr_test import lr_test

__all__ = [
    "walkforward_folds",
    "paired_bootstrap_ci",
    "deflated_sharpe_ratio", "sharpe",
    "lr_test",
]
