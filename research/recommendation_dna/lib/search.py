"""DEV028 search — query the DNA store by multiple dimensions."""
from __future__ import annotations

import pandas as pd

from .store import load_all


def search(ticker: str | None = None, sector: str | None = None,
            industry: str | None = None, recommendation: str | None = None,
            min_score: float | None = None, min_confidence: float | None = None,
            date_from: str | None = None, date_to: str | None = None) -> pd.DataFrame:
    df = load_all()
    if df.empty:
        return df

    if ticker:
        df = df[df["ticker"] == ticker]
    if sector:
        df = df[df["sector"] == sector]
    if industry:
        df = df[df["industry"] == industry]
    if recommendation:
        df = df[df["recommendation_type"] == recommendation]
    if min_score is not None and "company_score" in df.columns:
        df = df[df["company_score"] >= min_score]
    if min_confidence is not None and "confidence" in df.columns:
        df = df[df["confidence"] >= min_confidence]
    if date_from:
        df = df[df["snapshot_utc"] >= date_from]
    if date_to:
        df = df[df["snapshot_utc"] <= date_to]
    return df


def statistics() -> dict:
    """Aggregate stats across the DNA corpus."""
    df = load_all()
    if df.empty:
        return {"n_records": 0}

    stats = {
        "n_records":               int(len(df)),
        "n_unique_tickers":        int(df["ticker"].nunique()) if "ticker" in df.columns else 0,
        "n_unique_recommendations": int(df["recommendation_id"].nunique())
                                       if "recommendation_id" in df.columns else 0,
        "date_range": {
            "min": df["snapshot_utc"].min() if "snapshot_utc" in df.columns else None,
            "max": df["snapshot_utc"].max() if "snapshot_utc" in df.columns else None,
        },
    }

    if "recommendation_type" in df.columns:
        stats["by_recommendation_type"] = df["recommendation_type"].value_counts().to_dict()

    if "confidence" in df.columns:
        s = df["confidence"].dropna()
        if not s.empty:
            stats["avg_confidence"] = round(float(s.mean()), 4)

    if "company_score" in df.columns:
        s = df["company_score"].dropna()
        if not s.empty:
            stats["avg_company_score"] = round(float(s.mean()), 2)

    # Outcome coverage
    if "outcome_return_pct" in df.columns:
        with_outcome = df[df["outcome_return_pct"].notna()]
        stats["n_with_outcome"] = int(len(with_outcome))
        if not with_outcome.empty:
            stats["avg_return_pct"] = round(float(with_outcome["outcome_return_pct"].mean()), 3)
            if "outcome_win" in df.columns:
                stats["win_rate_pct"] = round(float(with_outcome["outcome_win"].mean()) * 100, 2)

    # Version stats
    if "recommendation_id" in df.columns and "version" in df.columns:
        version_counts = df.groupby("recommendation_id")["version"].max()
        stats["version_stats"] = {
            "avg_versions_per_recommendation":  round(float(version_counts.mean()), 2),
            "max_versions":                     int(version_counts.max()),
            "n_recommendations_with_updates":   int((version_counts > 1).sum()),
        }

    # Sector distribution
    if "sector" in df.columns:
        stats["by_sector"] = df["sector"].value_counts().head(10).to_dict()

    return stats
