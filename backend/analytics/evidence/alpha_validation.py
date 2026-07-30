"""Expected Alpha Validation · predicted vs realized.

Answers: "Has Expected Alpha historically predicted realized alpha?"

Uses `learning.parquet.score_at_entry` as proxy for expected alpha
(what the engine thought at rec time) and `return_pct` as realized.

Computes:
  · Pearson correlation between score_at_entry and return_pct
  · Median absolute error
  · Directional accuracy (score sign vs return sign)
  · Empirical distribution per score bucket → real uncertainty range
    (this unblocks the deferred Ticket 13)

Emits `reports/evidence/alpha_validation_report.json`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.analytics.evidence.alpha_validation.v1.20260730"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.evidence.alpha_validation.v1"

# Score buckets · learning.parquet score_at_entry range is roughly 0-100
DEFAULT_SCORE_BINS = [(0, 20), (20, 40), (40, 60), (60, 70), (70, 80), (80, 90), (90, 101)]


@dataclass
class AlphaBucket:
    score_lo: float
    score_hi: float
    n_trades: int
    median_return_pct: float
    p25_return_pct: float
    p75_return_pct: float
    p10_return_pct: float
    p90_return_pct: float
    win_rate: float


@dataclass
class AlphaValidationReport:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    version: str = SCHEMA_VERSION
    run_utc: str = ""
    source: str = "reports/learning.parquet"
    n_trades: int = 0
    pearson_r: float | None = None
    directional_accuracy: float | None = None
    median_abs_error_pct: float | None = None
    mean_error_pct: float | None = None
    buckets: list = field(default_factory=list)
    verdict: str = ""


def compute_alpha_validation(df) -> AlphaValidationReport:
    """Compute Expected Alpha validation from closed-trade DataFrame."""
    rep = AlphaValidationReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0:
        rep.verdict = "insufficient_data"
        return rep
    needed = ["score_at_entry", "return_pct"]
    if not all(c in df.columns for c in needed):
        rep.verdict = "missing_columns"
        return rep

    import numpy as np
    import pandas as pd

    df = df.dropna(subset=needed).copy()
    if len(df) < 20:
        rep.verdict = "sample_too_small"
        rep.n_trades = int(len(df))
        return rep

    rep.n_trades = int(len(df))

    # Pearson correlation between score and return
    try:
        pearson = df["score_at_entry"].corr(df["return_pct"])
        rep.pearson_r = round(float(pearson), 4) if pearson == pearson else None
    except Exception:
        pass

    # Directional accuracy: score above mean → return positive?
    try:
        median_score = float(df["score_at_entry"].median())
        expected_bullish = df["score_at_entry"] > median_score
        realized_bullish = df["return_pct"] > 0
        rep.directional_accuracy = round(float((expected_bullish == realized_bullish).mean()), 4)
    except Exception:
        pass

    # Error metrics · treat score as %-scaled expectation (0-100 → -0.05..+0.05
    # is roughly the engine's implied return; empirically we just report the
    # median absolute error between the normalized-score and return-pct)
    try:
        # Normalize score to [-1, +1] around median for comparable units to return_pct
        score_norm = (df["score_at_entry"] - df["score_at_entry"].median()) / max(
            1.0, df["score_at_entry"].std())
        err = (df["return_pct"] - score_norm * df["return_pct"].std()).abs()
        rep.median_abs_error_pct = round(float(err.median()), 4)
        rep.mean_error_pct = round(float((df["return_pct"] - score_norm * df["return_pct"].std()).mean()), 4)
    except Exception:
        pass

    # Per-bucket empirical distribution (unblocks Ticket 13)
    for lo, hi in DEFAULT_SCORE_BINS:
        sub = df[(df["score_at_entry"] >= lo) & (df["score_at_entry"] < hi)]
        n = int(len(sub))
        if n == 0:
            continue
        rep.buckets.append(asdict(AlphaBucket(
            score_lo=float(lo), score_hi=float(hi), n_trades=n,
            median_return_pct=round(float(sub["return_pct"].median()), 4),
            p25_return_pct=round(float(sub["return_pct"].quantile(0.25)), 4),
            p75_return_pct=round(float(sub["return_pct"].quantile(0.75)), 4),
            p10_return_pct=round(float(sub["return_pct"].quantile(0.10)), 4),
            p90_return_pct=round(float(sub["return_pct"].quantile(0.90)), 4),
            win_rate=round(float((sub["return_pct"] > 0).mean()), 4),
        )))

    # Verdict
    r = rep.pearson_r
    if r is None:
        rep.verdict = "insufficient"
    elif r > 0.25:
        rep.verdict = "strong_predictive_relationship"
    elif r > 0.10:
        rep.verdict = "modest_predictive_relationship"
    elif r > 0.0:
        rep.verdict = "weak_predictive_relationship"
    else:
        rep.verdict = "no_predictive_relationship"
    return rep


def run_alpha_validation(root: Path) -> dict:
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    out_dir = root / "reports" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not lp.exists():
        return asdict(AlphaValidationReport(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    rep = compute_alpha_validation(df)
    (out_dir / "alpha_validation_report.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)
