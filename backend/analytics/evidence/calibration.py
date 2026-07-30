"""Confidence calibration · confidence bucket → observed win rate.

Answers the operator's Ticket 12 remainder question:
  "Does 52% confidence actually correspond to a 52% win rate?"

If YES · confidence is calibrated · a 52% confidence rec should win
about 52% of the time. Operator can trust the number.
If NO · we can measure the bias (over-confident or under-confident)
and either recalibrate the confidence output OR label it explicitly.

Uses `reports/learning.parquet` (1060 closed trades since 2022-01)
with `confidence` + `is_winner` columns.

Emits `reports/evidence/calibration_report.json` and a compact
verdict string that feeds INTO the existing AI Scorecard display
(no new Telegram section per operator's Evidence Cycle discipline).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.analytics.evidence.calibration.v1.20260730"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.evidence.calibration.v1"

# Standard 10-point calibration bins across [0, 1)
DEFAULT_BINS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
                  (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


@dataclass
class CalibrationBucket:
    lo: float
    hi: float
    n_trades: int
    observed_win_rate: float
    expected_win_rate: float   # bucket midpoint
    calibration_error: float   # observed - expected · positive = over-delivered
    ci_lower_95: float          # Wilson lower bound
    ci_upper_95: float


@dataclass
class CalibrationReport:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    version: str = SCHEMA_VERSION
    run_utc: str = ""
    source: str = "reports/learning.parquet"
    n_trades: int = 0
    period_start: str = ""
    period_end: str = ""
    buckets: list = field(default_factory=list)
    overall_expected_win_rate: float = 0.0
    overall_observed_win_rate: float = 0.0
    calibration_slope: float | None = None    # regress observed on expected · 1.0 = perfect
    calibration_intercept: float | None = None
    brier_score: float | None = None           # lower is better (0 = perfect)
    verdict: str = ""
    verdict_short: str = ""    # for AI Scorecard display


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval · handles small-n and boundary cases."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def compute_calibration(df, bins: list | None = None) -> CalibrationReport:
    """Compute confidence-bucket calibration from a closed-trade DataFrame.

    Required columns: confidence, is_winner
    Optional columns: entry_date, exit_date (for period stamp)
    """
    if bins is None:
        bins = DEFAULT_BINS

    rep = CalibrationReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0 or "confidence" not in df.columns or "is_winner" not in df.columns:
        rep.verdict = "insufficient_data"
        rep.verdict_short = "no data"
        return rep

    # Clean
    df = df.dropna(subset=["confidence", "is_winner"]).copy()
    if len(df) == 0:
        rep.verdict = "no_valid_rows_after_dropna"
        rep.verdict_short = "no data"
        return rep

    rep.n_trades = len(df)
    if "entry_date" in df.columns:
        rep.period_start = str(df["entry_date"].min())[:10]
    if "exit_date" in df.columns:
        rep.period_end = str(df["exit_date"].max())[:10]

    # Bucket
    for lo, hi in bins:
        mask = (df["confidence"] >= lo) & (df["confidence"] < hi)
        sub = df[mask]
        n = int(len(sub))
        if n == 0:
            continue
        wins = int(sub["is_winner"].sum())
        obs_rate = wins / n
        exp_rate = (lo + hi) / 2
        ci_lo, ci_hi = _wilson_ci(wins, n)
        rep.buckets.append(asdict(CalibrationBucket(
            lo=round(lo, 2), hi=round(hi, 2), n_trades=n,
            observed_win_rate=round(obs_rate, 4),
            expected_win_rate=round(exp_rate, 4),
            calibration_error=round(obs_rate - exp_rate, 4),
            ci_lower_95=round(ci_lo, 4),
            ci_upper_95=round(ci_hi, 4),
        )))

    # Overall
    rep.overall_expected_win_rate = round(float(df["confidence"].mean()), 4)
    rep.overall_observed_win_rate = round(float(df["is_winner"].mean()), 4)

    # Simple regression slope (observed on expected · per bucket, weighted by n)
    if len(rep.buckets) >= 2:
        import numpy as np
        x = np.array([b["expected_win_rate"] for b in rep.buckets])
        y = np.array([b["observed_win_rate"] for b in rep.buckets])
        w = np.array([b["n_trades"] for b in rep.buckets], dtype=float)
        try:
            slope, intercept = np.polyfit(x, y, 1, w=w)
            rep.calibration_slope = round(float(slope), 4)
            rep.calibration_intercept = round(float(intercept), 4)
        except Exception:
            pass

    # Brier score: mean((confidence - is_winner)^2)
    try:
        rep.brier_score = round(float(((df["confidence"] - df["is_winner"]) ** 2).mean()), 4)
    except Exception:
        pass

    # Verdict
    slope = rep.calibration_slope
    if slope is None:
        rep.verdict = "insufficient_buckets"
        rep.verdict_short = "n/a"
    elif 0.90 <= slope <= 1.10 and abs(rep.overall_observed_win_rate - rep.overall_expected_win_rate) < 0.05:
        rep.verdict = "well_calibrated"
        rep.verdict_short = f"calibrated (slope {slope:.2f})"
    elif slope < 0.5:
        rep.verdict = "poorly_calibrated_flat"
        rep.verdict_short = f"flat (slope {slope:.2f} · confidence not discriminating)"
    elif rep.overall_observed_win_rate > rep.overall_expected_win_rate + 0.10:
        rep.verdict = "under_confident"
        rep.verdict_short = f"under-conf (+{(rep.overall_observed_win_rate - rep.overall_expected_win_rate):.2f})"
    elif rep.overall_observed_win_rate < rep.overall_expected_win_rate - 0.10:
        rep.verdict = "over_confident"
        rep.verdict_short = f"over-conf ({(rep.overall_observed_win_rate - rep.overall_expected_win_rate):.2f})"
    else:
        rep.verdict = "approximately_calibrated"
        rep.verdict_short = f"approx (slope {slope:.2f})"

    return rep


def run_calibration(root: Path) -> dict:
    """Load learning.parquet · compute + persist calibration report."""
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    out_dir = root / "reports" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not lp.exists():
        return asdict(CalibrationReport(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    rep = compute_calibration(df)
    (out_dir / "calibration_report.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)
