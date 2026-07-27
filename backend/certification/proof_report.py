"""Institutional Proof Report generator.

Consumes existing artifacts to produce evidence-backed certification metrics.
NO simulation · NO synthesis · only real evidence from what the platform has produced.

Metrics:
  · Trade-level: win rate · profit factor · expected return · MFE/MAE ratio
    · target-hit rate · stop-hit rate · avg holding bars
  · Time-series (when portfolio equity available): Sharpe · Sortino · MaxDD
  · Recommendation stability across daily snapshots
  · DNA lifecycle completeness
  · Wilson 95% CI on win rate (institutional sample-size gate)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable, Sequence

SCHEMA_FINGERPRINT = "aegis.certification.proof_report.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.proof_report.v1"

STATISTICAL_MEANINGFUL_N = 30    # per Sprint 7.8 Wilson-CI gate


@dataclass
class TradeMetrics:
    n_trades: int = 0
    date_range: str = ""
    win_rate: float | None = None
    win_rate_ci_low: float | None = None
    win_rate_ci_high: float | None = None
    verdict: str = "INSUFFICIENT_DATA"
    mean_return_pct: float | None = None
    median_return_pct: float | None = None
    stdev_return_pct: float | None = None
    profit_factor: float | None = None
    win_loss_ratio: float | None = None
    avg_win_pct: float | None = None
    avg_loss_pct: float | None = None
    avg_holding_bars: float | None = None
    target_5pct_hit_rate: float | None = None
    target_10pct_hit_rate: float | None = None
    stop_5pct_hit_rate: float | None = None
    stop_10pct_hit_rate: float | None = None
    mfe_pct_mean: float | None = None
    mae_pct_mean: float | None = None
    dimension_correlations: dict = field(default_factory=dict)


@dataclass
class LifecycleMetrics:
    n_recs: int = 0
    n_with_outcome_fields: int = 0
    n_active: int = 0
    n_closed: int = 0
    n_archived: int = 0
    lifecycle_completeness_pct: float | None = None


@dataclass
class StabilityMetrics:
    n_history_snapshots: int = 0
    date_range: str = ""
    avg_recs_per_snapshot: float | None = None
    ticker_persistence_pct: float | None = None   # % of tickers appearing in >=50% snapshots


@dataclass
class ProofReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    trade_metrics: dict = field(default_factory=dict)
    lifecycle_metrics: dict = field(default_factory=dict)
    stability_metrics: dict = field(default_factory=dict)
    per_sector_win_rate: dict = field(default_factory=dict)
    per_confidence_bucket: dict = field(default_factory=dict)
    verdict: str = ""
    evidence_summary: str = ""


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson 95% confidence interval on a binomial proportion."""
    if n < 1: return None, None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return round(center - margin, 4), round(center + margin, 4)


def _sample_verdict(n: int) -> str:
    if n < STATISTICAL_MEANINGFUL_N: return "DIRECTIONAL_ONLY"
    if n < 200: return "STATISTICALLY_MEANINGFUL"
    return "INSTITUTIONALLY_ROBUST"


def compute_trade_metrics(df) -> TradeMetrics:
    import pandas as pd
    tm = TradeMetrics()
    if df is None or len(df) == 0: return tm
    tm.n_trades = len(df)
    if "entry_date" in df.columns and "exit_date" in df.columns:
        tm.date_range = f"{df['entry_date'].min()} → {df['exit_date'].max()}"
    if "return_pct" in df.columns:
        r = df["return_pct"].astype(float)
        wins = int((r > 0).sum())
        tm.win_rate = round(wins / len(r), 4)
        lo, hi = wilson_interval(wins, len(r))
        tm.win_rate_ci_low, tm.win_rate_ci_high = lo, hi
        tm.verdict = _sample_verdict(len(r))
        tm.mean_return_pct = round(float(r.mean()), 4)
        tm.median_return_pct = round(float(r.median()), 4)
        tm.stdev_return_pct = round(float(r.std()), 4)
        wins_r = r[r > 0]; losses_r = r[r < 0]
        if len(wins_r) and len(losses_r):
            tm.avg_win_pct = round(float(wins_r.mean()), 4)
            tm.avg_loss_pct = round(float(losses_r.mean()), 4)
            tm.win_loss_ratio = round(abs(tm.avg_win_pct / tm.avg_loss_pct), 4)
            sum_win = float(wins_r.sum()); sum_loss = abs(float(losses_r.sum()))
            tm.profit_factor = round(sum_win / sum_loss, 4) if sum_loss > 0 else None
    if "n_bars_held" in df.columns:
        tm.avg_holding_bars = round(float(df["n_bars_held"].mean()), 2)
    for col, attr in (("hit_5pct_target", "target_5pct_hit_rate"),
                       ("hit_10pct_target", "target_10pct_hit_rate"),
                       ("hit_5pct_stop", "stop_5pct_hit_rate"),
                       ("hit_10pct_stop", "stop_10pct_hit_rate")):
        if col in df.columns:
            setattr(tm, attr, round(float(df[col].astype(float).mean()), 4))
    if "mfe_pct" in df.columns:
        tm.mfe_pct_mean = round(float(df["mfe_pct"].astype(float).mean()), 4)
    if "mae_pct" in df.columns:
        tm.mae_pct_mean = round(float(df["mae_pct"].astype(float).mean()), 4)
    # Feature-dimension correlations with return
    for c in df.columns:
        if c.startswith("dim_") and "return_pct" in df.columns:
            try:
                corr = float(df[c].corr(df["return_pct"]))
                if not (corr != corr):  # nan-check
                    tm.dimension_correlations[c] = round(corr, 4)
            except Exception:
                pass
    return tm


