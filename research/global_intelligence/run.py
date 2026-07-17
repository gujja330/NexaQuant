"""DEV017 — Global Intelligence Engine · top-level runner.

Usage:
    python research/global_intelligence/run.py                  # full cycle
    python research/global_intelligence/run.py --ingest-only    # just fetch + store raw
    python research/global_intelligence/run.py --compute-only   # skip ingest; use stored raw
    python research/global_intelligence/run.py --publish-only   # skip compute; use stored derived

Produces:
    data/market_intelligence/raw/YYYY-MM/observations_YYYYMMDD.parquet
    data/market_intelligence/derived/YYYY-MM/*.parquet
    reports/global_context.json
    reports/global_context.parquet
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

from global_intelligence.ingest import yfinance_ingest                                  # noqa: E402
from global_intelligence.compute import engine as compute_engine                          # noqa: E402
from global_intelligence.publish import bundle as publish                                   # noqa: E402
from global_intelligence.lib import catalog                                                # noqa: E402


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
    ap = argparse.ArgumentParser(description="DEV017 Global Intelligence Engine")
    ap.add_argument("--ingest-only", action="store_true", help="only fetch + store raw")
    ap.add_argument("--compute-only", action="store_true", help="only compute + store derived")
    ap.add_argument("--publish-only", action="store_true", help="only publish bundle from stored derived")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV017 - GLOBAL INTELLIGENCE ENGINE")
    print(f"  time (IST):   {_now_ist()}")
    print(f"  repo:         {ROOT}")
    print(f"  code_sha:     {_git_sha()}")
    cat = catalog.summary()
    print(f"  catalog:      {cat['total_variables']} variables "
            f"({cat['by_category']})")
    print(f"  deferred:     {', '.join(cat['deferred_to_v02'])}")

    do_ingest = not (args.compute_only or args.publish_only)
    do_compute = not (args.ingest_only or args.publish_only)
    do_publish = not (args.ingest_only or args.compute_only)

    ingest_result = None
    if do_ingest:
        _banner("STEP 1/3 · Ingest RawObservations from yfinance")
        print(f"  started:      {_now_ist()}")
        ingest_result = yfinance_ingest.fetch_all(verbose=True)
        print()
        print(f"  attempted:    {ingest_result['variables_attempted']}")
        print(f"  succeeded:    {ingest_result['variables_succeeded']}")
        print(f"  rows written: {ingest_result['rows_written']}")
        if ingest_result['failures']:
            print(f"  failures:     {', '.join(ingest_result['failures'])}")
        print(f"  partition:    {ingest_result['partition']}")

    compute_result = None
    if do_compute:
        _banner("STEP 2/3 · Compute DerivedMetrics / Normalized / Classifications / Composites")
        print(f"  started:      {_now_ist()}")
        compute_result = compute_engine.run_compute_cycle(verbose=True)
        if "error" in compute_result:
            print(f"  ERROR:        {compute_result['error']}")
            return 1

    if do_publish:
        _banner("STEP 3/3 · Publish global_context bundle")
        print(f"  started:      {_now_ist()}")

        if compute_result is None:
            compute_result = compute_engine.run_compute_cycle(verbose=False)

        derived = compute_result.get("_derived", [])
        normalized = compute_result.get("_normalized", [])
        classifications = compute_result.get("_classifications", [])
        composites = compute_result.get("_composites", {})

        bundle = publish.build_bundle(derived, normalized, classifications, composites,
                                        code_sha=_git_sha())
        json_path, parquet_path = publish.write_bundle(bundle)
        print(f"  json:         {json_path}")
        print(f"  parquet:      {parquet_path}")
        print()

        # Preview the headline
        gr = bundle["composites"].get("global_risk")
        if gr:
            print(f"  HEADLINE:   composite.global_risk = {gr['value_0_100']:.1f}   "
                    f"[{gr['classification']}]   confidence {gr['confidence']:.2f}")
        posture = bundle["classifications"].get("global_posture")
        if posture:
            print(f"              global_posture = {posture['label']}")
        usd = bundle["classifications"].get("usd")
        if usd:
            print(f"              usd            = {usd['label']}")
        vol = bundle["classifications"].get("vol_regime")
        if vol:
            print(f"              vol_regime     = {vol['label']}")

        top = bundle.get("contributions", {}).get("global_risk_top5", [])
        if top:
            print(f"  TOP CONTRIBUTORS:")
            for row in top:
                print(f"     {row['indicator']:<38} value {row['value_0_100']:5.1f}   "
                        f"weight {row['weight']:.2f}   contribution {row['contribution']:+.1f}")

        warnings = bundle.get("warnings", [])
        if warnings:
            print(f"  WARNINGS:")
            for w in warnings:
                print(f"     - {w}")

    _banner("DEV017 · DONE")
    print(f"  elapsed:      {time.time()-t0:.1f}s")
    print(f"  finished:     {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
