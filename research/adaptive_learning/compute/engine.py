"""DEV025 orchestration."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from adaptive_learning.lib import trade_history, calibration, patterns             # noqa: E402


REPORTS_DIR = _ROOT / "reports"
TRADE_HISTORY_CACHE = _ROOT / "data" / "market_intelligence" / "derived" / "trade_history_cache.parquet"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def extend_corpus(top_n: int, verbose: bool) -> pd.DataFrame:
    """Extend the published simulated corpus from its last completed window."""
    from backtesting.compute.backtest_engine import month_ends

    trades = pd.read_parquet(REPORTS_DIR / "learning.parquet")
    last_exit = pd.to_datetime(trades["exit_date"], errors="raise").max()
    nifty = pd.read_parquet(_ROOT / "data" / "raw" / "india" / "NSEI_D1.parquet")["close"].dropna()
    nifty.index = pd.to_datetime(nifty.index).tz_localize(None).normalize()
    if not nifty.index.is_unique or not nifty.index.is_monotonic_increasing:
        raise ValueError("daily Nifty history contains duplicate or unordered sessions")
    if trades.empty or nifty.empty:
        raise ValueError("missing learning history or Nifty observations")
    cutoff = nifty.index.max().normalize()
    due = month_ends(last_exit, cutoff)
    if len(due) < 2:
        return trades
    appended = trade_history.build_trade_history(
        top_n, last_exit.date().isoformat(), cutoff.date().isoformat(), verbose, nifty=nifty,
    )
    expected = {day.date().isoformat() for day in due[1:]}
    if appended.empty or set(appended["exit_date"]) != expected:
        raise ValueError("learning history is missing a completed monthly window")
    if set(appended.columns) != set(trades.columns):
        raise ValueError("learning history schema differs from the published corpus")
    combined = pd.concat([trades, appended], ignore_index=True)
    if combined.duplicated(["ticker", "entry_date", "exit_date"]).any():
        raise ValueError("duplicate simulated trade episode in learning history")
    return combined


def run(top_n: int = 20, start_date: str = "2022-01-01", end_date: str = "2026-06-30",
         use_cache: bool = True, verbose: bool = True, append_completed: bool = False) -> dict:
    """Build (or load) trade history + all learning artifacts."""
    if append_completed:
        trades = extend_corpus(top_n, verbose)
        start_date = str(trades["entry_date"].min())
        end_date = str(trades["exit_date"].max())
    elif use_cache and TRADE_HISTORY_CACHE.exists():
        try:
            trades = pd.read_parquet(TRADE_HISTORY_CACHE)
            if verbose:
                print(f"  loaded {len(trades)} trades from cache")
        except Exception:
            trades = trade_history.build_trade_history(top_n, start_date, end_date, verbose)
            if not trades.empty:
                TRADE_HISTORY_CACHE.parent.mkdir(parents=True, exist_ok=True)
                trades.to_parquet(TRADE_HISTORY_CACHE, index=False)
    else:
        trades = trade_history.build_trade_history(top_n, start_date, end_date, verbose)
        if not trades.empty:
            TRADE_HISTORY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            trades.to_parquet(TRADE_HISTORY_CACHE, index=False)

    if trades.empty:
        return {"error": "no trades to learn from — DEV017 raw store may be missing"}

    # ── Recommendation accuracy ─────────────────────────────────────────────
    score_buckets = patterns.score_bucket_accuracy(trades)
    sector_perf = patterns.per_sector_performance(trades)
    industry_perf = patterns.per_industry_performance(trades)
    dim_corr = patterns.dimension_correlations(trades)
    stop_stats = patterns.stop_loss_effectiveness(trades)
    target_stats = patterns.target_effectiveness(trades)

    # ── Confidence calibration ─────────────────────────────────────────────
    calib_curve = calibration.calibration_curve(trades, n_bins=10)
    brier = calibration.brier_score(trades)
    ece = calibration.expected_calibration_error(calib_curve)
    sector_calib = calibration.per_sector_calibration(trades)

    # ── Aggregates ─────────────────────────────────────────────────────────
    aggregate = {
        "n_trades":                  int(len(trades)),
        "n_winners":                 int(trades["is_winner"].sum()),
        "n_losers":                  int((~trades["is_winner"]).sum()),
        "overall_win_rate_pct":      round(float(trades["is_winner"].mean()) * 100, 2),
        "avg_return_pct":            round(float(trades["return_pct"].mean()), 3),
        "median_return_pct":         round(float(trades["return_pct"].median()), 3),
        "max_gain_pct":              round(float(trades["return_pct"].max()), 3),
        "max_loss_pct":              round(float(trades["return_pct"].min()), 3),
        "avg_hold_days":             round(float(trades["n_bars_held"].mean()), 1),
        "avg_mfe_pct":               round(float(trades["mfe_pct"].mean()), 3),
        "avg_mae_pct":               round(float(trades["mae_pct"].mean()), 3),
        "brier_score":               round(brier, 4) if brier == brier else None,
        "expected_calibration_err":  round(ece, 4) if ece == ece else None,
    }

    return {
        "run_utc":              datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":             _git_sha(),
        "dev_version":          "DEV025 v0.1",
        "top_n":                top_n,
        "start_date":           start_date,
        "end_date":             end_date,
        "aggregate":            aggregate,
        "trades":               trades,
        "score_buckets":        score_buckets,
        "sector_performance":   sector_perf,
        "industry_performance": industry_perf,
        "dimension_correlations": dim_corr,
        "stop_loss_stats":      stop_stats,
        "target_stats":         target_stats,
        "calibration_curve":    calib_curve,
        "sector_calibration":   sector_calib,
    }
