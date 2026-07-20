"""Unified Feature Store — the single input to every downstream engine.

Architecture:
  raw parquets → canonical adapters → Feature Store → engines

Contract:
  - One row per (market, ticker, date).
  - Every column is registered in feature_registry with category, source, dtype.
  - Every snapshot is a self-contained parquet at features/{market}/{YYYY-MM-DD}.parquet
    plus an append-only manifest at features/manifest.jsonl.
  - Deterministic: same canonical inputs + same cutoff → identical vectors.
  - Replayable: builder accepts a cutoff date; every feature is computed as-of
    that date only, no leakage.

Files (per operator directive 2026-07-20):
  feature_registry.py    — features registered here
  feature_builder.py     — orchestrates a snapshot build
  feature_history.py     — read/write parquet snapshots + manifest
  feature_versioning.py  — schema fingerprint + migrations
  feature_snapshot.py    — top-level convenience
  feature_validation.py  — completeness + null + distribution checks
  features/              — per-category computers
"""
from backend.feature_store.feature_registry import (                                    # noqa: F401
    FEATURE_REGISTRY, register, list_features, list_categories,
    Feature, FeatureCategory,
)
from backend.feature_store.feature_builder    import FeatureBuilder                     # noqa: F401
from backend.feature_store.feature_history    import (                                  # noqa: F401
    snapshot_path, write_snapshot, read_snapshot, list_snapshots, append_manifest,
)
from backend.feature_store.feature_versioning import schema_fingerprint                 # noqa: F401
from backend.feature_store.feature_snapshot   import build_and_persist                  # noqa: F401
from backend.feature_store.feature_validation import validate_snapshot                  # noqa: F401
