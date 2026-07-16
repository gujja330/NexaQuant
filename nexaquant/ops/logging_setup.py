"""OPS001-B structured logging with rotation and retention.

Central log configuration for the daemon. Emits JSON-per-line records to a
rotating file (bytes-based rotation by default; time-based available) and to
stderr for foreground / systemd journal / Task Scheduler capture.

Rotation policy (defaults):
- max_bytes:   5 MiB per active file
- backup_count: 14 (retains ~14 rotations)

Retention (separate from rotation) can archive rotated files by age.

Never crashes the caller: any I/O error falls back to a stderr-only logger.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGGER_NAME = "nexaquant.ops"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 14


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JsonFormatter(logging.Formatter):
    """One log record per JSON line. Extra fields are merged into the top-level object."""

    _standard_attrs = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _iso_utc(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "pid": record.process,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge caller-supplied `extra=` fields.
        for k, v in record.__dict__.items():
            if k in self._standard_attrs or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False, default=str)


@dataclass
class LogConfig:
    """Where to write and how big to grow before rotating."""
    log_dir: Path
    filename: str = "nexaquant_ops.jsonl"
    max_bytes: int = DEFAULT_MAX_BYTES
    backup_count: int = DEFAULT_BACKUP_COUNT
    level: str = "INFO"
    stderr_mirror: bool = True

    @property
    def active_log_path(self) -> Path:
        return self.log_dir / self.filename


def configure(cfg: LogConfig) -> logging.Logger:
    """Configure the shared nexaquant.ops logger. Idempotent — safe to call
    from multiple entrypoints; second-call handlers are not stacked.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
    # Idempotent: strip existing handlers so re-configure doesn't stack them.
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)

    formatter = JsonFormatter()

    try:
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(cfg.active_log_path),
            maxBytes=cfg.max_bytes,
            backupCount=cfg.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Fall back to stderr-only if file logging unavailable.
        pass

    if cfg.stderr_mirror:
        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """Return the shared logger. Callers before configure() get a plain stderr logger."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        # Minimal fallback so imports don't cause silent drops.
        h = logging.StreamHandler(stream=sys.stderr)
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def prune_old_logs(log_dir: Path, filename_prefix: str, retention_days: int) -> int:
    """Delete rotated log files older than `retention_days`. Returns number pruned.

    Never touches the active log file. Only rotated backups (with numeric or timestamp
    suffixes) are eligible. Any I/O error on an individual file is skipped.
    """
    if retention_days <= 0 or not log_dir.exists():
        return 0
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - retention_days * 86400.0
    pruned = 0
    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if not name.startswith(filename_prefix):
            continue
        if name == filename_prefix:
            continue  # never touch active file
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                p.unlink()
                pruned += 1
            except OSError:
                continue
    return pruned


def log_event(level: str, msg: str, **fields: Any) -> None:
    """Convenience: `log_event("INFO", "stage_started", stage=name, attempt=n)`."""
    logger = get_logger()
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, msg, extra=fields)


__all__ = [
    "LOGGER_NAME",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
    "JsonFormatter",
    "LogConfig",
    "configure",
    "get_logger",
    "log_event",
    "prune_old_logs",
]
