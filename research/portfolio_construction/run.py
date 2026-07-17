"""DEV022 — Portfolio Construction & Optimization Engine · CLI.

Requires DEV020 company_context.json + shared parquet stores.

Usage:
    python research/portfolio_construction/run.py
    python research/portfolio_construction/run.py --allocators equal,hrp,min_variance
    python research/portfolio_construction/run.py --portfolios top_10,top_20,concentrated
    python research/portfolio_construction/run.py --no-stress

Produces:
    reports/portfolio.json
    reports/portfolio.parquet
    reports/risk_report.json
    reports/allocation_report.json
    reports/rebalance_report.json
    reports/stress_test.json
    reports/portfolio_leaderboard.json
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

from portfolio_construction.compute import portfolio_builder                             # noqa: E402
from portfolio_construction.publish import bundle as publish                              # noqa: E402
from portfolio_construction.lib import allocators, constraints                             # noqa: E402


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


def _fmt(v, n=2):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{n}f}" if v == v else "—"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV022 Portfolio Construction Engine")
    ap.add_argument("--allocators", default=None,
                     help="Comma-separated allocator subset")
    ap.add_argument("--portfolios", default=None,
                     help="Comma-separated portfolio-type subset")
    ap.add_argument("--no-stress", action="store_true",
                     help="Skip stress-test replay (faster)")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV022 - PORTFOLIO CONSTRUCTION & OPTIMIZATION ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  code_sha:     {_git_sha()}")

    _banner("STEP 1/3 · Load inputs")
    print(f"  loading DEV020 company_context...")
    company_ctx = portfolio_builder.load_company_context()
    if company_ctx is None:
        print("  ERROR: reports/company_context.json missing — run DEV020 first")
        return 1
    computed = [c for c in company_ctx.get("companies", []) if c.get("status") == "computed"]
    print(f"    -> {len(computed)} scored companies from DEV020")

    print(f"  loading price data...")
    price_data = portfolio_builder.load_price_data()
    print(f"    -> {len(price_data)} constituent parquets")

    # Load Nifty from shared MI raw store
    from backtesting.compute.backtest_engine import load_nifty_series
    nifty_series = load_nifty_series()
    print(f"  loading Nifty benchmark:  {len(nifty_series)} bars")

    # Determine allocator + portfolio-type sets
    allocator_names = list(allocators.ALLOCATORS.keys())
    if args.allocators:
        wanted = set(args.allocators.split(","))
        allocator_names = [a for a in allocator_names if a in wanted]
    portfolio_types = portfolio_builder.PORTFOLIO_TYPES
    if args.portfolios:
        wanted = set(args.portfolios.split(","))
        portfolio_types = [p for p in portfolio_types if p.key in wanted]

    print(f"  allocators:   {allocator_names}")
    print(f"  portfolios:   {[p.key for p in portfolio_types]}")

    constr = constraints.Constraints()

    _banner("STEP 2/3 · Build portfolios (types × allocators)")
    print(f"  started:      {_now_ist()}")
    portfolios = portfolio_builder.build_all(company_ctx, allocator_names,
                                                portfolio_types, price_data, constr)
    n_built = sum(1 for p in portfolios if p.get("status") == "built")
    print(f"  built:        {n_built}/{len(portfolios)}")

    _banner("STEP 3/3 · Risk analytics, stress tests, publish")
    print(f"  started:      {_now_ist()}")
    published = publish.build_and_publish(portfolios, price_data, nifty_series,
                                             code_sha=_git_sha(),
                                             run_stress=not args.no_stress)

    _banner("PORTFOLIO LEADERBOARD (Top 12 by expected Sharpe)")
    print(f"\n  {'portfolio':<32} {'N':>4} {'ExRet%':>7} {'ExVol%':>7} {'ExSharpe':>9} "
            f"{'Beta':>6} {'EffN_S':>7} {'Top3Sec':>8}")
    print(f"  {'-' * 82}")
    for row in published["leaderboard"][:12]:
        print(f"  {row['portfolio']:<32} {_fmt(row['n_positions'], 0):>4} "
                f"{_fmt(row['expected_return_pct']):>7} "
                f"{_fmt(row['expected_vol_pct']):>7} "
                f"{_fmt(row['expected_sharpe'], 3):>9} "
                f"{_fmt(row['beta']):>6} "
                f"{_fmt(row['effective_n_stocks']):>7} "
                f"{_fmt(row['top3_sector_share'], 3):>8}")

    _banner("DEV022 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
