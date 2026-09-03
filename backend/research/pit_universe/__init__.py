"""AEGIS Point-in-Time Universe Audit (P5.4)

Reconstructs universe membership as of every historical trade date so
backtests can filter to what was ACTUALLY investable that day, not what
is investable today. Prevents survivorship bias in P0-P5 experiments.
"""
from backend.research.pit_universe.build import (
    build_pit_universe, load_pit_universe, was_in_universe,
)

__all__ = ["build_pit_universe", "load_pit_universe", "was_in_universe"]
