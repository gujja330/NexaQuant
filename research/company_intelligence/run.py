"""DEV020 — Company Intelligence Engine · top-level runner.

Requires DEV017 + DEV018 + DEV019 to have run first (or at least DEV017).

Usage:
    python research/company_intelligence/run.py                # full universe
    python research/company_intelligence/run.py --max 50       # first N companies (dev/testing)
    python research/company_intelligence/run.py --publish-only

Produces:
    reports/company_context.json
    reports/company_context.parquet
    data/market_intelligence/derived/YYYY-MM/company_*.parquet
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

from company_intelligence.compute import engine as compute_engine                            # noqa: E402
from company_intelligence.publish import bundle as publish                                     # noqa: E402
from company_intelligence.lib import company_catalog                                            # noqa: E402


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
    ap = argparse.ArgumentParser(description="DEV020 Company Intelligence Engine")
    ap.add_argument("--max", type=int, default=None, help="Limit to first N companies")
    ap.add_argument("--publish-only", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV020 - COMPANY INTELLIGENCE ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  repo:         {ROOT}")
    print(f"  code_sha:     {_git_sha()}")

    cat = company_catalog.summary()
    print(f"  universe:     {cat['total_companies_mapped']} companies mapped from DEV019 industries")
    print(f"                {cat['with_parquet_on_disk']} have parquet on disk")
    print(f"                {cat['unmapped_tickers_on_disk']} disk parquets NOT in any industry (v0.2 catalog gap)")
    print()
    print(f"  upstream:     global_context   {'FOUND' if (ROOT/'reports'/'global_context.json').exists() else 'MISSING - run DEV017'}")
    print(f"                sector_context   {'FOUND' if (ROOT/'reports'/'sector_context.json').exists() else 'MISSING - run DEV018'}")
    print(f"                industry_context {'FOUND' if (ROOT/'reports'/'industry_context.json').exists() else 'MISSING - run DEV019'}")

    if args.max:
        print(f"  LIMIT:        first {args.max} companies (dev/testing mode)")

    _banner("STEP 1/2 · Compute per-company 11-dim composite + inherit context")
    print(f"  started:      {_now_ist()}")
    result = compute_engine.run_compute_cycle(verbose=True, max_tickers=args.max)
    if "error" in result:
        print(f"  ERROR:        {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish company_context bundle")
    print(f"  started:      {_now_ist()}")
    bundle = publish.build_bundle(result, code_sha=_git_sha())
    json_path, parquet_path = publish.write_bundle(bundle)
    print(f"  json:         {json_path}")
    print(f"  parquet:      {parquet_path}")
    print()

    pl = bundle["portfolio_level"]
    print(f"  SUMMARY:  {pl['companies_computed']} scored · {pl['companies_rejected']} rejected"
            f"   avg score = {pl['average_score']}")
    print(f"  CLASSES:  {pl['class_distribution']}")
    print()
    print("  TOP 10 COMPANIES (universe-wide):")
    for i, row in enumerate(pl["top_10"], 1):
        print(f"     {i:2}. {row['ticker']:<15} score {row['score']:5.1f}   [{row['classification']:<14}]  "
                f"sector={row['sector']:<18}  industry={row['industry']}")
    print()
    print("  BOTTOM 5 COMPANIES:")
    for i, row in enumerate(pl["bottom_10"][-5:], 1):
        print(f"     {i:2}. {row['ticker']:<15} score {row['score']:5.1f}   [{row['classification']:<14}]  "
                f"sector={row['sector']:<18}  industry={row['industry']}")

    print()
    print("  SECTOR AVERAGES (top 5 by n_companies):")
    ss = sorted(pl["sector_summary"].items(), key=lambda x: x[1]["n"], reverse=True)[:5]
    for sec, data in ss:
        print(f"     {sec:<20}  n={data['n']:2d}  avg={data['avg_score']:5.1f}  "
                f"top={data['top_ticker']} ({data['top_score']:.1f})")

    warns = bundle.get("warnings", [])
    if warns:
        print()
        print(f"  WARNINGS ({len(warns)}):")
        for w in warns[:5]:
            print(f"     - {w}")

    _banner("DEV020 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
