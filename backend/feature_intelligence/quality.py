"""Feature Quality Engine — daily snapshot with history.

Extends Sprint 2.5's validate_snapshot() with:
  - Per-feature persistence (one row per (feature, day)) at
    features/quality_history.parquet — append-only.
  - Distribution summary (mean, std, min, p25, p50, p75, max).
  - Coverage tracking across snapshots so trends are visible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from backend.feature_store.feature_registry import FEATURE_REGISTRY, FeatureStatus

QUALITY_HISTORY_PATH = "features/quality_history.parquet"


@dataclass
class QualitySnapshot:
    market:            str
    asof:              date
    n_rows:            int
    n_features:        int
    null_pct_overall:  float
    per_feature_stats: list[dict] = field(default_factory=list)


def _dist_stats(s: pd.Series) -> dict:
    if len(s) == 0:
        return {"n_non_null": 0, "mean": None, "std": None,
                 "min": None, "p25": None, "p50": None, "p75": None, "max": None}
    if not pd.api.types.is_numeric_dtype(s):
        return {"n_non_null": int(s.notna().sum()), "mean": None, "std": None,
                 "min": None, "p25": None, "p50": None, "p75": None, "max": None}
    s2 = s.dropna()
    if len(s2) == 0:
        return {"n_non_null": 0, "mean": None, "std": None,
                 "min": None, "p25": None, "p50": None, "p75": None, "max": None}
    return {
        "n_non_null": int(len(s2)),
        "mean": float(s2.mean()),
        "std":  float(s2.std()) if len(s2) > 1 else 0.0,
        "min":  float(s2.min()),
        "p25":  float(s2.quantile(0.25)),
        "p50":  float(s2.quantile(0.50)),
        "p75":  float(s2.quantile(0.75)),
        "max":  float(s2.max()),
    }


def persist_quality_snapshot(repo_root: Path, market: str, asof: date,
                                df: pd.DataFrame) -> QualitySnapshot:
    """Extend a Feature Store snapshot with per-feature quality stats and persist."""
    stats: list[dict] = []
    n_rows = len(df)
    for f in FEATURE_REGISTRY:
        col = f.name
        if col not in df.columns: continue
        s = df[col]
        n_null = int(s.isna().sum())
        row = {
            "market":      market,
            "asof":        asof.isoformat(),
            "feature":     col,
            "category":    f.category.value,
            "status":      f.status.value,
            "n_rows":      n_rows,
            "n_null":      n_null,
            "null_pct":    round(n_null / n_rows, 4) if n_rows else 0.0,
            "coverage":    round(1 - (n_null / n_rows), 4) if n_rows else 0.0,
            **_dist_stats(s),
        }
        stats.append(row)

    df_hist = pd.DataFrame(stats)
    p = Path(repo_root) / QUALITY_HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    # Append-only: dedupe on (market, asof, feature) so re-runs on the same
    # day update in place but historical rows are preserved.
    if p.exists():
        try:
            old = pd.read_parquet(p)
            combined = pd.concat([old, df_hist], ignore_index=True) \
                          .drop_duplicates(subset=["market", "asof", "feature"], keep="last") \
                          .sort_values(["asof", "market", "feature"]).reset_index(drop=True)
        except Exception:
            combined = df_hist
    else:
        combined = df_hist
    combined.to_parquet(p, index=False)

    overall_null = 0.0
    if n_rows and stats:
        overall_null = round(sum(r["n_null"] for r in stats)
                              / (n_rows * len(stats)), 4)

    return QualitySnapshot(
        market=market, asof=asof,
        n_rows=n_rows, n_features=len(stats),
        null_pct_overall=overall_null,
        per_feature_stats=stats,
    )


def load_quality_history(repo_root: Path, market: str,
                            feature: str | None = None) -> pd.DataFrame:
    """Return the persistent history (optionally filtered)."""
    p = Path(repo_root) / QUALITY_HISTORY_PATH
    if not p.exists(): return pd.DataFrame()
    df = pd.read_parquet(p)
    df = df[df["market"] == market]
    if feature is not None:
        df = df[df["feature"] == feature]
    return df.sort_values("asof").reset_index(drop=True)
