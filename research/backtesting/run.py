"""DEV021 — Historical Validation & Backtesting Engine · CLI.

Usage:
    python research/backtesting/run.py                                 # full default
    python research/backtesting/run.py --start 2022-01-01 --end 2026-06-30
    python research/backtesting/run.py --strategies top_10_ew,top_20_ew   # subset

Produces:
    reports/backtest_summary.json
    reports/backtest_summary.parquet
    reports/strategy_comparison.json
    reports/performance_metrics.json
    reports/signal_attribution.json
    reports/failure_analysis.json
    reports/self_improvement.json
    reports/backtest_equity_curves.csv
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from backtesting.compute import backtest_engine                                        # noqa: E402
from backtesting.publish import bundle as publish                                        # noqa: E402
from backtesting.lib.strategies import STRATEGIES                                        # noqa: E402


ROOT = HERE.parents[1]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def _banner(msg: str) -> None:
    print()
    print("=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def _fmt(v, ndigits=2):
    if v is None:
        return "—"
    if isinstance(v, float):
        try:
            if v != v or v in (float("inf"), float("-inf")):
                return "—"
        except Exception:
            return "—"
        return f"{v:.{ndigits}f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV021 Backtesting Engine")
    ap.add_argument("--start", default="2022-01-01", help="Backtest start date (YYYY-MM-DD)")
    ap.add_argument("--end",   default="2026-06-30", help="Backtest end date")
    ap.add_argument("--strategies", default=None,
                     help="Comma-separated subset (e.g. top_10_ew,top_20_ew)")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV021 - HISTORICAL VALIDATION & BACKTESTING ENGINE")
    print(f"  time (IST):     {_now_ist()}")
    print(f"  code_sha:       {_git_sha()}")
    print(f"  window:         {args.start} -> {args.end}")

    strategies = STRATEGIES
    if args.strategies:
        wanted = set(args.strategies.split(","))
        strategies = {k: v for k, v in STRATEGIES.items() if k in wanted}
        if not strategies:
            print(f"  ERROR: no matching strategies in {list(STRATEGIES)}")
            return 1
    print(f"  strategies:     {list(strategies.keys())}")

    _banner("STEP 1/2 · Walk-forward backtest (point-in-time scoring, no look-ahead)")
    print(f"  started:        {_now_ist()}")
    result = backtest_engine.run_backtest(
        strategies=strategies,
        start_date=args.start, end_date=args.end,
        verbose=True,
    )

    _banner("STEP 2/2 · Aggregate metrics, attribution, failure analysis, publish")
    print(f"  started:        {_now_ist()}")
    published = publish.build_and_publish(result)

    print()
    print("  Output files:")
    for name, pth in published["paths"].items():
        print(f"    {name:<38}  {pth}")

    # Leaderboard printout
    _banner("STRATEGY LEADERBOARD")
    rows = []
    for name, s in published["strategy_summaries"].items():
        rows.append({
            "strategy":  name,
            "cagr":      s.get("cagr"),
            "sharpe":    s.get("sharpe_ratio"),
            "sortino":   s.get("sortino_ratio"),
            "calmar":    s.get("calmar_ratio"),
            "alpha":     s.get("alpha"),
            "beta":      s.get("beta"),
            "max_dd":    s.get("max_drawdown", {}).get("max_dd_pct") if isinstance(s.get("max_drawdown"), dict) else None,
            "turnover":  s.get("turnover_annualised"),
            "n_trades":  (s.get("trade_metrics") or {}).get("n_trades"),
            "win_rate":  (s.get("trade_metrics") or {}).get("win_rate_pct"),
        })
    # Sort by Sharpe descending, benchmark at bottom
    rows.sort(key=lambda r: (r["strategy"].startswith("BENCHMARK"),
                                -(r["sharpe"] or -99)))

    print(f"\n  {'strategy':<20} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} "
            f"{'Alpha':>7} {'Beta':>6} {'MaxDD':>8} {'Turn':>6} {'#Tr':>5} {'Win%':>6}")
    print(f"  {'-' * 88}")
    for r in rows:
        print(f"  {r['strategy']:<20} "
                f"{_fmt(r['cagr'], 3):>7} "
                f"{_fmt(r['sharpe']):>7} "
                f"{_fmt(r['sortino']):>8} "
                f"{_fmt(r['calmar']):>7} "
                f"{_fmt(r['alpha'], 3):>7} "
                f"{_fmt(r['beta']):>6} "
                f"{_fmt(r['max_dd']):>8} "
                f"{_fmt(r['turnover']):>6} "
                f"{_fmt(r['n_trades'], 0):>5} "
                f"{_fmt(r['win_rate']):>6}")

    _banner("DEV021 · DONE")
    print(f"  elapsed:        {time.time()-t0:.1f}s")
    print(f"  finished:       {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
