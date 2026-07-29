"""AI Performance Scorecard · 6 institutional metrics from closed-trade history.

Consumes: reports/learning.parquet (1060 closed trades, 4+ year history)
Emits:    reports/ai_scorecard.json   (also surfaced in Command Center)

Metrics (each 1-5 stars + numeric):
  1. Recommendation Accuracy — win rate on closed trades
  2. Exit Timing              — MFE-capture ratio (how much of the
                                 max favorable move did we realize)
  3. Target Hit Rate          — % of trades that hit 5% target
  4. Risk Control             — median MAE (max adverse excursion);
                                 lower is better
  5. Confidence Calibration   — Pearson correlation between
                                 confidence bucket and realized win rate
  6. Rotation Quality         — profit factor (Σ wins / |Σ losses|)

Star rules calibrated to institutional benchmarks:
  ★★★★★  top-quartile professional performance
  ★★★★☆  solid institutional
  ★★★☆☆  acceptable
  ★★☆☆☆  needs improvement
  ★☆☆☆☆  concerning

Article 101.2 · pure measurement, zero prediction, no new engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_FINGERPRINT = "aegis.analytics.scorecard.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.scorecard.v1"

# Institutional benchmarks per metric (each stars 1..5)
STAR_THRESHOLDS = {
    "recommendation_accuracy": [(0.65, 5), (0.58, 4), (0.52, 3), (0.45, 2), (0.0, 1)],
    "exit_timing_pct":          [(0.70, 5), (0.55, 4), (0.40, 3), (0.25, 2), (0.0, 1)],
    "target_hit_rate":          [(0.50, 5), (0.40, 4), (0.30, 3), (0.20, 2), (0.0, 1)],
    # Risk control: MAE is negative; smaller absolute is better
    # Threshold as "median MAE better than X pct"
    "risk_control_mae_pct":     [(-5.0, 5), (-8.0, 4), (-12.0, 3), (-18.0, 2), (-100.0, 1)],
    "confidence_calibration":   [(0.30, 5), (0.20, 4), (0.10, 3), (0.05, 2), (0.0, 1)],
    "rotation_quality_pf":      [(2.5, 5), (1.75, 4), (1.30, 3), (1.10, 2), (0.0, 1)],
}


@dataclass
class ScorecardMetric:
    name: str
    value: float
    stars: int
    unit: str
    n_observations: int
    description: str
    benchmark: str


@dataclass
class Scorecard:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    version: str = SCHEMA_VERSION
    run_utc: str = ""
    source: str = ""
    n_trades: int = 0
    period_start: str = ""
    period_end: str = ""
    metrics: list[dict] = field(default_factory=list)
    overall_stars: int = 0
    overall_score: float = 0.0
    verdict: str = ""


def _stars(metric_key: str, value: float) -> int:
    """Return 1-5 stars given a value and the calibrated thresholds."""
    thresholds = STAR_THRESHOLDS.get(metric_key)
    if not thresholds:
        return 3
    for threshold, stars in thresholds:
        if value >= threshold:
            return stars
    return 1


def _to_stars_str(n: int) -> str:
    return "★" * max(0, min(5, n)) + "☆" * max(0, 5 - n)


def compute_scorecard(learning_df, source: str = "learning.parquet") -> Scorecard:
    """Compute the full 6-metric scorecard from a closed-trade DataFrame.

    Expected columns (per reports/learning.parquet):
      entry_date, exit_date, return_pct, mfe_pct, mae_pct,
      hit_5pct_target, hit_5pct_stop, is_winner, confidence, n_bars_held
    """
    import numpy as np
    import pandas as pd

    sc = Scorecard(run_utc=datetime.now(timezone.utc).isoformat(), source=source)
    if learning_df is None or len(learning_df) == 0:
        sc.verdict = "insufficient_data"
        return sc

    df = learning_df.copy()
    sc.n_trades = int(len(df))
    if "entry_date" in df.columns and not df["entry_date"].isna().all():
        sc.period_start = str(df["entry_date"].min())[:10]
    if "exit_date" in df.columns and not df["exit_date"].isna().all():
        sc.period_end = str(df["exit_date"].max())[:10]

    metrics: list[ScorecardMetric] = []

    # 1. Recommendation Accuracy = win rate
    if "is_winner" in df.columns:
        wr = float(df["is_winner"].mean())
        metrics.append(ScorecardMetric(
            name="Recommendation Accuracy",
            value=round(wr, 4),
            stars=_stars("recommendation_accuracy", wr),
            unit="win_rate",
            n_observations=int(df["is_winner"].notna().sum()),
            description="% of closed trades that ended profitable",
            benchmark="institutional 58%+, top-tier 65%+",
        ))

    # 2. Exit Timing = MFE-capture ratio
    if "return_pct" in df.columns and "mfe_pct" in df.columns:
        winners = df[df["is_winner"] == True].copy() if "is_winner" in df.columns else df
        winners = winners[winners["mfe_pct"] > 0]
        if len(winners) > 0:
            # For each winning trade: what fraction of the max favorable
            # move was actually captured at exit
            capture = (winners["return_pct"] / winners["mfe_pct"]).clip(lower=-1.0, upper=1.5)
            median_capture = float(capture.median())
            metrics.append(ScorecardMetric(
                name="Exit Timing",
                value=round(median_capture, 4),
                stars=_stars("exit_timing_pct", median_capture),
                unit="mfe_capture_ratio",
                n_observations=len(winners),
                description="Median fraction of max-favorable-move captured at exit",
                benchmark="institutional 55%+, expert 70%+",
            ))

    # 3. Target Hit Rate
    if "hit_5pct_target" in df.columns:
        hit_rate = float(df["hit_5pct_target"].mean())
        metrics.append(ScorecardMetric(
            name="Target Hit Rate",
            value=round(hit_rate, 4),
            stars=_stars("target_hit_rate", hit_rate),
            unit="pct_hit_5pct_target",
            n_observations=int(df["hit_5pct_target"].notna().sum()),
            description="% of trades reaching +5% target before exit",
            benchmark="institutional 30-40%",
        ))

    # 4. Risk Control = median MAE (max adverse excursion)
    if "mae_pct" in df.columns:
        med_mae = float(df["mae_pct"].median())
        metrics.append(ScorecardMetric(
            name="Risk Control",
            value=round(med_mae, 2),
            stars=_stars("risk_control_mae_pct", med_mae),
            unit="pct_median_mae",
            n_observations=int(df["mae_pct"].notna().sum()),
            description="Median max-adverse-excursion (lower absolute is better)",
            benchmark="institutional > -8%, top-tier > -5%",
        ))

    # 5. Confidence Calibration = correlation of confidence-bucket vs win rate
    if "confidence" in df.columns and "is_winner" in df.columns:
        try:
            df_calib = df.dropna(subset=["confidence", "is_winner"])
            if len(df_calib) >= 30:
                # Bucket by decile
                df_calib = df_calib.copy()
                df_calib["conf_bucket"] = pd.qcut(df_calib["confidence"], q=5,
                                                       duplicates="drop", labels=False)
                bucket_stats = df_calib.groupby("conf_bucket").agg(
                    mean_conf=("confidence", "mean"),
                    win_rate=("is_winner", "mean"),
                )
                if len(bucket_stats) >= 2:
                    r = float(bucket_stats["mean_conf"].corr(bucket_stats["win_rate"]))
                    r = r if r == r else 0.0   # NaN guard
                    metrics.append(ScorecardMetric(
                        name="Confidence Calibration",
                        value=round(r, 4),
                        stars=_stars("confidence_calibration", r),
                        unit="pearson_r",
                        n_observations=len(df_calib),
                        description="Correlation between confidence bucket and realized win rate",
                        benchmark="institutional 0.20+, top-tier 0.30+",
                    ))
        except Exception:
            pass

    # 6. Rotation Quality = profit factor (Σ winner returns / |Σ loser returns|)
    if "return_pct" in df.columns:
        wins_sum = float(df[df["return_pct"] > 0]["return_pct"].sum())
        losses_sum = abs(float(df[df["return_pct"] < 0]["return_pct"].sum()))
        if losses_sum > 0:
            pf = wins_sum / losses_sum
            metrics.append(ScorecardMetric(
                name="Rotation Quality",
                value=round(pf, 2),
                stars=_stars("rotation_quality_pf", pf),
                unit="profit_factor",
                n_observations=len(df),
                description="Profit factor: sum-winners / abs(sum-losers)",
                benchmark="institutional 1.75+, top-tier 2.5+",
            ))

    # Overall = average stars
    sc.metrics = [asdict(m) for m in metrics]
    if metrics:
        avg = sum(m.stars for m in metrics) / len(metrics)
        sc.overall_stars = round(avg)
        sc.overall_score = round(avg * 20, 1)   # 0-100 scale
    else:
        sc.overall_stars = 0
        sc.overall_score = 0.0

    # Verdict
    if sc.overall_stars >= 4:
        sc.verdict = "institutional_grade"
    elif sc.overall_stars >= 3:
        sc.verdict = "acceptable"
    elif sc.overall_stars >= 2:
        sc.verdict = "needs_improvement"
    else:
        sc.verdict = "concerning"

    return sc


def render_scorecard_lines(sc: Scorecard) -> list[str]:
    """Format the scorecard for the Command Center Telegram message."""
    lines = [f"*AI SCORECARD  ({sc.overall_score}/100 · {sc.verdict})*"]
    lines.append(f"  {_to_stars_str(sc.overall_stars)}  · {sc.n_trades} trades  · {sc.period_start} → {sc.period_end}")
    for m in sc.metrics:
        stars = _to_stars_str(m.get("stars", 0))
        lines.append(f"  {m.get('name', '?')}: {stars}  {m.get('value')} {m.get('unit')}")
    return lines


def run_scorecard(root: Path) -> dict:
    """Load learning.parquet from repo root and compute + persist scorecard."""
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    if not lp.exists():
        return asdict(Scorecard(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    sc = compute_scorecard(df)
    out = root / "reports" / "ai_scorecard.json"
    out.write_text(json.dumps(asdict(sc), indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return asdict(sc)
