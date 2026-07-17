"""DEV019 — Industry Intelligence Engine · top-level runner.

Requires DEV017 (Global) + DEV018 (Sector) to have run first.
DEV019 has no ingest step — reads constituent parquets already on disk.

Usage:
    python research/industry_intelligence/run.py               # compute + publish
    python research/industry_intelligence/run.py --publish-only

Produces:
    reports/industry_context.json
    reports/industry_context.parquet
    data/market_intelligence/derived/YYYY-MM/industry_*.parquet
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

from industry_intelligence.compute import engine as compute_engine                        # noqa: E402
from industry_intelligence.publish import bundle as publish                                # noqa: E402
from industry_intelligence.lib import industry_catalog                                     # noqa: E402


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
    ap = argparse.ArgumentParser(description="DEV019 Industry Intelligence Engine")
    ap.add_argument("--publish-only", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV019 - INDUSTRY INTELLIGENCE ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  repo:         {ROOT}")
    print(f"  code_sha:     {_git_sha()}")

    cat = industry_catalog.summary()
    print(f"  industries:   {cat['total_industries_defined']} defined | "
            f"{cat['with_3plus_available_constituents']} with 3+ constituents available")
    print()
    print(f"  upstream:     global_context.json {'FOUND' if (ROOT/'reports'/'global_context.json').exists() else 'MISSING - run DEV017'}")
    print(f"                sector_context.json {'FOUND' if (ROOT/'reports'/'sector_context.json').exists() else 'MISSING - run DEV018'}")

    _banner("STEP 1/2 · Compute industry aggregates + 10-dim composite + rotation")
    print(f"  started:      {_now_ist()}")
    result = compute_engine.run_compute_cycle(verbose=True)
    if "error" in result:
        print(f"  ERROR:        {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish industry_context bundle")
    print(f"  started:      {_now_ist()}")
    bundle = publish.build_bundle(result, code_sha=_git_sha())
    json_path, parquet_path = publish.write_bundle(bundle)
    print(f"  json:         {json_path}")
    print(f"  parquet:      {parquet_path}")
    print()

    pl = bundle["portfolio_level"]
    print(f"  SUMMARY:  {pl['industries_computed']}/{pl['industries_total']} industries scored   "
            f"avg = {pl['average_score']}")
    print(f"  CLASSES:  {pl['class_distribution']}")
    print(f"  ROTATION: {pl['rotation_distribution']}")
    print()
    print("  TOP 3 INDUSTRIES (across all sectors):")
    for row in pl["top3_industries"]:
        print(f"     {row['display']:<32}  score {row['score']:5.1f}   [{row['classification']}]   "
                f"rot={row['rotation']:<18}  parent={row['parent_sector']}")
    print()
    print("  BOTTOM 3 INDUSTRIES:")
    for row in pl["bottom3_industries"]:
        print(f"     {row['display']:<32}  score {row['score']:5.1f}   [{row['classification']}]   "
                f"rot={row['rotation']:<18}  parent={row['parent_sector']}")

    warns = bundle.get("warnings", [])
    if warns:
        print()
        print(f"  WARNINGS ({len(warns)}):")
        for w in warns[:6]:
            print(f"     - {w}")
        if len(warns) > 6:
            print(f"     ... and {len(warns) - 6} more")

    _banner("DEV019 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
