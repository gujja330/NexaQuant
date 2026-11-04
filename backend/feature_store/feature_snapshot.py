"""Top-level Feature Store convenience — build + persist + validate + manifest."""
from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

#: Set by tests ONLY, to redirect snapshot + manifest writes away from
#: the live tree. Production leaves it unset and writes to repo_root.
OUT_ROOT_ENV = "AEGIS_FEATURE_OUT_ROOT"


def resolved_out_root(repo_root: Path) -> Path:
    """Where feature-store writes land for this process."""
    env = os.environ.get(OUT_ROOT_ENV)
    return Path(env) if env else Path(repo_root)

from backend.canonical.model import MarketProfile
from backend.feature_store.feature_registry   import FEATURE_REGISTRY
from backend.feature_store.feature_builder    import FeatureBuilder
from backend.feature_store.feature_history    import (
    write_snapshot, append_manifest, snapshot_path,
)
from backend.feature_store.feature_versioning import SCHEMA_VERSION, schema_fingerprint
from backend.feature_store.feature_validation import validate_snapshot


def build_and_persist(repo_root: Path, market: MarketProfile,
                        asof: date | None = None,
                        out_root: Path | None = None) -> dict:
    """Build a snapshot, write to disk, validate, append to manifest.

    Reads come from `repo_root`. Writes go to `out_root`, which defaults
    to `repo_root` so production is unchanged.

    WHY THE SPLIT · CEO 2026-11-04
    ------------------------------
    Three tests in backend/tests/test_sprint25.py called this with the
    live repository as the root, so every regression run wrote real
    snapshots into `features/` and appended to the TRACKED
    `features/manifest.jsonl`. On 2026-11-04 that produced 6 India and
    12 USA snapshot files dated that day and grew the manifest from 300
    to 306 lines.

    A test suite that mutates the production data it is meant to
    validate cannot be trusted to validate it: the ledger acquires
    entries no pipeline run ever made, and a snapshot appears for a date
    no pipeline ever scored. Separating the output root lets a test read
    the real substrate - which is the point of those tests - while
    writing somewhere disposable.

    Returns a summary dict suitable for JSON serialisation.
    """
    asof = asof or date.today()
    # The env var exists so a test can redirect a SUBPROCESS runner,
    # which cannot be handed a Python argument. Production never sets it.
    if out_root is None:
        env = os.environ.get(OUT_ROOT_ENV)
        out_root = Path(env) if env else Path(repo_root)
    else:
        out_root = Path(out_root)
    builder = FeatureBuilder(repo_root, market)
    df = builder.build(asof=asof)
    if df is None or df.empty:
        return {
            "market": market.name, "asof": asof.isoformat(),
            "verdict": "FAIL", "n_rows": 0, "n_features": 0,
            "note": "empty snapshot — no rows produced",
        }

    p = write_snapshot(out_root, market.name, asof, df)
    val = validate_snapshot(df, FEATURE_REGISTRY)

    entry = {
        "market":            market.name,
        "asof":              asof.isoformat(),
        "written_utc":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path":              str(p.relative_to(out_root).as_posix()),
        "schema_version":    SCHEMA_VERSION,
        "schema_fingerprint": schema_fingerprint(),
        "n_rows":            val.n_rows,
        "n_columns":         val.n_columns,
        "n_features":        val.n_features,
        "verdict":           val.verdict,
        "null_pct_overall":  val.null_pct_overall,
        "coverage_per_category": val.coverage_per_category,
    }
    append_manifest(out_root, entry)

    return {
        **entry,
        "outliers_flagged": val.outliers_flagged,
    }
