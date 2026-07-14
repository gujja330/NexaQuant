"""Standardized logger factory.

Replaces ad-hoc `print()` calls scattered across production scripts (~40 files
audited). Provides a single entry point that respects `AEGIS_LOG_LEVEL` env var
and writes to both stdout and an optional log file with a consistent format.

Does NOT rewire any existing caller — offered as an addition for future phases.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


DEFAULT_FORMAT: str = "%(asctime)s.%(msecs)03d [%(levelname)5s] %(name)s: %(message)s"
DEFAULT_DATEFMT: str = "%Y-%m-%dT%H:%M:%S"


def get_logger(name: str, *,
               level: str | int | None = None,
               log_file: Path | str | None = None,
               fmt: str = DEFAULT_FORMAT,
               datefmt: str = DEFAULT_DATEFMT) -> logging.Logger:
    """Return a configured logger.

    - `name`: identifier (usually `__name__`)
    - `level`: overrides AEGIS_LOG_LEVEL env var; defaults to INFO
    - `log_file`: optional file path to duplicate output to; parent auto-created
    - Idempotent: repeated calls for the same name reuse the existing logger
      instead of stacking handlers.
    """
    logger = logging.getLogger(name)
    if getattr(logger, "_nexaquant_configured", False):
        return logger

    if level is None:
        level = os.environ.get("AEGIS_LOG_LEVEL", "INFO")
    logger.setLevel(_coerce_level(level))

    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    if log_file is not None:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(p), encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger.propagate = False
    logger._nexaquant_configured = True  # type: ignore[attr-defined]
    return logger


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.INFO)
