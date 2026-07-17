"""DEV028 publish — 5 outputs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"

sys.path.insert(0, str(_ROOT / "research"))
from recommendation_dna.lib import store, search                                     # noqa: E402


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    return obj


def build_and_publish(engine_result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    df = store.load_all()

    # ── recommendation_dna.json ── most recent version per ticker ──
    if not df.empty:
        latest_per_rec = df.sort_values("snapshot_utc").groupby("recommendation_id").tail(1)
        latest_records = _sanitize(latest_per_rec.to_dict(orient="records"))
    else:
        latest_records = []
    with (PUBLISH_DIR / "recommendation_dna.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       engine_result["run_utc"],
            "dev_version":   engine_result["dev_version"],
            "n_records":     len(latest_records),
            "governance":    "Immutable, append-only, versioned. ARCH001A Article VII clause 7.4.",
            "records":       latest_records,
        }), f, indent=2, default=str)

    # ── recommendation_history.json ── all versions per rec ──
    if not df.empty:
        history_by_rec: dict[str, list] = {}
        for rec_id, group in df.groupby("recommendation_id"):
            history_by_rec[rec_id] = _sanitize(
                group.sort_values("version").to_dict(orient="records"))
    else:
        history_by_rec = {}
    with (PUBLISH_DIR / "recommendation_history.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       engine_result["run_utc"],
            "n_recommendations": len(history_by_rec),
            "history":       history_by_rec,
        }), f, indent=2, default=str)

    # ── recommendation_versions.json ── per-rec version summary ──
    version_rows = []
    if not df.empty:
        for rec_id, group in df.groupby("recommendation_id"):
            sorted_g = group.sort_values("version")
            version_rows.append({
                "recommendation_id": rec_id,
                "ticker":            sorted_g.iloc[-1].get("ticker"),
                "n_versions":        int(len(sorted_g)),
                "first_snapshot":    str(sorted_g.iloc[0]["snapshot_utc"]),
                "latest_snapshot":   str(sorted_g.iloc[-1]["snapshot_utc"]),
                "first_recommendation": sorted_g.iloc[0].get("recommendation_type"),
                "latest_recommendation": sorted_g.iloc[-1].get("recommendation_type"),
                "latest_confidence": sorted_g.iloc[-1].get("confidence"),
                "latest_score":      sorted_g.iloc[-1].get("company_score"),
            })
    with (PUBLISH_DIR / "recommendation_versions.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":         engine_result["run_utc"],
            "n_recommendations": len(version_rows),
            "versions":        version_rows,
        }), f, indent=2, default=str)

    # ── recommendation_statistics.json ──
    stats = search.statistics()
    with (PUBLISH_DIR / "recommendation_statistics.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":    engine_result["run_utc"],
            "statistics": stats,
        }), f, indent=2, default=str)

    # ── recommendation_dna.parquet ── full store ──
    if not df.empty:
        df.to_parquet(PUBLISH_DIR / "recommendation_dna.parquet", index=False)

    return {
        "n_records":         len(df) if not df.empty else 0,
        "n_recommendations": len(version_rows),
    }
