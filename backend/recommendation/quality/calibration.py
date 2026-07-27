"""Confidence Calibration + Kelly extension · Article 101.2 calibration correction.

Fits a per-confidence-bucket win-rate curve from historical closed trades
in learning.parquet. Every recommendation gets a `calibrated_kelly_fraction`
and `calibrated_expected_return_pct` derived from the ACTUAL trade evidence,
not from theoretical priors.

Institutional pattern:
    Historical confidence bucket → observed win rate → Kelly fraction
    → suggested max allocation

Constitution: extension of existing calibration.py (Article 101.2 permitted).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Iterable, Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.recommendation_quality.calibration.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.quality.calibration.v1"

# Kelly fraction is bounded institutionally. Full Kelly = 1.0. Half-Kelly is
# the industry default for risk-adjusted sizing. We cap at 0.5 (half-Kelly).
KELLY_CAP = 0.5


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    lo: float
    hi: float
    n: int
    win_rate: float | None
    mean_return_pct: float | None
    wilson_ci_low: float | None
    wilson_ci_high: float | None
    kelly_fraction: float | None
    suggested_allocation_pct: float | None


@dataclass
class CalibrationCurve:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    n_total_trades: int = 0
    buckets: list[dict] = field(default_factory=list)
    overall_win_rate: float | None = None
    overall_kelly: float | None = None


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    import math
    if n < 1: return None, None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return round(center - margin, 4), round(center + margin, 4)


def _kelly_fraction(win_rate: float | None, avg_win: float | None, avg_loss: float | None) -> float | None:
    """Kelly = p/L - q/W · where p=win_rate q=1-p L=avg_loss W=avg_win.
    Bounded [0, KELLY_CAP]. Returns None if inputs insufficient."""
    if win_rate is None or avg_win is None or avg_loss is None: return None
    if avg_win <= 0 or avg_loss >= 0: return None
    W = abs(avg_win)
    L = abs(avg_loss)
    p = win_rate
    q = 1 - p
    k = p / L * W - q  # equivalent to (bp - q) / b where b = W/L
    k = k / (W / L)  # normalize to fractional Kelly
    return round(max(0.0, min(KELLY_CAP, k)), 4)


def fit_calibration_curve(df,
                            buckets: Sequence[tuple[str, float, float]] | None = None
                            ) -> CalibrationCurve:
    """Fit a calibration curve from a trades DataFrame with columns:
    `confidence` · `return_pct`."""
    import pandas as pd
    curve = CalibrationCurve()
    if df is None or len(df) == 0 or "confidence" not in df.columns or "return_pct" not in df.columns:
        return curve
    curve.n_total_trades = len(df)
    overall_wins = int((df["return_pct"] > 0).sum())
    curve.overall_win_rate = round(overall_wins / len(df), 4)
    overall_avg_win = float(df[df["return_pct"] > 0]["return_pct"].mean()) if overall_wins > 0 else None
    overall_avg_loss = float(df[df["return_pct"] < 0]["return_pct"].mean()) if (df["return_pct"] < 0).any() else None
    curve.overall_kelly = _kelly_fraction(curve.overall_win_rate, overall_avg_win, overall_avg_loss)

    if buckets is None:
        buckets = [
            ("very_low(0-0.20)",  0.0, 0.20),
            ("low(0.20-0.40)",     0.20, 0.40),
            ("mid(0.40-0.60)",     0.40, 0.60),
            ("high(0.60-0.80)",    0.60, 0.80),
            ("very_high(0.80-1.0)",0.80, 1.01),
        ]
    for label, lo, hi in buckets:
        g = df[(df["confidence"] >= lo) & (df["confidence"] < hi)]
        n = len(g)
        if n == 0:
            curve.buckets.append(asdict(CalibrationBucket(
                label=label, lo=lo, hi=hi, n=0,
                win_rate=None, mean_return_pct=None,
                wilson_ci_low=None, wilson_ci_high=None,
                kelly_fraction=None, suggested_allocation_pct=None)))
            continue
        wins = int((g["return_pct"] > 0).sum())
        win_rate = round(wins / n, 4)
        ci_low, ci_high = _wilson(wins, n)
        mean_ret = round(float(g["return_pct"].mean()), 4)
        avg_win = float(g[g["return_pct"] > 0]["return_pct"].mean()) if wins > 0 else None
        avg_loss = float(g[g["return_pct"] < 0]["return_pct"].mean()) if (g["return_pct"] < 0).any() else None
        kelly = _kelly_fraction(win_rate, avg_win, avg_loss)
        # Suggested allocation = Kelly × 1% base (institutional 1% risk per trade default)
        alloc = round(kelly * 1.0, 4) if kelly is not None else None
        curve.buckets.append(asdict(CalibrationBucket(
            label=label, lo=lo, hi=hi, n=n,
            win_rate=win_rate, mean_return_pct=mean_ret,
            wilson_ci_low=ci_low, wilson_ci_high=ci_high,
            kelly_fraction=kelly, suggested_allocation_pct=alloc)))
    return curve


def apply_calibration_to_recs(recs: Sequence[Mapping], curve: dict) -> list[dict]:
    """For each rec, look up which calibration bucket its confidence falls
    into and enrich the rec with calibrated_kelly_fraction + calibrated_
    expected_return_pct + calibrated_win_probability."""
    out = []
    for r in recs:
        conf = float(r.get("confidence", 0.0))
        # Find bucket
        bucket = None
        for b in curve.get("buckets", []):
            if b["n"] > 0 and b["lo"] <= conf < b["hi"]:
                bucket = b; break
        if not bucket:
            enriched = {**r,
                        "calibrated_win_probability": None,
                        "calibrated_kelly_fraction": None,
                        "calibrated_expected_return_pct": None,
                        "calibrated_suggested_allocation_pct": None,
                        "calibration_source_n": 0,
                        "calibration_bucket": None}
        else:
            enriched = {**r,
                        "calibrated_win_probability": bucket["win_rate"],
                        "calibrated_kelly_fraction": bucket["kelly_fraction"],
                        "calibrated_expected_return_pct": bucket["mean_return_pct"],
                        "calibrated_suggested_allocation_pct": bucket["suggested_allocation_pct"],
                        "calibration_source_n": bucket["n"],
                        "calibration_bucket": bucket["label"]}
        out.append(enriched)
    return out
