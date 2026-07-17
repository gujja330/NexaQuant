"""DEV025 — Adaptive Portfolio Learning · CLI.

Usage:
    python research/adaptive_learning/run.py                    # cached trade history if present
    python research/adaptive_learning/run.py --rebuild-cache    # force rebuild (slower)
    python research/adaptive_learning/run.py --top-n 20 --start 2022-01-01

Produces:
    reports/learning_summary.json
    reports/recommendation_accuracy.json
    reports/confidence_calibration.json
    reports/pattern_discovery.json
    reports/improvement_suggestions.json
    reports/learning.parquet
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

from adaptive_learning.compute import engine, suggestions                             # noqa: E402
from adaptive_learning.publish import bundle as publish                                # noqa: E402


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
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV025 Adaptive Learning Engine")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end",   default="2026-06-30")
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV025 - ADAPTIVE PORTFOLIO LEARNING ENGINE")
    print(f"  time (IST):  {_now_ist()}")
    print(f"  code_sha:    {_git_sha()}")
    print(f"  window:      {args.start} -> {args.end}   top_n={args.top_n}")

    _banner("STEP 1/3 · Reconstruct or load trade history")
    result = engine.run(top_n=args.top_n, start_date=args.start, end_date=args.end,
                          use_cache=not args.rebuild_cache, verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/3 · Generate improvement suggestions")
    sugg = suggestions.generate(result)
    print(f"  {len(sugg)} suggestion(s) generated")

    _banner("STEP 3/3 · Publish 6 outputs")
    published = publish.build_and_publish(result, sugg)
    print(f"  outputs: learning_summary · recommendation_accuracy · "
            f"confidence_calibration · pattern_discovery · improvement_suggestions · "
            f"learning.parquet")

    _banner("LEARNING SUMMARY")
    a = result["aggregate"]
    print(f"  Trades analysed:       {a['n_trades']}")
    print(f"  Win rate:              {a['overall_win_rate_pct']:.2f}%")
    print(f"  Avg return:            {a['avg_return_pct']:+.3f}%   Median: {a['median_return_pct']:+.3f}%")
    print(f"  Max gain / max loss:   {a['max_gain_pct']:+.2f}% / {a['max_loss_pct']:+.2f}%")
    print(f"  Avg hold:              {a['avg_hold_days']:.1f} bars   MFE: {a['avg_mfe_pct']:.2f}%   MAE: {a['avg_mae_pct']:.2f}%")
    print(f"  Brier score:           {a['brier_score']}")
    print(f"  Expected Calibration Error: {a['expected_calibration_err']}")

    _banner("TOP 5 IMPROVEMENT SUGGESTIONS")
    if sugg:
        for s in sugg[:5]:
            print(f"  [{s['severity']}] {s['id']}: {s['category']}")
            print(f"     Evidence: {s['evidence'][:100]}")
            print(f"     Action:   {s['action'][:100]}")
    else:
        print("  No suggestions generated (all indicators within acceptable ranges).")

    _banner("DEV025 · DONE")
    print(f"  elapsed:     {time.time()-t0:.1f}s")
    print(f"  finished:    {_now_ist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
