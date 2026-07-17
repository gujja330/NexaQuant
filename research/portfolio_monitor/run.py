"""DEV024 — Portfolio Monitoring & Rebalancing Engine · CLI.

Usage:
    python research/portfolio_monitor/run.py --holdings holdings.json
    python research/portfolio_monitor/run.py --demo                     # synth from DEV023 top recs
    python research/portfolio_monitor/run.py --demo --portfolio-type top_10_ew

Produces:
    reports/portfolio_monitor.json
    reports/rebalance_plan.json
    reports/performance_report.json
    reports/alerts.json
    reports/portfolio_health.json
    reports/portfolio_monitor.parquet
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from portfolio_monitor.compute import engine                                             # noqa: E402
from portfolio_monitor.publish import bundle as publish                                    # noqa: E402
from portfolio_monitor.lib import holdings as hd                                            # noqa: E402


ROOT = HERE.parents[1]
DEMO_HOLDINGS_PATH = ROOT / "reports" / "holdings_demo.json"


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


def _fmt_money(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, (int, float)):
        return f"INR{v:,.0f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV024 Portfolio Monitor")
    ap.add_argument("--holdings", type=str, default=None, help="Path to holdings.json")
    ap.add_argument("--demo", action="store_true", help="Synthesise holdings from DEV023 recs")
    ap.add_argument("--portfolio-type", default="top_10_ew",
                     help="Portfolio type for --demo (top_5_ew / top_10_ew / top_20_ew)")
    ap.add_argument("--capital", type=float, default=10_000_000,
                     help="Demo total capital in INR")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV024 - PORTFOLIO MONITORING & REBALANCING ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  code_sha:     {_git_sha()}")

    # Resolve holdings source
    if args.demo:
        recs_path = ROOT / "reports" / "recommendations.json"
        if not recs_path.exists():
            print(f"  ERROR: --demo requires reports/recommendations.json (run DEV023 first)")
            return 1
        with recs_path.open("r", encoding="utf-8") as f:
            recs = json.load(f)
        demo_holdings = hd.synthesise_from_recommendations(recs, args.portfolio_type,
                                                              capital=args.capital)
        if not demo_holdings:
            print(f"  ERROR: could not synthesise demo (no Strong-Buy/Buy recs)")
            return 1
        with DEMO_HOLDINGS_PATH.open("w", encoding="utf-8") as f:
            json.dump(demo_holdings, f, indent=2)
        holdings_path = DEMO_HOLDINGS_PATH
        print(f"  demo synthesised from top {len(demo_holdings['holdings'])} "
                f"{args.portfolio_type} recs -> {DEMO_HOLDINGS_PATH.name}")
    elif args.holdings:
        holdings_path = Path(args.holdings)
        if not holdings_path.exists():
            print(f"  ERROR: {holdings_path} does not exist")
            return 1
    else:
        print(f"  ERROR: provide --holdings or --demo")
        return 1

    _banner("STEP 1/2 · Refresh, compute exposures + alerts + rebalance plan")
    print(f"  started:      {_now_ist()}")
    result = engine.run(holdings_path, verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 6 outputs")
    print(f"  started:      {_now_ist()}")
    published = publish.build_and_publish(result)

    _banner("PORTFOLIO SNAPSHOT")
    h = result["health"]
    print(f"  Portfolio ID:     {h['portfolio_id']}")
    print(f"  Days active:      {h.get('days_active')}")
    print(f"  Total value:      {_fmt_money(h['total_portfolio_value'])}")
    print(f"  Invested capital: {_fmt_money(h['total_invested_capital'])}")
    print(f"  P&L:              {_fmt_money(h['total_pnl_abs'])}   ({h['total_pnl_pct']:+.2f}%)")
    print(f"  Cash:             {_fmt_money(h['cash'])}   ({h['cash_pct']:.2f}%)")
    print(f"  Positions:        {h['n_positions_total']} total, {h['n_positions_computable']} priced")
    print(f"  Effective N:      {h['effective_n_stocks']}   HHI={h['stock_hhi']}")
    print(f"  Top sector:       {h['top_sector']}   ({h['top_sector_share']:.1%})"
            if h['top_sector_share'] else f"  Top sector:       {h['top_sector']}")
    print(f"  Health score:     {h['health_score']}/100")

    _banner("ALERTS")
    from portfolio_monitor.lib.alerts import summarise
    summary = summarise(result["alerts"])
    print(f"  Total: {summary['total']}   Critical: {summary['by_severity']['CRITICAL']}   "
            f"Warning: {summary['by_severity']['WARNING']}   Info: {summary['by_severity']['INFO']}")
    if summary["by_type"]:
        for atype, cnt in summary["by_type"].items():
            print(f"    {atype}: {cnt}")

    if result["alerts"]:
        print(f"\n  Top 5 critical/warning alerts:")
        top_alerts = [a for a in result["alerts"] if a.severity in ("CRITICAL", "WARNING")][:5]
        for a in top_alerts:
            print(f"    [{a.severity}] {a.message}")

    _banner("REBALANCE PLAN")
    plan = result["rebalance_plan"]
    if plan:
        print(f"  {len(plan)} action(s):")
        for p in plan[:10]:
            print(f"    {p['action']:<20} {p['ticker']:<12} "
                    f"shares_delta={p['shares_delta']:>+5}  "
                    f"value_delta={_fmt_money(p['value_delta']):>12}  "
                    f"reason={p['reason'][:50]}")
    else:
        print("  No rebalance actions above threshold.")

    _banner("TOP WINNERS / LOSERS")
    attr = result["attribution"]
    if attr["winners"]:
        print(f"  Winners:")
        for w in attr["winners"]:
            print(f"    {w['ticker']:<12} pnl={_fmt_money(w['pnl_abs']):>12}   "
                    f"({w['pnl_pct']:+.2f}%)  weight={w['current_weight']:.2%}")
    if attr["losers"]:
        print(f"  Losers:")
        for l in attr["losers"]:
            print(f"    {l['ticker']:<12} pnl={_fmt_money(l['pnl_abs']):>12}   "
                    f"({l['pnl_pct']:+.2f}%)  weight={l['current_weight']:.2%}")

    _banner("DEV024 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
