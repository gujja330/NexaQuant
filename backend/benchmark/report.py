"""
Sprint 7.8 · Recommendation Benchmark Report.

Full metric panel per operator directive of 2026-07-21:
    - Overall return · win rate · profit factor · expectancy
    - Sharpe · Sortino · Calmar · max drawdown
    - Average winner · average loser · reward/risk ratio
    - Consecutive losses distribution
    - BUY vs STRONG_BUY discrimination
    - Sector performance
    - Confidence-bucket performance (0.5-0.6, 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0)
    - Macro-regime performance (from regime_at_entry column)
    - Per-metric: sample size + 95% CI where applicable + significance verdict

Every metric explicitly carries its uncertainty. Small samples cannot
masquerade as institutional evidence.
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .statistical_significance import (
    wilson_confidence_interval, mean_confidence_interval, sample_size_verdict,
)


SIGNIFICANCE_MIN_SAMPLES = 30
INSTITUTIONAL_MIN_SAMPLES = 100
ANNUAL_TRADING_DAYS = 252


@dataclass(frozen=True)
class StatisticalVerdict:
    n: int
    verdict: str                          # INSUFFICIENT_DATA / DIRECTIONAL_ONLY / STATISTICALLY_MEANINGFUL / INSTITUTIONAL_GRADE
    reason: str


@dataclass
class BenchmarkMetrics:
    market: str
    runner: str
    n_closed_positions: int
    date_range: Optional[str] = None

    # Core returns
    total_return_pct: Optional[float] = None
    mean_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    stdev_return_pct: Optional[float] = None
    mean_return_ci_95: Optional[List[float]] = None

    # Win/Loss decomposition
    win_rate_pct: Optional[float] = None
    win_rate_ci_95: Optional[List[float]] = None
    n_winners: int = 0
    n_losers: int = 0
    n_flats: int = 0
    avg_win_pct: Optional[float] = None
    avg_loss_pct: Optional[float] = None
    largest_win_pct: Optional[float] = None
    largest_loss_pct: Optional[float] = None

    # Institutional edge metrics
    profit_factor: Optional[float] = None      # sum(wins) / |sum(losses)|
    expectancy_per_trade_pct: Optional[float] = None   # win_rate*avg_win + (1-win_rate)*avg_loss
    reward_risk_ratio: Optional[float] = None  # avg_win / |avg_loss|

    # Risk / drawdown
    sharpe_annualised: Optional[float] = None
    sortino_annualised: Optional[float] = None
    calmar: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    max_consecutive_wins: Optional[int] = None

    # Behavioural
    avg_holding_period_days: Optional[float] = None

    # Statistical framing (structural, not "good/bad")
    significance: Optional[StatisticalVerdict] = None

    notes: List[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    engine: str
    version: str
    market: str
    runner: str
    run_utc: str
    corpus_path: str
    overall: BenchmarkMetrics
    by_action: Dict[str, BenchmarkMetrics] = field(default_factory=dict)
    by_sector: Dict[str, BenchmarkMetrics] = field(default_factory=dict)
    by_confidence_bucket: Dict[str, BenchmarkMetrics] = field(default_factory=dict)
    by_regime: Dict[str, BenchmarkMetrics] = field(default_factory=dict)
    strong_buy_vs_buy: Dict[str, Any] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)


# ── helpers ─────────────────────────────────────────────────────

def _to_pct_decimals(returns_pct: np.ndarray) -> np.ndarray:
    return returns_pct.astype(float) / 100.0


def _compute_consecutive_streaks(is_winner: pd.Series) -> Dict[str, int]:
    """Longest consecutive True (wins) and longest consecutive False (losses)."""
    if is_winner.empty:
        return {"max_consecutive_wins": 0, "max_consecutive_losses": 0}
    max_w = max_l = cur_w = cur_l = 0
    for v in is_winner.values:
        if bool(v):
            cur_w += 1; cur_l = 0
            max_w = max(max_w, cur_w)
        else:
            cur_l += 1; cur_w = 0
            max_l = max(max_l, cur_l)
    return {"max_consecutive_wins": max_w, "max_consecutive_losses": max_l}


def _sig_verdict(n: int) -> StatisticalVerdict:
    v = sample_size_verdict(n,
                              min_directional=5,
                              min_significant=SIGNIFICANCE_MIN_SAMPLES,
                              min_institutional=INSTITUTIONAL_MIN_SAMPLES)
    reason_map = {
        "INSUFFICIENT_DATA":       f"{n} trades — cannot draw any conclusion",
        "DIRECTIONAL_ONLY":        f"{n} trades — pattern suggestive but not statistically proven",
        "STATISTICALLY_MEANINGFUL": f"{n} trades — statistically meaningful, still finite-sample noise",
        "INSTITUTIONAL_GRADE":     f"{n} trades — institutional-grade sample size",
    }
    return StatisticalVerdict(n=n, verdict=v, reason=reason_map[v])


def _bucket_confidence(conf: Optional[float]) -> str:
    if conf is None or (isinstance(conf, float) and math.isnan(conf)):
        return "unknown"
    if conf <= 0.5:  return "≤0.50"
    if conf <= 0.6:  return "0.50-0.60"
    if conf <= 0.7:  return "0.60-0.70"
    if conf <= 0.8:  return "0.70-0.80"
    if conf <= 0.9:  return "0.80-0.90"
    return "0.90-1.00"


# ── metric computation on a single slice ────────────────────────

def _compute_metrics_on_slice(df: pd.DataFrame, *, market: str, runner: str) -> BenchmarkMetrics:
    """
    Given a slice of the learning corpus (rows = closed positions), compute
    the full metric panel. Handles empty and near-empty slices gracefully.
    """
    m = BenchmarkMetrics(market=market, runner=runner, n_closed_positions=len(df))

    if df.empty:
        m.significance = _sig_verdict(0)
        m.notes.append("empty slice")
        return m

    if "return_pct" not in df.columns:
        m.significance = _sig_verdict(0)
        m.notes.append("no return_pct column")
        return m

    ret = df["return_pct"].astype(float).values
    ret_dec = ret / 100.0
    wins   = ret[ret > 0]
    losses = ret[ret < 0]
    flats  = ret[ret == 0]

    m.n_winners = int(len(wins))
    m.n_losers  = int(len(losses))
    m.n_flats   = int(len(flats))

    m.total_return_pct  = round(float(np.sum(ret)), 4)
    m.mean_return_pct   = round(float(np.mean(ret)), 4)
    m.median_return_pct = round(float(np.median(ret)), 4)
    m.stdev_return_pct  = round(float(np.std(ret, ddof=1)), 4) if len(ret) > 1 else None

    if m.stdev_return_pct:
        mci = mean_confidence_interval(m.mean_return_pct, m.stdev_return_pct, len(ret))
        m.mean_return_ci_95 = [mci[1], mci[2]]

    # Win rate + Wilson CI
    p, lo, hi = wilson_confidence_interval(len(wins), len(ret))
    m.win_rate_pct = round(100.0 * p, 2)
    m.win_rate_ci_95 = [round(100.0 * lo, 2), round(100.0 * hi, 2)]

    if len(wins):
        m.avg_win_pct    = round(float(wins.mean()), 4)
        m.largest_win_pct = round(float(wins.max()), 4)
    if len(losses):
        m.avg_loss_pct    = round(float(losses.mean()), 4)
        m.largest_loss_pct = round(float(losses.min()), 4)

    # Profit factor + expectancy + reward/risk
    if len(losses) and losses.sum() != 0:
        m.profit_factor = round(float(wins.sum() / -losses.sum()), 4)
    win_r = p
    if m.avg_win_pct is not None and m.avg_loss_pct is not None:
        m.expectancy_per_trade_pct = round(win_r * m.avg_win_pct + (1 - win_r) * m.avg_loss_pct, 4)
        if m.avg_loss_pct != 0:
            m.reward_risk_ratio = round(m.avg_win_pct / abs(m.avg_loss_pct), 4)

    # Risk-adjusted (approximation from per-trade returns; not per-day)
    if len(ret) > 1:
        avg_dec = float(np.mean(ret_dec))
        std_dec = float(np.std(ret_dec, ddof=1))
        if std_dec > 0:
            m.sharpe_annualised = round(avg_dec / std_dec * math.sqrt(ANNUAL_TRADING_DAYS), 4)
        downside = ret_dec[ret_dec < 0]
        if len(downside) > 1:
            dstd = float(np.std(downside, ddof=1))
            if dstd > 0:
                m.sortino_annualised = round(avg_dec / dstd * math.sqrt(ANNUAL_TRADING_DAYS), 4)

    # Max drawdown (per-trade equity walk)
    equity = np.cumprod(1 + ret_dec)
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    m.max_drawdown_pct = round(100.0 * float(dd.min()), 4)
    if m.max_drawdown_pct and m.max_drawdown_pct != 0 and m.mean_return_pct is not None:
        annualised = m.mean_return_pct * ANNUAL_TRADING_DAYS
        m.calmar = round(annualised / abs(m.max_drawdown_pct), 4)

    # Consecutive streaks (ordered by rec_asof if available)
    if "rec_asof" in df.columns:
        ordered = df.sort_values("rec_asof")
        streaks = _compute_consecutive_streaks(ordered["return_pct"].astype(float) > 0)
    else:
        streaks = _compute_consecutive_streaks(df["return_pct"].astype(float) > 0)
    m.max_consecutive_wins   = streaks["max_consecutive_wins"]
    m.max_consecutive_losses = streaks["max_consecutive_losses"]

    if "horizon_days" in df.columns:
        m.avg_holding_period_days = round(float(df["horizon_days"].astype(float).mean()), 2)

    # Date range
    if "rec_asof" in df.columns:
        try:
            dts = pd.to_datetime(df["rec_asof"], errors="coerce").dropna()
            if not dts.empty:
                m.date_range = f"{dts.min().date().isoformat()}..{dts.max().date().isoformat()}"
        except Exception:
            pass

    m.significance = _sig_verdict(len(ret))
    return m


# ── segment metrics ──────────────────────────────────────────────

def _split_by(df: pd.DataFrame, column: str, market: str, runner: str,
                 keys: Optional[List[str]] = None) -> Dict[str, BenchmarkMetrics]:
    if column not in df.columns:
        return {}
    out: Dict[str, BenchmarkMetrics] = {}
    for k, g in df.groupby(column, dropna=False):
        label = "unknown" if pd.isna(k) else str(k)
        if keys is not None and label not in keys:
            continue
        out[label] = _compute_metrics_on_slice(g, market=market, runner=runner)
    return out


def _strong_buy_vs_buy(df: pd.DataFrame, market: str, runner: str) -> Dict[str, Any]:
    """
    Test whether STRONG_BUY discriminates from BUY:
        - Do STRONG_BUY trades outperform BUY on mean return?
        - Do STRONG_BUY trades win more often?
        - Is the difference statistically flagged?
    """
    if "action" not in df.columns:
        return {"available": False, "reason": "no action column in corpus"}
    sb = df[df["action"] == "STRONG_BUY"]
    b  = df[df["action"] == "BUY"]

    out: Dict[str, Any] = {
        "available": True,
        "n_STRONG_BUY": len(sb),
        "n_BUY": len(b),
    }
    if sb.empty or b.empty:
        out["verdict"] = "INSUFFICIENT_DATA"
        out["reason"] = "one of the two action groups is empty"
        return out

    sb_mean = float(sb["return_pct"].astype(float).mean())
    b_mean  = float(b["return_pct"].astype(float).mean())
    sb_win  = float((sb["return_pct"].astype(float) > 0).mean()) * 100.0
    b_win   = float((b["return_pct"].astype(float)  > 0).mean()) * 100.0

    out["STRONG_BUY_mean_return_pct"] = round(sb_mean, 4)
    out["BUY_mean_return_pct"]        = round(b_mean, 4)
    out["mean_return_edge_pct"]       = round(sb_mean - b_mean, 4)
    out["STRONG_BUY_win_rate_pct"]    = round(sb_win, 2)
    out["BUY_win_rate_pct"]           = round(b_win, 2)
    out["win_rate_edge_pp"]           = round(sb_win - b_win, 2)

    n_min = min(len(sb), len(b))
    if n_min < SIGNIFICANCE_MIN_SAMPLES:
        out["verdict"] = "DIRECTIONAL_ONLY"
        out["reason"] = f"smallest group has {n_min} trades — cannot confirm STRONG_BUY discrimination"
    else:
        edge = sb_mean - b_mean
        if edge > 0.5:
            out["verdict"] = "STRONG_BUY_OUTPERFORMS_BUY"
        elif edge < -0.5:
            out["verdict"] = "STRONG_BUY_UNDERPERFORMS_BUY"
        else:
            out["verdict"] = "NO_MEANINGFUL_DIFFERENCE"
        out["reason"] = f"mean-return edge = {edge:+.2f}% on n_min={n_min}"
    return out


# ── public API ──────────────────────────────────────────────────

def build_benchmark_report(*, repo_root: Path, market: str, runner: str,
                             corpus_path: Optional[Path] = None,
                             output_path: Optional[Path] = None) -> BenchmarkReport:
    """
    Build the full benchmark report for `runner` on `market`.

    `runner` selects which learning corpus to read:
        "runner1"  → learning_corpus_runner1.parquet   (legacy audit ledger)
        "runner2"  → learning_corpus.parquet           (Rec Engine v3)
    """
    reports_dir = (repo_root / "reports") if market == "india" else (repo_root / "usa" / "reports")
    if corpus_path is None:
        corpus_path = (reports_dir / "learning_corpus_runner1.parquet") if runner == "runner1" \
                        else (reports_dir / "learning_corpus.parquet")

    if not corpus_path.exists():
        overall = BenchmarkMetrics(market=market, runner=runner, n_closed_positions=0)
        overall.significance = _sig_verdict(0)
        overall.notes.append(f"corpus file does not exist: {corpus_path}")
        report = BenchmarkReport(
            engine="aegis.benchmark.v1", version="1.0.0",
            market=market, runner=runner,
            run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            corpus_path=str(corpus_path), overall=overall,
            caveats=["no closed positions available yet — run history backfill first"],
        )
    else:
        df = pd.read_parquet(corpus_path)
        if "market" in df.columns:
            df = df[df["market"] == market].copy()
        overall = _compute_metrics_on_slice(df, market=market, runner=runner)

        by_action     = _split_by(df, "action",           market, runner,
                                       keys=["STRONG_BUY", "BUY", "SELL", "STRONG_SELL"])
        by_sector     = _split_by(df, "sector",           market, runner)
        by_regime     = _split_by(df, "regime_at_entry",  market, runner)

        # Confidence buckets
        if "confidence" in df.columns:
            df["_conf_bucket"] = df["confidence"].apply(_bucket_confidence)
            by_confidence = _split_by(df, "_conf_bucket", market, runner)
        else:
            by_confidence = {}

        sb_vs_b = _strong_buy_vs_buy(df, market, runner)

        caveats: List[str] = []
        if overall.significance and overall.significance.verdict in ("INSUFFICIENT_DATA", "DIRECTIONAL_ONLY"):
            caveats.append(f"OVERALL sample = {overall.n_closed_positions} trades. "
                             "Do NOT draw conclusions about runner quality. "
                             "Need ≥30 for statistical meaning, ≥100 for institutional grade.")
        if len(by_regime) > 0:
            small_regimes = [r for r, mm in by_regime.items() if mm.n_closed_positions < 5]
            if small_regimes:
                caveats.append(f"per-regime slices with <5 trades: {small_regimes}. "
                                 "These rows are noise, not signal.")
        if sb_vs_b.get("verdict") == "DIRECTIONAL_ONLY":
            caveats.append("STRONG_BUY vs BUY discrimination NOT confirmed — sample too small.")

        report = BenchmarkReport(
            engine="aegis.benchmark.v1", version="1.0.0",
            market=market, runner=runner,
            run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            corpus_path=str(corpus_path), overall=overall,
            by_action=by_action, by_sector=by_sector,
            by_confidence_bucket=by_confidence, by_regime=by_regime,
            strong_buy_vs_buy=sb_vs_b, caveats=caveats,
        )

    # Write report JSON
    if output_path is None:
        output_path = reports_dir / f"benchmark_{runner}_{market}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_report_to_dict(report), indent=2, default=str),
                              encoding="utf-8")
    return report


def _metrics_to_dict(m: BenchmarkMetrics) -> Dict[str, Any]:
    d = asdict(m)
    if m.significance is not None:
        d["significance"] = asdict(m.significance)
    return d


def _report_to_dict(r: BenchmarkReport) -> Dict[str, Any]:
    return {
        "engine": r.engine, "version": r.version,
        "market": r.market, "runner": r.runner, "run_utc": r.run_utc,
        "corpus_path": r.corpus_path,
        "overall": _metrics_to_dict(r.overall),
        "by_action":            {k: _metrics_to_dict(v) for k, v in r.by_action.items()},
        "by_sector":            {k: _metrics_to_dict(v) for k, v in r.by_sector.items()},
        "by_confidence_bucket": {k: _metrics_to_dict(v) for k, v in r.by_confidence_bucket.items()},
        "by_regime":            {k: _metrics_to_dict(v) for k, v in r.by_regime.items()},
        "strong_buy_vs_buy": r.strong_buy_vs_buy,
        "caveats": r.caveats,
    }


def build_comparison(*, repo_root: Path, market: str,
                        output_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Side-by-side benchmark of Runner 1 vs Runner 2 on the same market.

    Deliberately refuses to name a "winner" unless BOTH runners have
    ≥ SIGNIFICANCE_MIN_SAMPLES closed positions.  Below that threshold
    the comparison is descriptive only — matches operator guidance:
    "10 trades ≠ conclusion".
    """
    r1 = build_benchmark_report(repo_root=repo_root, market=market, runner="runner1")
    r2 = build_benchmark_report(repo_root=repo_root, market=market, runner="runner2")

    reports_dir = (repo_root / "reports") if market == "india" else (repo_root / "usa" / "reports")

    can_compare = (r1.overall.n_closed_positions >= SIGNIFICANCE_MIN_SAMPLES
                     and r2.overall.n_closed_positions >= SIGNIFICANCE_MIN_SAMPLES)

    payload: Dict[str, Any] = {
        "engine": "aegis.benchmark.v1", "version": "1.0.0",
        "market": market,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner1": {
            "n_closed_positions": r1.overall.n_closed_positions,
            "significance": asdict(r1.overall.significance) if r1.overall.significance else None,
            "mean_return_pct": r1.overall.mean_return_pct,
            "win_rate_pct": r1.overall.win_rate_pct,
            "expectancy_per_trade_pct": r1.overall.expectancy_per_trade_pct,
            "profit_factor": r1.overall.profit_factor,
            "reward_risk_ratio": r1.overall.reward_risk_ratio,
            "max_drawdown_pct": r1.overall.max_drawdown_pct,
        },
        "runner2": {
            "n_closed_positions": r2.overall.n_closed_positions,
            "significance": asdict(r2.overall.significance) if r2.overall.significance else None,
            "mean_return_pct": r2.overall.mean_return_pct,
            "win_rate_pct": r2.overall.win_rate_pct,
            "expectancy_per_trade_pct": r2.overall.expectancy_per_trade_pct,
            "profit_factor": r2.overall.profit_factor,
            "reward_risk_ratio": r2.overall.reward_risk_ratio,
            "max_drawdown_pct": r2.overall.max_drawdown_pct,
        },
        "verdict": ("READY_FOR_COMPARISON" if can_compare
                     else "CANNOT_COMPARE_INSUFFICIENT_DATA"),
        "reason": ("both runners have >= 30 closed positions" if can_compare
                    else f"Runner 1: {r1.overall.n_closed_positions} closed · "
                         f"Runner 2: {r2.overall.n_closed_positions} closed · "
                         f"need >= {SIGNIFICANCE_MIN_SAMPLES} each to compare"),
    }
    if output_path is None:
        output_path = reports_dir / "benchmark_compare.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload
