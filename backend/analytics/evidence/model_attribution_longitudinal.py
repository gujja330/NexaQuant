"""Longitudinal Model Attribution · rolling per-model IC.

Answers: "Which models actually contribute over time? Which have earned
their adaptive weight?"

Uses the `dim_*` columns in `learning.parquet` (dim_momentum · dim_trend
· dim_rs_nifty · dim_volatility · dim_drawdown · dim_position_52w · ...)
and computes rolling-window Information Coefficient (Pearson correlation
between dim score and realized return_pct) per year.

If a model's IC is consistently positive · it deserves its weight.
If a model's IC is consistently near zero · adaptive weights should
(and empirically do) downweight it.
If a model's IC is consistently negative · we have evidence to retire
that dimension.

Emits `reports/evidence/model_attribution_longitudinal.json`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.analytics.evidence.rolling_ic.v1.20260730"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.evidence.rolling_ic.v1"


@dataclass
class DimYearIC:
    dim: str
    year: int
    n_trades: int
    ic_pearson: float
    ic_significant: bool


@dataclass
class RollingICReport:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    version: str = SCHEMA_VERSION
    run_utc: str = ""
    source: str = "reports/learning.parquet"
    n_trades: int = 0
    per_dim_per_year: list = field(default_factory=list)
    per_dim_summary: list = field(default_factory=list)   # avg IC + verdict per dim
    verdict: str = ""


def compute_rolling_ic(df) -> RollingICReport:
    rep = RollingICReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0:
        rep.verdict = "insufficient_data"
        return rep
    if "return_pct" not in df.columns or "exit_date" not in df.columns:
        rep.verdict = "missing_required_columns"
        return rep

    import pandas as pd
    df = df.copy()
    df["exit_year"] = pd.to_datetime(df["exit_date"], errors="coerce").dt.year
    df = df.dropna(subset=["exit_year"])
    rep.n_trades = int(len(df))

    dim_cols = [c for c in df.columns if c.startswith("dim_")]
    if not dim_cols:
        rep.verdict = "no_dim_columns"
        return rep

    # Per-dim per-year IC
    for dim in dim_cols:
        year_ics = []
        for yr, sub in df.groupby("exit_year"):
            sub_valid = sub.dropna(subset=[dim, "return_pct"])
            n = int(len(sub_valid))
            if n < 20:
                continue
            try:
                ic = float(sub_valid[dim].corr(sub_valid["return_pct"]))
                if ic != ic:   # NaN check
                    continue
                # Significance threshold at n=100 · |r| >= 0.20 is meaningful
                significant = abs(ic) >= (2.0 / (n ** 0.5))
                rep.per_dim_per_year.append(asdict(DimYearIC(
                    dim=dim, year=int(yr), n_trades=n,
                    ic_pearson=round(ic, 4), ic_significant=significant,
                )))
                year_ics.append(ic)
            except Exception:
                continue
        # Summary per dim
        if year_ics:
            avg_ic = sum(year_ics) / len(year_ics)
            n_positive = sum(1 for ic in year_ics if ic > 0.05)
            n_negative = sum(1 for ic in year_ics if ic < -0.05)
            if avg_ic > 0.10 and n_positive == len(year_ics):
                verdict = "strong_and_consistent"
            elif avg_ic > 0.05 and n_positive >= len(year_ics) - 1:
                verdict = "modest_and_consistent"
            elif abs(avg_ic) < 0.03:
                verdict = "quiet_downweight_candidate"
            elif avg_ic < -0.05 and n_negative >= len(year_ics) - 1:
                verdict = "negative_retire_candidate"
            else:
                verdict = "mixed"
            rep.per_dim_summary.append({
                "dim":       dim,
                "years":     len(year_ics),
                "avg_ic":    round(avg_ic, 4),
                "positive_years":  n_positive,
                "negative_years":  n_negative,
                "verdict":   verdict,
            })
    rep.per_dim_summary.sort(key=lambda d: -d["avg_ic"])

    # Overall verdict
    n_strong = sum(1 for d in rep.per_dim_summary if "strong" in d["verdict"] or "modest" in d["verdict"])
    n_retire = sum(1 for d in rep.per_dim_summary if "retire" in d["verdict"])
    if n_strong >= 3 and n_retire == 0:
        rep.verdict = "attribution_healthy"
    elif n_retire >= 2:
        rep.verdict = "attribution_has_dead_weight"
    else:
        rep.verdict = "attribution_mixed"
    return rep


def run_rolling_ic(root: Path) -> dict:
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    out_dir = root / "reports" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not lp.exists():
        return asdict(RollingICReport(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    rep = compute_rolling_ic(df)
    (out_dir / "model_attribution_longitudinal.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)
