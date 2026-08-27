"""AEGIS · Delivery · Canonical Entry Resolver regression tests.

CEO 2026-08-27 · post-I26-oscillation directive:
> "build dataset twice from identical inputs
>  → byte / record equivalent canonical fields → I26 / I28 identical."

Covers exact failing rows from CI runs 33074829157 + 33079144704 plus the
determinism invariant.
"""
import json
import pytest
from pathlib import Path


def _write_parquet(tmp_path: Path, market: str, ticker: str,
                    date_close_pairs):
    """Bootstrap a minimal per-ticker parquet for the resolver."""
    import pandas as pd
    base = "usa/data/raw/us" if market == "usa" else "data/raw/india"
    d = tmp_path / base
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([p[0] for p in date_close_pairs])
    df = pd.DataFrame({"close": [p[1] for p in date_close_pairs]}, index=idx)
    df.to_parquet(d / f"{ticker}_D1.parquet")


# ── 1 · Exact PLTR row from CI run 33079144704 ──


def test_pltr_row_from_run_33079144704_uses_parquet_close_not_source(tmp_path):
    """Portfolio row: PLTR · R2 · entry_date=2026-08-10 · stored=$183.86.
    yfinance Aug 10 close for PLTR = $175.23 · drift 4.92% · I26 FAIL.
    Canonical resolver must return $175.23 (parquet close) via backfill
    path · NOT $183.86 (the source-XLSX restamped value)."""
    from backend.delivery.canonical_entry import resolve
    _write_parquet(tmp_path, "usa", "PLTR",
                   [("2026-08-10", 175.23)])
    result = resolve(tmp_path, market="usa", ticker="PLTR",
                     runner="R2", entry_date="2026-08-10")
    assert result.source == "parquet_backfill"
    assert result.entry_price == 175.23, \
        (f"PLTR canonical entry must be parquet close $175.23 · "
         f"got ${result.entry_price} · I26 would still FAIL in CI")
    assert result.entry_date == "2026-08-10"


# ── 2 · Determinism: two calls, byte-identical output ──


def test_resolve_is_deterministic_and_idempotent(tmp_path):
    """Two consecutive resolve() calls with identical inputs produce
    identical output AND do not grow the snapshot ledger."""
    from backend.delivery.canonical_entry import resolve
    from backend.delivery.prediction_snapshot import _load_ledger
    _write_parquet(tmp_path, "usa", "PLTR", [("2026-08-10", 175.23)])
    a = resolve(tmp_path, market="usa", ticker="PLTR",
                runner="R2", entry_date="2026-08-10")
    n1 = len(_load_ledger(tmp_path))
    b = resolve(tmp_path, market="usa", ticker="PLTR",
                runner="R2", entry_date="2026-08-10")
    n2 = len(_load_ledger(tmp_path))
    # 2nd call now hits path 1 (snapshot) instead of path 2 (backfill)
    assert a.entry_price == b.entry_price == 175.23
    assert a.entry_date == b.entry_date == "2026-08-10"
    # First call = parquet_backfill · second = snapshot (idempotent)
    assert a.source == "parquet_backfill"
    assert b.source == "snapshot"
    # Ledger did not grow (record_snapshot is idempotent per pid)
    assert n1 == n2 == 1, \
        f"snapshot ledger grew on rerun · {n1} → {n2} · not deterministic"


def test_resolve_ten_reruns_produce_identical_output(tmp_path):
    """Property-style: 10 reruns · all outputs identical · ledger stays 1."""
    from backend.delivery.canonical_entry import resolve
    from backend.delivery.prediction_snapshot import _load_ledger
    _write_parquet(tmp_path, "usa", "PLTR", [("2026-08-10", 175.23)])
    outputs = []
    for _ in range(10):
        r = resolve(tmp_path, market="usa", ticker="PLTR",
                    runner="R2", entry_date="2026-08-10")
        outputs.append((r.entry_date, r.entry_price))
    assert len(set(outputs)) == 1, \
        f"canonical resolve produced {len(set(outputs))} distinct outputs " \
        f"over 10 reruns · not deterministic"
    assert len(_load_ledger(tmp_path)) == 1


# ── 3 · Snapshot ledger overrides parquet (snapshot is authoritative) ──


def test_snapshot_ledger_beats_parquet_close(tmp_path):
    """When a snapshot exists (e.g., a canonical repair), resolve() must
    return the snapshot's value · not the parquet close · because snapshot
    is authoritative per CEO's rule."""
    from backend.delivery.canonical_entry import resolve
    from backend.delivery.prediction_snapshot import record_snapshot
    # Bootstrap: parquet says $71.41 for Aug 14 (yfinance-actual EIX close)
    _write_parquet(tmp_path, "usa", "EIX", [("2026-08-14", 71.41)])
    # Record a canonical snapshot at slightly different $71.08 (matches
    # source XLSX rows 3-7 · authoritative for AEGIS internal record)
    record_snapshot(tmp_path, market="USA", ticker="EIX",
                    prediction_date="2026-08-13",
                    entry_date="2026-08-14", entry_price=71.08,
                    source_close_date="2026-08-14",
                    source_dataset_version="canonical",
                    canonical_signal="R1_BUY")
    result = resolve(tmp_path, market="usa", ticker="EIX",
                     runner="R1", entry_date="2026-08-14")
    assert result.source == "snapshot"
    assert result.entry_price == 71.08, \
        "snapshot is authoritative · must beat parquet close"


# ── 4 · Missing parquet → source="unavailable" (never fabricate) ──


def test_no_parquet_no_snapshot_returns_unavailable(tmp_path):
    """When neither snapshot nor parquet has the ticker, resolve() returns
    source=unavailable · never fabricates a value."""
    from backend.delivery.canonical_entry import resolve
    result = resolve(tmp_path, market="usa", ticker="MISSING",
                     runner="R1", entry_date="2026-08-10")
    assert result.source == "unavailable"
    assert result.entry_price == 0.0


# ── 5 · Nearby-date lookback (matches I27/I28 tolerance) ──


def test_resolve_5day_nearby_lookback_matches_i27_i28(tmp_path):
    """When entry_date is not in parquet but a real close exists within
    5 calendar days · use that close. This mirrors I27/I28's 5-day
    nearby-lookback rule."""
    from backend.delivery.canonical_entry import resolve
    # Real close on 2026-08-10 · request for entry_date=2026-08-11
    # (position born same day ticker went inactive · same class as EA)
    _write_parquet(tmp_path, "usa", "EA", [("2026-08-10", 209.70)])
    result = resolve(tmp_path, market="usa", ticker="EA",
                     runner="R2", entry_date="2026-08-11")
    assert result.source == "parquet_backfill"
    assert result.entry_price == 209.70, \
        f"5-day nearby lookback should return Aug 10 close $209.70 · " \
        f"got ${result.entry_price}"


# ── 6 · Backfill switch off does not write to ledger ──


def test_backfill_off_returns_value_without_writing_ledger(tmp_path):
    """Callers that only want a validation reference (not a canonical
    commit) can pass backfill_snapshot=False."""
    from backend.delivery.canonical_entry import resolve
    from backend.delivery.prediction_snapshot import _load_ledger
    _write_parquet(tmp_path, "usa", "PLTR", [("2026-08-10", 175.23)])
    result = resolve(tmp_path, market="usa", ticker="PLTR",
                     runner="R2", entry_date="2026-08-10",
                     backfill_snapshot=False)
    assert result.source == "parquet_backfill"
    assert result.entry_price == 175.23
    assert len(_load_ledger(tmp_path)) == 0, \
        "backfill_snapshot=False must NOT write to ledger"
