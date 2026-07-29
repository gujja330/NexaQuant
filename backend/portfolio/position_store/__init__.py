"""Position Persistence Store · per-ticker state that survives across runs.

Enables the operator's roadmap items that need REAL per-position history:
  · Real `days_recommended` (not snapshot-derived approximation)
  · Real trailing stops (stop = max(stop, high_water * (1 - trail_pct)))
  · Real high-water tracking (max price observed since first_seen)
  · Real entry attribution (entry_price · entry_score · first_seen_date)
  · Real target progress tracking

Foundation for the Backtrack Timeline, AI Scorecard, Position History,
Performance-since-Recommendation columns.

Append-only per-ticker. Idempotent per (ticker, date). Never re-writes
historical entries — only extends the record.

Article 101.2 compliant · pure persistence · no analytics.
"""
from .store import (
    upsert_position,
    load_position,
    load_all_positions,
    update_from_recs,
    SCHEMA_FINGERPRINT,
    ENGINE_ID,
    TRAIL_PCT,
)

__all__ = [
    "upsert_position",
    "load_position",
    "load_all_positions",
    "update_from_recs",
    "SCHEMA_FINGERPRINT",
    "ENGINE_ID",
    "TRAIL_PCT",
]
