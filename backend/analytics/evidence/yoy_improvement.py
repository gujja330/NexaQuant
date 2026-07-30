"""Year-over-Year Learning Engine Validation.

Answers: "Is AEGIS getting better over time?" · buckets closed trades
by exit-year and reports win_rate + median_return + target_hit_rate.
If numbers are improving year-over-year, the Learning Engine is
demonstrably working. If flat or declining, we have evidence to
investigate.

Emits `reports/evidence/yoy_report.json`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.analytics.evidence.yoy.v1.20260730"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.evidence.yoy.v1"


@dataclass
class YearMetrics:
    year: int
    n_trades: int
    win_rate: float
    median_return_pct: float
    mean_return_pct: float
    target_hit_rate: float
    stop_hit_rate: float
    avg_hold_days: float


@dataclass
class YoYReport:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    version: str = SCHEMA_VERSION
    run_utc: str = ""
    source: str = "reports/learning.parquet"
    n_trades: int = 0
    per_year: list = field(default_factory=list)
    win_rate_trend: str = ""            # "improving" / "flat" / "declining"
    median_return_trend: str = ""
    verdict: str = ""


def _trend(values: list[float]) -> str:
    if len(values) < 2:
        return "insufficient"
    import numpy as np
    x = np.arange(len(values))
    slope = np.polyfit(x, values, 1)[0]
    if slope > 0.02:
        return "improving"
    if slope < -0.02:
        return "declining"
    return "flat"


def compute_yoy_report(df) -> YoYReport:
    rep = YoYReport(run_utc=datetime.now(timezone.utc).isoformat())
    if df is None or len(df) == 0 or "exit_date" not in df.columns:
        rep.verdict = "insufficient_data"
        return rep

    import pandas as pd
    df = df.copy()
    df["exit_year"] = pd.to_datetime(df["exit_date"], errors="coerce").dt.year
    df = df.dropna(subset=["exit_year"])
    rep.n_trades = int(len(df))

    for yr, sub in df.groupby("exit_year"):
        n = int(len(sub))
        if n < 10:   # skip years with too few closed trades to be meaningful
            continue
        m = YearMetrics(
            year=int(yr), n_trades=n,
            win_rate=round(float(sub["is_winner"].mean()) if "is_winner" in sub.columns else 0.0, 4),
            median_return_pct=round(float(sub["return_pct"].median()) if "return_pct" in sub.columns else 0.0, 4),
            mean_return_pct=round(float(sub["return_pct"].mean()) if "return_pct" in sub.columns else 0.0, 4),
            target_hit_rate=round(float(sub["hit_5pct_target"].mean()) if "hit_5pct_target" in sub.columns else 0.0, 4),
            stop_hit_rate=round(float(sub["hit_5pct_stop"].mean()) if "hit_5pct_stop" in sub.columns else 0.0, 4),
            avg_hold_days=round(float(sub["n_bars_held"].mean()) if "n_bars_held" in sub.columns else 0.0, 2),
        )
        rep.per_year.append(asdict(m))
    rep.per_year.sort(key=lambda m: m["year"])

    # Trends
    win_series = [m["win_rate"] for m in rep.per_year]
    med_series = [m["median_return_pct"] for m in rep.per_year]
    rep.win_rate_trend = _trend(win_series)
    rep.median_return_trend = _trend(med_series)

    # Verdict · combined
    if rep.win_rate_trend == "improving" and rep.median_return_trend == "improving":
        rep.verdict = "learning_engine_effective"
    elif rep.win_rate_trend == "declining" and rep.median_return_trend == "declining":
        rep.verdict = "learning_engine_regressing"
    elif "insufficient" in (rep.win_rate_trend, rep.median_return_trend):
        rep.verdict = "insufficient_history"
    else:
        rep.verdict = "mixed_signals"
    return rep


def run_yoy(root: Path) -> dict:
    import pandas as pd
    lp = root / "reports" / "learning.parquet"
    out_dir = root / "reports" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not lp.exists():
        return asdict(YoYReport(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    rep = compute_yoy_report(df)
    (out_dir / "yoy_report.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)
