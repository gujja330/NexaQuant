"""Walk-forward window generator for Multi-Layer Research.

Given a start / end date and a config (train_days, test_days, step_days),
yield anchored, non-overlapping (train, test) window pairs. No look-ahead
· each test window strictly follows its train window · no shared days.

Reference implementation intended for reproducibility. Downstream research
scripts consume windows via `generate_windows(...)` and must resolve every
feature strictly with a `PointInTimeReader` bound to the train window
end · never beyond.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator


@dataclass(frozen=True)
class WalkForwardWindow:
    fold: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def as_dict(self) -> dict:
        return {
            "fold": self.fold,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }


def generate_windows(
    start: date,
    end: date,
    train_days: int = 180,
    test_days: int = 30,
    step_days: int | None = None,
) -> Iterator[WalkForwardWindow]:
    """Yield anchored walk-forward windows.

    Rules:
      · train_end + 1 = test_start (no gap · no overlap)
      · test_end = test_start + test_days - 1
      · next fold: train_end += step_days (default = test_days)
      · Stops when test_end would exceed `end`
    """
    if train_days <= 0 or test_days <= 0:
        raise ValueError("train_days and test_days must be positive")
    step = step_days or test_days
    fold = 0
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > end:
            break
        yield WalkForwardWindow(fold, train_start, train_end,
                                 test_start, test_end)
        fold += 1
        train_start = train_start + timedelta(days=step)
