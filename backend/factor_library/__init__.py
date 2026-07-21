"""
Sprint 7.5 · Factor Library.

One row per (date, factor) — the substrate for AI-driven pattern search
(e.g. "show me every period where Oil + VIX + USD rose together") and
Research Factory factor validation without rebuilding data each time.
"""

from .engine import FactorLibraryEngine, build_factor_library
from .types import FactorReading, FactorLibraryResult

ENGINE_ID = "aegis.factor_library.v1"
ENGINE_VERSION = "1.0.0"

__all__ = [
    "FactorLibraryEngine",
    "build_factor_library",
    "FactorReading",
    "FactorLibraryResult",
    "ENGINE_ID",
    "ENGINE_VERSION",
]
