"""Top-level Feature Store convenience — build + persist + validate + manifest."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from backend.canonical.model import MarketProfile
from backend.feature_store.feature_registry   import FEATURE_REGISTRY
from backend.feature_store.feature_builder    import FeatureBuilder
from backend.feature_store.feature_history    import (
    write_snapshot, append_manifest, snapshot_path,
)
from backend.feature_store.feature_versioning import SCHEMA_VERSION, schema_fingerprint
from backend.feature_store.feature_validation import validate_snapshot


def build_and_persist(repo_root: Path, market: MarketProfile,
                        asof: date | None = None) -> dict:
    """Build a snapshot, write to disk, validate, append to manifest.

    Returns a summary dict suitable for JSON serialisation.
    """
    asof = asof or date.today()
    builder = FeatureBuilder(repo_root, market)
    df = builder.build(asof=asof)
    if df is None or df.empty:
        return {
            "market": market.name, "asof": asof.isoformat(),
            "verdict": "FAIL", "n_rows": 0, "n_features": 0,
            "note": "empty snapshot — no rows produced",
        }

    p = write_snapshot(repo_root, market.name, asof, df)
    val = validate_snapshot(df, FEATURE_REGISTRY)

    entry = {
        "market":            market.name,
        "asof":              asof.isoformat(),
        "written_utc":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path":              str(p.relative_to(repo_root).as_posix()),
        "schema_version":    SCHEMA_VERSION,
        "schema_fingerprint": schema_fingerprint(),
        "n_rows":            val.n_rows,
        "n_columns":         val.n_columns,
        "n_features":        val.n_features,
        "verdict":           val.verdict,
        "null_pct_overall":  val.null_pct_overall,
        "coverage_per_category": val.coverage_per_category,
    }
    append_manifest(repo_root, entry)

    return {
        **entry,
        "outliers_flagged": val.outliers_flagged,
    }
