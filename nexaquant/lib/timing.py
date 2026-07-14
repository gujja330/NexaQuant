"""Timing utilities: `@timed` decorator + `time_block` context manager.

Enables lightweight performance instrumentation without pulling in a full
observability stack. Metrics are emitted via the standard logger (see
`nexaquant.lib.logging_setup`) and optionally recorded to a caller-supplied
dict for aggregation.

Pure: no I/O beyond logging. Never modifies globals except the optional sink dict.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Iterator, TypeVar


T = TypeVar("T")


def timed(logger=None, *, sink: dict | None = None,
           label: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that logs (and optionally records) wall-clock runtime.

    Usage:
        from nexaquant.lib.logging_setup import get_logger
        from nexaquant.lib.timing import timed
        log = get_logger(__name__)

        @timed(log)
        def compute_something(...):
            ...

    If `sink` is provided, records into it as `sink[label or func.__qualname__] += elapsed`.
    """
    def _wrap(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def _inner(*args, **kwargs) -> T:
            key = label or func.__qualname__
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - t0
                if logger is not None:
                    logger.info(f"[timing] {key} = {elapsed*1000:.1f} ms")
                if sink is not None:
                    sink[key] = sink.get(key, 0.0) + elapsed
        return _inner
    return _wrap


@contextmanager
def time_block(label: str, logger=None,
               sink: dict | None = None) -> Iterator[dict]:
    """Context manager that measures its body's wall-clock runtime.

    Yields a dict with a live `elapsed` reading if you touch it inside.

    Usage:
        with time_block("load_panels", log):
            closes = ...
    """
    ctx = {"elapsed": 0.0}
    t0 = time.perf_counter()
    try:
        yield ctx
    finally:
        elapsed = time.perf_counter() - t0
        ctx["elapsed"] = elapsed
        if logger is not None:
            logger.info(f"[timing] {label} = {elapsed*1000:.1f} ms")
        if sink is not None:
            sink[label] = sink.get(label, 0.0) + elapsed
