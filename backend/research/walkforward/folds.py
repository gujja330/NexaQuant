"""Walk-forward fold generator · 252d train · 63d test · 21d step · 5d embargo.

Every experiment iterates these folds. Embargo prevents leakage from
overlapping forward-holding periods.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator


def walkforward_folds(start: str, end: str,
                      train_days: int = 252,
                      test_days: int = 63,
                      step_days: int = 21,
                      embargo_days: int = 5) -> Iterator[dict]:
    """Yield {train_start, train_end, embargo_start, embargo_end,
             test_start, test_end, fold_idx}.

    All dates are ISO strings · fold index starts at 0.
    """
    d0 = datetime.fromisoformat(start).date()
    d1 = datetime.fromisoformat(end).date()
    cursor = d0
    idx = 0
    while True:
        train_start = cursor
        train_end = train_start + timedelta(days=train_days - 1)
        embargo_start = train_end + timedelta(days=1)
        embargo_end = embargo_start + timedelta(days=embargo_days - 1)
        test_start = embargo_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > d1:
            break
        yield {
            "fold_idx": idx,
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "embargo_start": embargo_start.isoformat(),
            "embargo_end": embargo_end.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
        }
        cursor = cursor + timedelta(days=step_days)
        idx += 1
