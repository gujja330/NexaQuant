"""Sprint B0 · Per-family quality scoring."""
from __future__ import annotations
from typing import Iterable


def compute_family_score(*,
                            exists: bool,
                            n_rows: int,
                            n_duplicate_dates: int,
                            n_missing_trading_days: int,
                            schema_ok: bool,
                            expected_min_rows: int = 1) -> int:
    """
    Score 0-100 per family.

    Composition:
        exists      = 40 pts (file present + readable)
        rows        = 20 pts (n_rows >= expected_min_rows)
        no_dupes    = 15 pts (n_duplicate_dates == 0)
        no_missing  = 15 pts (n_missing_trading_days == 0)
        schema      = 10 pts (schema_ok)
    """
    if not exists:
        return 0

    score = 40                              # existence
    if n_rows >= expected_min_rows:
        score += 20
    elif n_rows > 0:
        # partial credit for any rows
        score += int(20 * n_rows / max(expected_min_rows, 1))

    if n_duplicate_dates == 0:
        score += 15
    else:
        # -3 pts per duplicate up to zero
        score += max(0, 15 - 3 * n_duplicate_dates)

    if n_missing_trading_days == 0:
        score += 15
    else:
        # -1 pt per missing day up to zero (soft — history builds up over time)
        score += max(0, 15 - n_missing_trading_days)

    if schema_ok:
        score += 10

    return max(0, min(100, score))


def aggregate_score(family_scores: Iterable[int]) -> int:
    """Simple mean across all family scores."""
    vals = list(family_scores)
    if not vals:
        return 0
    return int(round(sum(vals) / len(vals)))
