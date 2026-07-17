"""DEV023 — Recommendation & Trade Decision Engine · CLI.

Requires DEV020 (company_context.json) + DEV022 (portfolio.json) to have run.

Usage:
    python research/recommendations/run.py                          # no current holdings
    python research/recommendations/run.py --holdings holdings.json # with existing positions
    python research/recommendations/run.py --min-target-sharpe 1.0  # widen target-portfolio filter

Produces:
    reports/recommendations.json
    reports/recommendations.parquet
    reports/watchlist.json
    reports/trade_summary.json
    reports/execution_plan.json
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

from recommendations.compute import engine                                             # noqa: E402
from recommendations.publish import bundle as publish                                     # noqa: E402


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


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV023 Recommendation Engine")
    ap.add_argument("--holdings", type=str, default=None,
                     help="Path to holdings.json (optional)")
    ap.add_argument("--min-target-sharpe", type=float, default=1.5,
                     help="Only portfolios with ex-Sharpe above this count as 'target'")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV023 - RECOMMENDATION & TRADE DECISION ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  code_sha:     {_git_sha()}")

    holdings_path = Path(args.holdings) if args.holdings else None
    if holdings_path and holdings_path.exists():
        print(f"  holdings:     {holdings_path}")
    else:
        print(f"  holdings:     none (all recs treated as new positions)")

    _banner("STEP 1/2 · Apply decision rules across universe")
    print(f"  started:      {_now_ist()}")
    result = engine.run(holdings_path=holdings_path,
                          min_target_sharpe=args.min_target_sharpe,
                          verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 5 JSON outputs")
    print(f"  started:      {_now_ist()}")
    published = publish.build_and_publish(result)

    print(f"  written to reports/:")
    for name in ["recommendations.json", "recommendations.parquet",
                   "watchlist.json", "trade_summary.json", "execution_plan.json"]:
        print(f"    - {name}")

    _banner("RECOMMENDATION SUMMARY")
    ts = published["trade_summary"]
    for k, v in ts["counts"].items():
        print(f"  {k:<15}  {v:>3}")
    print()
    print("  TOP 10 EXECUTION ORDER:")
    n = 0
    ex = engine.run(holdings_path=holdings_path,
                     min_target_sharpe=args.min_target_sharpe,
                     verbose=False)
    for r in ex["recommendations"][:10]:
        ee = r.get("entry_exit") or {}
        print(f"    {r['ticker']:<12} {r['recommendation']:<12} "
                f"conv={r['conviction_pct']:5.1f}%  "
                f"CDS={r['composite_decision_score']:5.1f}  "
                f"score={r['score']:5.1f}  "
                f"@{ee.get('latest_close', 'n/a')}  "
                f"T1={ee.get('target_1', 'n/a')}  "
                f"SL={ee.get('stop_loss', 'n/a')}  "
                f"{r['sector']}")

    _banner("DEV023 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