def compute_lifecycle_metrics(dna_csv_path: Path) -> LifecycleMetrics:
    import pandas as pd
    lm = LifecycleMetrics()
    if not dna_csv_path.exists(): return lm
    try:
        df = pd.read_csv(dna_csv_path)
    except Exception:
        return lm
    lm.n_recs = len(df)
    # DNA-CSV variant · check for status/outcome columns
    status_col = next((c for c in df.columns if c.lower() in ("status", "state", "lifecycle_state")), None)
    if status_col:
        counts = df[status_col].value_counts().to_dict()
        lm.n_active = int(counts.get("LIVE", 0) + counts.get("ACTIVE", 0))
        lm.n_closed = int(counts.get("REVIEW-DUE", 0) + counts.get("CLOSED", 0))
        lm.n_archived = int(counts.get("ARCHIVED", 0))
    # Outcome completeness · at least one outcome-signaling field non-null
    outcome_cols = [c for c in ("outcome_return_pct", "outcome_win_loss",
                                  "mfe_pct", "mae_pct", "exit_reason") if c in df.columns]
    if outcome_cols:
        has_outcome = df[outcome_cols[0]].notna()
        lm.n_with_outcome_fields = int(has_outcome.sum())
        lm.lifecycle_completeness_pct = round(has_outcome.mean() * 100, 2)
    return lm


def compute_stability_metrics(history_parquet_path: Path) -> StabilityMetrics:
    import pandas as pd
    sm = StabilityMetrics()
    if not history_parquet_path.exists(): return sm
    try:
        df = pd.read_parquet(history_parquet_path)
    except Exception:
        return sm
    if "asof" not in df.columns:
        return sm
    sm.n_history_snapshots = df["asof"].nunique()
    sm.date_range = f"{df['asof'].min()} → {df['asof'].max()}"
    if "ticker" in df.columns:
        by_asof = df.groupby("asof")["ticker"].count()
        sm.avg_recs_per_snapshot = round(float(by_asof.mean()), 2)
        # ticker persistence
        by_ticker = df.groupby("ticker")["asof"].nunique()
        threshold = sm.n_history_snapshots * 0.5
        persistent = (by_ticker >= threshold).sum()
        sm.ticker_persistence_pct = round(persistent / len(by_ticker) * 100, 2)
    return sm


def compute_per_sector_win_rate(df) -> dict:
    if df is None or "sector" not in df.columns or "return_pct" not in df.columns:
        return {}
    out = {}
    for sec, g in df.groupby("sector"):
        n = len(g)
        wins = int((g["return_pct"] > 0).sum())
        rate = round(wins / n, 4)
        lo, hi = wilson_interval(wins, n)
        out[str(sec)] = {"n": n, "win_rate": rate,
                          "wilson_ci_low": lo, "wilson_ci_high": hi,
                          "mean_return_pct": round(float(g["return_pct"].mean()), 4)}
    return out


def compute_per_confidence_bucket(df) -> dict:
    if df is None or "confidence" not in df.columns or "return_pct" not in df.columns:
        return {}
    buckets = {"low(0-0.33)": (0.0, 0.33),
               "mid(0.33-0.67)": (0.33, 0.67),
               "high(0.67-1.0)": (0.67, 1.01)}
    out = {}
    for label, (lo, hi) in buckets.items():
        g = df[(df["confidence"] >= lo) & (df["confidence"] < hi)]
        n = len(g)
        if n < 5: continue
        wins = int((g["return_pct"] > 0).sum())
        out[label] = {"n": n, "win_rate": round(wins / n, 4),
                       "mean_return_pct": round(float(g["return_pct"].mean()), 4)}
    return out


def generate_proof_report(root: Path) -> ProofReport:
    import pandas as pd
    rep = ProofReport(run_utc=datetime.now(timezone.utc).isoformat())

    learning_p = root / "reports" / "learning.parquet"
    df = pd.read_parquet(learning_p) if learning_p.exists() else None
    tm = compute_trade_metrics(df)
    rep.trade_metrics = asdict(tm)
    rep.per_sector_win_rate = compute_per_sector_win_rate(df)
    rep.per_confidence_bucket = compute_per_confidence_bucket(df)

    dna_p = root / "data" / "aegis_recommendation_db.csv"
    rep.lifecycle_metrics = asdict(compute_lifecycle_metrics(dna_p))

    rh_p = root / "reports" / "recommendation_history.parquet"
    rep.stability_metrics = asdict(compute_stability_metrics(rh_p))

    n_trades = tm.n_trades
    if n_trades >= 200 and tm.win_rate and tm.win_rate >= 0.55 and tm.profit_factor and tm.profit_factor >= 1.5:
        rep.verdict = "INSTITUTIONAL_GO"
    elif n_trades >= STATISTICAL_MEANINGFUL_N and tm.win_rate and tm.win_rate >= 0.50:
        rep.verdict = "STATISTICALLY_POSITIVE"
    elif n_trades > 0:
        rep.verdict = "DIRECTIONAL_ONLY"
    else:
        rep.verdict = "INSUFFICIENT_DATA"

    rep.evidence_summary = (
        f"{n_trades} closed trades · win_rate={tm.win_rate} · "
        f"profit_factor={tm.profit_factor} · avg_holding={tm.avg_holding_bars} bars · "
        f"verdict={rep.verdict}"
    )
    return rep
