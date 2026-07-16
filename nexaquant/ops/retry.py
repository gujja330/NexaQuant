"""Retry policy primitive.

Pure data + tiny helper. No I/O. Used by the pipeline orchestrator to control
per-stage retry semantics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable


DEFAULT_BACKOFF_S: tuple[float, ...] = (5.0, 15.0, 45.0)


@dataclass
class RetryPolicy:
    """How many attempts and what backoff schedule between them.

    - max_attempts: including the initial attempt (so max_attempts=1 means no retry)
    - backoff_s: list of sleep durations BETWEEN attempts. If shorter than
      (max_attempts - 1), the last value is repeated. Empty list means no sleep.
    - timeout_per_attempt_s: hard timeout for each individual attempt
    """
    max_attempts: int = 1
    backoff_s: tuple[float, ...] = ()
    timeout_per_attempt_s: float = 600.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if any(b < 0 for b in self.backoff_s):
            raise ValueError("backoff_s must be non-negative")
        if self.timeout_per_attempt_s <= 0:
            raise ValueError("timeout_per_attempt_s must be positive")

    def sleep_before_attempt(self, attempt: int) -> float:
        """Return the sleep duration (seconds) BEFORE the given attempt number.

        Attempt 1 (the first) has no prior sleep → returns 0.
        Attempt 2 uses backoff_s[0]. Attempt 3 uses backoff_s[1]. Etc.
        Extends the last value if backoff_s is shorter than needed.
        """
        if attempt <= 1:
            return 0.0
        if not self.backoff_s:
            return 0.0
        idx = min(attempt - 2, len(self.backoff_s) - 1)
        return float(self.backoff_s[idx])

    def sleeper(self):
        """Return a callable (attempt: int) -> None that sleeps as configured.

        Extracted so tests can inject a fake sleeper (no wall-clock waits).
        """
        def _default_sleep(attempt: int) -> None:
            wait = self.sleep_before_attempt(attempt)
            if wait > 0:
                time.sleep(wait)
        return _default_sleep


@dataclass
class RetryOutcome:
    attempts: int
    succeeded: bool
    last_exception: BaseException | None = None
    last_exit_code: int | None = None
