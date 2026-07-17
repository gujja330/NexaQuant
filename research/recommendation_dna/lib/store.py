"""DEV028 append-only DNA store.

Every ingested recommendation becomes a new row. Existing rows are never
modified. Deduplicated by content key.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .dna_schema import DNARecord


_ROOT = Path(__file__).resolve().parents[3]
DNA_STORE = _ROOT / "data" / "market_intelligence" / "derived" / "recommendation_dna_store.parquet"


def _load_existing() -> pd.DataFrame:
    if not DNA_STORE.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(DNA_STORE)
    except Exception:
        return pd.DataFrame()


def append(records: list[DNARecord]) -> tuple[int, int]:
    """Append new records. Returns (n_added, n_deduped)."""
    if not records:
        return 0, 0
    DNA_STORE.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_existing()
    existing_keys = set(existing["_content_key"].tolist()) if not existing.empty and "_content_key" in existing.columns else set()

    new_rows = []
    n_dedup = 0
    for r in records:
        key = r.key()
        if key in existing_keys:
            n_dedup += 1
            continue
        row = r.to_dict()
        row["_content_key"] = key
        new_rows.append(row)

    if not new_rows:
        return 0, n_dedup

    new_df = pd.DataFrame(new_rows)
    # Coerce list-columns to JSON strings (parquet can't handle empty lists mixed with populated)
    for col in ["in_target_portfolios", "reasons_for", "reasons_against", "doctor_categories"]:
        if col in new_df.columns:
            new_df[col] = new_df[col].apply(lambda v: v if isinstance(v, list) else [])

    combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    combined.to_parquet(DNA_STORE, index=False)
    return len(new_rows), n_dedup


def load_all() -> pd.DataFrame:
    return _load_existing()


def latest_by_ticker(ticker: str) -> DNARecord | None:
    """Get the most recent DNA record for a ticker (across all versions)."""
    df = _load_existing()
    if df.empty or "ticker" not in df.columns:
        return None
    sub = df[df["ticker"] == ticker]
    if sub.empty:
        return None
    # Take the latest snapshot_utc
    latest = sub.sort_values("snapshot_utc").iloc[-1]
    return latest.to_dict()
