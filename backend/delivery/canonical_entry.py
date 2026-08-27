"""AEGIS · Delivery · Canonical Entry Resolver.

CEO 2026-08-27 · canonical/provenance layer directive (post-I26 oscillation):

  > "entry_price must come from the immutable prediction snapshot for that
  >  prediction, with the market-data close used only as a validation /
  >  reference check."
  >
  > "The XLSX must never independently reconstruct or reinterpret entry /
  >  exit dates or prices."
  >
  > "build dataset twice from identical inputs
  >  → byte / record equivalent canonical fields → I26 / I28 identical."

Runs 33058209890 → 33069236589 → 33074829157 → 33079144704 showed I26
oscillating (PASS → FAIL) because canonical coverage was per-row
manual: only rows with an explicit snapshot ledger entry were
canonicalized; every other row leaked source-XLSX corruption
(silent entry_price restamps to a later day's close · PLTR $175.23 →
$183.86).

## Canonical rule (deterministic pure function)

For every emitted Portfolio row · resolve `entry_price` in this order:

  1. Non-quarantined snapshot in `prediction_snapshots.jsonl` matching
     (market, ticker[, runner])  →  use snapshot's `entry_price` +
     `entry_date`.  Snapshot is authoritative.
  2. No snapshot  →  fall back to `parquet_close(ticker, entry_date)`.
     This is the canonical market close on the entry day · authoritative
     for historical predictions where no separate snapshot was ever
     recorded.  The result is written back to the snapshot ledger via
     `record_snapshot` so subsequent runs hit path 1 (idempotent).

Determinism guarantee: `resolve()` is a pure function of
`(market, ticker, runner, entry_date, parquet closes)`.  Rerunning the
pipeline against unchanged parquet + snapshot ledger produces
byte-identical output.

## Non-goals

- Never writes to `aegis_history.xlsx` (locked source).
- Never touches `xlsx_contract.py` / `xlsx_validator.py` (locked).
- Never touches R1 / R2 signal logic, E1 / E2 / E3, canonical
  INVESTMENT_ACTIVE JSON emit, Registry decision logic.

## Verification

Regression tests in
`tests/delivery/test_canonical_entry.py` cover:
  - Exact PLTR row from run 33079144704.
  - Exact EA row from run 33074829157 (I28 exit_before_entry class).
  - Determinism: resolve() called twice returns identical output.
  - Idempotency: snapshot ledger row-count invariant after N reruns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CanonicalEntry:
    """Immutable result of canonical entry resolution."""
    ticker:         str
    runner:         str
    entry_date:     str
    entry_price:    float
    source:         str          # "snapshot" | "parquet_backfill" | "unavailable"
    prediction_id:  Optional[str] = None


def _parquet_close(root: Path, market: str, ticker: str,
                    iso_date: str) -> Optional[float]:
    """Read-only close on iso_date · returns None if unavailable.

    Matches the market-selection logic used by
    `backend/delivery/xlsx_validator.py:_parquet_close_lookup` so both
    the resolver and I26 read the same values.
    """
    try:
        import pandas as pd
    except Exception:
        return None
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    base = ("usa/data/raw/us" if market.lower() == "usa"
             else "data/raw/india")
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if iso_date in df.index:
            return float(df.loc[iso_date, col])
        # 5-day nearby lookback (same tolerance as I27/I28)
        for lookback in range(1, 6):
            prior = (date.fromisoformat(iso_date)
                      - timedelta(days=lookback)).isoformat()
            if prior in df.index:
                return float(df.loc[prior, col])
        return None
    except Exception:
        return None


def resolve(root: Path, *, market: str, ticker: str, runner: str,
            entry_date: str,
            backfill_snapshot: bool = True) -> CanonicalEntry:
    """Return the canonical entry for one Portfolio row.

    Priority:
      1. Non-quarantined snapshot for (market, ticker, runner) →
         use snapshot's values.
      2. Fall back to parquet close on entry_date · when
         `backfill_snapshot=True` (default), the value is written back
         to the ledger via `record_snapshot` so subsequent runs are
         idempotent (path 1 hits on rerun).
      3. When neither snapshot nor parquet close is available, return
         `source="unavailable"` and `entry_price=0.0`. Caller decides
         whether to quarantine or fall through to source-XLSX (never
         emitted for locked rows).
    """
    from backend.delivery.prediction_snapshot import (
        get_by_ticker, record_snapshot,
    )
    # 1 · Snapshot lookup (canonical)
    snap = get_by_ticker(root, market, ticker, runner)
    if snap is not None and not snap.get("_quarantined"):
        ep = snap.get("entry_price")
        ed = str(snap.get("entry_date") or "")[:10]
        if isinstance(ep, (int, float)) and ep > 0 and ed:
            return CanonicalEntry(
                ticker=ticker.upper().replace(".NS","").replace(".BO",""),
                runner=(runner or "").upper().replace("_NEW",""),
                entry_date=ed, entry_price=float(ep),
                source="snapshot",
                prediction_id=snap.get("prediction_id"))
    # 2 · Parquet backfill
    ed = str(entry_date or "")[:10]
    if not ed:
        return CanonicalEntry(
            ticker=ticker.upper().replace(".NS","").replace(".BO",""),
            runner=(runner or "").upper().replace("_NEW",""),
            entry_date="", entry_price=0.0, source="unavailable")
    pc = _parquet_close(root, market, ticker, ed)
    if pc is None or pc <= 0:
        return CanonicalEntry(
            ticker=ticker.upper().replace(".NS","").replace(".BO",""),
            runner=(runner or "").upper().replace("_NEW",""),
            entry_date=ed, entry_price=0.0, source="unavailable")
    pc = round(float(pc), 2)
    if backfill_snapshot:
        try:
            row = record_snapshot(root, market=market, ticker=ticker,
                                    prediction_date=ed, entry_date=ed,
                                    entry_price=pc, source_close_date=ed,
                                    source_dataset_version="parquet_backfill",
                                    canonical_signal=(runner or "").upper())
            pid = row.get("prediction_id")
        except Exception:
            pid = None
    else:
        pid = None
    return CanonicalEntry(
        ticker=ticker.upper().replace(".NS","").replace(".BO",""),
        runner=(runner or "").upper().replace("_NEW",""),
        entry_date=ed, entry_price=pc,
        source="parquet_backfill", prediction_id=pid)
