"""Multi-Layer Research · CEO 2026-09-01.

Discovery-based research framework. NOT fixed to seven layers · candidate
layers are discovered from what the data actually supports. Every layer is
research-only · never auto-changes R2 · never auto-promotes weights.

Layers (candidate · not final):
    A · AEGIS baseline (current recommendation output)
    B · technical/context (momentum, volatility, breadth, regime)
    C · fundamentals (earnings, revenue, margins, growth)
    D · valuation (P/E, P/B, EV/EBITDA, DCF-style)
    E · balance sheet + cash flow quality
    F · sector / market regime
    G · interactions (factor combinations, non-linear scores)
    H · walk-forward / out-of-sample robustness

Hard invariants:
    1. Point-in-time only · no look-ahead
    2. Insufficient historical data returns UNAVAILABLE · never
       fabricated / interpolated / backfilled
    3. Research produces EVIDENCE only · never modifies R2 weights,
       thresholds, entry/exit logic
    4. Walk-forward is the acceptance criterion for any candidate
       proposed for future R2 promotion
    5. Every experiment record includes a reproducibility hash of its
       inputs and the version of this framework
"""
from .layers import Layer, LayerRegistry
from .unavailable_contract import UNAVAILABLE, is_available
from .walk_forward import WalkForwardWindow, generate_windows
from .point_in_time_reader import PointInTimeReader

__all__ = [
    "Layer", "LayerRegistry",
    "UNAVAILABLE", "is_available",
    "WalkForwardWindow", "generate_windows",
    "PointInTimeReader",
]

__version__ = "0.1.0-scaffold"
