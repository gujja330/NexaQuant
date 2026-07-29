"""Recommendation Snapshot Persistence.

Foundation for every downstream capability that requires historical
context: Evolution block, Backtrack Timeline, AI Performance Scorecard,
30-day / 90-day / 1-year windows, Monthly CEO Letter.

Contract:
  - Every daily run archives the day's enriched recommendations.json to
    reports/recommendations_history/{market}/{YYYY-MM-DD}.json (or the
    USA equivalent under usa/reports/).
  - Snapshots are APPEND-ONLY. A daily run for the same date overwrites
    the same file (idempotent) — but historical dates are never modified.
  - load_previous_snapshot() returns the newest snapshot strictly before
    a given asof date. Used by the enricher to compute evolution deltas.
  - load_snapshot_range() supports future Backtrack Engine windows
    (7 / 30 / 90 / 365 days).

Article 101.2 compliant · pure persistence · no analytics.
"""
from .store import (
    archive_snapshot,
    load_snapshot_for_date,
    load_previous_snapshot,
    load_snapshot_range,
    list_snapshot_dates,
    SCHEMA_FINGERPRINT,
    ENGINE_ID,
)

__all__ = [
    "archive_snapshot",
    "load_snapshot_for_date",
    "load_previous_snapshot",
    "load_snapshot_range",
    "list_snapshot_dates",
    "SCHEMA_FINGERPRINT",
    "ENGINE_ID",
]
