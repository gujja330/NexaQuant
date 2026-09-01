"""UNAVAILABLE contract for Multi-Layer Research.

When a feature or layer cannot be computed for a given (ticker, date)
because historical data does not exist / is insufficient / is out of
its support region, the framework returns the sentinel `UNAVAILABLE`
rather than 0 / NaN / a defaulted value.

Downstream code must call `is_available()` before treating a value as
numeric. Any downstream module that silently converts UNAVAILABLE to
zero / a mean / a fabricated interpolation is a contract violation and
must be surfaced by the reconciler.

CEO 2026-09-01 hard rule: `Insufficient historical data → UNAVAILABLE,
never fabricated`.
"""
from __future__ import annotations

from typing import Any


class _Unavailable:
    """Sentinel · single-instance · always returns False for is_available."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNAVAILABLE"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other) -> bool:
        return isinstance(other, _Unavailable)

    def __hash__(self) -> int:
        return hash("UNAVAILABLE")


UNAVAILABLE = _Unavailable()


def is_available(v: Any) -> bool:
    """True if v is a real value · False for UNAVAILABLE."""
    return not isinstance(v, _Unavailable)


def coalesce_unavailable(*values: Any, default: Any = None) -> Any:
    """Return the first available value · else default."""
    for v in values:
        if is_available(v):
            return v
    return default
