"""
Sprint 7.5 · Persistence layer.

Standard append-only history writer used by every engine runner.
Every daily JSON snapshot has a `_history.parquet` companion that
walk-forward, learning, AI auditor, and research factory replay
against.
"""

from .history_writer import (
    append_snapshot_row,
    append_and_record,
    record_not_attempted,
    persistence_state_path,
    ALLOWED_SKIP_REASONS,
    REASON_UPSTREAM_FATAL,
    write_snapshot_and_history,
    load_history,
    HISTORY_SCHEMA_VERSION,
)

__all__ = [
    "append_snapshot_row",
    "append_and_record",
    "record_not_attempted",
    "persistence_state_path",
    "ALLOWED_SKIP_REASONS",
    "REASON_UPSTREAM_FATAL",
    "write_snapshot_and_history",
    "load_history",
    "HISTORY_SCHEMA_VERSION",
]
