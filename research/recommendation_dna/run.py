"""DEV028 — Recommendation DNA · CLI."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from recommendation_dna.compute import engine                                          # noqa: E402
from recommendation_dna.publish import bundle as publish                                # noqa: E402
from recommendation_dna.lib import search                                                # noqa: E402


ROOT = HERE.parents[1]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV028 Recommendation DNA Engine")
    ap.add_argument("--search-ticker", type=str)
    ap.add_argument("--search-sector", type=str)
    ap.add_argument("--search-recommendation", type=str)
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV028 - RECOMMENDATION DNA ENGINE")
    print(f"  time (IST): {_now_ist()}")
    print(f"  code_sha:   {_git_sha()}")

    if not args.stats_only:
        _banner("STEP 1/3 · Ingest current recommendations into immutable store")
        result = engine.run(verbose=True)
    else:
        result = {"run_utc": datetime.now(timezone.utc).isoformat() + "Z",
                    "code_sha": _git_sha(), "dev_version": "DEV028 v0.1"}

    _banner("STEP 2/3 · Publish 5 outputs")
    published = publish.build_and_publish(result)
    print(f"  n_records in store:       {published['n_records']}")
    print(f"  n_unique_recommendations: {published['n_recommendations']}")

    _banner("CORPUS STATISTICS")
    stats = search.statistics()
    if stats.get("n_records", 0) == 0:
        print("  Empty corpus. Run this once to seed.")
        return 0
    print(f"  Records:                {stats['n_records']}")
    print(f"  Unique tickers:         {stats.get('n_unique_tickers')}")
    print(f"  Unique recommendations: {stats.get('n_unique_recommendations')}")
    dr = stats.get("date_range", {})
    print(f"  Date range:             {dr.get('min')} -> {dr.get('max')}")
    if "by_recommendation_type" in stats:
        print(f"  By recommendation:")
        for k, v in sorted(stats["by_recommendation_type"].items(), key=lambda kv: kv[1], reverse=True):
            print(f"    {k:<15}  {v}")
    if "version_stats" in stats:
        v = stats["version_stats"]
        print(f"  Versions: avg={v['avg_versions_per_recommendation']}, "
                f"max={v['max_versions']}, with_updates={v['n_recommendations_with_updates']}")

    if args.search_ticker or args.search_sector or args.search_recommendation:
        _banner("SEARCH RESULTS")
        df = search.search(
            ticker=args.search_ticker,
            sector=args.search_sector,
            recommendation=args.search_recommendation,
        )
        print(f"  {len(df)} row(s) matched")
        if not df.empty:
            display_cols = ["ticker", "version", "recommendation_type", "confidence",
                              "company_score", "snapshot_utc"]
            display_cols = [c for c in display_cols if c in df.columns]
            print()
            print(df[display_cols].head(20).to_string(index=False))

    _banner("DEV028 · DONE")
    print(f"  elapsed: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
