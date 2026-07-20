"""Feature Store history — read/write parquet snapshots + manifest.

Layout:
  features/india/YYYY-MM-DD.parquet
  features/usa/YYYY-MM-DD.parquet
  features/manifest.jsonl              (append-only ledger)

Every write appends to the manifest with schema fingerprint + row count
+ timestamp. Reads are by (market, date) → DataFrame or None.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd


FEATURES_ROOT = "features"          # relative to repo root
MANIFEST_NAME = "manifest.jsonl"


def snapshot_path(repo_root: Path, market: str, asof: date) -> Path:
    return Path(repo_root) / FEATURES_ROOT / market / f"{asof.isoformat()}.parquet"


def manifest_path(repo_root: Path) -> Path:
    return Path(repo_root) / FEATURES_ROOT / MANIFEST_NAME


def write_snapshot(repo_root: Path, market: str, asof: date, df: pd.DataFrame) -> Path:
    p = snapshot_path(repo_root, market, asof)
    p.parent.mkdir(parents=True, exist_ok=True)
    # DO NOT overwrite an existing snapshot silently — write a stamped variant instead.
    if p.exists():
        # Rename existing to preserve history — a snapshot for a given
        # asof date should be stable. If we need to re-emit, we write a
        # `.rebuilt_HHMMSS.parquet` next to it so the original is preserved.
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        p_new = p.with_suffix(f".rebuilt_{stamp}.parquet")
        df.to_parquet(p_new, index=False)
        return p_new
    df.to_parquet(p, index=False)
    return p


def read_snapshot(repo_root: Path, market: str, asof: date) -> pd.DataFrame | None:
    p = snapshot_path(repo_root, market, asof)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def list_snapshots(repo_root: Path, market: str) -> list[date]:
    base = Path(repo_root) / FEATURES_ROOT / market
    if not base.exists():
        return []
    dates: list[date] = []
    for f in base.glob("*.parquet"):
        if ".rebuilt" in f.name:
            continue
        try:
            dates.append(date.fromisoformat(f.stem))
        except ValueError:
            continue
    return sorted(dates)


def append_manifest(repo_root: Path, entry: dict) -> None:
    p = manifest_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
