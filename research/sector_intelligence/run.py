"""DEV018 — Sector Intelligence Engine · top-level runner.

Requires DEV017 to have run first (needs Nifty 50 series + global_context.json).

Usage:
    python research/sector_intelligence/run.py                 # full cycle
    python research/sector_intelligence/run.py --ingest-only   # fetch sector indices only
    python research/sector_intelligence/run.py --compute-only  # skip ingest
    python research/sector_intelligence/run.py --publish-only  # skip compute

Produces:
    data/market_intelligence/raw/YYYY-MM/observations_YYYYMMDD.parquet  (appended)
    data/market_intelligence/derived/YYYY-MM/sector_*.parquet
    reports/sector_context.json
    reports/sector_context.parquet
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

from sector_intelligence.ingest import yfinance_ingest                                      # noqa: E402
from sector_intelligence.compute import engine as compute_engine                             # noqa: E402
from sector_intelligence.publish import bundle as publish                                      # noqa: E402
from sector_intelligence.lib import sector_catalog                                             # noqa: E402


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
    ap = argparse.ArgumentParser(description="DEV018 Sector Intelligence Engine")
    ap.add_argument("--ingest-only", action="store_true")
    ap.add_argument("--compute-only", action="store_true")
    ap.add_argument("--publish-only", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV018 - SECTOR INTELLIGENCE ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  repo:         {ROOT}")
    print(f"  code_sha:     {_git_sha()}")
    cat = sector_catalog.summary()
    print(f"  sectors:      {cat['total_sectors']} ({', '.join(cat['sectors'])})")
    print(f"  universe:     {cat['constituent_universe_size']} constituents from {cat['sector_map_source']}")
    print()
    print(f"  upstream:     reports/global_context.json {'FOUND' if (ROOT/'reports'/'global_context.json').exists() else 'MISSING - run DEV017 first'}")

    do_ingest = not (args.compute_only or args.publish_only)
    do_compute = not (args.ingest_only or args.publish_only)
    do_publish = not (args.ingest_only or args.compute_only)

    if do_ingest:
        _banner("STEP 1/3 · Ingest sector indices via yfinance")
        r = yfinance_ingest.fetch_all(verbose=True)
        print()
        print(f"  attempted:    {r['attempted']}")
        print(f"  succeeded:    {r['succeeded']}")
        print(f"  rows written: {r['rows_written']}")
        if r['failures']:
            print(f"  failures:     {', '.join(r['failures'])}")
        print(f"  partition:    {r['partition']}")

    compute_result = None
    if do_compute:
        _banner("STEP 2/3 · Compute sector strength model (13 dimensions)")
        print(f"  started:      {_now_ist()}")
        compute_result = compute_engine.run_compute_cycle(verbose=True)
        if "error" in compute_result:
            print(f"  ERROR:        {compute_result['error']}")
            return 1

    if do_publish:
        _banner("STEP 3/3 · Publish sector_context bundle")
        print(f"  started:      {_now_ist()}")
        if compute_result is None:
            compute_result = compute_engine.run_compute_cycle(verbose=False)
        bundle = publish.build_bundle(compute_result, code_sha=_git_sha())
        json_path, parquet_path = publish.write_bundle(bundle)
        print(f"  json:         {json_path}")
        print(f"  parquet:      {parquet_path}")
        print()

        # Headline
        pl = bundle["portfolio_level"]
        print(f"  SUMMARY:  {pl['sectors_computed']}/{pl['sectors_total']} sectors scored   "
                f"avg score = {pl['average_score']}")
        print(f"  DISTRIBUTION: {pl['class_distribution']}")
        print()
        print(f"  TOP 3 SECTORS:")
        for row in pl["top3_sectors"]:
            print(f"     {row['key']:<32} score {row['score']:5.1f}   [{row['classification']}]")
        print()
        print(f"  BOTTOM 3 SECTORS:")
        for row in pl["bottom3_sectors"]:
            print(f"     {row['key']:<32} score {row['score']:5.1f}   [{row['classification']}]")

        warns = bundle.get("warnings", [])
        if warns:
            print()
            print(f"  WARNINGS ({len(warns)}):")
            for w in warns[:5]:
                print(f"     - {w}")

    _banner("DEV018 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
